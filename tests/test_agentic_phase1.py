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


from conversation_platform.schemas import (
    CheckoutCartItem,
    CheckoutPrepareRequest,
    CheckoutPrepareResponse,
    CreateConversationRequest,
    CreateTurnRequest,
    InitialProfile,
    SizeOverrides,
    TurnResponse,
)
from conversation_platform.orchestrator import ConversationOrchestrator
from conversation_platform.repositories import ConversationRepository
from user_profiler.schemas import BODY_ENUMS


# ---------------------------------------------------------------------------
# Schema / type tests
# ---------------------------------------------------------------------------

class SchemaTypeTests(unittest.TestCase):
    def test_mode_preference_defaults_to_auto(self) -> None:
        req = CreateTurnRequest(user_id="u1", message="hello")
        self.assertEqual("auto", req.mode_preference)

    def test_autonomy_level_defaults_to_suggest(self) -> None:
        req = CreateTurnRequest(user_id="u1", message="hello")
        self.assertEqual("suggest", req.autonomy_level)

    def test_target_garment_type_optional(self) -> None:
        req = CreateTurnRequest(user_id="u1", message="hello")
        self.assertIsNone(req.target_garment_type)

    def test_size_overrides_optional(self) -> None:
        req = CreateTurnRequest(user_id="u1", message="hello")
        self.assertIsNone(req.size_overrides)

    def test_size_overrides_model(self) -> None:
        so = SizeOverrides(top_size="M", fit_preference="regular")
        self.assertEqual("M", so.top_size)
        self.assertEqual("regular", so.fit_preference)
        self.assertIsNone(so.bottom_size)
        self.assertEqual([], so.comfort_preferences)

    def test_initial_profile_model(self) -> None:
        ip = InitialProfile(
            sizes={"top_size": "M"},
            budget_preferences={"soft_cap": 4000, "hard_cap": 5000, "currency": "INR"},
        )
        self.assertEqual({"top_size": "M"}, ip.sizes)
        self.assertIsNone(ip.fit_preferences)

    def test_create_conversation_request_accepts_initial_profile(self) -> None:
        req = CreateConversationRequest(
            user_id="u1",
            initial_profile=InitialProfile(sizes={"top_size": "L"}),
        )
        self.assertIsNotNone(req.initial_profile)
        self.assertEqual({"top_size": "L"}, req.initial_profile.sizes)

    def test_turn_request_with_all_new_fields(self) -> None:
        req = CreateTurnRequest(
            user_id="u1",
            message="Show me shirts",
            mode_preference="garment",
            target_garment_type="shirt",
            autonomy_level="suggest",
            size_overrides=SizeOverrides(top_size="M"),
        )
        self.assertEqual("garment", req.mode_preference)
        self.assertEqual("shirt", req.target_garment_type)
        self.assertEqual("M", req.size_overrides.top_size)

    def test_turn_response_new_fields_defaults(self) -> None:
        resp = TurnResponse(
            conversation_id="c1",
            turn_id="t1",
            assistant_message="msg",
            resolved_context={"occasion": "", "archetype": "", "gender": "", "age": ""},
        )
        self.assertIsNone(resp.resolved_mode)
        self.assertFalse(resp.complete_the_look_offer)
        self.assertEqual([], resp.style_constraints_applied)
        self.assertEqual([], resp.profile_fields_used)

    def test_turn_response_with_new_fields(self) -> None:
        resp = TurnResponse(
            conversation_id="c1",
            turn_id="t1",
            assistant_message="msg",
            resolved_context={"occasion": "", "archetype": "", "gender": "", "age": ""},
            resolved_mode="garment",
            complete_the_look_offer=True,
            style_constraints_applied=["body_harmony"],
            profile_fields_used=["HeightCategory"],
        )
        self.assertEqual("garment", resp.resolved_mode)
        self.assertTrue(resp.complete_the_look_offer)
        self.assertEqual(["body_harmony"], resp.style_constraints_applied)

    def test_checkout_prepare_request(self) -> None:
        req = CheckoutPrepareRequest(
            user_id="u1",
            recommendation_run_id="run1",
            selected_item_ids=["g1", "g2"],
            selected_outfit_id="combo::g1|g2",
            budget_cap=5000,
        )
        self.assertEqual(["g1", "g2"], req.selected_item_ids)
        self.assertEqual(5000, req.budget_cap)

    def test_checkout_prepare_response(self) -> None:
        resp = CheckoutPrepareResponse(
            checkout_prep_id="cp1",
            status="ready",
            cart_items=[
                CheckoutCartItem(garment_id="g1", unit_price=2000, final_price=2000),
            ],
            subtotal=2000,
            final_total=2000,
        )
        self.assertEqual("ready", resp.status)
        self.assertEqual(1, len(resp.cart_items))
        self.assertEqual("INR", resp.currency)

    def test_checkout_status_values(self) -> None:
        for status in ("pending", "ready", "needs_user_action", "failed"):
            resp = CheckoutPrepareResponse(checkout_prep_id="cp1", status=status)
            self.assertEqual(status, resp.status)


