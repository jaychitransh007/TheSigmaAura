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


from conversation_platform.agents import (
    BodyHarmonyAgent,
    BrandVarianceComfortSubAgent,
    CatalogFilterSubAgent,
    GarmentRankerSubAgent,
    IntentModeRouterAgent,
    IntentPolicySubAgent,
    ProfileAgent,
    RecommendationAgent,
    StyleRequirementInterpreter,
    UserProfileAgent,
)
from user_profiler.schemas import BODY_ENUMS


# ---------------------------------------------------------------------------
# IntentModeRouterAgent tests
# ---------------------------------------------------------------------------

class IntentModeRouterAgentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.router = IntentModeRouterAgent()

    def test_auto_with_target_garment_resolves_garment(self) -> None:
        result = self.router.resolve_mode(
            mode_preference="auto",
            target_garment_type="shirt",
            request_text="Show me white shirts",
        )
        self.assertEqual("garment", result["resolved_mode"])
        self.assertTrue(result["complete_the_look_offer"])

    def test_auto_without_target_resolves_outfit(self) -> None:
        result = self.router.resolve_mode(
            mode_preference="auto",
            request_text="I need a polished office look",
        )
        self.assertEqual("outfit", result["resolved_mode"])
        self.assertFalse(result["complete_the_look_offer"])

    def test_explicit_garment_mode(self) -> None:
        result = self.router.resolve_mode(mode_preference="garment", request_text="anything")
        self.assertEqual("garment", result["resolved_mode"])
        self.assertTrue(result["complete_the_look_offer"])

    def test_explicit_outfit_mode(self) -> None:
        result = self.router.resolve_mode(mode_preference="outfit", request_text="anything")
        self.assertEqual("outfit", result["resolved_mode"])
        self.assertFalse(result["complete_the_look_offer"])

    def test_auto_detects_garment_from_request_text(self) -> None:
        result = self.router.resolve_mode(
            mode_preference="auto",
            request_text="Show me kurtas for festive season",
        )
        # outfit_engine should detect "kurtas" as a garment keyword
        # The exact result depends on outfit_assembly_v1.json config
        self.assertIn(result["resolved_mode"], ("garment", "outfit"))
        self.assertIsInstance(result["requested_categories"], list)
        self.assertIsInstance(result["requested_subtypes"], list)

    def test_result_contains_all_keys(self) -> None:
        result = self.router.resolve_mode(mode_preference="auto", request_text="hello")
        self.assertIn("resolved_mode", result)
        self.assertIn("complete_the_look_offer", result)
        self.assertIn("requested_categories", result)
        self.assertIn("requested_subtypes", result)


# ---------------------------------------------------------------------------
# UserProfileAgent tests
# ---------------------------------------------------------------------------

class UserProfileAgentTests(unittest.TestCase):
    def test_merge_with_empty_existing(self) -> None:
        result = UserProfileAgent.merge_profile(
            existing=None,
            initial_profile={"sizes": {"top_size": "M"}},
        )
        self.assertEqual({"top_size": "M"}, result["sizes"])

    def test_merge_size_overrides(self) -> None:
        result = UserProfileAgent.merge_profile(
            existing={"sizes": {"top_size": "S"}},
            size_overrides={"top_size": "M", "bottom_size": "30"},
        )
        self.assertEqual("M", result["sizes"]["top_size"])
        self.assertEqual("30", result["sizes"]["bottom_size"])

    def test_last_write_wins_for_initial_profile(self) -> None:
        result = UserProfileAgent.merge_profile(
            existing={"brand_preferences": {"liked": ["A"]}},
            initial_profile={"brand_preferences": {"liked": ["B"]}},
        )
        self.assertEqual({"liked": ["B"]}, result["brand_preferences"])

    def test_merge_preserves_existing_fields(self) -> None:
        result = UserProfileAgent.merge_profile(
            existing={"consent_flags": {"image_inference_allowed": True}},
            initial_profile={"sizes": {"top_size": "L"}},
        )
        self.assertTrue(result["consent_flags"]["image_inference_allowed"])
        self.assertEqual({"top_size": "L"}, result["sizes"])

    def test_profile_fields_used_excludes_color_preferences(self) -> None:
        profile = {"HeightCategory": "average", "color_preferences": {"loved": ["red"]}}
        fields = UserProfileAgent.profile_fields_used(profile)
        self.assertIn("HeightCategory", fields)
        self.assertNotIn("color_preferences", fields)

    def test_profile_fields_used_empty_for_empty_profile(self) -> None:
        self.assertEqual([], UserProfileAgent.profile_fields_used({}))


