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
    ROOT / "modules" / "onboarding" / "src",
):
    sp = str(p)
    if sp not in sys.path:
        sys.path.insert(0, sp)


from conversation_platform.agents import PolicyGuardrailAgent
from conversation_platform.schemas import ActionCheckRequest, ActionCheckResponse
from conversation_platform.orchestrator import ConversationOrchestrator
from user_profiler.schemas import BODY_ENUMS


# ---------------------------------------------------------------------------
# Phase 5.1: PolicyGuardrailAgent — block execute_purchase
# ---------------------------------------------------------------------------

class PolicyGuardrailAgentTests(unittest.TestCase):
    def test_execute_purchase_blocked(self) -> None:
        result = PolicyGuardrailAgent.check_action("execute_purchase")
        self.assertFalse(result["allowed"])
        self.assertEqual("execute_purchase", result["blocked_action"])
        self.assertIn("not supported", result["reason"].lower())

    def test_place_order_blocked(self) -> None:
        result = PolicyGuardrailAgent.check_action("place_order")
        self.assertFalse(result["allowed"])
        self.assertEqual("place_order", result["blocked_action"])

    def test_confirm_order_blocked(self) -> None:
        result = PolicyGuardrailAgent.check_action("confirm_order")
        self.assertFalse(result["allowed"])

    def test_submit_order_blocked(self) -> None:
        result = PolicyGuardrailAgent.check_action("submit_order")
        self.assertFalse(result["allowed"])

    def test_recommend_allowed(self) -> None:
        result = PolicyGuardrailAgent.check_action("recommend")
        self.assertTrue(result["allowed"])
        self.assertIsNone(result["blocked_action"])
        self.assertEqual("", result["reason"])

    def test_prepare_checkout_allowed(self) -> None:
        result = PolicyGuardrailAgent.check_action("prepare_checkout")
        self.assertTrue(result["allowed"])

    def test_blocked_action_case_insensitive(self) -> None:
        result = PolicyGuardrailAgent.check_action("Execute_Purchase")
        self.assertFalse(result["allowed"])

    def test_blocked_action_with_hyphens(self) -> None:
        result = PolicyGuardrailAgent.check_action("execute-purchase")
        self.assertFalse(result["allowed"])

    def test_blocked_action_with_spaces(self) -> None:
        result = PolicyGuardrailAgent.check_action("execute purchase")
        self.assertFalse(result["allowed"])

    def test_blocked_actions_list(self) -> None:
        actions = PolicyGuardrailAgent.blocked_actions_list()
        self.assertIsInstance(actions, list)
        self.assertIn("execute_purchase", actions)
        self.assertIn("place_order", actions)
        self.assertEqual(actions, sorted(actions))

    def test_blocked_reason_mentions_checkout_preparation(self) -> None:
        result = PolicyGuardrailAgent.check_action("execute_purchase")
        self.assertIn("checkout", result["reason"].lower())


class OrchestratorCheckActionTests(unittest.TestCase):
    def test_orchestrator_check_action_blocked(self) -> None:
        repo = Mock()
        orch = ConversationOrchestrator(repo=repo, catalog_csv_path="data/output/enriched.csv")
        result = orch.check_action("execute_purchase")
        self.assertFalse(result["allowed"])

    def test_orchestrator_check_action_allowed(self) -> None:
        repo = Mock()
        orch = ConversationOrchestrator(repo=repo, catalog_csv_path="data/output/enriched.csv")
        result = orch.check_action("recommend")
        self.assertTrue(result["allowed"])

    def test_orchestrator_has_policy_guardrail(self) -> None:
        repo = Mock()
        orch = ConversationOrchestrator(repo=repo, catalog_csv_path="data/output/enriched.csv")
        self.assertIsInstance(orch.policy_guardrail, PolicyGuardrailAgent)


