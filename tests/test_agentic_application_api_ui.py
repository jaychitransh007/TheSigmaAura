import sys
import unittest
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient
from fastapi import APIRouter, FastAPI


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
from user.api import create_onboarding_router


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
        onboarding_gateway.render_onboarding_html.side_effect = (
            lambda user_id="", focus="": "<html>Wardrobe Manager</html>" if focus == "wardrobe" else "<html>Onboarding</html>"
        )
        onboarding_gateway.render_processing_html.return_value = "<html>Profile processing in progress.</html>"
        onboarding_gateway.render_wardrobe_manager_html.return_value = "<html>Wardrobe Manager</html>"
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
        # Phase 11A: the legacy "Agent Processing Stages" header was
        # replaced with a subtle stage bar driven by latestVisibleStage
        # in JS. Assert the new artifacts.
        self.assertIn("renderStages", html)
        self.assertIn("latestVisibleStage", html)
        self.assertIn("Logout", html)
        # Legacy admin/debug controls should NOT appear in the user-facing shell
        self.assertNotIn("Strictness", html)
        self.assertNotIn("Hard Filter Profile", html)
        self.assertNotIn("Rewards", html)
        self.assertNotIn("Image Upload", html)

    def test_pending_analysis_user_still_gets_processing_screen(self) -> None:
        app, _, _, _, _ = self._patched_app("running")
        client = TestClient(app)
        resp = client.get("/?user=user_processing")
        self.assertEqual(200, resp.status_code)
        # Phase 11A: the dedicated "Profile processing in progress." HTML
        # page was replaced with the chat shell rendered in profile-view
        # mode (active_view="profile"). Onboarded users with running
        # analysis land on the chat shell with the profile view active
        # so they can monitor analysis progress without leaving the app.
        html = resp.text
        self.assertIn("Sigma Aura", html)
        self.assertIn("view-profile", html)
        # User_id is plumbed through to the shell's USER_ID const
        self.assertIn("user_processing", html)

    def test_onboard_focus_wardrobe_renders_manager_html(self) -> None:
        app, _, _, onboarding_gateway, _ = self._patched_app("completed")
        client = TestClient(app)
        resp = client.get("/onboard?user=user_ready&focus=wardrobe")
        self.assertEqual(200, resp.status_code)
        self.assertIn("Wardrobe Manager", resp.text)
        onboarding_gateway.render_onboarding_html.assert_called_with(user_id="user_ready", focus="wardrobe")

    def test_home_focus_wardrobe_bypasses_main_chat_ui(self) -> None:
        app, _, _, onboarding_gateway, _ = self._patched_app("completed")
        client = TestClient(app)
        resp = client.get("/?user=user_ready&focus=wardrobe")
        self.assertEqual(200, resp.status_code)
        self.assertIn("Wardrobe Manager", resp.text)
        onboarding_gateway.render_wardrobe_manager_html.assert_called_with(user_id="user_ready")

    def test_onboarding_local_image_route_serves_saved_wardrobe_assets(self) -> None:
        app = FastAPI()
        app.include_router(create_onboarding_router(Mock(), Mock()))
        root = Path(__file__).resolve().parents[1]
        wardrobe_dir = root / "data" / "onboarding" / "images" / "wardrobe"
        wardrobe_dir.mkdir(parents=True, exist_ok=True)
        tmp = tempfile.NamedTemporaryFile(dir=wardrobe_dir, suffix=".jpg", delete=False)
        try:
            tmp.write(b"fake-image-bytes")
            tmp.close()
            rel_path = f"data/onboarding/images/wardrobe/{Path(tmp.name).name}"
            client = TestClient(app)
            resp = client.get("/v1/onboarding/images/local", params={"path": rel_path})
            self.assertEqual(200, resp.status_code)
            self.assertEqual(b"fake-image-bytes", resp.content)
        finally:
            Path(tmp.name).unlink(missing_ok=True)

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

    def test_ui_html_renders_split_polar_bar_chart(self) -> None:
        """Phase 12B follow-up (April 9 2026): the two stacked radar
        charts (style archetype + evaluation criteria) were merged into
        a single Nightingale-style split polar bar chart. Top semicircle
        owns the 8-axis archetype profile, bottom owns the dynamic 5-9
        axis fit profile, separated by a dashed horizontal divider.

        Verify the new structure is in place and the old two-radar
        scaffolding is fully removed."""
        app, _, _, _, _ = self._patched_app("completed")
        client = TestClient(app)
        resp = client.get("/?user=user_ready")
        html = resp.text
        # ── New structure must be present ──
        self.assertIn("drawProfile", html, "split polar bar drawProfile function missing")
        self.assertIn("CONTEXT_GATED_KEYS", html, "context-gating filter missing")
        # Top + bottom semicircle calls (start angles π and 0, both spanning π)
        self.assertIn("// start at 9 o'clock", html)
        self.assertIn("// start at 3 o'clock", html)
        # Both colors present (purple for archetype, burgundy for fit)
        self.assertIn("rgba(127, 119, 221, 0.38)", html, "archetype fill colour missing")
        self.assertIn("rgba(139, 48, 85, 0.35)", html, "fit fill colour missing")
        self.assertIn("#7F77DD", html, "archetype stroke colour missing")
        self.assertIn("#8B3055", html, "fit stroke colour missing")
        # Legend labels
        self.assertIn("Style profile", html)
        self.assertIn("Fit profile", html)
        # Dashed divider markers
        self.assertIn("setLineDash([4, 4])", html, "dashed divider missing")
        # Layout constants — pMaxR=70 outer, pLabelR=88 base label radius,
        # pLabelOffset=12 for the staggered odd-indexed labels (the
        # double-ring pattern that prevents adjacent label collisions
        # like Natural / Minimalist in the top semicircle).
        self.assertIn("pMaxR = 70", html)
        self.assertIn("pLabelR = 88", html)
        self.assertIn("pLabelOffset = 12", html)
        # Label staggering must be present in drawProfile
        self.assertIn("(i % 2) * pLabelOffset", html)
        # ── Old two-radar scaffolding must be GONE ──
        self.assertNotIn("var values = archetypes.map", html,
                         "old archetype radar polygon code still present")
        self.assertNotIn("rgba(139, 92, 246, 0.85)", html,
                         "old purple stroke (legacy archetype radar) still present")
        self.assertNotIn("rgba(111, 47, 69, 0.85)", html,
                         "old burgundy stroke (legacy criteria radar) still present")
        self.assertNotIn("criteriaRadarDiv", html,
                         "old separate criteria radar div still present")

    def test_ui_html_routes_pairing_through_chat_attachment_surface(self) -> None:
        app, _, _, _, _ = self._patched_app("completed")
        client = TestClient(app)
        resp = client.get("/?user=user_ready")
        html = resp.text
        # Legacy dedicated "Pair A Garment" surface should NOT exist —
        # pairing flows through the chat composer's attachment popover.
        self.assertNotIn("Pair A Garment", html)
        self.assertNotIn("uploadPairBtn", html)
        # Phase 11A: the chat composer's attachment surface uses a "+"
        # button with a popover that exposes "Upload image" and
        # "Select from wardrobe" entries (renamed from the legacy
        # `attachImgBtn`).
        self.assertIn("plusBtn", html)
        self.assertIn("uploadImageBtn", html)
        self.assertIn("selectWardrobeBtn", html)
        self.assertIn("chatImageFile", html)
        self.assertIn("What goes with this? Show me pairing options.", html)

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