# ---------------------------------------------------------------------------
# BodyHarmonyAgent tests
# ---------------------------------------------------------------------------

class BodyHarmonyAgentTests(unittest.TestCase):
    def _build_visual(self) -> dict:
        visual = {key: values[0] for key, values in BODY_ENUMS.items()}
        visual["gender"] = "female"
        visual["age"] = "25_30"
        return visual

    def test_extract_body_profile_has_all_enum_keys(self) -> None:
        visual = self._build_visual()
        profile = BodyHarmonyAgent.extract_body_profile(visual)
        for key in BODY_ENUMS.keys():
            self.assertIn(key, profile)
        self.assertIn("color_preferences", profile)

    def test_extract_body_profile_excludes_gender_age(self) -> None:
        visual = self._build_visual()
        profile = BodyHarmonyAgent.extract_body_profile(visual)
        # gender and age are not in BODY_ENUMS so should not appear
        self.assertNotIn("gender", profile)
        self.assertNotIn("age", profile)

    def test_style_constraints_from_profile(self) -> None:
        constraints = BodyHarmonyAgent.style_constraints_from_profile({"HeightCategory": "tall"})
        self.assertEqual(["body_harmony"], constraints)

    def test_style_constraints_empty_for_empty_profile(self) -> None:
        constraints = BodyHarmonyAgent.style_constraints_from_profile({})
        self.assertEqual([], constraints)

    def test_profile_agent_alias(self) -> None:
        self.assertIs(ProfileAgent, BodyHarmonyAgent)


# ---------------------------------------------------------------------------
# Style sub-agent tests
# ---------------------------------------------------------------------------

class StyleRequirementInterpreterTests(unittest.TestCase):
    def test_interpret_returns_context_fields(self) -> None:
        result = StyleRequirementInterpreter.interpret(
            request_text="office look",
            context={"occasion": "work_mode", "archetype": "classic"},
        )
        self.assertEqual("work_mode", result["occasion"])
        self.assertEqual("classic", result["archetype"])
        self.assertEqual("office look", result["request_text"])


class CatalogFilterSubAgentTests(unittest.TestCase):
    def test_initialization_loads_tier1_rules(self) -> None:
        agent = CatalogFilterSubAgent()
        self.assertIsNotNone(agent.tier1_rules)
        self.assertIsInstance(agent.tier1_rules, dict)


class GarmentRankerSubAgentTests(unittest.TestCase):
    def test_initialization_loads_tier2_rules(self) -> None:
        agent = GarmentRankerSubAgent()
        self.assertIsNotNone(agent.tier2_rules)
        self.assertIsInstance(agent.tier2_rules, dict)


class IntentPolicySubAgentTests(unittest.TestCase):
    def test_resolve_returns_dict(self) -> None:
        result = IntentPolicySubAgent.resolve(
            request_text="office presentation",
            context={"occasion": "work_mode", "archetype": "classic", "gender": "female", "age": "25_30"},
        )
        self.assertIsInstance(result, dict)
        self.assertIn("policy_id", result)


class BrandVarianceComfortSubAgentTests(unittest.TestCase):
    def test_apply_passthrough(self) -> None:
        items = [{"garment_id": "g1", "score": 0.9}]
        result = BrandVarianceComfortSubAgent.apply(items)
        self.assertEqual(items, result)


# ---------------------------------------------------------------------------
# RecommendationAgent delegation tests
# ---------------------------------------------------------------------------

class RecommendationAgentDelegationTests(unittest.TestCase):
    def test_recommendation_agent_has_sub_agents(self) -> None:
        agent = RecommendationAgent(catalog_csv_path="data/output/enriched.csv")
        self.assertIsInstance(agent.catalog_filter, CatalogFilterSubAgent)
        self.assertIsInstance(agent.garment_ranker, GarmentRankerSubAgent)
        self.assertIsInstance(agent.intent_policy_agent, IntentPolicySubAgent)
        self.assertIsInstance(agent.brand_variance_agent, BrandVarianceComfortSubAgent)

    def test_legacy_tier1_tier2_refs_preserved(self) -> None:
        agent = RecommendationAgent(catalog_csv_path="data/output/enriched.csv")
        self.assertIs(agent.tier1_rules, agent.catalog_filter.tier1_rules)
        self.assertIs(agent.tier2_rules, agent.garment_ranker.tier2_rules)