class ActionCheckSchemaTests(unittest.TestCase):
    def test_action_check_request(self) -> None:
        req = ActionCheckRequest(action="execute_purchase")
        self.assertEqual("execute_purchase", req.action)

    def test_action_check_response_blocked(self) -> None:
        resp = ActionCheckResponse(allowed=False, blocked_action="execute_purchase", reason="not allowed")
        self.assertFalse(resp.allowed)
        self.assertEqual("execute_purchase", resp.blocked_action)

    def test_action_check_response_allowed(self) -> None:
        resp = ActionCheckResponse(allowed=True)
        self.assertTrue(resp.allowed)
        self.assertIsNone(resp.blocked_action)
        self.assertEqual("", resp.reason)


# ---------------------------------------------------------------------------
# Phase 5.1: API endpoint for action check
# ---------------------------------------------------------------------------

class ActionCheckEndpointTests(unittest.TestCase):
    def _create_test_app(self):
        from fastapi.testclient import TestClient

        with patch("conversation_platform.api.load_config") as load_cfg, \
            patch("conversation_platform.api.SupabaseRestClient"), \
            patch("conversation_platform.api.ConversationRepository"), \
            patch("conversation_platform.api.ConversationOrchestrator") as orch_cls:
            load_cfg.return_value = Mock(
                supabase_rest_url="http://127.0.0.1:55321/rest/v1",
                supabase_service_role_key="x",
                request_timeout_seconds=5,
                catalog_csv_path="data/output/enriched.csv",
            )
            mock_orch = Mock()
            orch_cls.return_value = mock_orch
            mock_orch.check_action.side_effect = lambda a: PolicyGuardrailAgent.check_action(a)

            from conversation_platform.api import create_app
            app = create_app()
            return TestClient(app), mock_orch

    def test_execute_purchase_returns_blocked(self) -> None:
        client, _ = self._create_test_app()
        resp = client.post("/v1/actions/check", json={"action": "execute_purchase"})
        self.assertEqual(200, resp.status_code)
        data = resp.json()
        self.assertFalse(data["allowed"])
        self.assertEqual("execute_purchase", data["blocked_action"])
        self.assertIn("not supported", data["reason"].lower())

    def test_recommend_returns_allowed(self) -> None:
        client, _ = self._create_test_app()
        resp = client.post("/v1/actions/check", json={"action": "recommend"})
        self.assertEqual(200, resp.status_code)
        data = resp.json()
        self.assertTrue(data["allowed"])


# ---------------------------------------------------------------------------
# Phase 5.2: Mode resolution and guardrail trace logging
# ---------------------------------------------------------------------------

class ModeResolutionTraceTests(unittest.TestCase):
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
        repo.log_tool_trace.return_value = {"id": "tt1"}

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

    def test_process_turn_logs_mode_resolution_trace(self) -> None:
        repo = Mock()
        orch = self._setup_orchestrator(repo)

        orch.process_turn(
            conversation_id="c1",
            external_user_id="u1",
            message="Show me shirts",
            image_refs=["/tmp/u.jpg"],
            strictness="balanced",
            hard_filter_profile="rl_ready_minimal",
            max_results=5,
            mode_preference="garment",
            target_garment_type="shirt",
        )

        # Should have at least 2 log_tool_trace calls:
        # 1) mode_router.resolve_mode
        # 2) recommendation_agent.recommend
        trace_calls = repo.log_tool_trace.call_args_list
        tool_names = [c.kwargs["tool_name"] for c in trace_calls]
        self.assertIn("mode_router.resolve_mode", tool_names)

    def test_mode_resolution_trace_contains_constraints(self) -> None:
        repo = Mock()
        orch = self._setup_orchestrator(repo)

        orch.process_turn(
            conversation_id="c1",
            external_user_id="u1",
            message="Show me shirts",
            image_refs=["/tmp/u.jpg"],
            strictness="balanced",
            hard_filter_profile="rl_ready_minimal",
            max_results=5,
            mode_preference="garment",
        )

        trace_calls = repo.log_tool_trace.call_args_list
        mode_trace = next(c for c in trace_calls if c.kwargs["tool_name"] == "mode_router.resolve_mode")
        output = mode_trace.kwargs["output_json"]
        self.assertIn("style_constraints_applied", output)
        self.assertIn("profile_fields_used", output)
        self.assertIn("resolved_mode", output)

    def test_mode_resolution_trace_input_has_preference(self) -> None:
        repo = Mock()
        orch = self._setup_orchestrator(repo)

        orch.process_turn(
            conversation_id="c1",
            external_user_id="u1",
            message="office looks",
            image_refs=["/tmp/u.jpg"],
            strictness="balanced",
            hard_filter_profile="rl_ready_minimal",
            max_results=5,
            mode_preference="outfit",
        )

        trace_calls = repo.log_tool_trace.call_args_list
        mode_trace = next(c for c in trace_calls if c.kwargs["tool_name"] == "mode_router.resolve_mode")
        input_json = mode_trace.kwargs["input_json"]
        self.assertEqual("outfit", input_json["mode_preference"])