# ---------------------------------------------------------------------------
# Repository tests
# ---------------------------------------------------------------------------

class RepositoryCheckoutTests(unittest.TestCase):
    def test_create_turn_with_mode_and_autonomy(self) -> None:
        client = Mock()
        client.insert_one.return_value = {"id": "t1"}
        repo = ConversationRepository(client)

        repo.create_turn(
            "c1", "hello",
            mode_preference="garment",
            autonomy_level="suggest",
        )

        args = client.insert_one.call_args
        payload = args[0][1]
        self.assertEqual("garment", payload["mode_preference"])
        self.assertEqual("suggest", payload["autonomy_level"])

    def test_create_turn_without_new_fields_backward_compat(self) -> None:
        client = Mock()
        client.insert_one.return_value = {"id": "t1"}
        repo = ConversationRepository(client)

        repo.create_turn("c1", "hello")

        args = client.insert_one.call_args
        payload = args[0][1]
        self.assertNotIn("mode_preference", payload)
        self.assertNotIn("autonomy_level", payload)

    def test_finalize_turn_with_resolved_mode(self) -> None:
        client = Mock()
        client.update_one.return_value = {"id": "t1"}
        repo = ConversationRepository(client)

        repo.finalize_turn(
            turn_id="t1",
            assistant_message="msg",
            resolved_context={"occasion": "work_mode"},
            profile_snapshot_id="ps1",
            recommendation_run_id="run1",
            resolved_mode="outfit",
        )

        patch_arg = client.update_one.call_args[1]["patch"]
        self.assertEqual("outfit", patch_arg["resolved_mode"])

    def test_create_recommendation_run_with_new_fields(self) -> None:
        client = Mock()
        client.insert_one.return_value = {"id": "run1"}
        repo = ConversationRepository(client)

        repo.create_recommendation_run(
            conversation_id="c1",
            turn_id="t1",
            profile_snapshot_id="ps1",
            context_snapshot_id="cs1",
            strictness="balanced",
            hard_filter_profile="rl_ready_minimal",
            candidate_count=10,
            returned_count=3,
            resolved_mode="garment",
            requested_garment_types_json=["shirt"],
            style_constraints_json={"constraints": ["body_harmony"]},
        )

        args = client.insert_one.call_args
        payload = args[0][1]
        self.assertEqual("garment", payload["resolved_mode"])
        self.assertEqual(["shirt"], payload["requested_garment_types_json"])

    def test_update_user_profile(self) -> None:
        client = Mock()
        client.update_one.return_value = {"id": "u1"}
        repo = ConversationRepository(client)

        profile = {"sizes": {"top_size": "M"}}
        repo.update_user_profile("u1", profile)

        args = client.update_one.call_args
        self.assertEqual("users", args[0][0])
        patch = args[1]["patch"]
        self.assertEqual(profile, patch["profile_json"])
        self.assertIn("profile_updated_at", patch)

    def test_create_checkout_preparation(self) -> None:
        client = Mock()
        client.insert_one.return_value = {"id": "cp1"}
        repo = ConversationRepository(client)

        repo.create_checkout_preparation(
            conversation_id="c1",
            turn_id="t1",
            recommendation_run_id="run1",
            user_id="u1",
            status="ready",
            cart_payload_json=[{"garment_id": "g1"}],
            pricing_json={"subtotal": 2000},
        )

        args = client.insert_one.call_args
        self.assertEqual("checkout_preparations", args[0][0])
        payload = args[0][1]
        self.assertEqual("ready", payload["status"])
        self.assertEqual("run1", payload["recommendation_run_id"])

    def test_insert_checkout_preparation_items(self) -> None:
        client = Mock()
        client.insert_many.return_value = [{"id": "cpi1"}]
        repo = ConversationRepository(client)

        repo.insert_checkout_preparation_items(
            "cp1",
            [{"rank": 1, "garment_id": "g1", "qty": 1, "unit_price": 2000, "discount": 0, "final_price": 2000}],
        )

        args = client.insert_many.call_args
        self.assertEqual("checkout_preparation_items", args[0][0])
        rows = args[0][1]
        self.assertEqual(1, len(rows))
        self.assertEqual("cp1", rows[0]["checkout_preparation_id"])

    def test_get_checkout_preparation(self) -> None:
        client = Mock()
        client.select_one.return_value = {"id": "cp1", "status": "ready"}
        repo = ConversationRepository(client)

        out = repo.get_checkout_preparation("cp1")
        self.assertEqual("ready", out["status"])

    def test_get_checkout_preparation_items(self) -> None:
        client = Mock()
        client.select_many.return_value = [{"id": "cpi1", "rank": 1}]
        repo = ConversationRepository(client)

        out = repo.get_checkout_preparation_items("cp1")
        self.assertEqual(1, len(out))


