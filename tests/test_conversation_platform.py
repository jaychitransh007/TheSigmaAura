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


from conversation_platform.agents import MemoryAgent, RecommendationAgent, StylistAgent, TelemetryAgent
from conversation_platform.config import load_config
from conversation_platform.schemas import CreateTurnRequest, FeedbackRequest
from style_engine.outfit_engine import RecommendationMeta


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
        self.assertEqual(20, agent.reward_for_event("buy"))
        self.assertEqual(10, agent.reward_for_event("share"))
        self.assertEqual(2, agent.reward_for_event("like"))
        self.assertEqual(-5, agent.reward_for_event("dislike"))
        self.assertEqual(-1, agent.reward_for_event("no_action"))
        self.assertEqual(-1, agent.reward_for_event("skip"))

    def test_turn_request_defaults(self) -> None:
        req = CreateTurnRequest(user_id="u1", message="Need looks")
        self.assertEqual("balanced", req.strictness)
        self.assertEqual("rl_ready_minimal", req.hard_filter_profile)
        self.assertEqual(12, req.max_results)
        self.assertEqual("complete_plus_combos", req.result_filter)

    def test_feedback_event_type_validation(self) -> None:
        req = FeedbackRequest(
            user_id="u1",
            conversation_id="c1",
            recommendation_run_id="r1",
            garment_id="g1",
            event_type="like",
        )
        self.assertEqual("like", req.event_type)

    def test_feedback_event_type_validation_dislike(self) -> None:
        req = FeedbackRequest(
            user_id="u1",
            conversation_id="c1",
            recommendation_run_id="r1",
            garment_id="g1",
            event_type="dislike",
        )
        self.assertEqual("dislike", req.event_type)

    def test_feedback_event_type_validation_no_action(self) -> None:
        req = FeedbackRequest(
            user_id="u1",
            conversation_id="c1",
            recommendation_run_id="r1",
            garment_id="g1",
            event_type="no_action",
        )
        self.assertEqual("no_action", req.event_type)

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

    def test_recommendation_policy_relaxes_when_complete_only_has_too_few_complete_items(self) -> None:
        base_row = {
            "id": "",
            "title": "Office Option",
            "price": "3200",
            "GenderExpression": "feminine",
            "OccasionSignal": "office",
            "OccasionFit": "workwear",
            "FormalityLevel": "semi_formal",
            "TimeOfDay": "day",
            "EmbellishmentLevel": "minimal",
            "GarmentCategory": "top",
            "GarmentSubtype": "shirt",
            "StylingCompleteness": "needs_bottomwear",
            "images__0__src": "https://img/1.jpg",
        }
        passed = []
        for idx in range(8):
            row = dict(base_row)
            row["id"] = f"g_{idx}"
            if idx == 0:
                row["GarmentCategory"] = "one_piece"
                row["StylingCompleteness"] = "complete"
                row["GarmentSubtype"] = "dress"
                row["title"] = "Office Sheath Dress"
            passed.append(row)

        agent = RecommendationAgent(catalog_csv_path="data/catalog/enriched_catalog.csv")
        mock_meta = RecommendationMeta(
            resolved_mode="outfit",
            requested_categories=[],
            requested_subtypes=[],
            base_ranked_rows=8,
            single_candidates=8,
            combo_candidates=0,
            returned_rows=0,
        )
        with patch("conversation_platform.agents.read_csv_rows", return_value=passed), patch.object(
            agent,
            "_filter_rows",
            return_value=(passed, [], []),
        ), patch(
            "conversation_platform.agents.rank_recommendation_candidates",
            return_value=([], mock_meta),
        ) as mock_rank:
            out = agent.recommend(
                context={"occasion": "work_mode", "archetype": "classic", "gender": "female", "age": "25_30"},
                profile={"color_preferences": {}},
                strictness="balanced",
                hard_filter_profile="rl_ready_minimal",
                max_results=6,
                recommendation_mode="auto",
                include_combos=False,
                request_text="Big presentation day at work!",
            )

        kwargs = mock_rank.call_args.kwargs
        self.assertEqual(8, len(kwargs["rows"]))
        self.assertEqual("high_stakes_work", kwargs["intent_policy_id"])
        self.assertFalse(out["meta"]["intent_policy_hard_filter_applied"])
        self.assertTrue(out["meta"]["intent_policy_hard_filter_relaxed"])


if __name__ == "__main__":
    unittest.main()
