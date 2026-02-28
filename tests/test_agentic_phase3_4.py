import unittest
from pathlib import Path
from unittest.mock import Mock, patch

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


from conversation_platform.schemas import (
    CheckoutPrepareResponse,
    SubstitutionSuggestion,
    TurnResponse,
)
from conversation_platform.orchestrator import ConversationOrchestrator
from user_profiler.schemas import BODY_ENUMS


# ---------------------------------------------------------------------------
# Phase 3.3: mode_switch_cta in TurnResponse
# ---------------------------------------------------------------------------

class ModeSwitchCtaSchemaTests(unittest.TestCase):
    def test_mode_switch_cta_defaults_to_empty(self) -> None:
        resp = TurnResponse(
            conversation_id="c1",
            turn_id="t1",
            assistant_message="msg",
            resolved_context={"occasion": "", "archetype": "", "gender": "", "age": ""},
        )
        self.assertEqual("", resp.mode_switch_cta)

    def test_mode_switch_cta_accepts_value(self) -> None:
        resp = TurnResponse(
            conversation_id="c1",
            turn_id="t1",
            assistant_message="msg",
            resolved_context={"occasion": "", "archetype": "", "gender": "", "age": ""},
            mode_switch_cta="Switch to outfit mode to see complete looks",
        )
        self.assertEqual("Switch to outfit mode to see complete looks", resp.mode_switch_cta)


class ModeSwitchCtaOrchestratorTests(unittest.TestCase):
    def _build_visual_profile(self) -> dict:
        visual = {key: values[0] for key, values in BODY_ENUMS.items()}
        visual["gender"] = "female"
        visual["age"] = "25_30"
        return visual

    def _setup_orchestrator(self, repo: Mock) -> ConversationOrchestrator:
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
            "image_artifact": {"source_type": "file", "source": "/tmp/u.jpg", "stored_path": "/tmp/u.jpg"},
            "model": "gpt-5.2", "request": {}, "response": {}, "reasoning_notes": [],
        }
        text_log = {"model": "gpt-5-mini", "request": {}, "response": {}}
        orchestrator.profile_agent = Mock(infer_visual=Mock(return_value=(visual, visual_log)))
        orchestrator.intent_agent = Mock(
            infer_text=Mock(return_value=({"occasion": "work_mode", "archetype": "classic"}, text_log))
        )
        orchestrator.recommendation_agent = Mock(
            recommend=Mock(return_value={
                "items": [],
                "meta": {"ranked_rows": 0, "returned_rows": 0},
            })
        )
        orchestrator.stylist_agent = Mock(build_response_message=Mock(return_value=("msg", False, "")))
        return orchestrator

    def test_garment_mode_sets_mode_switch_cta(self) -> None:
        repo = Mock()
        orch = self._setup_orchestrator(repo)

        out = orch.process_turn(
            conversation_id="c1",
            external_user_id="u1",
            message="Show me shirts",
            image_refs=["/tmp/u.jpg"],
            strictness="balanced",
            hard_filter_profile="rl_ready_minimal",
            max_results=5,
            mode_preference="garment",
        )

        self.assertTrue(out["complete_the_look_offer"])
        self.assertIn("outfit mode", out["mode_switch_cta"].lower())
        self.assertNotEqual("", out["mode_switch_cta"])

    def test_outfit_mode_has_empty_mode_switch_cta(self) -> None:
        repo = Mock()
        orch = self._setup_orchestrator(repo)

        out = orch.process_turn(
            conversation_id="c1",
            external_user_id="u1",
            message="Need office looks",
            image_refs=["/tmp/u.jpg"],
            strictness="balanced",
            hard_filter_profile="rl_ready_minimal",
            max_results=5,
            mode_preference="outfit",
        )

        self.assertFalse(out["complete_the_look_offer"])
        self.assertEqual("", out["mode_switch_cta"])

    def test_auto_with_target_garment_sets_cta(self) -> None:
        repo = Mock()
        orch = self._setup_orchestrator(repo)

        out = orch.process_turn(
            conversation_id="c1",
            external_user_id="u1",
            message="Show me white shirts",
            image_refs=["/tmp/u.jpg"],
            strictness="balanced",
            hard_filter_profile="rl_ready_minimal",
            max_results=5,
            mode_preference="auto",
            target_garment_type="shirt",
        )

        self.assertEqual("garment", out["resolved_mode"])
        self.assertNotEqual("", out["mode_switch_cta"])


# ---------------------------------------------------------------------------
# Phase 4.2: substitution suggestions in checkout-prep
# ---------------------------------------------------------------------------