class GuardrailTraceTests(unittest.TestCase):
    def test_log_guardrail_trace_blocked(self) -> None:
        repo = Mock()
        repo.log_tool_trace.return_value = {"id": "tt1"}
        orch = ConversationOrchestrator(repo=repo, catalog_csv_path="data/output/enriched.csv")

        result = PolicyGuardrailAgent.check_action("execute_purchase")
        orch._log_guardrail_trace(
            conversation_id="c1",
            turn_id="t1",
            action="execute_purchase",
            result=result,
        )

        repo.log_tool_trace.assert_called_once()
        call_kwargs = repo.log_tool_trace.call_args.kwargs
        self.assertEqual("policy_guardrail.check_action", call_kwargs["tool_name"])
        self.assertEqual("blocked", call_kwargs["status"])

    def test_log_guardrail_trace_allowed(self) -> None:
        repo = Mock()
        repo.log_tool_trace.return_value = {"id": "tt1"}
        orch = ConversationOrchestrator(repo=repo, catalog_csv_path="data/output/enriched.csv")

        result = PolicyGuardrailAgent.check_action("recommend")
        orch._log_guardrail_trace(
            conversation_id="c1",
            turn_id="t1",
            action="recommend",
            result=result,
        )

        call_kwargs = repo.log_tool_trace.call_args.kwargs
        self.assertEqual("ok", call_kwargs["status"])


# ---------------------------------------------------------------------------
# Phase 5.3: Dashboard query files exist
# ---------------------------------------------------------------------------

class DashboardQueryTests(unittest.TestCase):
    def test_funnel_metrics_sql_exists(self) -> None:
        path = ROOT / "ops" / "queries" / "funnel_metrics.sql"
        self.assertTrue(path.exists(), f"Query file not found: {path}")

    def test_funnel_metrics_contains_key_queries(self) -> None:
        path = ROOT / "ops" / "queries" / "funnel_metrics.sql"
        content = path.read_text()
        self.assertIn("recommendation_runs", content)
        self.assertIn("checkout_preparations", content)
        self.assertIn("feedback_events", content)
        self.assertIn("conversation_turns", content)
        self.assertIn("tool_traces", content)
        self.assertIn("mode_preference", content)
        self.assertIn("resolved_mode", content)

    def test_funnel_metrics_has_daily_summary(self) -> None:
        path = ROOT / "ops" / "queries" / "funnel_metrics.sql"
        content = path.read_text()
        self.assertIn("Daily Funnel Summary", content)

    def test_funnel_metrics_has_guardrail_query(self) -> None:
        path = ROOT / "ops" / "queries" / "funnel_metrics.sql"
        content = path.read_text()
        self.assertIn("Guardrail Block Events", content)
        self.assertIn("policy_guardrail.check_action", content)

    def test_funnel_metrics_has_substitution_query(self) -> None:
        path = ROOT / "ops" / "queries" / "funnel_metrics.sql"
        content = path.read_text()
        self.assertIn("Substitution Acceptance Rate", content)


if __name__ == "__main__":
    unittest.main()
