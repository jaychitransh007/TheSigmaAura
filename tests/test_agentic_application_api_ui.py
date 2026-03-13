import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient
from fastapi import APIRouter


ROOT = Path(__file__).resolve().parents[1]
for p in (
    ROOT,
    ROOT / "modules" / "user" / "src",
    ROOT / "modules" / "agentic_application" / "src",
    ROOT / "modules" / "catalog" / "src",
    ROOT / "modules" / "catalog_retrieval" / "src",
    ROOT / "modules" / "platform_core" / "src",
    ROOT / "modules" / "user_profiler" / "src",
    ROOT / "modules" / "onboarding" / "src",
):
    sp = str(p)
    if sp not in sys.path:
        sys.path.insert(0, sp)


from agentic_application.api import create_app


class AgenticApplicationApiUiTests(unittest.TestCase):
    def _patched_app(self, analysis_status: str = "completed"):
        load_cfg = patch("agentic_application.api.load_config")
        sb_client = patch("agentic_application.api.SupabaseRestClient")
        repo_cls = patch("agentic_application.api.ConversationRepository")
        orch_cls = patch("agentic_application.api.AgenticOrchestrator")
        onboarding_gateway_cls = patch("agentic_application.api.ApplicationOnboardingGateway")

        mocked = [
            load_cfg.start(),
            sb_client.start(),
            repo_cls.start(),
            orch_cls.start(),
            onboarding_gateway_cls.start(),
        ]
        self.addCleanup(load_cfg.stop)
        self.addCleanup(sb_client.stop)
        self.addCleanup(repo_cls.stop)
        self.addCleanup(orch_cls.stop)
        self.addCleanup(onboarding_gateway_cls.stop)

        mocked[0].return_value = Mock(
            supabase_rest_url="http://127.0.0.1:55321/rest/v1",
            supabase_service_role_key="x",
            request_timeout_seconds=5,
            catalog_csv_path="data/catalog/enriched_catalog.csv",
            retrieval_match_count=12,
        )
        mocked[1].return_value = Mock()
        mocked[2].return_value = Mock()
        onboarding_gateway = Mock()
        onboarding_gateway.create_router.return_value = APIRouter()
        onboarding_gateway.render_onboarding_html.return_value = "<html>Onboarding</html>"
        onboarding_gateway.render_processing_html.return_value = "<html>Profile processing in progress.</html>"
        onboarding_gateway.get_onboarding_status.return_value = {"onboarding_complete": True}
        onboarding_gateway.get_analysis_status.return_value = {
            "status": analysis_status,
            "profile": {},
            "attributes": {},
            "derived_interpretations": {},
        }
        mocked[4].return_value = onboarding_gateway
        return create_app(), mocked[3].return_value

    def test_completed_user_gets_minimal_conversation_ui(self) -> None:
        app, _ = self._patched_app("completed")
        client = TestClient(app)
        resp = client.get("/?user=user_ready")
        self.assertEqual(200, resp.status_code)
        html = resp.text
        self.assertIn("Sigma Aura", html)
        self.assertIn("Agent Processing Stages", html)
        self.assertIn("Logout", html)
        self.assertNotIn("Strictness", html)
        self.assertNotIn("Hard Filter Profile", html)
        self.assertNotIn("Rewards", html)
        self.assertNotIn("Image Upload", html)

    def test_pending_analysis_user_still_gets_processing_screen(self) -> None:
        app, _ = self._patched_app("running")
        client = TestClient(app)
        resp = client.get("/?user=user_processing")
        self.assertEqual(200, resp.status_code)
        self.assertIn("Profile processing in progress.", resp.text)

    def test_turn_endpoint_uses_minimal_payload(self) -> None:
        app, orchestrator = self._patched_app("completed")
        orchestrator.process_turn.return_value = {
            "conversation_id": "c1",
            "turn_id": "t1",
            "assistant_message": "I pulled 1 embedding matches.",
            "resolved_context": {"request_summary": "Need office wear", "occasion": "office", "style_goal": ""},
            "filters_applied": {"gender_expression": "feminine", "styling_completeness": "complete"},
            "outfits": [],
            "follow_up_suggestions": [],
            "metadata": {"plan_type": "mixed"},
        }
        client = TestClient(app)
        resp = client.post("/v1/conversations/c1/turns", json={"user_id": "u1", "message": "Need office wear"})
        self.assertEqual(200, resp.status_code)
        payload = resp.json()
        self.assertEqual("t1", payload["turn_id"])
        self.assertEqual([], payload["outfits"])
        self.assertEqual({"plan_type": "mixed"}, payload["metadata"])
        kwargs = orchestrator.process_turn.call_args.kwargs
        self.assertEqual("u1", kwargs["external_user_id"])
        self.assertEqual("Need office wear", kwargs["message"])

    def test_turn_endpoint_preserves_capped_outfit_payload(self) -> None:
        app, orchestrator = self._patched_app("completed")
        orchestrator.process_turn.return_value = {
            "conversation_id": "c1",
            "turn_id": "t1",
            "assistant_message": "Here are 5 outfit recommendations.",
            "resolved_context": {"request_summary": "Need options", "occasion": "", "style_goal": ""},
            "filters_applied": {"gender_expression": "feminine"},
            "outfits": [{"rank": index, "title": f"Outfit {index}", "items": []} for index in range(1, 6)],
            "follow_up_suggestions": ["Show me more options"],
            "metadata": {"plan_type": "mixed", "outfit_count": 5},
        }
        client = TestClient(app)
        resp = client.post("/v1/conversations/c1/turns", json={"user_id": "u1", "message": "Need options"})
        self.assertEqual(200, resp.status_code)
        payload = resp.json()
        self.assertEqual(5, len(payload["outfits"]))
        self.assertEqual(5, payload["metadata"]["outfit_count"])

    def test_admin_catalog_page_renders(self) -> None:
        app, _ = self._patched_app("completed")
        client = TestClient(app)
        resp = client.get("/admin/catalog")
        self.assertEqual(200, resp.status_code)
        self.assertIn("Catalog Admin", resp.text)
        self.assertIn("Run Full Pipeline", resp.text)
        self.assertIn("Generate Embeddings", resp.text)

    def test_catalog_backfill_endpoint_returns_missing_url_counts(self) -> None:
        with patch("agentic_application.api.load_config") as load_cfg, patch(
            "agentic_application.api.SupabaseRestClient"
        ) as sb_client, patch(
            "agentic_application.api.ConversationRepository"
        ) as repo_cls, patch(
            "agentic_application.api.AgenticOrchestrator"
        ) as orch_cls, patch(
            "agentic_application.api.ApplicationOnboardingGateway"
        ) as onboarding_gateway_cls, patch(
            "agentic_application.api.create_catalog_admin_router"
        ) as catalog_router_factory:
            load_cfg.return_value = Mock(
                supabase_rest_url="http://127.0.0.1:55321/rest/v1",
                supabase_service_role_key="x",
                request_timeout_seconds=5,
                catalog_csv_path="data/catalog/enriched_catalog.csv",
                retrieval_match_count=12,
            )
            sb_client.return_value = Mock()
            repo_cls.return_value = Mock()
            orch_cls.return_value = Mock()
            onboarding_gateway = Mock()
            onboarding_gateway.create_router.return_value = APIRouter()
            onboarding_gateway.render_onboarding_html.return_value = "<html>Onboarding</html>"
            onboarding_gateway.render_processing_html.return_value = "<html>Processing</html>"
            onboarding_gateway.get_onboarding_status.return_value = {"onboarding_complete": True}
            onboarding_gateway.get_analysis_status.return_value = {"status": "completed"}
            onboarding_gateway_cls.return_value = onboarding_gateway

            admin_router = APIRouter()

            @admin_router.post("/v1/admin/catalog/items/backfill-urls")
            def backfill_catalog_urls() -> dict:
                return {
                    "input_csv_path": "catalog_enriched",
                    "processed_rows": 10,
                    "saved_rows": 8,
                    "missing_url_rows": 2,
                    "mode": "catalog_enriched_url_backfill",
                }

            catalog_router_factory.return_value = admin_router
            app = create_app()

        client = TestClient(app)
        resp = client.post("/v1/admin/catalog/items/backfill-urls", json={"input_csv_path": "ignored", "max_rows": 5})
        self.assertEqual(200, resp.status_code)
        payload = resp.json()
        self.assertEqual(8, payload["saved_rows"])
        self.assertEqual(2, payload["missing_url_rows"])


if __name__ == "__main__":
    unittest.main()
