import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
for p in (
    ROOT,
    ROOT / "modules" / "user" / "src",
    ROOT / "modules" / "agentic_application" / "src",
    ROOT / "modules" / "catalog" / "src",
    ROOT / "modules" / "catalog_retrieval" / "src",
    ROOT / "modules" / "user_profiler" / "src",
    ROOT / "modules" / "conversation_platform" / "src",
    ROOT / "modules" / "onboarding" / "src",
):
    sp = str(p)
    if sp not in sys.path:
        sys.path.insert(0, sp)


from conversation_platform.api import create_app


class ConversationApiUiTests(unittest.TestCase):
    def _patched_app(self, analysis_status: str = "completed"):
        load_cfg = patch("conversation_platform.api.load_config")
        sb_client = patch("conversation_platform.api.SupabaseRestClient")
        repo_cls = patch("conversation_platform.api.ConversationRepository")
        orch_cls = patch("conversation_platform.api.ConversationOrchestrator")
        analysis_cls = patch("conversation_platform.api.UserAnalysisService")
        onboarding_repo_cls = patch("conversation_platform.api.OnboardingRepository")
        onboarding_service_cls = patch("conversation_platform.api.OnboardingService")

        mocked = [
            load_cfg.start(),
            sb_client.start(),
            repo_cls.start(),
            orch_cls.start(),
            analysis_cls.start(),
            onboarding_repo_cls.start(),
            onboarding_service_cls.start(),
        ]
        self.addCleanup(load_cfg.stop)
        self.addCleanup(sb_client.stop)
        self.addCleanup(repo_cls.stop)
        self.addCleanup(orch_cls.stop)
        self.addCleanup(analysis_cls.stop)
        self.addCleanup(onboarding_repo_cls.stop)
        self.addCleanup(onboarding_service_cls.stop)

        mocked[0].return_value = Mock(
            supabase_rest_url="http://127.0.0.1:55321/rest/v1",
            supabase_service_role_key="x",
            request_timeout_seconds=5,
            catalog_csv_path="data/catalog/enriched_catalog.csv",
            retrieval_match_count=12,
        )
        mocked[1].return_value = Mock()
        mocked[2].return_value = Mock()
        mocked[5].return_value = Mock()
        onboarding_service = Mock()
        onboarding_service.get_status.return_value = {"onboarding_complete": True}
        mocked[6].return_value = onboarding_service
        analysis_service = Mock()
        analysis_service.get_analysis_status.return_value = {
            "status": analysis_status,
            "profile": {},
            "attributes": {},
            "derived_interpretations": {},
        }
        mocked[4].return_value = analysis_service
        return create_app(), mocked[3].return_value

    def test_completed_user_gets_minimal_conversation_ui(self) -> None:
        app, _ = self._patched_app("completed")
        client = TestClient(app)
        resp = client.get("/?user=user_ready")
        self.assertEqual(200, resp.status_code)
        html = resp.text
        self.assertIn("Conversation Platform", html)
        self.assertIn("Retrieval Query", html)
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
            "retrieval_query_document": "USER_NEED:",
            "filters_applied": {"gender_expression": "feminine", "styling_completeness": "complete"},
            "recommendations": [],
        }
        client = TestClient(app)
        resp = client.post("/v1/conversations/c1/turns", json={"user_id": "u1", "message": "Need office wear"})
        self.assertEqual(200, resp.status_code)
        payload = resp.json()
        self.assertEqual("t1", payload["turn_id"])
        self.assertEqual("USER_NEED:", payload["retrieval_query_document"])
        kwargs = orchestrator.process_turn.call_args.kwargs
        self.assertEqual("u1", kwargs["external_user_id"])
        self.assertEqual("Need office wear", kwargs["message"])

    def test_admin_catalog_page_renders(self) -> None:
        app, _ = self._patched_app("completed")
        client = TestClient(app)
        resp = client.get("/admin/catalog")
        self.assertEqual(200, resp.status_code)
        self.assertIn("Catalog Admin", resp.text)
        self.assertIn("Run Full Pipeline", resp.text)
        self.assertIn("Generate Embeddings", resp.text)


if __name__ == "__main__":
    unittest.main()
