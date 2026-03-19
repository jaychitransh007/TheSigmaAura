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
    ROOT / "modules" / "platform_core" / "src",
    ROOT / "modules" / "user_profiler" / "src",
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
        onboarding_gateway_cls = patch("agentic_application.api.ApplicationUserGateway")
        dependency_reporting_cls = patch("agentic_application.api.DependencyReportingService")

        mocked = [
            load_cfg.start(),
            sb_client.start(),
            repo_cls.start(),
            orch_cls.start(),
            onboarding_gateway_cls.start(),
            dependency_reporting_cls.start(),
        ]
        self.addCleanup(load_cfg.stop)
        self.addCleanup(sb_client.stop)
        self.addCleanup(repo_cls.stop)
        self.addCleanup(orch_cls.stop)
        self.addCleanup(onboarding_gateway_cls.stop)
        self.addCleanup(dependency_reporting_cls.stop)

        mocked[0].return_value = Mock(
            supabase_rest_url="http://127.0.0.1:55321/rest/v1",
            supabase_service_role_key="x",
            request_timeout_seconds=5,
            catalog_csv_path="data/catalog/enriched_catalog.csv",
            retrieval_match_count=12,
        )
        mocked[1].return_value = Mock()
        mocked[2].return_value = Mock()
        repo = mocked[2].return_value
        onboarding_gateway = Mock()
        onboarding_gateway.create_router.return_value = APIRouter()
        onboarding_gateway.render_onboarding_html.return_value = "<html>Onboarding</html>"
        onboarding_gateway.render_processing_html.return_value = "<html>Profile processing in progress.</html>"
        onboarding_gateway.get_onboarding_status.return_value = {"onboarding_complete": True}
        onboarding_gateway.get_effective_seasonal_groups.return_value = None
        onboarding_gateway.resolve_user_id_by_mobile.return_value = None
        onboarding_gateway.get_analysis_status.return_value = {
            "status": analysis_status,
            "profile": {},
            "attributes": {},
            "derived_interpretations": {},
        }
        mocked[4].return_value = onboarding_gateway
        mocked[5].return_value.build_report.return_value = {"overview": {"onboarded_user_count": 0}}
        return create_app(), mocked[3].return_value, repo, onboarding_gateway, mocked[5].return_value

    def test_completed_user_gets_minimal_conversation_ui(self) -> None:
        app, _, _, _, _ = self._patched_app("completed")
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
        app, _, _, _, _ = self._patched_app("running")
        client = TestClient(app)
        resp = client.get("/?user=user_processing")
        self.assertEqual(200, resp.status_code)
        self.assertIn("Profile processing in progress.", resp.text)

    def test_turn_endpoint_uses_minimal_payload(self) -> None:
        app, orchestrator, _, _, _ = self._patched_app("completed")
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
        self.assertEqual("web", kwargs["channel"])

    def test_resolve_conversation_endpoint_reuses_active_conversation(self) -> None:
        app, orchestrator, _, _, _ = self._patched_app("completed")
        orchestrator.resolve_active_conversation.return_value = {
            "conversation_id": "c-shared",
            "user_id": "user-1",
            "status": "active",
            "created_at": "2026-03-19T00:00:00+00:00",
            "reused_existing": True,
        }
        client = TestClient(app)
        resp = client.post("/v1/conversations/resolve", json={"user_id": "user-1"})
        self.assertEqual(200, resp.status_code)
        payload = resp.json()
        self.assertEqual("c-shared", payload["conversation_id"])
        self.assertTrue(payload["reused_existing"])
        orchestrator.resolve_active_conversation.assert_called_once_with(external_user_id="user-1")

    def test_resolve_conversation_endpoint_can_create_when_missing(self) -> None:
        app, orchestrator, _, _, _ = self._patched_app("completed")
        orchestrator.resolve_active_conversation.return_value = {
            "conversation_id": "c-new",
            "user_id": "user-1",
            "status": "active",
            "created_at": "2026-03-19T00:00:00+00:00",
            "reused_existing": False,
        }
        client = TestClient(app)
        resp = client.post("/v1/conversations/resolve", json={"user_id": "user-1"})
        self.assertEqual(200, resp.status_code)
        self.assertFalse(resp.json()["reused_existing"])

    def test_turn_endpoint_preserves_capped_outfit_payload(self) -> None:
        app, orchestrator, _, _, _ = self._patched_app("completed")
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

    def test_whatsapp_inbound_endpoint_creates_conversation_and_routes_turn(self) -> None:
        app, orchestrator, repo, _, _ = self._patched_app("completed")
        repo.get_or_create_user.return_value = {"id": "db-user"}
        repo.get_latest_conversation_for_user.return_value = None
        orchestrator.create_conversation.return_value = {
            "conversation_id": "c-wa-1",
            "user_id": "whatsapp:+15551234567",
            "status": "active",
            "created_at": "2026-03-19T00:00:00+00:00",
        }
        orchestrator.process_turn.return_value = {
            "conversation_id": "c-wa-1",
            "turn_id": "t-wa-1",
            "assistant_message": "Use your navy blazer.",
            "response_type": "recommendation",
            "resolved_context": {"request_summary": "Need office look", "occasion": "office", "style_goal": ""},
            "filters_applied": {},
            "outfits": [
                {
                    "rank": 1,
                    "title": "Office Option",
                    "items": [
                        {"product_id": "w1", "title": "Navy Blazer", "source": "wardrobe"},
                        {"product_id": "sku-1", "title": "Cream Trousers", "source": "catalog"},
                    ],
                }
            ],
            "follow_up_suggestions": ["Show me more", "Show me catalog alternatives", "Save this", "Explain why"],
            "metadata": {"primary_intent": "occasion_recommendation"},
        }
        client = TestClient(app)
        resp = client.post("/v1/channels/whatsapp/inbound", json={
            "phone_number": "+1 (555) 123-4567",
            "message": "Need an office look for tomorrow",
            "message_id": "wamid-1",
            "profile_name": "Maya",
        })
        self.assertEqual(200, resp.status_code)
        payload = resp.json()
        self.assertEqual("c-wa-1", payload["conversation_id"])
        self.assertEqual("t-wa-1", payload["turn_id"])
        self.assertEqual("whatsapp:+15551234567", payload["user_id"])
        self.assertEqual("whatsapp", payload["channel"])
        self.assertTrue(payload["conversation_created"])
        self.assertEqual("+15551234567", payload["phone_number"])
        self.assertEqual("wamid-1", payload["input_message_id"])
        self.assertIn("Top options:", payload["assistant_message"])
        self.assertIn("Navy Blazer (your wardrobe)", payload["assistant_message"])
        self.assertIn("Cream Trousers (catalog)", payload["assistant_message"])
        self.assertEqual(3, len(payload["follow_up_suggestions"]))
        self.assertEqual("whatsapp", payload["metadata"]["channel_rendering"]["surface"])
        self.assertEqual("Use your navy blazer.", payload["metadata"]["channel_rendering"]["raw_assistant_message"])
        orchestrator.create_conversation.assert_called_once()
        create_kwargs = orchestrator.create_conversation.call_args.kwargs
        self.assertEqual("whatsapp:+15551234567", create_kwargs["external_user_id"])
        self.assertEqual("whatsapp", create_kwargs["initial_context"]["entry_channel"])
        process_kwargs = orchestrator.process_turn.call_args.kwargs
        self.assertEqual("c-wa-1", process_kwargs["conversation_id"])
        self.assertEqual("whatsapp:+15551234567", process_kwargs["external_user_id"])
        self.assertEqual("whatsapp", process_kwargs["channel"])

    def test_whatsapp_inbound_endpoint_reuses_latest_conversation(self) -> None:
        app, orchestrator, repo, _, _ = self._patched_app("completed")
        repo.get_or_create_user.return_value = {"id": "db-user"}
        repo.get_latest_conversation_for_user.return_value = {"id": "c-existing", "user_id": "db-user"}
        orchestrator.process_turn.return_value = {
            "conversation_id": "c-existing",
            "turn_id": "t-wa-2",
            "assistant_message": "Start with your cream trousers.",
            "response_type": "recommendation",
            "resolved_context": {"request_summary": "Pair this", "occasion": "", "style_goal": "pairing"},
            "filters_applied": {},
            "outfits": [],
            "follow_up_suggestions": ["Show me better options from the catalog"],
            "metadata": {"primary_intent": "pairing_request"},
        }
        client = TestClient(app)
        resp = client.post("/v1/channels/whatsapp/inbound", json={
            "phone_number": "15551234567",
            "message": "What goes with my navy blazer?",
        })
        self.assertEqual(200, resp.status_code)
        payload = resp.json()
        self.assertEqual("c-existing", payload["conversation_id"])
        self.assertFalse(payload["conversation_created"])
        orchestrator.create_conversation.assert_not_called()
        process_kwargs = orchestrator.process_turn.call_args.kwargs
        self.assertEqual("c-existing", process_kwargs["conversation_id"])
        self.assertEqual("whatsapp:+15551234567", process_kwargs["external_user_id"])
        self.assertEqual("whatsapp", process_kwargs["channel"])
        self.assertEqual("What goes with my navy blazer?", process_kwargs["message"])

    def test_whatsapp_inbound_endpoint_resolves_canonical_user_from_verified_mobile(self) -> None:
        app, orchestrator, repo, onboarding_gateway, _ = self._patched_app("completed")
        repo.get_or_create_user.return_value = {"id": "db-canonical"}
        repo.get_latest_conversation_for_user.return_value = {"id": "c-canonical", "user_id": "db-canonical"}
        orchestrator.process_turn.return_value = {
            "conversation_id": "c-canonical",
            "turn_id": "t-wa-3",
            "assistant_message": "Use your saved wardrobe first.",
            "response_type": "recommendation",
            "resolved_context": {"request_summary": "What should I wear", "occasion": "office", "style_goal": ""},
            "filters_applied": {},
            "outfits": [],
            "follow_up_suggestions": ["Show me better options from the catalog"],
            "metadata": {"primary_intent": "occasion_recommendation"},
        }
        onboarding_gateway.resolve_user_id_by_mobile.return_value = "user_verified_123"

        client = TestClient(app)
        resp = client.post("/v1/channels/whatsapp/inbound", json={
            "phone_number": "+1 555 123 4567",
            "message": "What should I wear to office tomorrow?",
        })
        self.assertEqual(200, resp.status_code)
        payload = resp.json()
        self.assertEqual("user_verified_123", payload["user_id"])
        repo.merge_external_user_identity.assert_called_once_with(
            canonical_external_user_id="user_verified_123",
            alias_external_user_id="whatsapp:+15551234567",
        )
        process_kwargs = orchestrator.process_turn.call_args.kwargs
        self.assertEqual("user_verified_123", process_kwargs["external_user_id"])

    def test_web_resolver_can_resume_whatsapp_seeded_conversation(self) -> None:
        app, orchestrator, _, _, _ = self._patched_app("completed")
        orchestrator.resolve_active_conversation.return_value = {
            "conversation_id": "c-wa-shared",
            "user_id": "user_verified_123",
            "status": "active",
            "created_at": "2026-03-19T00:00:00+00:00",
            "reused_existing": True,
        }

        client = TestClient(app)
        resp = client.post("/v1/conversations/resolve", json={"user_id": "user_verified_123"})
        self.assertEqual(200, resp.status_code)
        self.assertEqual("c-wa-shared", resp.json()["conversation_id"])
        self.assertTrue(resp.json()["reused_existing"])

    def test_whatsapp_inbound_endpoint_formats_clarification_for_channel(self) -> None:
        app, orchestrator, repo, _, _ = self._patched_app("completed")
        repo.get_or_create_user.return_value = {"id": "db-user"}
        repo.get_latest_conversation_for_user.return_value = {"id": "c-existing", "user_id": "db-user"}
        orchestrator.process_turn.return_value = {
            "conversation_id": "c-existing",
            "turn_id": "t-wa-4",
            "assistant_message": "What's the occasion?",
            "response_type": "clarification",
            "resolved_context": {"request_summary": "Help me", "occasion": "", "style_goal": ""},
            "filters_applied": {},
            "outfits": [],
            "follow_up_suggestions": ["Office", "Date night", "Wedding", "Vacation"],
            "metadata": {"gate_blocked": True},
        }

        client = TestClient(app)
        resp = client.post("/v1/channels/whatsapp/inbound", json={
            "phone_number": "+15551234567",
            "message": "Help me choose something",
        })
        self.assertEqual(200, resp.status_code)
        payload = resp.json()
        self.assertEqual("clarification", payload["response_type"])
        self.assertIn("Reply with:", payload["assistant_message"])
        self.assertIn("1. Office", payload["assistant_message"])
        self.assertEqual(["Office", "Date night", "Wedding"], payload["follow_up_suggestions"])

    def test_whatsapp_inbound_endpoint_normalizes_link_only_product_input(self) -> None:
        app, orchestrator, repo, _, _ = self._patched_app("completed")
        repo.get_or_create_user.return_value = {"id": "db-user"}
        repo.get_latest_conversation_for_user.return_value = {"id": "c-existing", "user_id": "db-user"}
        orchestrator.process_turn.return_value = {
            "conversation_id": "c-existing",
            "turn_id": "t-wa-5",
            "assistant_message": "My current buy / skip verdict is: BUY.",
            "response_type": "recommendation",
            "resolved_context": {"request_summary": "Should I buy this?", "occasion": "", "style_goal": "buy_or_skip"},
            "filters_applied": {},
            "outfits": [],
            "follow_up_suggestions": ["What goes with this?"],
            "metadata": {"primary_intent": "shopping_decision"},
        }

        client = TestClient(app)
        resp = client.post("/v1/channels/whatsapp/inbound", json={
            "phone_number": "+15551234567",
            "message": "",
            "link_url": "https://store.example/item",
            "media_type": "product",
        })
        self.assertEqual(200, resp.status_code)
        process_kwargs = orchestrator.process_turn.call_args.kwargs
        self.assertEqual("Should I buy this? https://store.example/item", process_kwargs["message"])
        self.assertEqual("https://store.example/item", resp.json()["metadata"]["whatsapp_input"]["link_url"])
        self.assertTrue(resp.json()["metadata"]["whatsapp_input"]["has_link"])
        self.assertEqual("restricted_category_guardrail", repo.create_policy_event.call_args.kwargs["policy_event_type"])
        self.assertEqual("allowed", repo.create_policy_event.call_args.kwargs["decision"])
        self.assertEqual("allowed_category", repo.create_policy_event.call_args.kwargs["reason_code"])

    def test_whatsapp_inbound_endpoint_normalizes_image_only_outfit_input(self) -> None:
        app, orchestrator, repo, _, _ = self._patched_app("completed")
        repo.get_or_create_user.return_value = {"id": "db-user"}
        repo.get_latest_conversation_for_user.return_value = {"id": "c-existing", "user_id": "db-user"}
        orchestrator.process_turn.return_value = {
            "conversation_id": "c-existing",
            "turn_id": "t-wa-6",
            "assistant_message": "My current outfit-check read is strong.",
            "response_type": "recommendation",
            "resolved_context": {"request_summary": "Outfit check this.", "occasion": "", "style_goal": "outfit_check"},
            "filters_applied": {},
            "outfits": [],
            "follow_up_suggestions": ["What would improve this look?"],
            "metadata": {"primary_intent": "outfit_check"},
        }

        client = TestClient(app)
        resp = client.post("/v1/channels/whatsapp/inbound", json={
            "phone_number": "+15551234567",
            "image_url": "https://img.example/look.jpg",
            "media_type": "outfit_photo",
        })
        self.assertEqual(200, resp.status_code)
        process_kwargs = orchestrator.process_turn.call_args.kwargs
        self.assertEqual("Outfit check this. https://img.example/look.jpg", process_kwargs["message"])
        self.assertEqual("https://img.example/look.jpg", resp.json()["metadata"]["whatsapp_input"]["image_url"])
        self.assertTrue(resp.json()["metadata"]["whatsapp_input"]["has_image"])
        self.assertEqual("image_upload_guardrail", repo.create_policy_event.call_args.kwargs["policy_event_type"])
        self.assertEqual("allowed", repo.create_policy_event.call_args.kwargs["decision"])

    def test_whatsapp_inbound_endpoint_blocks_explicit_image_input(self) -> None:
        app, orchestrator, repo, _, _ = self._patched_app("completed")
        repo.get_or_create_user.return_value = {"id": "db-user"}
        repo.get_latest_conversation_for_user.return_value = {"id": "c-existing", "user_id": "db-user"}

        client = TestClient(app)
        resp = client.post("/v1/channels/whatsapp/inbound", json={
            "phone_number": "+15551234567",
            "image_url": "https://img.example/nude_selfie.jpg",
            "media_type": "outfit_photo",
            "message_id": "wamid-blocked",
        })
        self.assertEqual(400, resp.status_code)
        self.assertIn("Upload a clothed full-body", resp.text)
        orchestrator.process_turn.assert_not_called()
        repo.create_policy_event.assert_called_once()
        self.assertEqual("image_upload_guardrail", repo.create_policy_event.call_args.kwargs["policy_event_type"])
        self.assertEqual("explicit_nudity", repo.create_policy_event.call_args.kwargs["reason_code"])

    def test_whatsapp_inbound_endpoint_blocks_minor_image_input(self) -> None:
        app, orchestrator, repo, _, _ = self._patched_app("completed")
        repo.get_or_create_user.return_value = {"id": "db-user"}
        repo.get_latest_conversation_for_user.return_value = {"id": "c-existing", "user_id": "db-user"}

        client = TestClient(app)
        resp = client.post("/v1/channels/whatsapp/inbound", json={
            "phone_number": "+15551234567",
            "image_url": "https://img.example/child_portrait.jpg",
            "media_type": "outfit_photo",
        })
        self.assertEqual(400, resp.status_code)
        self.assertIn("adult outfit", resp.text)
        orchestrator.process_turn.assert_not_called()
        self.assertEqual("unsafe_minor", repo.create_policy_event.call_args.kwargs["reason_code"])

    def test_whatsapp_inbound_endpoint_blocks_restricted_category_item_input(self) -> None:
        app, orchestrator, repo, _, _ = self._patched_app("completed")
        repo.get_or_create_user.return_value = {"id": "db-user"}
        repo.get_latest_conversation_for_user.return_value = {"id": "c-existing", "user_id": "db-user"}

        client = TestClient(app)
        resp = client.post("/v1/channels/whatsapp/inbound", json={
            "phone_number": "+15551234567",
            "link_url": "https://store.example/lingerie-item",
            "media_type": "product",
        })
        self.assertEqual(400, resp.status_code)
        self.assertIn("not supported here", resp.text)
        orchestrator.process_turn.assert_not_called()
        self.assertEqual("restricted_category_guardrail", repo.create_policy_event.call_args.kwargs["policy_event_type"])
        self.assertEqual("restricted_category_upload", repo.create_policy_event.call_args.kwargs["reason_code"])

    def test_whatsapp_reminder_endpoint_uses_latest_conversation_context(self) -> None:
        app, _, repo, _, _ = self._patched_app("completed")
        repo.get_or_create_user.return_value = {"id": "db-user"}
        repo.get_latest_conversation_for_user.return_value = {
            "id": "c-existing",
            "user_id": "db-user",
            "session_context_json": {
                "last_intent": "shopping_decision",
                "memory": {"wardrobe_item_count": 2},
            },
        }

        client = TestClient(app)
        resp = client.post("/v1/channels/whatsapp/reminders", json={
            "phone_number": "+15551234567",
        })
        self.assertEqual(200, resp.status_code)
        payload = resp.json()
        self.assertEqual("whatsapp:+15551234567", payload["user_id"])
        self.assertEqual("c-existing", payload["conversation_id"])
        self.assertEqual("shopping", payload["reminder_type"])
        self.assertIn("buy / skip", payload["assistant_message"].lower())
        self.assertTrue(payload["metadata"]["has_conversation_context"])

    def test_whatsapp_reminder_endpoint_can_force_reactivation_without_conversation(self) -> None:
        app, _, repo, _, _ = self._patched_app("completed")
        repo.get_or_create_user.return_value = {"id": "db-user"}
        repo.get_latest_conversation_for_user.return_value = None

        client = TestClient(app)
        resp = client.post("/v1/channels/whatsapp/reminders", json={
            "phone_number": "+15551234567",
            "reminder_type": "reactivation",
        })
        self.assertEqual(200, resp.status_code)
        payload = resp.json()
        self.assertEqual("reactivation", payload["reminder_type"])
        self.assertIn("what to wear or buy this week", payload["assistant_message"].lower())
        self.assertFalse(payload["metadata"]["has_conversation_context"])

    def test_whatsapp_deep_link_endpoint_infers_onboarding_task(self) -> None:
        app, _, repo, _, _ = self._patched_app("completed")
        repo.get_or_create_user.return_value = {"id": "db-user"}
        repo.get_latest_conversation_for_user.return_value = {
            "id": "c-existing",
            "user_id": "db-user",
            "session_context_json": {
                "last_response_metadata": {"onboarding_required": True},
            },
        }

        client = TestClient(app)
        resp = client.post("/v1/channels/whatsapp/deep-links", json={
            "phone_number": "+15551234567",
        })
        self.assertEqual(200, resp.status_code)
        payload = resp.json()
        self.assertEqual("complete_onboarding", payload["task"])
        self.assertIn("/onboard?", payload["deep_link_url"])
        self.assertIn("focus=onboarding", payload["deep_link_url"])

    def test_whatsapp_deep_link_endpoint_supports_explicit_task(self) -> None:
        app, _, repo, _, _ = self._patched_app("completed")
        repo.get_conversation.return_value = {
            "id": "c-existing",
            "user_id": "db-user",
            "session_context_json": {"last_intent": "pairing_request"},
        }
        repo.get_user_by_id.return_value = {"external_user_id": "user-1"}

        client = TestClient(app)
        resp = client.post("/v1/channels/whatsapp/deep-links", json={
            "conversation_id": "c-existing",
            "task": "manage_wardrobe",
        })
        self.assertEqual(200, resp.status_code)
        payload = resp.json()
        self.assertEqual("manage_wardrobe", payload["task"])
        self.assertIn("focus=wardrobe", payload["deep_link_url"])
        self.assertIn("conversation_id=c-existing", payload["deep_link_url"])

    def test_admin_catalog_page_renders(self) -> None:
        app, _, _, _, _ = self._patched_app("completed")
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
            "agentic_application.api.ApplicationUserGateway"
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
            onboarding_gateway.get_effective_seasonal_groups.return_value = None
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

    def test_referral_event_endpoint_persists_dependency_event(self) -> None:
        app, _, repo, _, _ = self._patched_app("completed")
        repo.create_dependency_event.return_value = {"id": "dep-1"}

        client = TestClient(app)
        resp = client.post("/v1/analytics/referrals", json={
            "user_id": "user-1",
            "channel": "whatsapp",
            "referral_type": "invite",
            "target": "friend-42",
            "metadata": {"campaign": "friends-and-family"},
        })

        self.assertEqual(200, resp.status_code)
        payload = resp.json()
        self.assertTrue(payload["success"])
        self.assertEqual("dep-1", payload["event_id"])
        self.assertEqual("invite", payload["referral_type"])
        kwargs = repo.create_dependency_event.call_args.kwargs
        self.assertEqual("referral", kwargs["event_type"])
        self.assertEqual("whatsapp", kwargs["source_channel"])
        self.assertEqual("friend-42", kwargs["metadata_json"]["target"])

    def test_dependency_report_endpoint_returns_reporting_payload(self) -> None:
        app, _, _, _, reporting = self._patched_app("completed")
        reporting.build_report.return_value = {
            "overview": {"onboarded_user_count": 12, "second_session_within_14d_rate_pct": 50.0},
            "acquisition_sources": [{"key": "instagram", "count": 7}],
        }

        client = TestClient(app)
        resp = client.get("/v1/analytics/dependency-report")

        self.assertEqual(200, resp.status_code)
        payload = resp.json()
        self.assertEqual(12, payload["report"]["overview"]["onboarded_user_count"])
        self.assertEqual("instagram", payload["report"]["acquisition_sources"][0]["key"])
        reporting.build_report.assert_called_once()


    def test_ui_html_contains_outfit_card_classes(self) -> None:
        app, _, _, _, _ = self._patched_app("completed")
        client = TestClient(app)
        resp = client.get("/?user=user_ready")
        html = resp.text
        self.assertIn("outfit-card", html)
        self.assertIn("outfit-thumbs", html)
        self.assertIn("outfit-main-img", html)
        self.assertIn("outfit-info", html)
        self.assertIn("outfit-feedback", html)
        self.assertIn("dislike-form", html)
        self.assertIn("sendFeedback", html)
        self.assertIn("buildOutfitCard", html)
        self.assertIn("renderOutfits", html)
        # Old classes should be gone
        self.assertNotIn("tryon-section", html)
        self.assertNotIn("tryon-label", html)
        self.assertNotIn("renderRecommendations", html)

    def test_ui_html_exposes_garment_pairing_upload_surface(self) -> None:
        app, _, _, _, _ = self._patched_app("completed")
        client = TestClient(app)
        resp = client.get("/?user=user_ready")
        html = resp.text
        self.assertIn("Pair A Garment", html)
        self.assertIn("uploadPairBtn", html)
        self.assertIn("/v1/onboarding/wardrobe/items", html)
        self.assertIn("What goes with my ", html)

    def test_outfit_card_schema_accepts_tryon_and_enrichment_fields(self) -> None:
        from platform_core.api_schemas import OutfitCard, OutfitItem
        item = OutfitItem(
            product_id="p1",
            formality_level="smart_casual",
            occasion_fit="office",
            pattern_type="solid",
            volume_profile="fitted",
            fit_type="slim",
            silhouette_type="straight",
        )
        card = OutfitCard(
            rank=1,
            title="Test Outfit",
            tryon_image="data:image/png;base64,abc",
            items=[item],
        )
        self.assertEqual("data:image/png;base64,abc", card.tryon_image)
        self.assertEqual("smart_casual", card.items[0].formality_level)
        self.assertEqual("office", card.items[0].occasion_fit)
        self.assertEqual("solid", card.items[0].pattern_type)

    def test_feedback_request_schema_validates_event_type(self) -> None:
        from platform_core.api_schemas import FeedbackRequest
        fb = FeedbackRequest(outfit_rank=1, event_type="like")
        self.assertEqual("like", fb.event_type)
        self.assertEqual("", fb.turn_id)
        fb2 = FeedbackRequest(outfit_rank=2, event_type="dislike", notes="Too bold")
        self.assertEqual("dislike", fb2.event_type)
        self.assertEqual("Too bold", fb2.notes)
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            FeedbackRequest(outfit_rank=1, event_type="invalid")

    def _patched_feedback_app(self, repo_mock):
        """Create an app with a controlled repo mock for feedback endpoint tests."""
        import agentic_application.api as api_mod
        with patch.object(api_mod, "ConversationRepository") as repo_cls, \
             patch.object(api_mod, "load_config") as load_cfg, \
             patch.object(api_mod, "SupabaseRestClient"), \
             patch.object(api_mod, "AgenticOrchestrator"), \
             patch.object(api_mod, "ApplicationUserGateway") as gw_cls:
            load_cfg.return_value = Mock(
                supabase_rest_url="http://127.0.0.1:55321/rest/v1",
                supabase_service_role_key="x",
                request_timeout_seconds=5,
                catalog_csv_path="data/catalog/enriched_catalog.csv",
                retrieval_match_count=12,
            )
            repo_cls.return_value = repo_mock
            gw = Mock()
            gw.create_router.return_value = APIRouter()
            gw.get_person_image_path.return_value = None
            gw_cls.return_value = gw
            return create_app()

    def test_feedback_endpoint_returns_ok(self) -> None:
        repo_mock = Mock()
        repo_mock.get_conversation.return_value = {"user_id": "uid-1", "id": "c1"}
        repo_mock.get_latest_turn.return_value = {"id": "t1", "resolved_context_json": {}}
        repo_mock.get_user_by_id.return_value = {"external_user_id": "user-1"}
        repo_mock.create_feedback_event.return_value = {"id": "fb1"}

        app = self._patched_feedback_app(repo_mock)
        client = TestClient(app)
        resp = client.post("/v1/conversations/c1/feedback", json={
            "outfit_rank": 1,
            "event_type": "like",
            "item_ids": ["g1", "g2"],
        })
        self.assertEqual(200, resp.status_code)
        data = resp.json()
        self.assertTrue(data["ok"])
        self.assertEqual(2, data["count"])
        self.assertEqual("t1", data["turn_id"])
        self.assertEqual(2, repo_mock.create_feedback_event.call_count)
        self.assertEqual(2, repo_mock.create_catalog_interaction.call_count)
        call_kwargs = repo_mock.create_feedback_event.call_args_list[0].kwargs
        self.assertEqual("like", call_kwargs["event_type"])
        self.assertEqual("g1", call_kwargs["garment_id"])
        self.assertEqual("c1", call_kwargs["conversation_id"])
        interaction_kwargs = repo_mock.create_catalog_interaction.call_args_list[0].kwargs
        self.assertEqual("user-1", interaction_kwargs["user_id"])
        self.assertEqual("save", interaction_kwargs["interaction_type"])
        self.assertEqual("outfit_feedback", interaction_kwargs["source_surface"])
        session_context = repo_mock.update_conversation_context.call_args.kwargs["session_context"]
        self.assertEqual("like", session_context["last_feedback_summary"]["event_type"])
        self.assertEqual(["g1", "g2"], session_context["last_feedback_summary"]["item_ids"])

    def test_feedback_endpoint_resolves_items_from_turn(self) -> None:
        repo_mock = Mock()
        repo_mock.get_conversation.return_value = {"user_id": "uid-1", "id": "c1"}
        repo_mock.get_user_by_id.return_value = {"external_user_id": "user-1"}
        repo_mock.get_latest_turn.return_value = {
            "id": "t1",
            "resolved_context_json": {
                "final_recommendations": [
                    {"rank": 1, "item_ids": ["g1", "g2"]},
                    {"rank": 2, "item_ids": ["g3"]},
                ]
            }
        }
        repo_mock.create_feedback_event.return_value = {"id": "fb1"}

        app = self._patched_feedback_app(repo_mock)
        client = TestClient(app)
        resp = client.post("/v1/conversations/c1/feedback", json={
            "outfit_rank": 1,
            "event_type": "dislike",
            "notes": "Too bold for me",
        })
        self.assertEqual(200, resp.status_code)
        data = resp.json()
        self.assertEqual(2, data["count"])
        call_kwargs = repo_mock.create_feedback_event.call_args_list[0].kwargs
        self.assertEqual("dislike", call_kwargs["event_type"])
        self.assertEqual("Too bold for me", call_kwargs["notes"])
        self.assertEqual("g1", call_kwargs["garment_id"])
        interaction_kwargs = repo_mock.create_catalog_interaction.call_args_list[0].kwargs
        self.assertEqual("dismiss", interaction_kwargs["interaction_type"])

    def test_feedback_endpoint_uses_explicit_turn_id(self) -> None:
        repo_mock = Mock()
        repo_mock.get_conversation.return_value = {"user_id": "uid-1", "id": "c1"}
        repo_mock.get_user_by_id.return_value = {"external_user_id": "user-1"}
        repo_mock.get_turn.return_value = {
            "id": "t9",
            "conversation_id": "c1",
            "resolved_context_json": {
                "recommendations": [{"rank": 2, "item_ids": ["g9"]}],
            },
        }
        repo_mock.create_feedback_event.return_value = {"id": "fb1"}

        app = self._patched_feedback_app(repo_mock)
        client = TestClient(app)
        resp = client.post("/v1/conversations/c1/feedback", json={
            "turn_id": "t9",
            "outfit_rank": 2,
            "event_type": "like",
        })
        self.assertEqual(200, resp.status_code)
        self.assertEqual("t9", resp.json()["turn_id"])
        repo_mock.get_turn.assert_called_once_with("t9")
        call_kwargs = repo_mock.create_feedback_event.call_args.kwargs
        self.assertEqual("t9", call_kwargs["turn_id"])
        self.assertEqual("g9", call_kwargs["garment_id"])

    def test_feedback_endpoint_rejects_unresolved_items(self) -> None:
        repo_mock = Mock()
        repo_mock.get_conversation.return_value = {"user_id": "uid-1", "id": "c1"}
        repo_mock.get_user_by_id.return_value = {"external_user_id": "user-1"}
        repo_mock.get_latest_turn.return_value = {"id": "t1", "resolved_context_json": {"recommendations": []}}

        app = self._patched_feedback_app(repo_mock)
        client = TestClient(app)
        resp = client.post("/v1/conversations/c1/feedback", json={
            "outfit_rank": 1,
            "event_type": "like",
        })
        self.assertEqual(400, resp.status_code)
        self.assertIn("couldn't attach that feedback", resp.text)
        repo_mock.create_policy_event.assert_called_once()
        self.assertEqual("unresolved_feedback_items", repo_mock.create_policy_event.call_args.kwargs["reason_code"])

    def test_feedback_endpoint_rejects_items_outside_selected_outfit(self) -> None:
        repo_mock = Mock()
        repo_mock.get_conversation.return_value = {"user_id": "uid-1", "id": "c1"}
        repo_mock.get_user_by_id.return_value = {"external_user_id": "user-1"}
        repo_mock.get_latest_turn.return_value = {
            "id": "t1",
            "resolved_context_json": {
                "recommendations": [{"rank": 1, "item_ids": ["g1", "g2"]}],
            },
        }

        app = self._patched_feedback_app(repo_mock)
        client = TestClient(app)
        resp = client.post("/v1/conversations/c1/feedback", json={
            "outfit_rank": 1,
            "event_type": "dislike",
            "item_ids": ["g3"],
        })
        self.assertEqual(400, resp.status_code)
        self.assertIn("does not belong to the selected outfit", resp.text)
        repo_mock.create_policy_event.assert_called_once()
        self.assertEqual("item_outside_selected_outfit", repo_mock.create_policy_event.call_args.kwargs["reason_code"])

    def test_tryon_endpoint_logs_policy_event_when_person_image_missing(self) -> None:
        repo_mock = Mock()
        app = self._patched_feedback_app(repo_mock)
        client = TestClient(app)
        resp = client.post("/v1/tryon", json={
            "user_id": "user-1",
            "product_image_url": "https://img/item.jpg",
        })
        self.assertEqual(400, resp.status_code)
        self.assertIn("full-body photo", resp.text)
        repo_mock.create_policy_event.assert_called_once()
        self.assertEqual("virtual_tryon_guardrail", repo_mock.create_policy_event.call_args.kwargs["policy_event_type"])

    def test_tryon_endpoint_blocks_failed_quality_gate(self) -> None:
        import agentic_application.api as api_mod

        repo_mock = Mock()
        with patch.object(api_mod, "ConversationRepository") as repo_cls, \
             patch.object(api_mod, "load_config") as load_cfg, \
             patch.object(api_mod, "SupabaseRestClient"), \
             patch.object(api_mod, "AgenticOrchestrator"), \
             patch.object(api_mod, "ApplicationUserGateway") as gw_cls, \
             patch.object(api_mod, "TryonService") as tryon_cls, \
             patch.object(api_mod, "TryonQualityGate") as gate_cls:
            load_cfg.return_value = Mock(
                supabase_rest_url="http://127.0.0.1:55321/rest/v1",
                supabase_service_role_key="x",
                request_timeout_seconds=5,
                catalog_csv_path="data/catalog/enriched_catalog.csv",
                retrieval_match_count=12,
            )
            repo_cls.return_value = repo_mock
            gw = Mock()
            gw.create_router.return_value = APIRouter()
            gw.get_person_image_path.return_value = "/tmp/person.jpg"
            gw_cls.return_value = gw
            tryon_cls.return_value.generate_tryon.return_value = {
                "success": True,
                "data_url": "data:image/png;base64,abc",
            }
            gate_cls.return_value.evaluate.return_value = {
                "passed": False,
                "quality_score_pct": 0,
                "reason_code": "low_detail_output",
                "message": "Generated try-on output lacks enough visual detail.",
                "factors": [],
            }

            app = create_app()

        client = TestClient(app)
        resp = client.post("/v1/tryon", json={
            "user_id": "user-1",
            "product_image_url": "https://img/item.jpg",
        })
        self.assertEqual(400, resp.status_code)
        self.assertIn("cleaner product image", resp.text)
        self.assertEqual("virtual_tryon_guardrail", repo_mock.create_policy_event.call_args.kwargs["policy_event_type"])
        self.assertEqual("low_detail_output", repo_mock.create_policy_event.call_args.kwargs["reason_code"])

    def test_tryon_endpoint_logs_allowed_quality_gate(self) -> None:
        import agentic_application.api as api_mod

        repo_mock = Mock()
        with patch.object(api_mod, "ConversationRepository") as repo_cls, \
             patch.object(api_mod, "load_config") as load_cfg, \
             patch.object(api_mod, "SupabaseRestClient"), \
             patch.object(api_mod, "AgenticOrchestrator"), \
             patch.object(api_mod, "ApplicationUserGateway") as gw_cls, \
             patch.object(api_mod, "TryonService") as tryon_cls, \
             patch.object(api_mod, "TryonQualityGate") as gate_cls:
            load_cfg.return_value = Mock(
                supabase_rest_url="http://127.0.0.1:55321/rest/v1",
                supabase_service_role_key="x",
                request_timeout_seconds=5,
                catalog_csv_path="data/catalog/enriched_catalog.csv",
                retrieval_match_count=12,
            )
            repo_cls.return_value = repo_mock
            gw = Mock()
            gw.create_router.return_value = APIRouter()
            gw.get_person_image_path.return_value = "/tmp/person.jpg"
            gw_cls.return_value = gw
            tryon_cls.return_value.generate_tryon.return_value = {
                "success": True,
                "data_url": "data:image/png;base64,abc",
            }
            gate_cls.return_value.evaluate.return_value = {
                "passed": True,
                "quality_score_pct": 88,
                "reason_code": "",
                "message": "Passed quality checks.",
                "factors": [],
            }

            app = create_app()

        client = TestClient(app)
        resp = client.post("/v1/tryon", json={
            "user_id": "user-1",
            "product_image_url": "https://img/item.jpg",
        })
        self.assertEqual(200, resp.status_code)
        self.assertEqual("virtual_tryon_guardrail", repo_mock.create_policy_event.call_args.kwargs["policy_event_type"])
        self.assertEqual("allowed", repo_mock.create_policy_event.call_args.kwargs["decision"])
        self.assertEqual("quality_gate_passed", repo_mock.create_policy_event.call_args.kwargs["reason_code"])

    def test_feedback_endpoint_rejects_invalid_event_type(self) -> None:
        repo_mock = Mock()
        app = self._patched_feedback_app(repo_mock)
        client = TestClient(app)
        resp = client.post("/v1/conversations/c1/feedback", json={
            "outfit_rank": 1,
            "event_type": "invalid_type",
        })
        self.assertEqual(422, resp.status_code)


if __name__ == "__main__":
    unittest.main()