# ---------------------------------------------------------------------------
# Orchestrator tests - mode routing
# ---------------------------------------------------------------------------

class OrchestratorModeRoutingTests(unittest.TestCase):
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

        orchestrator = ConversationOrchestrator(repo=repo, catalog_csv_path="data/output/enriched.csv")
        visual = self._build_visual_profile()
        visual_log = {
            "image_artifact": {"source_type": "file", "source": "/tmp/user.jpg", "stored_path": "/tmp/user.jpg"},
            "model": "gpt-5.2",
            "request": {},
            "response": {},
            "reasoning_notes": [],
        }
        text_log = {"model": "gpt-5-mini", "request": {}, "response": {}}
        orchestrator.profile_agent = Mock(infer_visual=Mock(return_value=(visual, visual_log)))
        orchestrator.intent_agent = Mock(
            infer_text=Mock(return_value=({"occasion": "work_mode", "archetype": "classic"}, text_log))
        )
        orchestrator.recommendation_agent = Mock(
            recommend=Mock(return_value={
                "items": [],
                "meta": {"total_catalog_rows": 20, "filtered_rows": 5, "failed_rows": 15, "ranked_rows": 5, "returned_rows": 0},
            })
        )
        orchestrator.stylist_agent = Mock(build_response_message=Mock(return_value=("msg", False, "")))
        return orchestrator

    def test_auto_mode_with_target_garment_resolves_to_garment(self) -> None:
        repo = Mock()
        orchestrator = self._setup_orchestrator(repo)

        out = orchestrator.process_turn(
            conversation_id="c1",
            external_user_id="user_1",
            message="Show me white shirts",
            image_refs=["/tmp/user.jpg"],
            strictness="balanced",
            hard_filter_profile="rl_ready_minimal",
            max_results=5,
            mode_preference="auto",
            target_garment_type="shirt",
        )

        self.assertEqual("garment", out["resolved_mode"])
        self.assertTrue(out["complete_the_look_offer"])

    def test_auto_mode_without_target_garment_resolves_to_outfit(self) -> None:
        repo = Mock()
        orchestrator = self._setup_orchestrator(repo)

        out = orchestrator.process_turn(
            conversation_id="c1",
            external_user_id="user_1",
            message="Need office looks",
            image_refs=["/tmp/user.jpg"],
            strictness="balanced",
            hard_filter_profile="rl_ready_minimal",
            max_results=5,
            mode_preference="auto",
        )

        self.assertEqual("outfit", out["resolved_mode"])
        self.assertFalse(out["complete_the_look_offer"])

    def test_explicit_garment_mode(self) -> None:
        repo = Mock()
        orchestrator = self._setup_orchestrator(repo)

        out = orchestrator.process_turn(
            conversation_id="c1",
            external_user_id="user_1",
            message="Need office looks",
            image_refs=["/tmp/user.jpg"],
            strictness="balanced",
            hard_filter_profile="rl_ready_minimal",
            max_results=5,
            mode_preference="garment",
        )

        self.assertEqual("garment", out["resolved_mode"])
        self.assertTrue(out["complete_the_look_offer"])

    def test_explicit_outfit_mode(self) -> None:
        repo = Mock()
        orchestrator = self._setup_orchestrator(repo)

        out = orchestrator.process_turn(
            conversation_id="c1",
            external_user_id="user_1",
            message="Need office looks",
            image_refs=["/tmp/user.jpg"],
            strictness="balanced",
            hard_filter_profile="rl_ready_minimal",
            max_results=5,
            mode_preference="outfit",
        )

        self.assertEqual("outfit", out["resolved_mode"])
        self.assertFalse(out["complete_the_look_offer"])

    def test_resolved_mode_persisted_to_run(self) -> None:
        repo = Mock()
        orchestrator = self._setup_orchestrator(repo)

        orchestrator.process_turn(
            conversation_id="c1",
            external_user_id="user_1",
            message="Show me shirts",
            image_refs=["/tmp/user.jpg"],
            strictness="balanced",
            hard_filter_profile="rl_ready_minimal",
            max_results=5,
            mode_preference="garment",
        )

        run_kwargs = repo.create_recommendation_run.call_args.kwargs
        self.assertEqual("garment", run_kwargs["resolved_mode"])

    def test_resolved_mode_persisted_to_turn(self) -> None:
        repo = Mock()
        orchestrator = self._setup_orchestrator(repo)

        orchestrator.process_turn(
            conversation_id="c1",
            external_user_id="user_1",
            message="Need looks",
            image_refs=["/tmp/user.jpg"],
            strictness="balanced",
            hard_filter_profile="rl_ready_minimal",
            max_results=5,
            mode_preference="outfit",
        )

        finalize_kwargs = repo.finalize_turn.call_args.kwargs
        self.assertEqual("outfit", finalize_kwargs["resolved_mode"])

    def test_style_constraints_applied_in_response(self) -> None:
        repo = Mock()
        orchestrator = self._setup_orchestrator(repo)

        out = orchestrator.process_turn(
            conversation_id="c1",
            external_user_id="user_1",
            message="Need looks",
            image_refs=["/tmp/user.jpg"],
            strictness="balanced",
            hard_filter_profile="rl_ready_minimal",
            max_results=5,
        )

        self.assertIn("body_harmony", out["style_constraints_applied"])

    def test_profile_fields_used_in_response(self) -> None:
        repo = Mock()
        orchestrator = self._setup_orchestrator(repo)

        out = orchestrator.process_turn(
            conversation_id="c1",
            external_user_id="user_1",
            message="Need looks",
            image_refs=["/tmp/user.jpg"],
            strictness="balanced",
            hard_filter_profile="rl_ready_minimal",
            max_results=5,
        )

        self.assertIsInstance(out["profile_fields_used"], list)
        self.assertTrue(len(out["profile_fields_used"]) > 0)


