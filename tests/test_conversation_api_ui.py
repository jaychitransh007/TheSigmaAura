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

from fastapi.testclient import TestClient

from conversation_platform.api import create_app
from conversation_platform.supabase_rest import SupabaseError


class ConversationApiUiTests(unittest.TestCase):
    def test_root_returns_html(self) -> None:
        with patch("conversation_platform.api.load_config") as load_cfg, \
            patch("conversation_platform.api.SupabaseRestClient") as sb_client, \
            patch("conversation_platform.api.ConversationRepository") as repo_cls, \
            patch("conversation_platform.api.ConversationOrchestrator") as orch_cls, \
            patch("conversation_platform.api.UserAnalysisService") as analysis_cls:
            load_cfg.return_value = Mock(
                supabase_rest_url="http://127.0.0.1:55321/rest/v1",
                supabase_service_role_key="x",
                request_timeout_seconds=5,
                catalog_csv_path="data/output/enriched.csv",
            )
            sb_client.return_value = Mock()
            repo_cls.return_value = Mock()
            orch_cls.return_value = Mock()
            analysis_cls.return_value = Mock()

            app = create_app()
            client = TestClient(app)
            resp = client.get("/")
            self.assertEqual(200, resp.status_code)
            self.assertIn("text/html", resp.headers.get("content-type", ""))
            self.assertIn("no-store", resp.headers.get("cache-control", ""))
            self.assertIn("Onboard before you enter the conversation studio.", resp.text)
            self.assertIn("123456", resp.text)
            self.assertIn("2:3 frame", resp.text)
            self.assertIn("Mobile Number", resp.text)
            self.assertIn("Step 1 of 11", resp.text)
            self.assertIn("Select the outfits that feel like you.", resp.text)
            self.assertIn("Continue to Profile Processing", resp.text)

    def test_root_with_completed_user_contains_action_layout_and_reward_contract(self) -> None:
        with patch("conversation_platform.api.load_config") as load_cfg, \
            patch("conversation_platform.api.SupabaseRestClient") as sb_client, \
            patch("conversation_platform.api.ConversationRepository") as repo_cls, \
            patch("conversation_platform.api.ConversationOrchestrator") as orch_cls, \
            patch("conversation_platform.api.UserAnalysisService") as analysis_cls:
            load_cfg.return_value = Mock(
                supabase_rest_url="http://127.0.0.1:55321/rest/v1",
                supabase_service_role_key="x",
                request_timeout_seconds=5,
                catalog_csv_path="data/output/enriched.csv",
            )
            sb_client.return_value = Mock()
            repo_cls.return_value = Mock()
            orch_cls.return_value = Mock()
            onboarding_profile = {
                "user_id": "user_ready",
                "mobile": "+919999999999",
                "profile_complete": True,
                "onboarding_complete": True,
            }
            sb_client.return_value.select_one.return_value = onboarding_profile
            sb_client.return_value.select_many.return_value = [
                {"category": "full_body"},
                {"category": "headshot"},
                {"category": "veins"},
            ]
            analysis_service = Mock()
            analysis_service.get_analysis_status.return_value = {
                "user_id": "user_ready",
                "status": "completed",
                "analysis_run_id": "run_1",
                "error_message": "",
                "agent_outputs": {},
                "attributes": {},
                "grouped_attributes": {},
            }
            analysis_cls.return_value = analysis_service

            app = create_app()
            client = TestClient(app)
            resp = client.get("/?user=user_ready")
            self.assertEqual(200, resp.status_code)

            html = resp.text
            self.assertIn("Conversation Stylist", html)
            self.assertIn("buy-row", html)
            self.assertIn("feedback-row", html)
            self.assertIn("Logout", html)
            self.assertIn("Buy Now: +20", html)
            self.assertIn("Share: +10", html)
            self.assertIn("Like: +2", html)
            self.assertIn("No Action: -1", html)
            self.assertIn("Dislike: -5", html)
            self.assertIn("buyRow.appendChild(buyBtn);", html)
            self.assertIn("feedbackRow.appendChild(dislikeBtn);", html)
            self.assertIn("feedbackRow.appendChild(likeBtn);", html)
            self.assertIn("feedbackRow.appendChild(shareBtn);", html)
            self.assertLess(
                html.find("feedbackRow.appendChild(dislikeBtn);"),
                html.find("feedbackRow.appendChild(likeBtn);"),
            )
            self.assertLess(
                html.find("feedbackRow.appendChild(likeBtn);"),
                html.find("feedbackRow.appendChild(shareBtn);"),
            )
            self.assertIn('value="user_ready"', html)

    def test_root_with_pending_analysis_shows_processing_screen(self) -> None:
        with patch("conversation_platform.api.load_config") as load_cfg, \
            patch("conversation_platform.api.SupabaseRestClient") as sb_client, \
            patch("conversation_platform.api.ConversationRepository") as repo_cls, \
            patch("conversation_platform.api.ConversationOrchestrator") as orch_cls, \
            patch("conversation_platform.api.UserAnalysisService") as analysis_cls:
            load_cfg.return_value = Mock(
                supabase_rest_url="http://127.0.0.1:55321/rest/v1",
                supabase_service_role_key="x",
                request_timeout_seconds=5,
                catalog_csv_path="data/output/enriched.csv",
            )
            sb_client.return_value = Mock()
            repo_cls.return_value = Mock()
            orch_cls.return_value = Mock()
            sb_client.return_value.select_one.return_value = {
                "user_id": "user_processing",
                "mobile": "+919999999999",
                "profile_complete": True,
                "onboarding_complete": True,
            }
            sb_client.return_value.select_many.return_value = [
                {"category": "full_body"},
                {"category": "headshot"},
                {"category": "veins"},
            ]
            analysis_service = Mock()
            analysis_service.get_analysis_status.return_value = {
                "user_id": "user_processing",
                "status": "running",
                "analysis_run_id": "run_2",
                "error_message": "",
                "agent_outputs": {},
                "attributes": {},
                "grouped_attributes": {},
            }
            analysis_cls.return_value = analysis_service

            app = create_app()
            client = TestClient(app)
            resp = client.get("/?user=user_processing")
            self.assertEqual(200, resp.status_code)
            self.assertIn("Profile processing in progress.", resp.text)
            self.assertIn("Body type analysis", resp.text)
            self.assertIn("Open Conversation Platform", resp.text)

    def test_favicon_route_exists(self) -> None:
        with patch("conversation_platform.api.load_config") as load_cfg, \
            patch("conversation_platform.api.SupabaseRestClient") as sb_client, \
            patch("conversation_platform.api.ConversationRepository") as repo_cls, \
            patch("conversation_platform.api.ConversationOrchestrator") as orch_cls, \
            patch("conversation_platform.api.UserAnalysisService") as analysis_cls:
            load_cfg.return_value = Mock(
                supabase_rest_url="http://127.0.0.1:55321/rest/v1",
                supabase_service_role_key="x",
                request_timeout_seconds=5,
                catalog_csv_path="data/output/enriched.csv",
            )
            sb_client.return_value = Mock()
            repo_cls.return_value = Mock()
            orch_cls.return_value = Mock()
            analysis_cls.return_value = Mock()

            app = create_app()
            client = TestClient(app)
            resp = client.get("/favicon.ico")
            self.assertEqual(204, resp.status_code)

    def test_normalize_image_endpoint_returns_jpeg_payload(self) -> None:
        with patch("conversation_platform.api.load_config") as load_cfg, \
            patch("conversation_platform.api.SupabaseRestClient") as sb_client, \
            patch("conversation_platform.api.ConversationRepository") as repo_cls, \
            patch("conversation_platform.api.ConversationOrchestrator") as orch_cls, \
            patch("conversation_platform.api.UserAnalysisService") as analysis_cls, \
            patch("onboarding.service.subprocess.run") as run_mock:
            load_cfg.return_value = Mock(
                supabase_rest_url="http://127.0.0.1:55321/rest/v1",
                supabase_service_role_key="x",
                request_timeout_seconds=5,
                catalog_csv_path="data/output/enriched.csv",
            )
            sb_client.return_value = Mock()
            repo_cls.return_value = Mock()
            orch_cls.return_value = Mock()
            analysis_cls.return_value = Mock()

            def fake_run(cmd, check, capture_output, text):
                Path(cmd[-1]).write_bytes(b"jpeg-preview")
                return Mock()

            run_mock.side_effect = fake_run

            app = create_app()
            client = TestClient(app)
            resp = client.post(
                "/v1/onboarding/images/normalize",
                files={"file": ("portrait.heic", b"heic-bytes", "image/heic")},
            )
            self.assertEqual(200, resp.status_code)
            self.assertEqual("image/jpeg", resp.headers.get("content-type"))
            self.assertEqual("portrait.jpg", resp.headers.get("x-normalized-filename"))
            self.assertEqual(b"jpeg-preview", resp.content)

    def test_analysis_status_endpoint_returns_payload(self) -> None:
        with patch("conversation_platform.api.load_config") as load_cfg, \
            patch("conversation_platform.api.SupabaseRestClient") as sb_client, \
            patch("conversation_platform.api.ConversationRepository") as repo_cls, \
            patch("conversation_platform.api.ConversationOrchestrator") as orch_cls, \
            patch("conversation_platform.api.UserAnalysisService") as analysis_cls:
            load_cfg.return_value = Mock(
                supabase_rest_url="http://127.0.0.1:55321/rest/v1",
                supabase_service_role_key="x",
                request_timeout_seconds=5,
                catalog_csv_path="data/output/enriched.csv",
            )
            sb_client.return_value = Mock()
            repo_cls.return_value = Mock()
            orch_cls.return_value = Mock()
            analysis_service = Mock()
            analysis_service.get_analysis_status.return_value = {
                "user_id": "user_ana",
                "analysis_run_id": "run_ana",
                "status": "completed",
                "error_message": "",
                "agent_outputs": {"body_type_analysis": {"TorsoToLegRatio": {"value": "Balanced", "confidence": 0.8, "evidence_note": "Midpoint sits near the waist.", "source_agent": "body_type_analysis"}}},
                "attributes": {"TorsoToLegRatio": {"value": "Balanced", "confidence": 0.8, "evidence_note": "Midpoint sits near the waist.", "source_agent": "body_type_analysis"}},
                "grouped_attributes": {"body_type_analysis": {"TorsoToLegRatio": {"value": "Balanced", "confidence": 0.8, "evidence_note": "Midpoint sits near the waist.", "source_agent": "body_type_analysis"}}},
                "derived_interpretations": {
                    "HeightCategory": {"value": "Average", "confidence": 1.0, "evidence_note": "Derived from entered height.", "source_agent": "deterministic_interpreter"},
                    "WaistSizeBand": {"value": "Medium", "confidence": 1.0, "evidence_note": "Derived from entered waist.", "source_agent": "deterministic_interpreter"},
                },
            }
            analysis_cls.return_value = analysis_service

            app = create_app()
            client = TestClient(app)
            resp = client.get("/v1/onboarding/analysis/user_ana")
            self.assertEqual(200, resp.status_code)
            payload = resp.json()
            self.assertEqual("completed", payload["status"])
            self.assertEqual("Balanced", payload["attributes"]["TorsoToLegRatio"]["value"])
            self.assertEqual("Average", payload["derived_interpretations"]["HeightCategory"]["value"])
            self.assertEqual("Medium", payload["derived_interpretations"]["WaistSizeBand"]["value"])

    def test_style_session_endpoint_returns_eight_archetypes(self) -> None:
        with patch("conversation_platform.api.load_config") as load_cfg, \
            patch("conversation_platform.api.SupabaseRestClient") as sb_client, \
            patch("conversation_platform.api.ConversationRepository") as repo_cls, \
            patch("conversation_platform.api.ConversationOrchestrator") as orch_cls, \
            patch("conversation_platform.api.UserAnalysisService") as analysis_cls:
            load_cfg.return_value = Mock(
                supabase_rest_url="http://127.0.0.1:55321/rest/v1",
                supabase_service_role_key="x",
                request_timeout_seconds=5,
                catalog_csv_path="data/output/enriched.csv",
            )
            supabase = Mock()
            supabase.select_one.return_value = {
                "user_id": "user_style",
                "gender": "female",
            }
            supabase.select_many.return_value = []
            sb_client.return_value = supabase
            repo_cls.return_value = Mock()
            orch_cls.return_value = Mock()
            analysis_cls.return_value = Mock()

            app = create_app()
            client = TestClient(app)
            resp = client.get("/v1/onboarding/style/session/user_style")
            self.assertEqual(200, resp.status_code)
            payload = resp.json()
            self.assertEqual("female", payload["gender"])
            self.assertEqual(3, payload["minSelections"])
            self.assertEqual(5, payload["maxSelections"])
            self.assertEqual(8, len(payload["layer1"]))
            self.assertEqual(
                ["classic", "dramatic", "romantic", "natural", "minimalist", "creative", "sporty", "edgy"],
                [image["primaryArchetype"] for image in payload["layer1"]],
            )

    def test_analysis_rerun_endpoint_starts_new_run(self) -> None:
        class InlineThread:
            def __init__(self, target=None, daemon=None):
                self._target = target

            def start(self):
                if self._target is not None:
                    self._target()

        with patch("conversation_platform.api.load_config") as load_cfg, \
            patch("conversation_platform.api.SupabaseRestClient") as sb_client, \
            patch("conversation_platform.api.ConversationRepository") as repo_cls, \
            patch("conversation_platform.api.ConversationOrchestrator") as orch_cls, \
            patch("conversation_platform.api.Thread", InlineThread), \
            patch("conversation_platform.api.UserAnalysisService") as analysis_cls:
            load_cfg.return_value = Mock(
                supabase_rest_url="http://127.0.0.1:55321/rest/v1",
                supabase_service_role_key="x",
                request_timeout_seconds=5,
                catalog_csv_path="data/output/enriched.csv",
            )
            sb_client.return_value = Mock()
            repo_cls.return_value = Mock()
            orch_cls.return_value = Mock()
            sb_client.return_value.select_one.return_value = {
                "user_id": "user_rerun",
                "mobile": "+919999999999",
                "profile_complete": True,
                "onboarding_complete": True,
            }
            sb_client.return_value.select_many.return_value = [
                {"category": "full_body"},
                {"category": "headshot"},
                {"category": "veins"},
            ]
            analysis_service = Mock()
            analysis_service.force_analysis_restart.return_value = {
                "id": "run_rerun",
                "status": "pending",
            }
            analysis_service.run_analysis.return_value = {
                "user_id": "user_rerun",
                "status": "completed",
            }
            analysis_cls.return_value = analysis_service

            app = create_app()
            client = TestClient(app)
            resp = client.post("/v1/onboarding/analysis/rerun", json={"user_id": "user_rerun"})
            self.assertEqual(200, resp.status_code)
            payload = resp.json()
            self.assertEqual("run_rerun", payload["analysis_run_id"])
            self.assertEqual("Analysis re-run started", payload["message"])
            analysis_service.force_analysis_restart.assert_called_once_with("user_rerun")

    def test_analysis_agent_rerun_endpoint_starts_selected_agent_run(self) -> None:
        class InlineThread:
            def __init__(self, target=None, daemon=None):
                self._target = target

            def start(self):
                if self._target is not None:
                    self._target()

        with patch("conversation_platform.api.load_config") as load_cfg, \
            patch("conversation_platform.api.SupabaseRestClient") as sb_client, \
            patch("conversation_platform.api.ConversationRepository") as repo_cls, \
            patch("conversation_platform.api.ConversationOrchestrator") as orch_cls, \
            patch("conversation_platform.api.Thread", InlineThread), \
            patch("conversation_platform.api.UserAnalysisService") as analysis_cls:
            load_cfg.return_value = Mock(
                supabase_rest_url="http://127.0.0.1:55321/rest/v1",
                supabase_service_role_key="x",
                request_timeout_seconds=5,
                catalog_csv_path="data/output/enriched.csv",
            )
            sb_client.return_value = Mock()
            repo_cls.return_value = Mock()
            orch_cls.return_value = Mock()
            sb_client.return_value.select_one.return_value = {
                "user_id": "user_rerun_agent",
                "mobile": "+919999999999",
                "profile_complete": True,
                "onboarding_complete": True,
            }
            sb_client.return_value.select_many.return_value = [
                {"category": "full_body"},
                {"category": "headshot"},
                {"category": "veins"},
            ]
            analysis_service = Mock()
            analysis_service.force_agent_restart.return_value = {
                "id": "run_agent_rerun",
                "status": "pending",
            }
            analysis_service.run_agent_rerun.return_value = {
                "user_id": "user_rerun_agent",
                "status": "completed",
            }
            analysis_cls.return_value = analysis_service

            app = create_app()
            client = TestClient(app)
            resp = client.post(
                "/v1/onboarding/analysis/rerun-agent",
                json={"user_id": "user_rerun_agent", "agent_name": "other_details_analysis"},
            )
            self.assertEqual(200, resp.status_code)
            payload = resp.json()
            self.assertEqual("run_agent_rerun", payload["analysis_run_id"])
            self.assertEqual("other_details_analysis re-run started", payload["message"])
            analysis_service.force_agent_restart.assert_called_once_with("user_rerun_agent", "other_details_analysis")
            analysis_service.run_agent_rerun.assert_called_once_with(
                "user_rerun_agent",
                "other_details_analysis",
                run_id="run_agent_rerun",
            )

    def test_turn_job_start_and_status(self) -> None:
        class InlineThread:
            def __init__(self, target=None, daemon=None):
                self._target = target

            def start(self):
                if self._target is not None:
                    self._target()

        with patch("conversation_platform.api.load_config") as load_cfg, \
            patch("conversation_platform.api.SupabaseRestClient") as sb_client, \
            patch("conversation_platform.api.ConversationRepository") as repo_cls, \
            patch("conversation_platform.api.Thread", InlineThread), \
            patch("conversation_platform.api.ConversationOrchestrator") as orch_cls:
            load_cfg.return_value = Mock(
                supabase_rest_url="http://127.0.0.1:55321/rest/v1",
                supabase_service_role_key="x",
                request_timeout_seconds=5,
                catalog_csv_path="data/output/enriched.csv",
            )
            sb_client.return_value = Mock()
            repo_cls.return_value = Mock()
            orchestrator = Mock()
            orchestrator.process_turn.return_value = {
                "conversation_id": "c1",
                "turn_id": "t1",
                "assistant_message": "ok",
                "resolved_context": {
                    "occasion": "work_mode",
                    "archetype": "classic",
                    "gender": "female",
                    "age": "25_30",
                },
                "profile_snapshot_id": "ps1",
                "recommendation_run_id": "r1",
                "recommendations": [],
                "needs_clarification": False,
                "clarifying_question": "",
            }
            orch_cls.return_value = orchestrator

            app = create_app()
            client = TestClient(app)
            start_resp = client.post(
                "/v1/conversations/c1/turns/start",
                json={
                    "user_id": "user_1",
                    "message": "Need work look",
                    "image_refs": [],
                    "strictness": "balanced",
                    "hard_filter_profile": "rl_ready_minimal",
                    "max_results": 5,
                },
            )
            self.assertEqual(200, start_resp.status_code)
            job_id = start_resp.json()["job_id"]

            status_resp = client.get(f"/v1/conversations/c1/turns/{job_id}/status")
            self.assertEqual(200, status_resp.status_code)
            payload = status_resp.json()
            self.assertEqual("completed", payload["status"])
            self.assertTrue(payload["stages"])
            self.assertEqual("ok", payload["result"]["assistant_message"])

    def test_turn_job_start_and_status_failed(self) -> None:
        class InlineThread:
            def __init__(self, target=None, daemon=None):
                self._target = target

            def start(self):
                if self._target is not None:
                    self._target()

        with patch("conversation_platform.api.load_config") as load_cfg, \
            patch("conversation_platform.api.SupabaseRestClient") as sb_client, \
            patch("conversation_platform.api.ConversationRepository") as repo_cls, \
            patch("conversation_platform.api.Thread", InlineThread), \
            patch("conversation_platform.api.ConversationOrchestrator") as orch_cls:
            load_cfg.return_value = Mock(
                supabase_rest_url="http://127.0.0.1:55321/rest/v1",
                supabase_service_role_key="x",
                request_timeout_seconds=5,
                catalog_csv_path="data/output/enriched.csv",
            )
            sb_client.return_value = Mock()
            repo_cls.return_value = Mock()
            orchestrator = Mock()
            orchestrator.process_turn.side_effect = ValueError("bad turn")
            orch_cls.return_value = orchestrator

            app = create_app()
            client = TestClient(app)
            start_resp = client.post(
                "/v1/conversations/c1/turns/start",
                json={
                    "user_id": "user_1",
                    "message": "Need work look",
                    "image_refs": [],
                    "strictness": "balanced",
                    "hard_filter_profile": "rl_ready_minimal",
                    "max_results": 5,
                },
            )
            self.assertEqual(200, start_resp.status_code)
            job_id = start_resp.json()["job_id"]

            status_resp = client.get(f"/v1/conversations/c1/turns/{job_id}/status")
            self.assertEqual(200, status_resp.status_code)
            payload = status_resp.json()
            self.assertEqual("failed", payload["status"])
            self.assertIn("bad turn", payload["error"])

    def test_feedback_endpoint_success(self) -> None:
        with patch("conversation_platform.api.load_config") as load_cfg, \
            patch("conversation_platform.api.SupabaseRestClient") as sb_client, \
            patch("conversation_platform.api.ConversationRepository") as repo_cls, \
            patch("conversation_platform.api.ConversationOrchestrator") as orch_cls:
            load_cfg.return_value = Mock(
                supabase_rest_url="http://127.0.0.1:55321/rest/v1",
                supabase_service_role_key="x",
                request_timeout_seconds=5,
                catalog_csv_path="data/output/enriched.csv",
            )
            sb_client.return_value = Mock()
            repo_cls.return_value = Mock()
            orchestrator = Mock()
            orchestrator.record_feedback.return_value = {"event_id": "evt_1", "reward_value": 10}
            orch_cls.return_value = orchestrator

            app = create_app()
            client = TestClient(app)
            resp = client.post(
                "/v1/feedback",
                json={
                    "user_id": "user_1",
                    "conversation_id": "c1",
                    "recommendation_run_id": "r1",
                    "garment_id": "g1",
                    "event_type": "share",
                    "notes": "clicked share",
                },
            )
            self.assertEqual(200, resp.status_code)
            payload = resp.json()
            self.assertEqual("evt_1", payload["event_id"])
            self.assertEqual(10, payload["reward_value"])

    def test_feedback_endpoint_dislike_success(self) -> None:
        with patch("conversation_platform.api.load_config") as load_cfg, \
            patch("conversation_platform.api.SupabaseRestClient") as sb_client, \
            patch("conversation_platform.api.ConversationRepository") as repo_cls, \
            patch("conversation_platform.api.ConversationOrchestrator") as orch_cls:
            load_cfg.return_value = Mock(
                supabase_rest_url="http://127.0.0.1:55321/rest/v1",
                supabase_service_role_key="x",
                request_timeout_seconds=5,
                catalog_csv_path="data/output/enriched.csv",
            )
            sb_client.return_value = Mock()
            repo_cls.return_value = Mock()
            orchestrator = Mock()
            orchestrator.record_feedback.return_value = {"event_id": "evt_2", "reward_value": -5}
            orch_cls.return_value = orchestrator

            app = create_app()
            client = TestClient(app)
            resp = client.post(
                "/v1/feedback",
                json={
                    "user_id": "user_1",
                    "conversation_id": "c1",
                    "recommendation_run_id": "r1",
                    "garment_id": "g1",
                    "event_type": "dislike",
                    "notes": "not my style",
                },
            )
            self.assertEqual(200, resp.status_code)
            payload = resp.json()
            self.assertEqual("evt_2", payload["event_id"])
            self.assertEqual(-5, payload["reward_value"])

    def test_feedback_endpoint_returns_migration_hint_for_old_event_type_constraint(self) -> None:
        with patch("conversation_platform.api.load_config") as load_cfg, \
            patch("conversation_platform.api.SupabaseRestClient") as sb_client, \
            patch("conversation_platform.api.ConversationRepository") as repo_cls, \
            patch("conversation_platform.api.ConversationOrchestrator") as orch_cls:
            load_cfg.return_value = Mock(
                supabase_rest_url="http://127.0.0.1:55321/rest/v1",
                supabase_service_role_key="x",
                request_timeout_seconds=5,
                catalog_csv_path="data/output/enriched.csv",
            )
            sb_client.return_value = Mock()
            repo_cls.return_value = Mock()
            orchestrator = Mock()
            orchestrator.record_feedback.side_effect = SupabaseError(
                (
                    'Supabase request failed (400) POST /feedback_events: '
                    '{"message":"new row for relation \\"feedback_events\\" violates check constraint '
                    '\\"feedback_events_event_type_check\\""}'
                )
            )
            orch_cls.return_value = orchestrator

            app = create_app()
            client = TestClient(app)
            resp = client.post(
                "/v1/feedback",
                json={
                    "user_id": "user_1",
                    "conversation_id": "c1",
                    "recommendation_run_id": "r1",
                    "garment_id": "g1",
                    "event_type": "dislike",
                    "notes": "not my style",
                },
            )
            self.assertEqual(400, resp.status_code)
            self.assertIn("Apply latest Supabase migrations", resp.json().get("detail", ""))


if __name__ == "__main__":
    unittest.main()
