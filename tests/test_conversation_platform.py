import unittest
from pathlib import Path
from unittest.mock import patch

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


from conversation_platform.agents import MemoryAgent, StylistAgent, TelemetryAgent
from conversation_platform.config import load_config
from conversation_platform.schemas import CreateTurnRequest, FeedbackRequest


class ConversationPlatformTests(unittest.TestCase):
    def test_memory_agent_merges_context(self) -> None:
        agent = MemoryAgent()
        merged = agent.merge_context(
            previous={"occasion": "work_mode", "archetype": "classic", "gender": "female", "age": "25_30"},
            inferred_text={"occasion": "night_out", "archetype": "glamorous"},
            inferred_visual={"gender": "female", "age": "30_35"},
        )
        self.assertEqual("night_out", merged["occasion"])
        self.assertEqual("glamorous", merged["archetype"])
        self.assertEqual("female", merged["gender"])
        self.assertEqual("30_35", merged["age"])

    def test_stylist_agent_response_with_items(self) -> None:
        agent = StylistAgent()
        message, needs_clarification, question = agent.build_response_message(
            items=[{"title": "Dress 1", "score": 0.91}],
            context={"occasion": "night_out", "archetype": "glamorous"},
        )
        self.assertIn("Dress 1", message)
        self.assertFalse(needs_clarification)
        self.assertEqual("", question)

    def test_stylist_agent_response_without_items(self) -> None:
        agent = StylistAgent()
        message, needs_clarification, question = agent.build_response_message(
            items=[],
            context={"occasion": "work_mode", "archetype": "classic"},
        )
        self.assertTrue(needs_clarification)
        self.assertTrue(question)
        self.assertIn("no strong matches", message)

    def test_stylist_agent_asks_refinement_on_low_confidence(self) -> None:
        agent = StylistAgent()
        message, needs_clarification, question = agent.build_response_message(
            items=[{"title": "Dress 1", "score": 0.61, "compatibility_confidence": 0.52}],
            context={"occasion": "night_out", "archetype": "glamorous"},
            user_message="Need something for tonight",
        )
        self.assertIn("Dress 1", message)
        self.assertTrue(needs_clarification)
        self.assertIn("preferred colors", question.lower())

    def test_stylist_agent_asks_refinement_on_short_ambiguous_prompt(self) -> None:
        agent = StylistAgent()
        _, needs_clarification, question = agent.build_response_message(
            items=[{"title": "Dress 1", "score": 0.88, "compatibility_confidence": 0.91}],
            context={"occasion": "night_out", "archetype": "glamorous"},
            user_message="help me",
        )
        self.assertTrue(needs_clarification)
        self.assertIn("fit", question.lower())

    def test_telemetry_reward_mapping(self) -> None:
        agent = TelemetryAgent()
        self.assertEqual(50, agent.reward_for_event("buy"))
        self.assertEqual(-1, agent.reward_for_event("skip"))

    def test_turn_request_defaults(self) -> None:
        req = CreateTurnRequest(user_id="u1", message="Need looks")
        self.assertEqual("balanced", req.strictness)
        self.assertEqual("rl_ready_minimal", req.hard_filter_profile)
        self.assertEqual(12, req.max_results)

    def test_feedback_event_type_validation(self) -> None:
        req = FeedbackRequest(
            user_id="u1",
            conversation_id="c1",
            recommendation_run_id="r1",
            garment_id="g1",
            event_type="like",
        )
        self.assertEqual("like", req.event_type)

    def test_load_config_accepts_supabase_cli_env_vars(self) -> None:
        with patch("conversation_platform.config._load_dotenv", return_value=None), patch.dict(
            "os.environ",
            {
                "API_URL": "http://127.0.0.1:55321",
                "SERVICE_ROLE_KEY": "service-role-jwt",
                "CATALOG_CSV_PATH": "data/output/enriched.csv",
            },
            clear=True,
        ):
            cfg = load_config()
        self.assertEqual("http://127.0.0.1:55321/rest/v1", cfg.supabase_rest_url)
        self.assertEqual("service-role-jwt", cfg.supabase_service_role_key)


if __name__ == "__main__":
    unittest.main()