# ---------------------------------------------------------------------------
# Orchestrator tests - checkout preparation
# ---------------------------------------------------------------------------

class OrchestratorCheckoutTests(unittest.TestCase):
    def test_prepare_checkout_happy_path(self) -> None:
        repo = Mock()
        repo.get_or_create_user.return_value = {"id": "user_uuid"}
        repo.get_conversation.return_value = {"id": "c1", "user_id": "user_uuid"}
        repo.get_recommendation_run.return_value = {"id": "run1"}
        repo.get_recommendation_items.return_value = [
            {"garment_id": "g1", "title": "Shirt", "score": 2000},
            {"garment_id": "g2", "title": "Pants", "score": 3000},
        ]
        repo.get_latest_turn.return_value = {"id": "t1"}
        repo.create_checkout_preparation.return_value = {"id": "cp1"}
        repo.insert_checkout_preparation_items.return_value = []

        orchestrator = ConversationOrchestrator(repo=repo, catalog_csv_path="data/output/enriched.csv")

        out = orchestrator.prepare_checkout(
            conversation_id="c1",
            external_user_id="user_1",
            recommendation_run_id="run1",
            selected_item_ids=["g1", "g2"],
        )

        self.assertEqual("cp1", out["checkout_prep_id"])
        self.assertEqual("ready", out["status"])
        self.assertEqual(2, len(out["cart_items"]))
        self.assertEqual("INR", out["currency"])
        repo.create_checkout_preparation.assert_called_once()
        repo.insert_checkout_preparation_items.assert_called_once()

    def test_prepare_checkout_over_budget(self) -> None:
        repo = Mock()
        repo.get_or_create_user.return_value = {"id": "user_uuid"}
        repo.get_conversation.return_value = {"id": "c1", "user_id": "user_uuid"}
        repo.get_recommendation_run.return_value = {"id": "run1"}
        repo.get_recommendation_items.return_value = [
            {"garment_id": "g1", "title": "Shirt", "score": 3000},
            {"garment_id": "g2", "title": "Pants", "score": 4000},
        ]
        repo.get_latest_turn.return_value = {"id": "t1"}
        repo.create_checkout_preparation.return_value = {"id": "cp1"}
        repo.insert_checkout_preparation_items.return_value = []

        orchestrator = ConversationOrchestrator(repo=repo, catalog_csv_path="data/output/enriched.csv")

        out = orchestrator.prepare_checkout(
            conversation_id="c1",
            external_user_id="user_1",
            recommendation_run_id="run1",
            selected_item_ids=["g1", "g2"],
            budget_cap=5000,
        )

        self.assertEqual("needs_user_action", out["status"])
        self.assertIn("over_budget", out["validation_notes"])

    def test_prepare_checkout_wrong_user(self) -> None:
        repo = Mock()
        repo.get_or_create_user.return_value = {"id": "user_uuid"}
        repo.get_conversation.return_value = {"id": "c1", "user_id": "other_uuid"}

        orchestrator = ConversationOrchestrator(repo=repo, catalog_csv_path="data/output/enriched.csv")

        with self.assertRaises(ValueError):
            orchestrator.prepare_checkout(
                conversation_id="c1",
                external_user_id="user_1",
                recommendation_run_id="run1",
                selected_item_ids=["g1"],
            )

    def test_prepare_checkout_missing_run(self) -> None:
        repo = Mock()
        repo.get_or_create_user.return_value = {"id": "user_uuid"}
        repo.get_conversation.return_value = {"id": "c1", "user_id": "user_uuid"}
        repo.get_recommendation_run.return_value = None

        orchestrator = ConversationOrchestrator(repo=repo, catalog_csv_path="data/output/enriched.csv")

        with self.assertRaises(ValueError):
            orchestrator.prepare_checkout(
                conversation_id="c1",
                external_user_id="user_1",
                recommendation_run_id="run1",
                selected_item_ids=["g1"],
            )

    def test_get_checkout_preparation(self) -> None:
        repo = Mock()
        repo.get_checkout_preparation.return_value = {
            "id": "cp1",
            "status": "ready",
            "pricing_json": {"subtotal": 2000, "discount_total": 0, "final_total": 2000, "currency": "INR"},
            "validation_json": {"notes": ["stock_revalidated"]},
            "checkout_ref": "",
        }
        repo.get_checkout_preparation_items.return_value = [
            {"garment_id": "g1", "title": "Shirt", "qty": 1, "unit_price": 2000, "discount": 0, "final_price": 2000},
        ]

        orchestrator = ConversationOrchestrator(repo=repo, catalog_csv_path="data/output/enriched.csv")

        out = orchestrator.get_checkout_preparation("cp1")

        self.assertEqual("cp1", out["checkout_prep_id"])
        self.assertEqual("ready", out["status"])
        self.assertEqual(1, len(out["cart_items"]))
        self.assertEqual(2000, out["subtotal"])

    def test_get_checkout_preparation_not_found(self) -> None:
        repo = Mock()
        repo.get_checkout_preparation.return_value = None

        orchestrator = ConversationOrchestrator(repo=repo, catalog_csv_path="data/output/enriched.csv")

        with self.assertRaises(ValueError):
            orchestrator.get_checkout_preparation("nonexistent")


