import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
for p in (
    ROOT,
    ROOT / "modules" / "platform_core" / "src",
    ROOT / "modules" / "user_profiler" / "src",
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

    def test_list_recent_user_actions_returns_chronological_timeline_with_query_and_attrs(self) -> None:
        """The architect's episodic-memory input: feedback events joined to
        the user_query (from conversation_turns) and to the garment's
        catalog attributes. Each row should land with the shape the
        architect prompt describes: event_type, created_at, turn_id,
        user_query, item dict."""
        client = unittest.mock.Mock()

        def _select_many(table, **kwargs):
            if table == "feedback_events":
                return [
                    {"garment_id": "g1", "event_type": "dislike", "created_at": "2026-05-04T10:00:00Z", "turn_id": "t1"},
                    {"garment_id": "g2", "event_type": "like",    "created_at": "2026-05-03T08:00:00Z", "turn_id": "t2"},
                ]
            if table == "catalog_enriched":
                # Mirror the real DB schema: enrichment attributes are
                # PascalCase, only `title` and `product_id` are lowercase.
                # The repo method must translate these to snake_case keys
                # for the architect prompt.
                return [
                    {"product_id": "g1", "title": "Solid Navy Blazer", "PrimaryColor": "navy",
                     "ColorTemperature": "cool", "PatternType": "solid", "FitType": "tailored",
                     "SilhouetteType": "structured", "EmbellishmentLevel": "none",
                     "FormalityLevel": "business_casual", "GarmentSubtype": "blazer",
                     "OccasionFit": "office"},
                    {"product_id": "g2", "title": "Warm Tonal Sweater", "PrimaryColor": "camel",
                     "ColorTemperature": "warm", "PatternType": "solid", "FitType": "relaxed",
                     "SilhouetteType": "soft", "EmbellishmentLevel": "none",
                     "FormalityLevel": "smart_casual", "GarmentSubtype": "sweater",
                     "OccasionFit": "weekend"},
                ]
            if table == "conversation_turns":
                return [
                    {"id": "t1", "user_message": "what should I wear to the office"},
                    {"id": "t2", "user_message": "find me a casual weekend outfit"},
                ]
            return []
        client.select_many.side_effect = _select_many
        repo = ConversationRepository(client)

        rows = repo.list_recent_user_actions("user-1")

        self.assertEqual(2, len(rows))
        d, l = rows[0], rows[1]
        # Order preserved from feedback_events (newest first per repo's order=desc).
        self.assertEqual("dislike", d["event_type"])
        self.assertEqual("t1", d["turn_id"])
        self.assertEqual("what should I wear to the office", d["user_query"])
        self.assertEqual("Solid Navy Blazer", d["item"]["title"])
        # Output keys are snake_case for the prompt, even though DB cols
        # are PascalCase. This is the contract the architect expects.
        self.assertEqual("cool", d["item"]["color_temperature"])
        self.assertEqual("solid", d["item"]["pattern_type"])
        self.assertEqual("navy", d["item"]["primary_color"])
        self.assertEqual("blazer", d["item"]["garment_subtype"])
        self.assertEqual("office", d["item"]["occasion_fit"])
        self.assertEqual("like", l["event_type"])
        self.assertEqual("find me a casual weekend outfit", l["user_query"])
        self.assertEqual("warm", l["item"]["color_temperature"])
        # The catalog_enriched query selects the PascalCase DB columns,
        # not the snake_case prompt keys. Verify so we don't regress to
        # the silent-failure mode (PostgREST 400 → except → empty).
        catalog_calls = [c for c in client.select_many.call_args_list if c.args[0] == "catalog_enriched"]
        self.assertEqual(1, len(catalog_calls))
        ce_cols = catalog_calls[0].kwargs["columns"]
        self.assertIn("PrimaryColor", ce_cols)
        self.assertIn("ColorTemperature", ce_cols)
        self.assertIn("PatternType", ce_cols)
        self.assertNotIn("primary_color", ce_cols)
        self.assertNotIn("color_temperature", ce_cols)
        # The feedback_events query carries the lookback cutoff and limits.
        feedback_calls = [c for c in client.select_many.call_args_list if c.args[0] == "feedback_events"]
        self.assertEqual(1, len(feedback_calls))
        ff_kwargs = feedback_calls[0].kwargs
        self.assertEqual("eq.user-1", ff_kwargs["filters"]["user_id"])
        self.assertEqual("in.(like,dislike)", ff_kwargs["filters"]["event_type"])
        self.assertTrue(ff_kwargs["filters"]["created_at"].startswith("gte."))

    def test_list_recent_user_actions_returns_empty_on_cold_start_or_db_error(self) -> None:
        """Cold-start users (no events yet) and any DB error must yield
        ``[]`` so the architect's episodic-memory branch becomes a no-op
        instead of raising."""
        client = unittest.mock.Mock()
        repo = ConversationRepository(client)

        client.select_many.return_value = []
        self.assertEqual([], repo.list_recent_user_actions("cold-start-user"))

        client.select_many.side_effect = RuntimeError("supabase down")
        self.assertEqual([], repo.list_recent_user_actions("user-1"))

    def test_list_recent_user_actions_skips_events_without_hydratable_item(self) -> None:
        """If a garment_id is no longer in ``catalog_enriched`` (catalog
        has been re-ingested or the row is row_status='removed'), the
        event is skipped — opaque IDs without attributes don't help the
        architect find patterns."""
        client = unittest.mock.Mock()

        def _select_many(table, **kwargs):
            if table == "feedback_events":
                return [
                    {"garment_id": "g1", "event_type": "dislike", "created_at": "2026-05-04T10:00:00Z", "turn_id": "t1"},
                    {"garment_id": "g_missing", "event_type": "dislike", "created_at": "2026-05-04T11:00:00Z", "turn_id": "t1"},
                ]
            if table == "catalog_enriched":
                # PascalCase mirrors the real DB schema (see the chronological
                # test above). Only g1 hydrates; g_missing is gone.
                return [
                    {"product_id": "g1", "title": "Solid Navy", "PrimaryColor": "navy",
                     "ColorTemperature": "cool", "PatternType": "solid", "FitType": "tailored",
                     "SilhouetteType": "structured", "EmbellishmentLevel": "none",
                     "FormalityLevel": "business_casual", "GarmentSubtype": "blazer",
                     "OccasionFit": "office"},
                ]
            if table == "conversation_turns":
                return [{"id": "t1", "user_message": "office"}]
            return []
        client.select_many.side_effect = _select_many
        repo = ConversationRepository(client)

        rows = repo.list_recent_user_actions("user-1")
        self.assertEqual(1, len(rows))
        self.assertEqual("Solid Navy", rows[0]["item"]["title"])

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


class RequestContextTests(unittest.TestCase):
    """Item 2 (May 1, 2026): contextvar-based correlation IDs flow into log
    records and observability inserts."""

    def setUp(self) -> None:
        from platform_core import request_context as rc
        self.rc = rc
        # Clear any leaked state from a prior test in the same thread.
        rc.set_request_id("")
        rc.set_turn_id("")
        rc.set_conversation_id("")
        rc.set_external_user_id("")

    def tearDown(self) -> None:
        self.rc.set_request_id("")
        self.rc.set_turn_id("")
        self.rc.set_conversation_id("")
        self.rc.set_external_user_id("")

    def test_setters_and_getters_round_trip(self) -> None:
        self.rc.set_request_id("req-xyz")
        self.rc.set_turn_id("t-42")
        self.rc.set_conversation_id("c-7")
        self.rc.set_external_user_id("user-test")
        self.assertEqual("req-xyz", self.rc.get_request_id())
        self.assertEqual("t-42", self.rc.get_turn_id())
        self.assertEqual("c-7", self.rc.get_conversation_id())
        self.assertEqual("user-test", self.rc.get_external_user_id())

    def test_snapshot_returns_all_four_ids(self) -> None:
        self.rc.set_request_id("rid")
        self.rc.set_turn_id("tid")
        snap = self.rc.snapshot()
        self.assertEqual("rid", snap["request_id"])
        self.assertEqual("tid", snap["turn_id"])
        self.assertEqual("", snap["conversation_id"])

    def test_filter_injects_contextvars_into_log_record(self) -> None:
        import logging as _logging
        self.rc.set_request_id("req-abc")
        self.rc.set_turn_id("t-99")
        self.rc.set_conversation_id("c-3")
        self.rc.set_external_user_id("user-u1")
        record = _logging.LogRecord(
            "test", _logging.INFO, "f", 1, "msg %s", ("arg",), None,
        )
        f = self.rc.RequestContextFilter()
        self.assertTrue(f.filter(record))
        self.assertEqual("req-abc", record.request_id)
        self.assertEqual("t-99", record.turn_id)
        self.assertEqual("c-3", record.conversation_id)
        self.assertEqual("user-u1", record.external_user_id)

    def test_filter_emits_empty_strings_when_unset(self) -> None:
        import logging as _logging
        record = _logging.LogRecord(
            "test", _logging.INFO, "f", 1, "msg", (), None,
        )
        f = self.rc.RequestContextFilter()
        f.filter(record)
        self.assertEqual("", record.request_id)
        self.assertEqual("", record.turn_id)


class RepositoryRequestIdStampingTests(unittest.TestCase):
    """Item 2 (May 1, 2026): repo helpers auto-stamp request_id from the
    contextvar so observability rows correlate to logs without explicit
    threading at every callsite."""

    def setUp(self) -> None:
        from platform_core import request_context as rc
        rc.set_request_id("")

    def tearDown(self) -> None:
        from platform_core import request_context as rc
        rc.set_request_id("")

    def test_log_model_call_stamps_active_request_id(self) -> None:
        from platform_core import request_context as rc
        rc.set_request_id("req-from-context")
        client = unittest.mock.Mock()
        client.insert_one.return_value = {"id": "m1"}
        repo = ConversationRepository(client)
        repo.log_model_call(
            conversation_id="c1", turn_id="t1",
            service="agentic_application", call_type="copilot_planner",
            model="gpt-5.4",
            request_json={}, response_json={}, reasoning_notes=[],
        )
        payload = client.insert_one.call_args.args[1]
        self.assertEqual("req-from-context", payload["request_id"])

    def test_log_model_call_explicit_request_id_overrides_contextvar(self) -> None:
        from platform_core import request_context as rc
        rc.set_request_id("ambient")
        client = unittest.mock.Mock()
        client.insert_one.return_value = {"id": "m1"}
        repo = ConversationRepository(client)
        repo.log_model_call(
            conversation_id="c1", turn_id="t1",
            service="x", call_type="y", model="z",
            request_json={}, response_json={}, reasoning_notes=[],
            request_id="explicit-override",
        )
        payload = client.insert_one.call_args.args[1]
        self.assertEqual("explicit-override", payload["request_id"])

    def test_log_tool_trace_stamps_request_id_from_contextvar(self) -> None:
        from platform_core import request_context as rc
        rc.set_request_id("rid-tool")
        client = unittest.mock.Mock()
        client.insert_one.return_value = {"id": "tt1"}
        repo = ConversationRepository(client)
        repo.log_tool_trace(
            conversation_id="c1", turn_id="t1",
            tool_name="catalog_search_agent",
            input_json={}, output_json={},
        )
        payload = client.insert_one.call_args.args[1]
        self.assertEqual("rid-tool", payload["request_id"])

    def test_insert_turn_trace_stamps_request_id_from_contextvar(self) -> None:
        from platform_core import request_context as rc
        rc.set_request_id("rid-turn")
        client = unittest.mock.Mock()
        client.insert_one.return_value = {"id": "tt1"}
        repo = ConversationRepository(client)
        repo.insert_turn_trace(
            turn_id="t1", conversation_id="c1", user_id="u1",
        )
        payload = client.insert_one.call_args.args[1]
        self.assertEqual("rid-turn", payload["request_id"])

    def test_repo_helpers_emit_empty_request_id_when_unset(self) -> None:
        client = unittest.mock.Mock()
        client.insert_one.return_value = {"id": "m1"}
        repo = ConversationRepository(client)
        repo.log_model_call(
            conversation_id="c1", turn_id="t1",
            service="x", call_type="y", model="z",
            request_json={}, response_json={}, reasoning_notes=[],
        )
        payload = client.insert_one.call_args.args[1]
        self.assertEqual("", payload["request_id"])


class ArchetypalFeedbackAggregationTests(unittest.TestCase):
    """R4 (PR #67): aggregate_archetypal_feedback joins recent
    feedback_events to catalog_enriched and rolls up like/dislike
    signals into archetypal axes (color_temperature, pattern_type,
    fit_type, silhouette_type, embellishment_level)."""

    def _repo_with_events_and_catalog(self, events, catalog):
        client = unittest.mock.Mock()
        # First call → feedback_events; second → catalog_enriched.
        # We discriminate by table name.
        def select_many(table, filters=None, **kwargs):
            if table == "feedback_events":
                return events
            if table == "catalog_enriched":
                return catalog
            return []
        client.select_many.side_effect = select_many
        return ConversationRepository(client)

    def test_returns_top_3_dislikes_above_min_count(self) -> None:
        events = [
            {"garment_id": "p1", "event_type": "dislike"},
            {"garment_id": "p2", "event_type": "dislike"},
            {"garment_id": "p3", "event_type": "dislike"},
            {"garment_id": "p4", "event_type": "dislike"},
        ]
        catalog = [
            {"product_id": "p1", "ColorTemperature": "warm",  "PatternType": "floral"},
            {"product_id": "p2", "ColorTemperature": "warm",  "PatternType": "floral"},
            {"product_id": "p3", "ColorTemperature": "cool",  "PatternType": "floral"},
            {"product_id": "p4", "ColorTemperature": "warm",  "PatternType": "solid"},  # solid count = 1 → suppressed
        ]
        repo = self._repo_with_events_and_catalog(events, catalog)
        out = repo.aggregate_archetypal_feedback("u1")
        # 3 disliked products with 'warm' color → above floor of 2
        self.assertIn("color_temperature", out["disliked"])
        warm_entry = next(e for e in out["disliked"]["color_temperature"] if e["value"] == "warm")
        self.assertEqual(3, warm_entry["count"])
        # Floral pattern → 3 events → above floor
        self.assertIn("pattern_type", out["disliked"])
        floral_entry = next(e for e in out["disliked"]["pattern_type"] if e["value"] == "floral")
        self.assertEqual(3, floral_entry["count"])
        # 'solid' had count=1 → suppressed
        solid_entries = [e for e in out["disliked"]["pattern_type"] if e["value"] == "solid"]
        self.assertEqual([], solid_entries)

    def test_dedupes_repeated_like_dislike_on_same_garment(self) -> None:
        # Same garment liked twice should count once.
        events = [
            {"garment_id": "p1", "event_type": "like"},
            {"garment_id": "p1", "event_type": "like"},
            {"garment_id": "p2", "event_type": "like"},
        ]
        catalog = [
            {"product_id": "p1", "ColorTemperature": "warm"},
            {"product_id": "p2", "ColorTemperature": "warm"},
        ]
        repo = self._repo_with_events_and_catalog(events, catalog)
        out = repo.aggregate_archetypal_feedback("u1")
        # 2 unique garments both warm → count 2 → above floor
        self.assertIn("color_temperature", out["liked"])
        warm = next(e for e in out["liked"]["color_temperature"] if e["value"] == "warm")
        self.assertEqual(2, warm["count"])

    def test_returns_empty_on_no_feedback(self) -> None:
        repo = self._repo_with_events_and_catalog([], [])
        self.assertEqual({}, repo.aggregate_archetypal_feedback("u1"))

    def test_returns_empty_on_db_error(self) -> None:
        client = unittest.mock.Mock()
        client.select_many.side_effect = RuntimeError("supabase down")
        repo = ConversationRepository(client)
        # Should swallow the exception and return {}.
        self.assertEqual({}, repo.aggregate_archetypal_feedback("u1"))


class CostEstimatorTests(unittest.TestCase):
    """Item 4 (May 1, 2026): cost estimation per LLM/image-gen call."""

    def test_text_model_uses_input_and_output_pricing(self) -> None:
        from platform_core.cost_estimator import estimate_cost_usd
        # gpt-5.4: $2.50 in / $10.00 out per 1M tokens
        # 100k input + 50k output = 0.25 + 0.50 = $0.75
        cost = estimate_cost_usd(model="gpt-5.4", prompt_tokens=100_000, completion_tokens=50_000)
        self.assertEqual(0.75, cost)

    def test_mini_model_pricing(self) -> None:
        from platform_core.cost_estimator import estimate_cost_usd
        # gpt-5-mini: $0.15 in / $0.60 out per 1M
        # 1M input + 1M output = 0.75
        cost = estimate_cost_usd(model="gpt-5-mini", prompt_tokens=1_000_000, completion_tokens=1_000_000)
        self.assertEqual(0.75, cost)

    def test_gemini_image_model_uses_per_image_pricing(self) -> None:
        from platform_core.cost_estimator import estimate_cost_usd
        cost = estimate_cost_usd(model="gemini-3.1-flash-image-preview", image_count=3)
        self.assertAlmostEqual(0.117, cost, places=4)  # 3 * 0.039

    def test_unknown_model_returns_zero(self) -> None:
        from platform_core.cost_estimator import estimate_cost_usd
        self.assertEqual(0.0, estimate_cost_usd(model="not-a-real-model", prompt_tokens=999, completion_tokens=999))

    def test_extract_token_usage_handles_responses_api_shape(self) -> None:
        from platform_core.cost_estimator import extract_token_usage
        class _Usage:
            input_tokens = 1234
            output_tokens = 567
            total_tokens = 1801
        class _Response:
            usage = _Usage()
        out = extract_token_usage(_Response())
        self.assertEqual(1234, out["prompt_tokens"])
        self.assertEqual(567, out["completion_tokens"])
        self.assertEqual(1801, out["total_tokens"])

    def test_extract_token_usage_handles_chat_completion_shape(self) -> None:
        from platform_core.cost_estimator import extract_token_usage
        response = {"usage": {"prompt_tokens": 100, "completion_tokens": 200, "total_tokens": 300}}
        out = extract_token_usage(response)
        self.assertEqual(100, out["prompt_tokens"])
        self.assertEqual(200, out["completion_tokens"])
        self.assertEqual(300, out["total_tokens"])

    def test_extract_token_usage_returns_zeros_when_usage_absent(self) -> None:
        from platform_core.cost_estimator import extract_token_usage
        out = extract_token_usage(object())
        self.assertEqual(0, out["prompt_tokens"])
        self.assertEqual(0, out["completion_tokens"])
        self.assertEqual(0, out["total_tokens"])

    def test_log_model_call_persists_token_columns(self) -> None:
        client = unittest.mock.Mock()
        client.insert_one.return_value = {"id": "m1"}
        repo = ConversationRepository(client)
        repo.log_model_call(
            conversation_id="c1", turn_id="t1",
            service="agentic_application", call_type="copilot_planner", model="gpt-5.4",
            request_json={}, response_json={}, reasoning_notes=[],
            prompt_tokens=1000, completion_tokens=500, total_tokens=1500,
        )
        payload = client.insert_one.call_args.args[1]
        self.assertEqual(1000, payload["prompt_tokens"])
        self.assertEqual(500, payload["completion_tokens"])
        self.assertEqual(1500, payload["total_tokens"])
        # Auto-computed cost from the pricing table: 1000/1M * 2.50 + 500/1M * 10.00 = 0.0025 + 0.005 = 0.0075
        self.assertAlmostEqual(0.0075, payload["estimated_cost_usd"], places=6)

    def test_log_model_call_back_compat_when_token_kwargs_omitted(self) -> None:
        client = unittest.mock.Mock()
        client.insert_one.return_value = {"id": "m1"}
        repo = ConversationRepository(client)
        repo.log_model_call(
            conversation_id="c1", turn_id="t1",
            service="x", call_type="y", model="z",
            request_json={}, response_json={}, reasoning_notes=[],
        )
        payload = client.insert_one.call_args.args[1]
        # Old callers don't pass token columns — payload omits them rather
        # than persisting null/0 placeholder values.
        self.assertNotIn("prompt_tokens", payload)
        self.assertNotIn("completion_tokens", payload)
        self.assertNotIn("estimated_cost_usd", payload)


class PrometheusMetricsTests(unittest.TestCase):
    """Item 5 (May 1, 2026): /metrics endpoint and helper observe_* shims."""

    def test_metrics_module_exposes_canonical_names(self) -> None:
        from platform_core import metrics
        self.assertTrue(hasattr(metrics, "aura_turn_total"))
        self.assertTrue(hasattr(metrics, "aura_turn_duration_seconds"))
        self.assertTrue(hasattr(metrics, "aura_llm_call_total"))
        self.assertTrue(hasattr(metrics, "aura_llm_call_duration_seconds"))
        self.assertTrue(hasattr(metrics, "aura_external_call_duration_seconds"))
        self.assertTrue(hasattr(metrics, "aura_in_flight_turns"))

    def test_observe_turn_stage_is_safe_with_none(self) -> None:
        from platform_core import metrics
        # Should not raise when latency is missing.
        metrics.observe_turn_stage("architect", None)

    def test_observe_turn_outcome_increments_counter(self) -> None:
        from platform_core import metrics
        metrics.observe_turn_outcome(intent="occasion_recommendation", action="run_recommendation_pipeline", status="recommendation")
        # Counter is global — value increases across runs but we just
        # verify the call doesn't raise.

    def test_observe_llm_call_records_latency_and_cost(self) -> None:
        from platform_core import metrics
        metrics.observe_llm_call(
            service="agentic_application",
            model="gpt-5.4",
            status="ok",
            latency_ms=1234.5,
            estimated_cost_usd=0.0075,
        )

    def test_generate_latest_returns_prometheus_text(self) -> None:
        from platform_core import metrics
        # Increment something to ensure the registry has at least one sample.
        metrics.observe_turn_outcome(intent="x", action="y", status="ok")
        out = metrics.generate_latest()
        self.assertIsInstance(out, (bytes, bytearray))
        text = out.decode("utf-8") if isinstance(out, (bytes, bytearray)) else str(out)
        self.assertIn("aura_turn_total", text)


class StructuredLoggingConfigTests(unittest.TestCase):
    """May 1, 2026: structured logging is opt-in via AURA_LOG_FORMAT=json.

    Default (text) preserves the existing developer experience; json
    emits sink-ready records every modern log aggregator can ingest
    without further parsing.
    """

    def setUp(self) -> None:
        import logging as _logging
        self._root = _logging.getLogger()
        self._saved_level = self._root.level
        self._saved_handlers = list(self._root.handlers)

    def tearDown(self) -> None:
        for h in list(self._root.handlers):
            self._root.removeHandler(h)
        for h in self._saved_handlers:
            self._root.addHandler(h)
        self._root.setLevel(self._saved_level)

    def _capture_json(self) -> dict:
        import io
        import json as _json
        import logging as _logging
        import os as _os
        from unittest.mock import patch as _patch

        from platform_core.logging_config import configure_logging

        buf = io.StringIO()
        with _patch.dict(_os.environ, {"AURA_LOG_FORMAT": "json"}, clear=False):
            configure_logging()
            for h in _logging.getLogger().handlers:
                if isinstance(h, _logging.StreamHandler):
                    h.stream = buf
            log = _logging.getLogger("aura.test")
            log.info("hello world", extra={"turn_id": "t-42", "rank": 0})
        line = buf.getvalue().strip().splitlines()[-1]
        return _json.loads(line)

    def test_json_format_emits_required_fields(self) -> None:
        payload = self._capture_json()
        for key in ("ts", "level", "logger", "message", "module", "func", "line"):
            self.assertIn(key, payload)
        self.assertEqual("INFO", payload["level"])
        self.assertEqual("aura.test", payload["logger"])
        self.assertEqual("hello world", payload["message"])

    def test_json_format_carries_extra_fields(self) -> None:
        payload = self._capture_json()
        self.assertEqual("t-42", payload["turn_id"])
        self.assertEqual(0, payload["rank"])

    def test_text_format_default_does_not_emit_json(self) -> None:
        import io
        import logging as _logging
        import os as _os
        from unittest.mock import patch as _patch

        from platform_core.logging_config import configure_logging

        buf = io.StringIO()
        env = {k: v for k, v in _os.environ.items()
               if k not in ("AURA_LOG_FORMAT", "LOG_FORMAT")}
        with _patch.dict(_os.environ, env, clear=True):
            configure_logging()
            for h in _logging.getLogger().handlers:
                if isinstance(h, _logging.StreamHandler):
                    h.stream = buf
            _logging.getLogger("aura.test").info("ping")
        line = buf.getvalue().strip()
        self.assertNotIn("{", line.splitlines()[-1])
        self.assertIn("ping", line)


if __name__ == "__main__":
    unittest.main()
