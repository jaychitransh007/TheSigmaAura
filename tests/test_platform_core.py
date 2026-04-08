import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
for p in (
    ROOT,
    ROOT / "modules" / "platform_core" / "src",
):
    sp = str(p)
    if sp not in sys.path:
        sys.path.insert(0, sp)


from platform_core.api_schemas import CreateTurnRequest
from platform_core.config import load_config
from platform_core.fallback_messages import graceful_policy_message
from platform_core.image_moderation import ImageModerationService, image_block_message
from platform_core.restricted_categories import detect_restricted_category, detect_restricted_record
from platform_core.repositories import ConversationRepository


class PlatformCoreTests(unittest.TestCase):
    def test_turn_request_minimal_contract(self) -> None:
        req = CreateTurnRequest(user_id="u1", message="Need smart casual office wear")
        self.assertEqual("u1", req.user_id)
        self.assertEqual("Need smart casual office wear", req.message)
        self.assertEqual("web", req.channel)

    def test_image_moderation_blocks_explicit_filename_heuristically(self) -> None:
        service = ImageModerationService()

        result = service.moderate_bytes(
            file_data=b"fake-bytes",
            filename="nude_selfie.jpg",
            content_type="image/jpeg",
            purpose="onboarding_full_body",
        )

        self.assertFalse(result.allowed)
        self.assertEqual("explicit_nudity", result.reason_code)

    def test_image_moderation_blocks_minor_image_heuristically(self) -> None:
        service = ImageModerationService()

        result = service.moderate_bytes(
            file_data=b"fake-bytes",
            filename="child_selfie.jpg",
            content_type="image/jpeg",
            purpose="onboarding_full_body",
        )

        self.assertFalse(result.allowed)
        self.assertEqual("unsafe_minor", result.reason_code)
        self.assertEqual("Images of minors are not allowed.", image_block_message(result.reason_code))

    def test_image_moderation_blocks_unsafe_image_heuristically(self) -> None:
        service = ImageModerationService()

        result = service.moderate_url(
            image_url="https://img.example/gore_scene.jpg",
            purpose="whatsapp_image_input",
        )

        self.assertFalse(result.allowed)
        self.assertEqual("unsafe_image", result.reason_code)
        self.assertEqual("Unsafe or graphic images are not allowed.", image_block_message(result.reason_code))

    def test_restricted_category_detector_flags_lingerie_terms(self) -> None:
        matched = detect_restricted_category("Silk bralette set", "https://store.example/lingerie-item")
        self.assertIn(matched, {"bralette", "lingerie"})

    def test_restricted_record_detector_uses_catalog_fields(self) -> None:
        matched = detect_restricted_record(
            {
                "title": "Silk set",
                "garment_category": "intimates",
                "garment_subtype": "bralette",
            }
        )
        self.assertEqual("bralette", matched)

    def test_graceful_policy_message_returns_actionable_copy(self) -> None:
        self.assertIn("clothed", graceful_policy_message("explicit_nudity"))
        self.assertIn("full-body photo", graceful_policy_message("missing_person_image"))
        self.assertIn("cleaner product image", graceful_policy_message("low_detail_output"))

    def test_load_config_accepts_supabase_cli_env_vars(self) -> None:
        with patch("platform_core.config._load_dotenv", return_value=None), patch.dict(
            "os.environ",
            {
                "API_URL": "http://127.0.0.1:55321",
                "SERVICE_ROLE_KEY": "service-role-jwt",
            },
            clear=True,
        ):
            cfg = load_config()
        self.assertEqual("http://127.0.0.1:55321/rest/v1", cfg.supabase_rest_url)
        self.assertEqual("service-role-jwt", cfg.supabase_service_role_key)
        self.assertEqual(12, cfg.retrieval_match_count)

    def test_create_catalog_interaction_persists_expected_payload(self) -> None:
        client = unittest.mock.Mock()
        client.insert_one.return_value = {"id": "i1"}
        repo = ConversationRepository(client)

        out = repo.create_catalog_interaction(
            user_id="user-1",
            product_id="sku-1",
            interaction_type="click",
            conversation_id="c1",
            turn_id="t1",
            source_channel="web",
            source_surface="chat_card",
            metadata_json={"position": 1},
        )

        self.assertEqual({"id": "i1"}, out)
        payload = client.insert_one.call_args.args[1]
        self.assertEqual("user-1", payload["user_id"])
        self.assertEqual("sku-1", payload["product_id"])
        self.assertEqual("click", payload["interaction_type"])
        self.assertEqual("web", payload["source_channel"])
        self.assertEqual("chat_card", payload["source_surface"])
        self.assertEqual({"position": 1}, payload["metadata_json"])

    def test_list_catalog_interactions_filters_by_user_and_type(self) -> None:
        client = unittest.mock.Mock()
        client.select_many.return_value = [{"id": "i1"}]
        repo = ConversationRepository(client)

        rows = repo.list_catalog_interactions("user-1", interaction_type="click", limit=5)

        self.assertEqual([{"id": "i1"}], rows)
        kwargs = client.select_many.call_args.kwargs
        self.assertEqual("eq.user-1", kwargs["filters"]["user_id"])
        self.assertEqual("eq.click", kwargs["filters"]["interaction_type"])
        self.assertEqual(5, kwargs["limit"])

    def test_get_latest_conversation_for_user_filters_active_rows(self) -> None:
        client = unittest.mock.Mock()
        client.select_many.return_value = [{"id": "c-latest"}]
        repo = ConversationRepository(client)

        row = repo.get_latest_conversation_for_user("user-db-1")

        self.assertEqual({"id": "c-latest"}, row)
        kwargs = client.select_many.call_args.kwargs
        self.assertEqual("eq.user-db-1", kwargs["filters"]["user_id"])
        self.assertEqual("eq.active", kwargs["filters"]["status"])
        self.assertEqual("updated_at.desc", kwargs["order"])
        self.assertEqual(1, kwargs["limit"])

    def test_merge_external_user_identity_reassigns_conversations_and_history(self) -> None:
        client = unittest.mock.Mock()
        client.select_one.side_effect = [
            {"id": "canonical-db", "external_user_id": "user_verified_123"},
            {"id": "alias-db", "external_user_id": "whatsapp:+15551234567"},
        ]
        repo = ConversationRepository(client)

        row = repo.merge_external_user_identity(
            canonical_external_user_id="user_verified_123",
            alias_external_user_id="whatsapp:+15551234567",
        )

        self.assertEqual("canonical-db", row["id"])
        self.assertEqual(5, client.update_one.call_count)
        first_update = client.update_one.call_args_list[0]
        self.assertEqual("conversations", first_update.args[0])
        self.assertEqual("eq.alias-db", first_update.kwargs["filters"]["user_id"])
        self.assertEqual("canonical-db", first_update.kwargs["patch"]["user_id"])
        history_tables = [call.args[0] for call in client.update_one.call_args_list[1:]]
        self.assertEqual(
            [
                "catalog_interaction_history",
                "confidence_history",
                "policy_event_log",
                "dependency_validation_events",
            ],
            history_tables,
        )

    def test_merge_external_user_identity_noops_when_alias_missing(self) -> None:
        client = unittest.mock.Mock()
        client.select_one.side_effect = [
            {"id": "canonical-db", "external_user_id": "user_verified_123"},
            None,
        ]
        repo = ConversationRepository(client)

        row = repo.merge_external_user_identity(
            canonical_external_user_id="user_verified_123",
            alias_external_user_id="whatsapp:+15551234567",
        )

        self.assertEqual("canonical-db", row["id"])
        client.update_one.assert_not_called()

    def test_create_confidence_history_persists_expected_payload(self) -> None:
        client = unittest.mock.Mock()
        client.insert_one.return_value = {"id": "c1"}
        repo = ConversationRepository(client)

        out = repo.create_confidence_history(
            user_id="user-1",
            confidence_type="profile",
            score_pct=82,
            conversation_id="conv-1",
            turn_id="turn-1",
            source_channel="web",
            factors_json=[{"factor": "profile_complete", "score": 20}],
            metadata_json={"primary_intent": "garment_evaluation"},
        )

        self.assertEqual({"id": "c1"}, out)
        payload = client.insert_one.call_args.args[1]
        self.assertEqual("user-1", payload["user_id"])
        self.assertEqual("profile", payload["confidence_type"])
        self.assertEqual(82, payload["score_pct"])
        self.assertEqual([{"factor": "profile_complete", "score": 20}], payload["factors_json"])

    def test_list_confidence_history_filters_by_user_and_type(self) -> None:
        client = unittest.mock.Mock()
        client.select_many.return_value = [{"id": "c1"}]
        repo = ConversationRepository(client)

        rows = repo.list_confidence_history("user-1", confidence_type="recommendation", limit=4)

        self.assertEqual([{"id": "c1"}], rows)
        kwargs = client.select_many.call_args.kwargs
        self.assertEqual("eq.user-1", kwargs["filters"]["user_id"])
        self.assertEqual("eq.recommendation", kwargs["filters"]["confidence_type"])
        self.assertEqual(4, kwargs["limit"])

    def test_create_policy_event_persists_expected_payload(self) -> None:
        client = unittest.mock.Mock()
        client.insert_one.return_value = {"id": "p1"}
        repo = ConversationRepository(client)

        out = repo.create_policy_event(
            policy_event_type="feedback_guardrail",
            input_class="feedback_submission",
            reason_code="unresolved_feedback_items",
            decision="blocked",
            user_id="user-1",
            conversation_id="conv-1",
            turn_id="turn-1",
            source_channel="web",
            metadata_json={"outfit_rank": 1},
        )

        self.assertEqual({"id": "p1"}, out)
        payload = client.insert_one.call_args.args[1]
        self.assertEqual("feedback_guardrail", payload["policy_event_type"])
        self.assertEqual("feedback_submission", payload["input_class"])
        self.assertEqual("unresolved_feedback_items", payload["reason_code"])
        self.assertEqual("blocked", payload["decision"])

    def test_list_policy_events_filters_by_user_and_decision(self) -> None:
        client = unittest.mock.Mock()
        client.select_many.return_value = [{"id": "p1"}]
        repo = ConversationRepository(client)

        rows = repo.list_policy_events(user_id="user-1", decision="blocked", limit=2)

        self.assertEqual([{"id": "p1"}], rows)
        kwargs = client.select_many.call_args.kwargs
        self.assertEqual("eq.user-1", kwargs["filters"]["user_id"])
        self.assertEqual("eq.blocked", kwargs["filters"]["decision"])
        self.assertEqual(2, kwargs["limit"])


if __name__ == "__main__":
    unittest.main()