# ---------------------------------------------------------------------------
# Orchestrator tests - initial profile
# ---------------------------------------------------------------------------

class OrchestratorInitialProfileTests(unittest.TestCase):
    def test_create_conversation_with_initial_profile(self) -> None:
        repo = Mock()
        repo.get_or_create_user.return_value = {"id": "user_uuid"}
        repo.create_conversation.return_value = {"id": "c1", "status": "active", "created_at": "2026-01-01"}
        repo.update_user_profile.return_value = {"id": "user_uuid"}

        orchestrator = ConversationOrchestrator(repo=repo, catalog_csv_path="data/output/enriched.csv")

        out = orchestrator.create_conversation(
            external_user_id="user_1",
            initial_profile={"sizes": {"top_size": "M"}},
        )

        self.assertEqual("c1", out["conversation_id"])
        repo.update_user_profile.assert_called_once_with("user_uuid", {"sizes": {"top_size": "M"}})

    def test_create_conversation_without_initial_profile(self) -> None:
        repo = Mock()
        repo.get_or_create_user.return_value = {"id": "user_uuid"}
        repo.create_conversation.return_value = {"id": "c1", "status": "active", "created_at": "2026-01-01"}

        orchestrator = ConversationOrchestrator(repo=repo, catalog_csv_path="data/output/enriched.csv")

        out = orchestrator.create_conversation(external_user_id="user_1")

        self.assertEqual("c1", out["conversation_id"])
        repo.update_user_profile.assert_not_called()


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------