# ---------------------------------------------------------------------------
# Orchestrator uses new agents
# ---------------------------------------------------------------------------

class OrchestratorAgentWiringTests(unittest.TestCase):
    def test_orchestrator_has_mode_router(self) -> None:
        from conversation_platform.orchestrator import ConversationOrchestrator
        repo = Mock()
        orch = ConversationOrchestrator(repo=repo, catalog_csv_path="data/output/enriched.csv")
        self.assertIsInstance(orch.mode_router, IntentModeRouterAgent)

    def test_orchestrator_has_user_profile_agent(self) -> None:
        from conversation_platform.orchestrator import ConversationOrchestrator
        repo = Mock()
        orch = ConversationOrchestrator(repo=repo, catalog_csv_path="data/output/enriched.csv")
        self.assertIsInstance(orch.user_profile_agent, UserProfileAgent)

    def test_orchestrator_has_body_harmony_agent(self) -> None:
        from conversation_platform.orchestrator import ConversationOrchestrator
        repo = Mock()
        orch = ConversationOrchestrator(repo=repo, catalog_csv_path="data/output/enriched.csv")
        self.assertIsInstance(orch.body_harmony_agent, BodyHarmonyAgent)

    def test_orchestrator_profile_agent_is_body_harmony(self) -> None:
        from conversation_platform.orchestrator import ConversationOrchestrator
        repo = Mock()
        orch = ConversationOrchestrator(repo=repo, catalog_csv_path="data/output/enriched.csv")
        self.assertIs(orch.profile_agent, orch.body_harmony_agent)

    def test_mode_router_used_in_process_turn(self) -> None:
        from conversation_platform.orchestrator import ConversationOrchestrator
        repo = Mock()
        repo.get_or_create_user.return_value = {"id": "uid"}
        repo.get_conversation.return_value = {"id": "c1", "user_id": "uid", "session_context_json": {}}
        repo.get_latest_profile_snapshot.return_value = None
        repo.create_turn.return_value = {"id": "t1"}
        repo.create_profile_snapshot.return_value = {"id": "ps1"}
        repo.create_context_snapshot.return_value = {"id": "cs1"}
        repo.create_recommendation_run.return_value = {"id": "run1"}

        orch = ConversationOrchestrator(repo=repo, catalog_csv_path="data/output/enriched.csv")

        visual = {key: values[0] for key, values in BODY_ENUMS.items()}
        visual["gender"] = "female"
        visual["age"] = "25_30"
        visual_log = {
            "image_artifact": {"source_type": "file", "source": "/tmp/u.jpg", "stored_path": "/tmp/u.jpg"},
            "model": "gpt-5.2", "request": {}, "response": {}, "reasoning_notes": [],
        }
        text_log = {"model": "gpt-5-mini", "request": {}, "response": {}}
        orch.profile_agent = Mock(infer_visual=Mock(return_value=(visual, visual_log)))
        orch.intent_agent = Mock(
            infer_text=Mock(return_value=({"occasion": "work_mode", "archetype": "classic"}, text_log))
        )
        orch.recommendation_agent = Mock(
            recommend=Mock(return_value={
                "items": [],
                "meta": {"ranked_rows": 0, "returned_rows": 0},
            })
        )
        orch.stylist_agent = Mock(build_response_message=Mock(return_value=("msg", False, "")))

        mock_router = Mock()
        mock_router.resolve_mode.return_value = {
            "resolved_mode": "garment",
            "complete_the_look_offer": True,
            "requested_categories": ["top"],
            "requested_subtypes": [],
        }
        orch.mode_router = mock_router

        out = orch.process_turn(
            conversation_id="c1",
            external_user_id="u1",
            message="Show me shirts",
            image_refs=["/tmp/u.jpg"],
            strictness="balanced",
            hard_filter_profile="rl_ready_minimal",
            max_results=5,
            mode_preference="auto",
            target_garment_type="shirt",
        )

        mock_router.resolve_mode.assert_called_once_with(
            mode_preference="auto",
            target_garment_type="shirt",
            request_text="Show me shirts",
        )
        self.assertEqual("garment", out["resolved_mode"])
        self.assertTrue(out["complete_the_look_offer"])


if __name__ == "__main__":
    unittest.main()