class SubstitutionSuggestionSchemaTests(unittest.TestCase):
    def test_substitution_suggestion_model(self) -> None:
        s = SubstitutionSuggestion(
            original_garment_id="g1",
            suggested_garment_id="g3",
            suggested_title="Cheaper Shirt",
            suggested_price=1500,
            reason="lower_price_within_budget",
        )
        self.assertEqual("g1", s.original_garment_id)
        self.assertEqual("g3", s.suggested_garment_id)
        self.assertEqual(1500, s.suggested_price)

    def test_checkout_response_substitution_defaults_empty(self) -> None:
        resp = CheckoutPrepareResponse(checkout_prep_id="cp1", status="ready")
        self.assertEqual([], resp.substitution_suggestions)

    def test_checkout_response_accepts_substitutions(self) -> None:
        resp = CheckoutPrepareResponse(
            checkout_prep_id="cp1",
            status="needs_user_action",
            substitution_suggestions=[
                SubstitutionSuggestion(
                    original_garment_id="g1",
                    suggested_garment_id="g3",
                    reason="lower_price_within_budget",
                ),
            ],
        )
        self.assertEqual(1, len(resp.substitution_suggestions))


class SubstitutionOrchestratorTests(unittest.TestCase):
    def _make_orchestrator(self, repo: Mock) -> ConversationOrchestrator:
        repo.get_or_create_user.return_value = {"id": "user_uuid"}
        repo.get_conversation.return_value = {"id": "c1", "user_id": "user_uuid"}
        repo.get_latest_turn.return_value = {"id": "t1"}
        repo.create_checkout_preparation.return_value = {"id": "cp1"}
        repo.insert_checkout_preparation_items.return_value = []
        repo.log_tool_trace.return_value = {"id": "tt1"}
        return ConversationOrchestrator(repo=repo, catalog_csv_path="data/output/enriched.csv")

    def test_over_budget_with_cheaper_alternative_suggests_substitution(self) -> None:
        repo = Mock()
        repo.get_recommendation_run.return_value = {"id": "run1"}
        # g1 (3000) + g2 (4000) = 7000, budget = 5000, surplus = 2000
        # g3 (1000) is unused and cheaper than g2 by 3000 >= 2000
        repo.get_recommendation_items.return_value = [
            {"garment_id": "g1", "title": "Shirt", "score": 3000},
            {"garment_id": "g2", "title": "Pants", "score": 4000},
            {"garment_id": "g3", "title": "Budget Pants", "score": 1000},
        ]

        orch = self._make_orchestrator(repo)
        out = orch.prepare_checkout(
            conversation_id="c1",
            external_user_id="u1",
            recommendation_run_id="run1",
            selected_item_ids=["g1", "g2"],
            budget_cap=5000,
        )

        self.assertEqual("needs_user_action", out["status"])
        self.assertIn("substitution_suggested", out["validation_notes"])
        self.assertEqual(1, len(out["substitution_suggestions"]))
        sub = out["substitution_suggestions"][0]
        self.assertEqual("g2", sub["original_garment_id"])
        self.assertEqual("g3", sub["suggested_garment_id"])
        self.assertEqual(1000, sub["suggested_price"])

    def test_over_budget_no_cheaper_alternative_no_substitution(self) -> None:
        repo = Mock()
        repo.get_recommendation_run.return_value = {"id": "run1"}
        # g1 (3000) + g2 (4000) = 7000, budget = 5000, surplus = 2000
        # No unused items available
        repo.get_recommendation_items.return_value = [
            {"garment_id": "g1", "title": "Shirt", "score": 3000},
            {"garment_id": "g2", "title": "Pants", "score": 4000},
        ]

        orch = self._make_orchestrator(repo)
        out = orch.prepare_checkout(
            conversation_id="c1",
            external_user_id="u1",
            recommendation_run_id="run1",
            selected_item_ids=["g1", "g2"],
            budget_cap=5000,
        )

        self.assertEqual("needs_user_action", out["status"])
        self.assertIn("no_substitution_available", out["validation_notes"])
        self.assertEqual(0, len(out["substitution_suggestions"]))

    def test_within_budget_no_substitution(self) -> None:
        repo = Mock()
        repo.get_recommendation_run.return_value = {"id": "run1"}
        repo.get_recommendation_items.return_value = [
            {"garment_id": "g1", "title": "Shirt", "score": 2000},
            {"garment_id": "g2", "title": "Pants", "score": 3000},
        ]

        orch = self._make_orchestrator(repo)
        out = orch.prepare_checkout(
            conversation_id="c1",
            external_user_id="u1",
            recommendation_run_id="run1",
            selected_item_ids=["g1", "g2"],
            budget_cap=10000,
        )

        self.assertEqual("ready", out["status"])
        self.assertEqual(0, len(out["substitution_suggestions"]))
        self.assertNotIn("over_budget", out["validation_notes"])

    def test_no_budget_cap_no_substitution(self) -> None:
        repo = Mock()
        repo.get_recommendation_run.return_value = {"id": "run1"}
        repo.get_recommendation_items.return_value = [
            {"garment_id": "g1", "title": "Shirt", "score": 9999},
        ]

        orch = self._make_orchestrator(repo)
        out = orch.prepare_checkout(
            conversation_id="c1",
            external_user_id="u1",
            recommendation_run_id="run1",
            selected_item_ids=["g1"],
        )

        self.assertEqual("ready", out["status"])
        self.assertEqual(0, len(out["substitution_suggestions"]))


