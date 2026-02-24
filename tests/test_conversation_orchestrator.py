import unittest
from pathlib import Path
from unittest.mock import Mock

import sys

ROOT = Path(__file__).resolve().parents[1]
for p in (
    ROOT,
    ROOT / "modules" / "catalog_enrichment" / "src",
    ROOT / "modules" / "style_engine" / "src",
    ROOT / "modules" / "user_profiler" / "src",
    ROOT / "modules" / "conversation_platform" / "src",
):
    sp = str(p)
    if sp not in sys.path:
        sys.path.insert(0, sp)


from conversation_platform.orchestrator import ConversationOrchestrator
from conversation_platform.repositories import ConversationRepository
from user_profiler.schemas import BODY_ENUMS


class ConversationRepositoryTests(unittest.TestCase):
    def test_get_or_create_user_returns_existing(self) -> None:
        client = Mock()
        existing = {"id": "u1", "external_user_id": "user_1"}
        client.select_one.return_value = existing
        repo = ConversationRepository(client)

        out = repo.get_or_create_user("user_1")

        self.assertEqual(existing, out)
        client.insert_one.assert_not_called()
        client.select_one.assert_called_once_with("users", filters={"external_user_id": "eq.user_1"})

    def test_get_or_create_user_creates_when_missing(self) -> None:
        client = Mock()
        client.select_one.return_value = None
        created = {"id": "u1", "external_user_id": "user_1"}
        client.insert_one.return_value = created
        repo = ConversationRepository(client)

        out = repo.get_or_create_user("user_1")

        self.assertEqual(created, out)
        client.insert_one.assert_called_once_with("users", {"external_user_id": "user_1"})

    def test_get_user_by_id(self) -> None:
        client = Mock()
        client.select_one.return_value = {"id": "u1", "external_user_id": "user_1"}
        repo = ConversationRepository(client)

        out = repo.get_user_by_id("u1")

        self.assertEqual("user_1", out["external_user_id"])
        client.select_one.assert_called_once_with("users", filters={"id": "eq.u1"})