class ApiCheckoutEndpointTests(unittest.TestCase):
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

            from conversation_platform.api import create_app
            app = create_app()
            return TestClient(app), mock_orch

    def test_checkout_prepare_endpoint_exists(self) -> None:
        client, mock_orch = self._create_test_app()
        mock_orch.prepare_checkout.return_value = {
            "checkout_prep_id": "cp1",
            "status": "ready",
            "cart_items": [],
            "subtotal": 0,
            "discount_total": 0,
            "final_total": 0,
            "currency": "INR",
            "checkout_url_or_token": "",
            "validation_notes": [],
        }

        resp = client.post(
            "/v1/conversations/c1/checkout/prepare",
            json={
                "user_id": "u1",
                "recommendation_run_id": "run1",
                "selected_item_ids": ["g1"],
            },
        )
        self.assertEqual(200, resp.status_code)
        data = resp.json()
        self.assertEqual("cp1", data["checkout_prep_id"])
        self.assertEqual("ready", data["status"])

    def test_get_checkout_preparation_endpoint_exists(self) -> None:
        client, mock_orch = self._create_test_app()
        mock_orch.get_checkout_preparation.return_value = {
            "checkout_prep_id": "cp1",
            "status": "ready",
            "cart_items": [],
            "subtotal": 0,
            "discount_total": 0,
            "final_total": 0,
            "currency": "INR",
            "checkout_url_or_token": "",
            "validation_notes": [],
        }

        resp = client.get("/v1/checkout/preparations/cp1")
        self.assertEqual(200, resp.status_code)
        data = resp.json()
        self.assertEqual("cp1", data["checkout_prep_id"])

    def test_turn_endpoint_accepts_new_fields(self) -> None:
        client, mock_orch = self._create_test_app()
        mock_orch.process_turn.return_value = {
            "conversation_id": "c1",
            "turn_id": "t1",
            "assistant_message": "msg",
            "resolved_context": {"occasion": "", "archetype": "", "gender": "", "age": ""},
            "profile_snapshot_id": None,
            "recommendation_run_id": None,
            "resolved_mode": "garment",
            "complete_the_look_offer": True,
            "style_constraints_applied": ["body_harmony"],
            "profile_fields_used": ["HeightCategory"],
            "recommendations": [],
            "needs_clarification": True,
            "clarifying_question": "upload image",
        }

        resp = client.post(
            "/v1/conversations/c1/turns",
            json={
                "user_id": "u1",
                "message": "Show me shirts",
                "mode_preference": "garment",
                "target_garment_type": "shirt",
                "autonomy_level": "suggest",
                "size_overrides": {"top_size": "M"},
            },
        )
        self.assertEqual(200, resp.status_code)
        data = resp.json()
        self.assertEqual("garment", data["resolved_mode"])
        self.assertTrue(data["complete_the_look_offer"])
        self.assertEqual(["body_harmony"], data["style_constraints_applied"])

    def test_create_conversation_accepts_initial_profile(self) -> None:
        client, mock_orch = self._create_test_app()
        mock_orch.create_conversation.return_value = {
            "conversation_id": "c1",
            "user_id": "u1",
            "status": "active",
            "created_at": "2026-01-01",
        }

        resp = client.post(
            "/v1/conversations",
            json={
                "user_id": "u1",
                "initial_profile": {
                    "sizes": {"top_size": "M"},
                    "budget_preferences": {"soft_cap": 4000},
                },
            },
        )
        self.assertEqual(200, resp.status_code)
        call_kwargs = mock_orch.create_conversation.call_args.kwargs
        self.assertIsNotNone(call_kwargs.get("initial_profile"))
        self.assertEqual({"top_size": "M"}, call_kwargs["initial_profile"]["sizes"])


# ---------------------------------------------------------------------------
# DB Migration sanity
# ---------------------------------------------------------------------------

class MigrationFileTests(unittest.TestCase):
    def test_phase1_migration_file_exists(self) -> None:
        path = ROOT / "supabase" / "migrations" / "20260228120000_agentic_commerce_phase1.sql"
        self.assertTrue(path.exists(), f"Migration file not found: {path}")

    def test_phase1_migration_contains_checkout_tables(self) -> None:
        path = ROOT / "supabase" / "migrations" / "20260228120000_agentic_commerce_phase1.sql"
        content = path.read_text()
        self.assertIn("checkout_preparations", content)
        self.assertIn("checkout_preparation_items", content)
        self.assertIn("profile_json", content)
        self.assertIn("profile_updated_at", content)
        self.assertIn("mode_preference", content)
        self.assertIn("resolved_mode", content)
        self.assertIn("autonomy_level", content)
        self.assertIn("requested_garment_types_json", content)
        self.assertIn("style_constraints_json", content)


if __name__ == "__main__":
    unittest.main()