# ---------------------------------------------------------------------------
# Phase 4.3: tool trace logging in checkout-prep
# ---------------------------------------------------------------------------

class CheckoutToolTraceTests(unittest.TestCase):
    def _make_orchestrator(self, repo: Mock) -> ConversationOrchestrator:
        repo.get_or_create_user.return_value = {"id": "user_uuid"}
        repo.get_conversation.return_value = {"id": "c1", "user_id": "user_uuid"}
        repo.get_recommendation_run.return_value = {"id": "run1"}
        repo.get_recommendation_items.return_value = [
            {"garment_id": "g1", "title": "Shirt", "score": 2000},
        ]
        repo.get_latest_turn.return_value = {"id": "t1"}
        repo.create_checkout_preparation.return_value = {"id": "cp1"}
        repo.insert_checkout_preparation_items.return_value = []
        repo.log_tool_trace.return_value = {"id": "tt1"}
        return ConversationOrchestrator(repo=repo, catalog_csv_path="data/output/enriched.csv")

    def test_prepare_checkout_logs_tool_trace(self) -> None:
        repo = Mock()
        orch = self._make_orchestrator(repo)

        orch.prepare_checkout(
            conversation_id="c1",
            external_user_id="u1",
            recommendation_run_id="run1",
            selected_item_ids=["g1"],
        )

        repo.log_tool_trace.assert_called_once()
        call_kwargs = repo.log_tool_trace.call_args.kwargs
        self.assertEqual("checkout_prep.prepare", call_kwargs["tool_name"])
        self.assertEqual("c1", call_kwargs["conversation_id"])
        self.assertEqual("t1", call_kwargs["turn_id"])

    def test_tool_trace_input_contains_request_params(self) -> None:
        repo = Mock()
        orch = self._make_orchestrator(repo)

        orch.prepare_checkout(
            conversation_id="c1",
            external_user_id="u1",
            recommendation_run_id="run1",
            selected_item_ids=["g1"],
            budget_cap=5000,
        )

        input_json = repo.log_tool_trace.call_args.kwargs["input_json"]
        self.assertEqual("run1", input_json["recommendation_run_id"])
        self.assertEqual(["g1"], input_json["selected_item_ids"])
        self.assertEqual(5000, input_json["budget_cap"])

    def test_tool_trace_output_contains_status(self) -> None:
        repo = Mock()
        orch = self._make_orchestrator(repo)

        orch.prepare_checkout(
            conversation_id="c1",
            external_user_id="u1",
            recommendation_run_id="run1",
            selected_item_ids=["g1"],
        )

        output_json = repo.log_tool_trace.call_args.kwargs["output_json"]
        self.assertEqual("cp1", output_json["checkout_prep_id"])
        self.assertEqual("ready", output_json["status"])
        self.assertEqual(0, output_json["substitution_count"])

    def test_tool_trace_with_substitutions_shows_count(self) -> None:
        repo = Mock()
        repo.get_or_create_user.return_value = {"id": "user_uuid"}
        repo.get_conversation.return_value = {"id": "c1", "user_id": "user_uuid"}
        repo.get_recommendation_run.return_value = {"id": "run1"}
        repo.get_recommendation_items.return_value = [
            {"garment_id": "g1", "title": "Shirt", "score": 5000},
            {"garment_id": "g2", "title": "Alt", "score": 1000},
        ]
        repo.get_latest_turn.return_value = {"id": "t1"}
        repo.create_checkout_preparation.return_value = {"id": "cp1"}
        repo.insert_checkout_preparation_items.return_value = []
        repo.log_tool_trace.return_value = {"id": "tt1"}

        orch = ConversationOrchestrator(repo=repo, catalog_csv_path="data/output/enriched.csv")

        orch.prepare_checkout(
            conversation_id="c1",
            external_user_id="u1",
            recommendation_run_id="run1",
            selected_item_ids=["g1"],
            budget_cap=3000,
        )

        output_json = repo.log_tool_trace.call_args.kwargs["output_json"]
        self.assertEqual(1, output_json["substitution_count"])


if __name__ == "__main__":
    unittest.main()