class ConversationOrchestratorTests(unittest.TestCase):
    def _build_visual_profile(self) -> dict:
        visual = {key: values[0] for key, values in BODY_ENUMS.items()}
        visual["gender"] = "female"
        visual["age"] = "25_30"
        return visual

    def test_get_conversation_state_includes_external_user_id(self) -> None:
        repo = Mock()
        repo.get_conversation.return_value = {
            "id": "c1",
            "user_id": "user_uuid",
            "status": "active",
            "session_context_json": {
                "occasion": "work_mode",
                "archetype": "classic",
                "gender": "female",
                "age": "25_30",
                "latest_profile_snapshot_id": "ps1",
            },
        }
        repo.get_user_by_id.return_value = {"id": "user_uuid", "external_user_id": "user_1"}
        repo.get_latest_profile_snapshot.return_value = {"id": "ps1"}
        repo.get_latest_turn.return_value = {"recommendation_run_id": "run1"}

        orchestrator = ConversationOrchestrator(repo=repo, catalog_csv_path="data/output/enriched.csv")
        state = orchestrator.get_conversation_state(conversation_id="c1")

        self.assertEqual("user_1", state["user_id"])
        self.assertEqual("work_mode", state["latest_context"]["occasion"])
        self.assertEqual("ps1", state["latest_profile_snapshot_id"])
        self.assertEqual("run1", state["latest_recommendation_run_id"])

    def test_process_turn_requests_clarification_without_first_image(self) -> None:
        repo = Mock()
        repo.get_or_create_user.return_value = {"id": "user_uuid"}
        repo.get_conversation.return_value = {"id": "c1", "user_id": "user_uuid", "session_context_json": {}}
        repo.get_latest_profile_snapshot.return_value = None
        repo.create_turn.return_value = {"id": "t1"}
        orchestrator = ConversationOrchestrator(repo=repo, catalog_csv_path="data/output/enriched.csv")
        text_log = {"model": "gpt-5-mini", "request": {"a": 1}, "response": {"b": 2}}
        orchestrator.intent_agent = Mock(
            infer_text=Mock(return_value=({"occasion": "work_mode", "archetype": "classic"}, text_log))
        )

        out = orchestrator.process_turn(
            conversation_id="c1",
            external_user_id="user_1",
            message="Need looks",
            image_refs=[],
            strictness="balanced",
            hard_filter_profile="rl_ready_minimal",
            max_results=5,
        )

        self.assertTrue(out["needs_clarification"])
        self.assertIn("upload", out["clarifying_question"].lower())
        self.assertEqual([], out["recommendations"])
        self.assertIsNone(out["recommendation_run_id"])
        repo.create_turn.assert_called_once()
        repo.finalize_turn.assert_called_once()
        repo.create_recommendation_run.assert_not_called()

    def test_process_turn_requests_clarification_for_missing_text_context(self) -> None:
        repo = Mock()
        repo.get_or_create_user.return_value = {"id": "user_uuid"}
        repo.get_conversation.return_value = {"id": "c1", "user_id": "user_uuid", "session_context_json": {}}
        repo.get_latest_profile_snapshot.return_value = {
            "id": "ps_existing",
            "profile_json": {},
            "gender": "female",
            "age": "25_30",
        }
        repo.create_turn.return_value = {"id": "t1"}
        orchestrator = ConversationOrchestrator(repo=repo, catalog_csv_path="data/output/enriched.csv")
        text_log = {"model": "gpt-5-mini", "request": {"a": 1}, "response": {"b": 2}}
        orchestrator.intent_agent = Mock(
            infer_text=Mock(return_value=({"occasion": "", "archetype": ""}, text_log))
        )

        out = orchestrator.process_turn(
            conversation_id="c1",
            external_user_id="user_1",
            message="show me options",
            image_refs=[],
            strictness="balanced",
            hard_filter_profile="rl_ready_minimal",
            max_results=5,
        )

        self.assertTrue(out["needs_clarification"])
        self.assertIn("occasion", out["clarifying_question"].lower())
        self.assertIn("archetype", out["clarifying_question"].lower())
        self.assertIsNone(out["recommendation_run_id"])
        repo.create_recommendation_run.assert_not_called()

    def test_process_turn_happy_path_with_image(self) -> None:
        repo = Mock()
        repo.get_or_create_user.return_value = {"id": "user_uuid"}
        repo.get_conversation.return_value = {"id": "c1", "user_id": "user_uuid", "session_context_json": {}}
        repo.get_latest_profile_snapshot.return_value = None
        repo.create_turn.return_value = {"id": "t1"}
        repo.create_profile_snapshot.return_value = {"id": "ps1"}
        repo.create_context_snapshot.return_value = {"id": "cs1"}
        repo.create_recommendation_run.return_value = {"id": "run1"}

        orchestrator = ConversationOrchestrator(repo=repo, catalog_csv_path="data/output/enriched.csv")
        visual = self._build_visual_profile()
        visual_log = {
            "image_artifact": {
                "source_type": "file",
                "source": "/tmp/user.jpg",
                "stored_path": "/tmp/user.jpg",
            },
            "model": "gpt-5.2",
            "request": {"x": 1},
            "response": {"y": 2},
            "reasoning_notes": ["note"],
        }
        text_log = {"model": "gpt-5-mini", "request": {"a": 1}, "response": {"b": 2}}
        orchestrator.profile_agent = Mock(infer_visual=Mock(return_value=(visual, visual_log)))
        orchestrator.intent_agent = Mock(
            infer_text=Mock(return_value=({"occasion": "work_mode", "archetype": "classic"}, text_log))
        )
        orchestrator.recommendation_agent = Mock(
            recommend=Mock(
                return_value={
                    "items": [
                        {
                            "rank": 1,
                            "garment_id": "g1",
                            "title": "Test Shirt",
                            "image_url": "https://img",
                            "score": 0.9,
                            "max_score": 1.0,
                            "compatibility_confidence": 0.9,
                            "reasons": "reason 1",
                        }
                    ],
                    "meta": {
                        "total_catalog_rows": 20,
                        "filtered_rows": 5,
                        "failed_rows": 15,
                        "ranked_rows": 5,
                        "returned_rows": 1,
                    },
                }
            )
        )
        orchestrator.stylist_agent = Mock(
            build_response_message=Mock(return_value=("assistant message", False, ""))
        )

        out = orchestrator.process_turn(
            conversation_id="c1",
            external_user_id="user_1",
            message="Need office looks",
            image_refs=["/tmp/user.jpg"],
            strictness="balanced",
            hard_filter_profile="rl_ready_minimal",
            max_results=5,
        )

        self.assertEqual("c1", out["conversation_id"])
        self.assertEqual("run1", out["recommendation_run_id"])
        self.assertEqual("assistant message", out["assistant_message"])
        self.assertEqual(1, len(out["recommendations"]))
        self.assertEqual("g1", out["recommendations"][0]["garment_id"])

        self.assertEqual(2, repo.log_model_call.call_count)
        repo.insert_recommendation_items.assert_called_once()
        repo.finalize_turn.assert_called_once()
        repo.update_conversation_context.assert_called_once()


if __name__ == "__main__":
    unittest.main()
