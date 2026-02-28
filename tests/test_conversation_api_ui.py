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

from fastapi.testclient import TestClient

from conversation_platform.api import create_app
from conversation_platform.supabase_rest import SupabaseError


class ConversationApiUiTests(unittest.TestCase):
    def test_root_returns_html(self) -> None:
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
            orch_cls.return_value = Mock()

            app = create_app()
            client = TestClient(app)
            resp = client.get("/")
            self.assertEqual(200, resp.status_code)
            self.assertIn("text/html", resp.headers.get("content-type", ""))
            self.assertIn("no-store", resp.headers.get("cache-control", ""))
            self.assertIn("Conversation Stylist", resp.text)
            self.assertIn("Result Mix", resp.text)
            self.assertIn("complete_only", resp.text)
            self.assertIn("complete_plus_combos", resp.text)
            self.assertIn("Buy Now", resp.text)
            self.assertIn("Dislike", resp.text)
            self.assertIn("Like", resp.text)
            self.assertIn("Share", resp.text)
            self.assertIn("buy-row", resp.text)
            self.assertIn("feedback-row", resp.text)
            self.assertIn("UI build: actions-v2", resp.text)
            self.assertIn("No Action: -1", resp.text)

    def test_root_contains_action_layout_and_reward_contract(self) -> None:
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
            orch_cls.return_value = Mock()

            app = create_app()
            client = TestClient(app)
            resp = client.get("/")
            self.assertEqual(200, resp.status_code)

            html = resp.text
            self.assertIn("buy-row", html)
            self.assertIn("feedback-row", html)
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

    def test_favicon_route_exists(self) -> None:
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
            orch_cls.return_value = Mock()

            app = create_app()
            client = TestClient(app)
            resp = client.get("/favicon.ico")
            self.assertEqual(204, resp.status_code)

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
