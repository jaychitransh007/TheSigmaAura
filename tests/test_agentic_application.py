import sys
import unittest
import json
import base64
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch


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


from agentic_application.agents.catalog_search_agent import CatalogSearchAgent
from agentic_application.agents.outfit_assembler import OutfitAssembler
from agentic_application.agents.response_formatter import ResponseFormatter
from agentic_application.agents.outfit_architect import OutfitArchitect
from agentic_application.agents.outfit_evaluator import (
    _build_eval_payload,
    _candidate_delta,
    _fallback_evaluations,
    _followup_reasoning_defaults,
    OutfitEvaluator,
)
from agentic_application.context.conversation_memory import (
    apply_conversation_memory,
    build_conversation_memory,
)
from agentic_application.intent_router import classify as classify_intent
from agentic_application.onboarding_gate import evaluate as evaluate_onboarding_gate
from agentic_application.orchestrator import AgenticOrchestrator
from agentic_application.profile_confidence import evaluate_profile_confidence
from agentic_application.recommendation_confidence import evaluate_recommendation_confidence
from agentic_application.product_links import resolve_product_url
from agentic_application.sentiment import extract_sentiment
from agentic_application.services.whatsapp_formatter import format_turn_response_for_whatsapp
from agentic_application.services.whatsapp_deep_links import build_whatsapp_deep_link
from agentic_application.services.whatsapp_reengagement import build_whatsapp_reengagement_message
from agentic_application.services.dependency_reporting import build_dependency_report
from agentic_application.services.tryon_quality_gate import TryonQualityGate
from agentic_application.intent_handlers import (
    build_capsule_or_trip_planning_response,
    build_explanation_response,
    build_feedback_submission_response,
    build_garment_on_me_response,
    build_outfit_check_response,
    build_pairing_request_response,
    build_shopping_decision_response,
    build_wardrobe_ingestion_response,
    build_virtual_tryon_response,
)
from agentic_application.schemas import (
    CombinedContext,
    ConversationMemory,
    DirectionSpec,
    EvaluatedRecommendation,
    LiveContext,
    OutfitCandidate,
    OutfitCard,
    QuerySpec,
    RecommendationPlan,
    RecommendationResponse,
    ResolvedContextBlock,
    RetrievedProduct,
    RetrievedSet,
    UserContext,
)


class AgenticApplicationTests(unittest.TestCase):
    @staticmethod
    def _png_data_url(*, color: tuple[int, int, int], size: tuple[int, int] = (512, 768)) -> tuple[str, str]:
        try:
            from PIL import Image
        except ImportError as exc:
            raise unittest.SkipTest(f"Pillow not available: {exc}") from exc

        image = Image.new("RGB", size, color)
        buffer = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        buffer.close()
        image.save(buffer.name, format="PNG")
        data = Path(buffer.name).read_bytes()
        encoded = base64.b64encode(data).decode("ascii")
        return buffer.name, f"data:image/png;base64,{encoded}"

    def test_tryon_quality_gate_passes_reasonable_output(self) -> None:
        person_path, _unused = self._png_data_url(color=(120, 120, 120))
        generated_path, _unused_generated = self._png_data_url(color=(120, 120, 120))
        try:
            try:
                from PIL import Image, ImageDraw
            except ImportError as exc:
                raise unittest.SkipTest(f"Pillow not available: {exc}") from exc
            image = Image.open(generated_path).convert("RGB")
            drawer = ImageDraw.Draw(image)
            drawer.rectangle((120, 220, 380, 620), fill=(30, 60, 180))
            image.save(generated_path, format="PNG")
            generated_bytes = Path(generated_path).read_bytes()
            generated_data_url = "data:image/png;base64," + base64.b64encode(generated_bytes).decode("ascii")

            gate = TryonQualityGate()
            result = gate.evaluate(
                person_image_path=person_path,
                tryon_result={"success": True, "data_url": generated_data_url},
            )

            self.assertTrue(result["passed"])
            self.assertGreaterEqual(result["quality_score_pct"], 60)
        finally:
            Path(person_path).unlink(missing_ok=True)
            Path(generated_path).unlink(missing_ok=True)

    def test_tryon_quality_gate_blocks_low_resolution_output(self) -> None:
        person_path, _unused = self._png_data_url(color=(100, 100, 100), size=(512, 768))
        generated_path, generated_data_url = self._png_data_url(color=(20, 20, 160), size=(80, 120))
        try:
            gate = TryonQualityGate()
            result = gate.evaluate(
                person_image_path=person_path,
                tryon_result={"success": True, "data_url": generated_data_url},
            )

            self.assertFalse(result["passed"])
            self.assertEqual("low_resolution_output", result["reason_code"])
        finally:
            Path(person_path).unlink(missing_ok=True)
            Path(generated_path).unlink(missing_ok=True)

    def test_whatsapp_formatter_builds_channel_safe_message(self) -> None:
        result = format_turn_response_for_whatsapp(
            {
                "assistant_message": "Here are your best options.",
                "outfits": [
                    {
                        "rank": 1,
                        "title": "Office Look",
                        "items": [
                            {"title": "Navy Blazer", "source": "wardrobe"},
                            {"title": "Cream Trousers", "source": "catalog"},
                        ],
                    }
                ],
                "follow_up_suggestions": ["Show me more", "Show me catalog alternatives", "Explain why", "Save this"],
                "metadata": {"primary_intent": "occasion_recommendation"},
            }
        )

        self.assertIn("Top options:", result["assistant_message"])
        self.assertIn("Navy Blazer (your wardrobe)", result["assistant_message"])
        self.assertIn("Cream Trousers (catalog)", result["assistant_message"])
        self.assertIn("Reply with:", result["assistant_message"])
        self.assertEqual(3, len(result["follow_up_suggestions"]))
        self.assertEqual("whatsapp", result["metadata"]["channel_rendering"]["surface"])

    def test_whatsapp_reengagement_uses_last_intent(self) -> None:
        reminder = build_whatsapp_reengagement_message(
            previous_context={
                "last_intent": "shopping_decision",
                "memory": {"wardrobe_item_count": 2},
            },
        )

        self.assertEqual("shopping", reminder["reminder_type"])
        self.assertIn("buy / skip", reminder["assistant_message"].lower())
        self.assertIn("Should I buy this?", reminder["follow_up_suggestions"])

    def test_whatsapp_reengagement_can_force_reactivation(self) -> None:
        reminder = build_whatsapp_reengagement_message(
            previous_context={"last_intent": "occasion_recommendation"},
            reminder_type="reactivation",
        )

        self.assertEqual("reactivation", reminder["reminder_type"])
        self.assertIn("what to wear or buy this week", reminder["assistant_message"].lower())
        self.assertEqual(3, len(reminder["follow_up_suggestions"]))

    def test_whatsapp_deep_link_infers_onboarding_handoff(self) -> None:
        link = build_whatsapp_deep_link(
            base_app_url="http://127.0.0.1:55321",
            user_id="user-1",
            previous_context={
                "last_response_metadata": {"onboarding_required": True},
            },
        )

        self.assertEqual("complete_onboarding", link["task"])
        self.assertIn("/onboard?", link["deep_link_url"])
        self.assertIn("focus=onboarding", link["deep_link_url"])

    def test_whatsapp_deep_link_supports_explicit_wardrobe_task(self) -> None:
        link = build_whatsapp_deep_link(
            base_app_url="http://127.0.0.1:55321/rest/v1",
            user_id="user-1",
            conversation_id="c1",
            task="manage_wardrobe",
        )

        self.assertEqual("manage_wardrobe", link["task"])
        self.assertIn("focus=wardrobe", link["deep_link_url"])
        self.assertIn("conversation_id=c1", link["deep_link_url"])
        self.assertIn("manage your saved wardrobe", link["assistant_message"].lower())

    def test_dependency_report_summarizes_repeat_usage_cohorts_and_memory_lift(self) -> None:
        report = build_dependency_report(
            onboarding_profiles=[
                {"user_id": "user-1", "onboarding_complete": True, "acquisition_source": "instagram"},
                {"user_id": "user-2", "onboarding_complete": True, "acquisition_source": "referral"},
            ],
            dependency_events=[
                {
                    "user_id": "user-1",
                    "event_type": "turn_completed",
                    "source_channel": "web",
                    "primary_intent": "occasion_recommendation",
                    "metadata_json": {"memory_sources_read": ["user_profile", "wardrobe_memory"]},
                    "created_at": "2026-03-01T10:00:00+00:00",
                },
                {
                    "user_id": "user-1",
                    "event_type": "turn_completed",
                    "source_channel": "whatsapp",
                    "primary_intent": "pairing_request",
                    "metadata_json": {"memory_sources_read": ["wardrobe_memory"]},
                    "created_at": "2026-03-03T10:00:00+00:00",
                },
                {
                    "user_id": "user-1",
                    "event_type": "turn_completed",
                    "source_channel": "whatsapp",
                    "primary_intent": "pairing_request",
                    "metadata_json": {"memory_sources_read": ["wardrobe_memory"]},
                    "created_at": "2026-03-10T10:00:00+00:00",
                },
                {
                    "user_id": "user-1",
                    "event_type": "referral",
                    "source_channel": "whatsapp",
                    "primary_intent": "referral",
                    "metadata_json": {"referral_type": "invite"},
                    "created_at": "2026-03-11T10:00:00+00:00",
                },
                {
                    "user_id": "user-2",
                    "event_type": "turn_completed",
                    "source_channel": "web",
                    "primary_intent": "style_discovery",
                    "metadata_json": {"memory_sources_read": ["user_profile"]},
                    "created_at": "2026-03-02T09:00:00+00:00",
                },
            ],
            wardrobe_items=[
                {"user_id": "user-1", "is_active": True},
            ],
            feedback_events=[],
            catalog_interactions=[
                {"user_id": "user-1"},
            ],
        )

        self.assertEqual(2, report["overview"]["onboarded_user_count"])
        self.assertEqual(1, report["overview"]["second_session_within_14d_count"])
        self.assertEqual(1, report["overview"]["third_session_within_30d_count"])
        self.assertEqual(100.0, report["overview"]["repeat_sessions_whatsapp_rate_pct"])
        self.assertEqual("instagram", report["acquisition_sources"][0]["key"])
        self.assertEqual("pairing_request", report["recurring_anchor_intents_by_cohort"]["instagram"][0]["key"])
        wardrobe_lift = next(item for item in report["memory_input_retention_lift"] if item["memory_input"] == "wardrobe_items")
        self.assertGreater(wardrobe_lift["lift_pct_points"], 0)

    def test_capsule_plan_builds_top_bottom_wardrobe_combinations(self) -> None:
        orchestrator = AgenticOrchestrator(repo=Mock(), onboarding_gateway=Mock(), config=Mock())

        cards = orchestrator._build_wardrobe_first_capsule_plan(
            message="Plan a workweek capsule for my office trip",
            wardrobe_items=[
                {"id": "top-1", "title": "Navy Blazer", "garment_category": "blazer"},
                {"id": "bottom-1", "title": "Cream Trousers", "garment_category": "trousers"},
            ],
        )

        self.assertEqual(1, len(cards))
        self.assertEqual(2, len(cards[0].items))
        self.assertEqual({"top-1", "bottom-1"}, {cards[0].items[0]["product_id"], cards[0].items[1]["product_id"]})

    def test_orchestrator_resolve_active_conversation_reuses_existing(self) -> None:
        repo = Mock()
        repo.get_or_create_user.return_value = {"id": "db-user"}
        repo.get_latest_conversation_for_user.return_value = {
            "id": "c-shared",
            "status": "active",
            "created_at": "2026-03-19T00:00:00+00:00",
        }
        orchestrator = AgenticOrchestrator(repo=repo, onboarding_gateway=Mock(), config=Mock())

        result = orchestrator.resolve_active_conversation(external_user_id="user-1")

        self.assertEqual("c-shared", result["conversation_id"])
        self.assertTrue(result["reused_existing"])
        repo.create_conversation.assert_not_called()

    def test_orchestrator_resolve_active_conversation_creates_when_missing(self) -> None:
        repo = Mock()
        repo.get_or_create_user.return_value = {"id": "db-user"}
        repo.get_latest_conversation_for_user.return_value = None
        repo.create_conversation.return_value = {
            "id": "c-new",
            "status": "active",
            "created_at": "2026-03-19T00:00:00+00:00",
        }
        orchestrator = AgenticOrchestrator(repo=repo, onboarding_gateway=Mock(), config=Mock())

        result = orchestrator.resolve_active_conversation(external_user_id="user-1")

        self.assertEqual("c-new", result["conversation_id"])
        self.assertFalse(result["reused_existing"])
        repo.create_conversation.assert_called_once_with(user_id="db-user", initial_context={})

    def test_conversation_memory_carries_context_for_followups(self) -> None:
        previous_context = {
            "memory": {
                "occasion_signal": "wedding",
                "formality_hint": "formal",
                "specific_needs": ["elongation"],
                "plan_type": "mixed",
                "followup_count": 1,
                "last_recommendation_ids": ["prev-1"],
            },
            "last_recommendations": [{"candidate_id": "prev-1"}],
        }

        live_context = LiveContext(
            user_need="Show me something bolder",
            is_followup=True,
            followup_intent="increase_boldness",
        )
        memory = build_conversation_memory(previous_context, live_context)
        effective = apply_conversation_memory(live_context, memory)

        self.assertTrue(effective.is_followup)
        self.assertEqual("wedding", effective.occasion_signal)
        self.assertEqual("formal", effective.formality_hint)
        self.assertIn("elongation", effective.specific_needs)
        self.assertEqual(2, memory.followup_count)

    def test_conversation_memory_tracks_intent_channel_sentiment_and_wardrobe(self) -> None:
        previous_context = {
            "memory": {
                "recent_intents": ["shopping_decision"],
                "recent_channels": ["web"],
                "recent_sentiment_labels": ["uncertain"],
                "last_sentiment_label": "uncertain",
                "wardrobe_item_count": 1,
                "wardrobe_memory_enabled": True,
            },
        }

        live_context = LiveContext(user_need="Need help for office tomorrow", occasion_signal="office")
        memory = build_conversation_memory(
            previous_context,
            live_context,
            current_intent="occasion_recommendation",
            channel="whatsapp",
            sentiment_trace={"sentiment_label": "anxious"},
            wardrobe_item_count=3,
        )

        self.assertEqual(["shopping_decision", "occasion_recommendation"], memory.recent_intents)
        self.assertEqual(["web", "whatsapp"], memory.recent_channels)
        self.assertEqual(["uncertain", "anxious"], memory.recent_sentiment_labels)
        self.assertEqual("anxious", memory.last_sentiment_label)
        self.assertEqual("Need help for office tomorrow", memory.last_user_need)
        self.assertEqual(3, memory.wardrobe_item_count)
        self.assertTrue(memory.wardrobe_memory_enabled)

    def test_recommendation_confidence_engine_returns_runtime_backed_summary(self) -> None:
        confidence = evaluate_recommendation_confidence(
            answer_mode="catalog_pipeline",
            profile_confidence_score_pct=84,
            intent_confidence=0.92,
            top_match_score=0.94,
            second_match_score=0.81,
            retrieved_product_count=18,
            candidate_count=9,
            response_outfit_count=3,
            wardrobe_items_used=0,
            restricted_item_exclusion_count=0,
        )

        self.assertGreaterEqual(confidence.score_pct, 70)
        self.assertEqual("high", confidence.confidence_band)
        self.assertTrue(confidence.summary)
        self.assertTrue(confidence.explanation)
        self.assertTrue(confidence.factors)

    def test_catalog_search_agent_applies_document_and_direction_filters(self) -> None:
        retrieval_gateway = Mock()
        retrieval_gateway.embed_texts.return_value = [[0.1, 0.2]]
        retrieval_gateway.similarity_search.return_value = []
        client = Mock()

        agent = CatalogSearchAgent(retrieval_gateway=retrieval_gateway, client=client)
        plan = RecommendationPlan(
            plan_type="paired_only",
            retrieval_count=8,
            directions=[
                DirectionSpec(
                    direction_id="B",
                    direction_type="paired",
                    label="Pairing",
                    queries=[
                        QuerySpec(
                            query_id="B1",
                            role="top",
                            hard_filters={},
                            query_document=(
                                "GARMENT_REQUIREMENTS:\n"
                                "- GarmentCategory: top\n"
                                "- GarmentSubtype: blouse\n"
                                "- StylingCompleteness: needs_bottomwear\n"
                                "OCCASION_AND_SIGNAL:\n"
                                "- FormalityLevel: Smart Casual\n"
                                "- OccasionFit: Date Night\n"
                                "- TimeOfDay: Evening"
                            ),
                        )
                    ],
                )
            ],
        )
        context = CombinedContext(
            user=UserContext(user_id="u1", gender="female"),
            live=LiveContext(user_need="Need pairings for date night"),
            hard_filters={"gender_expression": "feminine"},
        )

        agent.search(plan, context)

        filters = retrieval_gateway.similarity_search.call_args.kwargs["filters"]
        self.assertEqual("feminine", filters["gender_expression"])
        self.assertEqual("needs_bottomwear", filters["styling_completeness"])
        self.assertEqual("top", filters["garment_category"])
        self.assertEqual("blouse", filters["garment_subtype"])
        # time_of_day, occasion_fit, and formality_level are soft signals, not hard filters
        self.assertNotIn("time_of_day", filters)
        self.assertNotIn("occasion_fit", filters)
        self.assertNotIn("formality_level", filters)

    def test_catalog_search_agent_excludes_restricted_products_from_results(self) -> None:
        retrieval_gateway = Mock()
        retrieval_gateway.embed_texts.return_value = [[0.1, 0.2]]
        retrieval_gateway.similarity_search.return_value = [
            {
                "product_id": "sku-safe",
                "similarity": 0.91,
                "metadata_json": {"title": "Structured Blazer"},
            },
            {
                "product_id": "sku-blocked",
                "similarity": 0.95,
                "metadata_json": {"title": "Silk Bralette Set", "GarmentSubtype": "bralette"},
            },
        ]
        client = Mock()
        client.select_many.return_value = [
            {"product_id": "sku-safe", "garment_category": "blazer", "title": "Structured Blazer"},
            {"product_id": "sku-blocked", "garment_category": "lingerie", "title": "Silk Bralette Set"},
        ]

        agent = CatalogSearchAgent(retrieval_gateway=retrieval_gateway, client=client)
        plan = RecommendationPlan(
            plan_type="complete_only",
            retrieval_count=8,
            directions=[
                DirectionSpec(
                    direction_id="A",
                    direction_type="complete",
                    label="Complete",
                    queries=[
                        QuerySpec(
                            query_id="A1",
                            role="complete",
                            hard_filters={},
                            query_document="Need a polished blazer look",
                        )
                    ],
                )
            ],
        )
        context = CombinedContext(
            user=UserContext(user_id="u1", gender="female"),
            live=LiveContext(user_need="Need a blazer"),
        )

        results = agent.search(plan, context)

        self.assertEqual(1, len(results))
        self.assertEqual(["sku-safe"], [product.product_id for product in results[0].products])
        self.assertEqual("excluded", results[0].applied_filters["restricted_category_policy"])

    def test_outfit_architect_raises_on_llm_failure(self) -> None:
        context = CombinedContext(
            user=UserContext(
                user_id="u1",
                gender="female",
                derived_interpretations={
                    "SeasonalColorGroup": {"value": "Soft Summer"},
                },
                style_preference={"primaryArchetype": "classic"},
                profile_richness="full",
            ),
            live=LiveContext(
                user_need="Need blue top and bottom pairing for a wedding",
                occasion_signal="wedding",
                formality_hint="formal",
            ),
            hard_filters={"gender_expression": "feminine"},
        )

        with patch("agentic_application.agents.outfit_architect.get_api_key", return_value="x"), patch(
            "agentic_application.agents.outfit_architect.OpenAI"
        ) as openai_cls:
            openai_cls.return_value.responses.create.side_effect = RuntimeError("boom")
            architect = OutfitArchitect()
            with self.assertRaises(RuntimeError):
                architect.plan(context)

    def test_outfit_architect_raises_on_empty_directions(self) -> None:
        context = CombinedContext(
            user=UserContext(user_id="u1", gender="female"),
            live=LiveContext(user_need="Show me something"),
            hard_filters={"gender_expression": "feminine"},
        )

        mock_response = Mock()
        mock_response.output_text = json.dumps({
            "resolved_context": {
                "occasion_signal": None,
                "formality_hint": None,
                "time_hint": None,
                "specific_needs": [],
                "is_followup": False,
                "followup_intent": None,
            },
            "plan_type": "complete_only",
            "retrieval_count": 12,
            "directions": [],
        })

        with patch("agentic_application.agents.outfit_architect.get_api_key", return_value="x"), patch(
            "agentic_application.agents.outfit_architect.OpenAI"
        ) as openai_cls:
            openai_cls.return_value.responses.create.return_value = mock_response
            architect = OutfitArchitect()
            with self.assertRaises(RuntimeError):
                architect.plan(context)

    def test_outfit_assembler_rejects_paired_candidates_with_mismatched_occasion(self) -> None:
        assembler = OutfitAssembler()
        plan = RecommendationPlan(
            plan_type="paired_only",
            directions=[
                DirectionSpec(
                    direction_id="B",
                    direction_type="paired",
                    label="Pairing",
                    queries=[],
                )
            ],
        )
        retrieved_sets = [
            RetrievedSet(
                direction_id="B",
                query_id="B1",
                role="top",
                products=[
                    RetrievedProduct(
                        product_id="top-1",
                        similarity=0.9,
                        metadata={"OccasionFit": "wedding", "FormalityLevel": "formal"},
                        enriched_data={"occasion_fit": "wedding", "formality_level": "formal"},
                    )
                ],
            ),
            RetrievedSet(
                direction_id="B",
                query_id="B2",
                role="bottom",
                products=[
                    RetrievedProduct(
                        product_id="bottom-1",
                        similarity=0.88,
                        metadata={"OccasionFit": "office", "FormalityLevel": "formal"},
                        enriched_data={"occasion_fit": "office", "formality_level": "formal"},
                    )
                ],
            ),
        ]

        candidates = assembler.assemble(
            retrieved_sets,
            plan,
            CombinedContext(
                user=UserContext(user_id="u1", gender="female"),
                live=LiveContext(user_need="Need pairings"),
            ),
        )

        self.assertEqual([], candidates)

    def test_orchestrator_persists_memory_and_turn_artifacts(self) -> None:
        repo = Mock()
        onboarding_gateway = Mock()
        onboarding_gateway.get_effective_seasonal_groups.return_value = None
        onboarding_gateway.get_onboarding_status.return_value = {
            "profile_complete": True,
            "style_preference_complete": True,
            "images_uploaded": ["full_body", "headshot"],
            "onboarding_complete": True,
        }
        repo.client = Mock()
        repo.get_or_create_user.return_value = {"id": "db-user"}
        repo.get_conversation.return_value = {
            "id": "c1",
            "user_id": "db-user",
            "session_context_json": {
                "memory": {
                    "occasion_signal": "wedding",
                    "formality_hint": "formal",
                    "specific_needs": ["elongation"],
                    "plan_type": "mixed",
                    "followup_count": 1,
                    "last_recommendation_ids": ["prev-1"],
                },
                "last_recommendations": [{"candidate_id": "prev-1"}],
                "last_plan_type": "mixed",
                "last_occasion": "wedding",
                "last_live_context": {"specific_needs": ["elongation"]},
            },
        }
        repo.create_turn.return_value = {"id": "t1"}

        retrieved_sets = [
            RetrievedSet(
                direction_id="A",
                query_id="A1",
                role="complete",
                applied_filters={
                    "gender_expression": "feminine",
                    "styling_completeness": "complete",
                },
                products=[
                    RetrievedProduct(
                        product_id="sku-1",
                        similarity=0.91,
                        metadata={
                            "title": "Evening Dress",
                            "images__0__src": "https://img/1.jpg",
                            "price": "3999",
                            "GarmentCategory": "dress",
                            "StylingCompleteness": "complete",
                            "PrimaryColor": "blue",
                        },
                        enriched_data={
                            "garment_category": "dress",
                            "styling_completeness": "complete",
                            "primary_color": "blue",
                        },
                    )
                ],
            )
        ]
        candidates = [
            OutfitCandidate(
                candidate_id="cand-1",
                direction_id="A",
                candidate_type="complete",
                items=[
                    {
                        "product_id": "sku-1",
                        "title": "Evening Dress",
                        "image_url": "https://img/1.jpg",
                        "price": "3999",
                        "primary_color": "blue",
                        "occasion_fit": "wedding",
                        "formality_level": "formal",
                        "garment_category": "dress",
                    }
                ],
                assembly_score=0.91,
            )
        ]
        evaluated = [
            EvaluatedRecommendation(
                candidate_id="cand-1",
                rank=1,
                match_score=0.95,
                title="Refined evening option",
                reasoning="Strong fit for the occasion.",
                item_ids=["sku-1"],
            )
        ]
        response = RecommendationResponse(
            message="Here are your refined options.",
            outfits=[
                OutfitCard(
                    rank=1,
                    title="Refined evening option",
                    reasoning="Strong fit for the occasion.",
                    items=[{"product_id": "sku-1", "title": "Evening Dress"}],
                )
            ],
            follow_up_suggestions=["Show me something bolder"],
            metadata={"plan_type": "mixed", "plan_source": "llm"},
        )
        plan = RecommendationPlan(
            plan_type="mixed",
            retrieval_count=8,
            plan_source="llm",
            directions=[
                DirectionSpec(
                    direction_id="A",
                    direction_type="complete",
                    label="Complete outfit",
                    queries=[
                        QuerySpec(
                            query_id="A1",
                            role="complete",
                            hard_filters={"styling_completeness": "complete"},
                            query_document="USER_NEED:\n- request_summary: something bolder",
                        )
                    ],
                )
            ],
            resolved_context=ResolvedContextBlock(
                occasion_signal="wedding",
                formality_hint="formal",
                is_followup=True,
                followup_intent="increase_boldness",
            ),
        )
        analysis_payload = {
            "status": "completed",
            "profile": {
                "gender": "female",
                "style_preference": {"primaryArchetype": "classic"},
            },
            "attributes": {
                "BodyShape": {"value": "Hourglass"},
            },
            "derived_interpretations": {
                "SeasonalColorGroup": {"value": "Soft Summer"},
                "HeightCategory": {"value": "Tall"},
            },
        }

        onboarding_gateway.get_analysis_status.return_value = analysis_payload

        with patch("agentic_application.orchestrator.ApplicationCatalogRetrievalGateway"), patch(
            "agentic_application.orchestrator.OutfitArchitect"
        ) as architect_cls, patch(
            "agentic_application.orchestrator.CatalogSearchAgent"
        ) as search_cls, patch(
            "agentic_application.orchestrator.OutfitAssembler"
        ) as assembler_cls, patch(
            "agentic_application.orchestrator.OutfitEvaluator"
        ) as evaluator_cls, patch(
            "agentic_application.orchestrator.ResponseFormatter"
        ) as formatter_cls:
            architect_cls.return_value.plan.return_value = plan
            search_cls.return_value.search.return_value = retrieved_sets
            assembler_cls.return_value.assemble.return_value = candidates
            evaluator_cls.return_value.evaluate.return_value = evaluated
            formatter_cls.return_value.format.return_value = response

            orchestrator = AgenticOrchestrator(
                repo=repo,
                onboarding_gateway=onboarding_gateway,
                config=Mock(),
            )
            result = orchestrator.process_turn(
                conversation_id="c1",
                external_user_id="user-1",
                message="Show me something bolder",
            )

        resolved_context = repo.finalize_turn.call_args.kwargs["resolved_context"]
        session_context = repo.update_conversation_context.call_args.kwargs["session_context"]

        self.assertEqual("llm", resolved_context["plan"]["plan_source"])
        self.assertEqual("wedding", resolved_context["conversation_memory"]["occasion_signal"])
        self.assertEqual("complete", resolved_context["retrieval"][0]["applied_filters"]["styling_completeness"])
        self.assertEqual(2, session_context["memory"]["followup_count"])
        self.assertEqual("feminine", result["filters_applied"]["gender_expression"])
        self.assertEqual(["blue"], session_context["last_recommendations"][0]["primary_colors"])
        self.assertEqual("complete", session_context["last_recommendations"][0]["candidate_type"])
        self.assertEqual(["wedding"], session_context["last_recommendations"][0]["occasion_fits"])
        self.assertEqual(["formal"], session_context["last_recommendations"][0]["formality_levels"])
        self.assertEqual("neutral", session_context["last_sentiment_trace"]["sentiment_label"])
        self.assertEqual(["occasion_recommendation"], session_context["memory"]["recent_intents"])
        self.assertEqual(["web"], session_context["memory"]["recent_channels"])
        self.assertEqual(["neutral"], session_context["memory"]["recent_sentiment_labels"])
        self.assertEqual("Show me something bolder", session_context["memory"]["last_user_need"])
        self.assertFalse(session_context["memory"]["wardrobe_memory_enabled"])
        repo.create_catalog_interaction.assert_called_once_with(
            user_id="user-1",
            conversation_id="c1",
            turn_id="t1",
            product_id="sku-1",
            interaction_type="view",
            source_channel="web",
            source_surface="recommendation_outfit",
            metadata_json={
                "outfit_rank": 1,
                "item_position": 1,
                "item_role": "",
                "primary_intent": "occasion_recommendation",
                "title": "Evening Dress",
            },
        )
        repo.create_sentiment_trace.assert_called_once_with(
            user_id="user-1",
            conversation_id="c1",
            turn_id="t1",
            source_channel="web",
            sentiment_source="user_message",
            sentiment_label="neutral",
            sentiment_score=0.0,
            intensity=0.0,
            cues_json=[],
            metadata_json={"message_length": 24, "has_question": False},
        )
        self.assertEqual(2, repo.create_confidence_history.call_count)
        self.assertEqual("profile", repo.create_confidence_history.call_args_list[0].kwargs["confidence_type"])
        self.assertEqual("recommendation", repo.create_confidence_history.call_args_list[1].kwargs["confidence_type"])
        self.assertFalse(repo.create_confidence_history.call_args_list[1].kwargs["metadata_json"]["provisional"])
        self.assertEqual("runtime_evidence_v1", repo.create_confidence_history.call_args_list[1].kwargs["metadata_json"]["estimation_method"])
        self.assertIn("recommendation_confidence", result["metadata"])
        self.assertIn("summary", result["metadata"]["recommendation_confidence"])

    def test_orchestrator_recommendation_summary_includes_followup_attributes(self) -> None:
        evaluated = [
            EvaluatedRecommendation(
                candidate_id="cand-1",
                rank=1,
                match_score=0.94,
                title="Refined set",
                item_ids=["sku-1", "sku-2"],
            )
        ]
        candidates = [
            OutfitCandidate(
                candidate_id="cand-1",
                direction_id="B",
                candidate_type="paired",
                items=[
                    {
                        "product_id": "sku-1",
                        "primary_color": "navy",
                        "garment_category": "top",
                        "garment_subtype": "blouse",
                        "role": "top",
                        "occasion_fit": "date_night",
                        "formality_level": "smart_casual",
                        "pattern_type": "striped",
                        "volume_profile": "oversized",
                        "fit_type": "relaxed",
                        "silhouette_type": "draped",
                    },
                    {
                        "product_id": "sku-2",
                        "primary_color": "cream",
                        "garment_category": "bottom",
                        "garment_subtype": "trousers",
                        "role": "bottom",
                        "occasion_fit": "date_night",
                        "formality_level": "smart_casual",
                        "pattern_type": "striped",
                        "volume_profile": "oversized",
                        "fit_type": "relaxed",
                        "silhouette_type": "draped",
                    },
                ],
            )
        ]

        summaries = AgenticOrchestrator._build_recommendation_summaries(evaluated, candidates)

        self.assertEqual(["navy", "cream"], summaries[0]["primary_colors"])
        self.assertEqual(["date_night"], summaries[0]["occasion_fits"])
        self.assertEqual(["smart_casual"], summaries[0]["formality_levels"])
        self.assertEqual(["striped"], summaries[0]["pattern_types"])
        self.assertEqual(["oversized"], summaries[0]["volume_profiles"])
        self.assertEqual(["relaxed"], summaries[0]["fit_types"])
        self.assertEqual(["draped"], summaries[0]["silhouette_types"])
        self.assertEqual("paired", summaries[0]["candidate_type"])

    def test_evaluator_payload_includes_memory_and_prior_recommendations(self) -> None:
        context = CombinedContext(
            user=UserContext(
                user_id="u1",
                gender="female",
                style_preference={
                    "primaryArchetype": "classic",
                    "riskTolerance": "moderate",
                    "comfortBoundaries": [{"area": "arms", "preference": "covered"}],
                },
            ),
            live=LiveContext(
                user_need="Show me something similar",
                is_followup=True,
                followup_intent="similar_to_previous",
            ),
            hard_filters={"gender_expression": "feminine"},
            conversation_memory=ConversationMemory(
                occasion_signal="date_night",
                formality_hint="smart_casual",
                plan_type="paired_only",
                followup_count=2,
                last_recommendation_ids=["cand-1"],
            ),
            previous_recommendations=[
                {
                    "candidate_id": "cand-1",
                    "candidate_type": "paired",
                    "primary_colors": ["navy"],
                    "occasion_fits": ["date_night"],
                }
            ],
        )
        payload = json.loads(
            _build_eval_payload(
                [
                    OutfitCandidate(
                        candidate_id="cand-2",
                        direction_id="B",
                        candidate_type="paired",
                        items=[
                            {
                                "product_id": "sku-2",
                                "primary_color": "navy",
                                "occasion_fit": "date_night",
                                "role": "top",
                                "garment_category": "top",
                            },
                            {
                                "product_id": "sku-3",
                                "primary_color": "cream",
                                "occasion_fit": "date_night",
                                "role": "bottom",
                                "garment_category": "bottom",
                            },
                        ],
                    )
                ],
                context,
                RecommendationPlan(plan_type="paired_only", retrieval_count=8, directions=[]),
            )
        )

        self.assertEqual("date_night", payload["conversation_memory"]["occasion_signal"])
        self.assertEqual("paired", payload["previous_recommendations"][0]["candidate_type"])
        self.assertEqual(["navy"], payload["previous_recommendations"][0]["primary_colors"])
        self.assertEqual("moderate", payload["user_profile"]["style_preference"]["riskTolerance"])
        self.assertEqual(
            [{"area": "arms", "preference": "covered"}],
            payload["user_profile"]["style_preference"]["comfortBoundaries"],
        )
        self.assertEqual("cand-2", payload["candidate_deltas"][0]["candidate_id"])
        self.assertTrue(payload["candidate_deltas"][0]["candidate_type_matches_previous"])
        self.assertTrue(payload["candidate_deltas"][0]["preserves_occasion"])

    def test_evaluator_fallback_explains_color_shift_for_change_color_followup(self) -> None:
        context = CombinedContext(
            user=UserContext(user_id="u1", gender="female"),
            live=LiveContext(
                user_need="Show me a different color",
                is_followup=True,
                followup_intent="change_color",
            ),
            previous_recommendations=[
                {
                    "candidate_id": "cand-1",
                    "candidate_type": "paired",
                    "primary_colors": ["navy"],
                    "occasion_fits": ["date_night"],
                    "roles": ["top", "bottom"],
                }
            ],
        )
        candidates = [
            OutfitCandidate(
                candidate_id="cand-2",
                direction_id="B",
                candidate_type="paired",
                assembly_score=0.84,
                items=[
                    {"product_id": "sku-1", "title": "Top", "primary_color": "burgundy", "occasion_fit": "date_night", "role": "top"},
                    {"product_id": "sku-2", "title": "Bottom", "primary_color": "cream", "occasion_fit": "date_night", "role": "bottom"},
                ],
            )
        ]

        with patch("agentic_application.agents.outfit_evaluator.get_api_key", return_value="x"), patch(
            "agentic_application.agents.outfit_evaluator.OpenAI"
        ) as openai_cls:
            openai_cls.return_value.responses.create.side_effect = RuntimeError("boom")
            evaluator = OutfitEvaluator()
            results = evaluator.evaluate(
                candidates,
                context,
                RecommendationPlan(plan_type="paired_only", retrieval_count=8, directions=[]),
            )

        self.assertIn("color-shift comparison", results[0].reasoning)
        self.assertIn("burgundy", results[0].color_note)

    def test_evaluator_fallback_explains_similarity_preservation(self) -> None:
        context = CombinedContext(
            user=UserContext(user_id="u1", gender="female"),
            live=LiveContext(
                user_need="Show me something similar",
                is_followup=True,
                followup_intent="similar_to_previous",
            ),
            previous_recommendations=[
                {
                    "candidate_id": "cand-1",
                    "candidate_type": "paired",
                    "primary_colors": ["navy"],
                    "occasion_fits": ["date_night"],
                    "roles": ["top", "bottom"],
                }
            ],
        )
        candidates = [
            OutfitCandidate(
                candidate_id="cand-2",
                direction_id="B",
                candidate_type="paired",
                assembly_score=0.82,
                items=[
                    {"product_id": "sku-1", "title": "Top", "primary_color": "navy", "occasion_fit": "date_night", "role": "top"},
                    {"product_id": "sku-2", "title": "Bottom", "primary_color": "cream", "occasion_fit": "date_night", "role": "bottom"},
                ],
            )
        ]

        with patch("agentic_application.agents.outfit_evaluator.get_api_key", return_value="x"), patch(
            "agentic_application.agents.outfit_evaluator.OpenAI"
        ) as openai_cls:
            openai_cls.return_value.responses.create.side_effect = RuntimeError("boom")
            evaluator = OutfitEvaluator()
            results = evaluator.evaluate(
                candidates,
                context,
                RecommendationPlan(plan_type="paired_only", retrieval_count=8, directions=[]),
            )

        self.assertIn("similarity-to-previous comparison", results[0].reasoning)
        self.assertIn("same outfit structure", results[0].style_note)
        self.assertIn("same occasion", results[0].style_note)

    def test_evaluator_failure_falls_back_to_top_assembly_scored_candidates(self) -> None:
        context = CombinedContext(
            user=UserContext(user_id="u1", gender="female"),
            live=LiveContext(user_need="Need options"),
        )
        candidates = [
            OutfitCandidate(
                candidate_id="cand-low",
                direction_id="A",
                candidate_type="complete",
                assembly_score=0.31,
                items=[{"product_id": "sku-low", "title": "Low"}],
            ),
            OutfitCandidate(
                candidate_id="cand-high",
                direction_id="A",
                candidate_type="complete",
                assembly_score=0.92,
                items=[{"product_id": "sku-high", "title": "High"}],
            ),
        ]

        with patch("agentic_application.agents.outfit_evaluator.get_api_key", return_value="x"), patch(
            "agentic_application.agents.outfit_evaluator.OpenAI"
        ) as openai_cls:
            openai_cls.return_value.responses.create.side_effect = RuntimeError("boom")
            evaluator = OutfitEvaluator()
            results = evaluator.evaluate(
                candidates,
                context,
                RecommendationPlan(plan_type="complete_only", retrieval_count=8, directions=[]),
            )

        self.assertEqual("cand-high", results[0].candidate_id)
        self.assertEqual(1, results[0].rank)
        self.assertIn("retrieval similarity", results[0].reasoning)

    def test_evaluator_llm_results_are_enriched_with_followup_delta_notes(self) -> None:
        context = CombinedContext(
            user=UserContext(user_id="u1", gender="female"),
            live=LiveContext(
                user_need="Show me something similar",
                is_followup=True,
                followup_intent="similar_to_previous",
            ),
            previous_recommendations=[
                {
                    "candidate_id": "cand-1",
                    "candidate_type": "paired",
                    "primary_colors": ["navy"],
                    "occasion_fits": ["date_night"],
                    "roles": ["top", "bottom"],
                }
            ],
        )
        candidates = [
            OutfitCandidate(
                candidate_id="cand-2",
                direction_id="B",
                candidate_type="paired",
                assembly_score=0.83,
                items=[
                    {"product_id": "sku-1", "title": "Top", "primary_color": "navy", "occasion_fit": "date_night", "role": "top"},
                    {"product_id": "sku-2", "title": "Bottom", "primary_color": "cream", "occasion_fit": "date_night", "role": "bottom"},
                ],
            )
        ]
        llm_output = {
            "evaluations": [
                {
                    "candidate_id": "cand-2",
                    "rank": 4,
                    "match_score": 0.88,
                    "title": "Refined pairing",
                    "reasoning": "",
                    "body_note": "",
                    "color_note": "",
                    "style_note": "",
                    "occasion_note": "",
                    "item_ids": ["sku-1", "sku-2"],
                }
            ]
        }

        with patch("agentic_application.agents.outfit_evaluator.get_api_key", return_value="x"), patch(
            "agentic_application.agents.outfit_evaluator.OpenAI"
        ) as openai_cls:
            openai_cls.return_value.responses.create.return_value = Mock(
                output_text=json.dumps(llm_output)
            )
            evaluator = OutfitEvaluator()
            results = evaluator.evaluate(
                candidates,
                context,
                RecommendationPlan(plan_type="paired_only", retrieval_count=8, directions=[]),
            )

        self.assertEqual(1, results[0].rank)
        self.assertIn("previous recommendation", results[0].reasoning)
        self.assertIn("outfit structure", results[0].style_note)

    def test_evaluator_normalizes_score_and_validates_item_ids(self) -> None:
        context = CombinedContext(
            user=UserContext(user_id="u1", gender="male"),
            live=LiveContext(user_need="date outfit"),
        )
        candidates = [
            OutfitCandidate(
                candidate_id="cand-1",
                direction_id="A",
                candidate_type="complete",
                assembly_score=0.8,
                items=[{"product_id": "sku-real", "title": "Real Item"}],
            )
        ]
        llm_output = {
            "evaluations": [
                {
                    "candidate_id": "cand-1",
                    "rank": 7,
                    "match_score": 1.5,
                    "title": "Good outfit",
                    "reasoning": "Looks great",
                    "body_note": "",
                    "color_note": "",
                    "style_note": "",
                    "occasion_note": "",
                    "item_ids": ["sku-fake", "sku-wrong"],
                }
            ]
        }

        with patch("agentic_application.agents.outfit_evaluator.get_api_key", return_value="x"), patch(
            "agentic_application.agents.outfit_evaluator.OpenAI"
        ) as openai_cls:
            openai_cls.return_value.responses.create.return_value = Mock(
                output_text=json.dumps(llm_output)
            )
            evaluator = OutfitEvaluator()
            results = evaluator.evaluate(
                candidates,
                context,
                RecommendationPlan(plan_type="complete_only", retrieval_count=8, directions=[]),
            )

        self.assertEqual(1, len(results))
        self.assertEqual(1, results[0].rank)
        self.assertLessEqual(results[0].match_score, 1.0)
        self.assertGreaterEqual(results[0].match_score, 0.0)
        self.assertEqual(["sku-real"], results[0].item_ids)
        self.assertTrue(results[0].body_note)
        self.assertTrue(results[0].color_note)
        self.assertTrue(results[0].style_note)
        self.assertTrue(results[0].occasion_note)

    def test_response_formatter_preserves_product_url_and_price(self) -> None:
        formatter = ResponseFormatter()
        evaluated = [
            EvaluatedRecommendation(
                candidate_id="cand-1",
                rank=1,
                match_score=0.9,
                title="Structured Blazer",
                reasoning="Strong structured option.",
                item_ids=["sku-2"],
            )
        ]
        candidates = [
            OutfitCandidate(
                candidate_id="cand-1",
                direction_id="A",
                candidate_type="complete",
                items=[
                    {
                        "product_id": "sku-2",
                        "similarity": 0.8,
                        "title": "Structured Blazer",
                        "image_url": "https://img/2.jpg",
                        "price": "4999",
                        "product_url": "https://example.com/sku-2",
                    }
                ],
                assembly_score=0.8,
            )
        ]
        context = CombinedContext(
            user=UserContext(
                user_id="u1",
                gender="female",
                style_preference={"primaryArchetype": "classic"},
                derived_interpretations={"SeasonalColorGroup": {"value": "Soft Summer"}},
            ),
            live=LiveContext(user_need="Need a blazer"),
            hard_filters={"gender_expression": "feminine"},
        )
        plan = RecommendationPlan(
            plan_type="complete_only",
            retrieval_count=8,
            directions=[],
        )

        response = formatter.format(evaluated, context, plan, candidates)

        self.assertEqual(0.8, response.outfits[0].items[0]["similarity"])
        self.assertEqual("4999", response.outfits[0].items[0]["price"])
        self.assertEqual("https://example.com/sku-2", response.outfits[0].items[0]["product_url"])
        self.assertEqual("catalog", response.outfits[0].items[0]["source"])
        self.assertEqual("catalog", response.metadata["answer_components"]["primary_source"])

    def test_response_formatter_caps_output_to_top_five_outfits(self) -> None:
        formatter = ResponseFormatter()
        evaluated = [
            EvaluatedRecommendation(
                candidate_id=f"cand-{index}",
                rank=index,
                match_score=1.0 - (index * 0.01),
                title=f"Outfit {index}",
                reasoning="Reasoning",
                item_ids=[f"sku-{index}"],
            )
            for index in range(1, 8)
        ]
        candidates = [
            OutfitCandidate(
                candidate_id=f"cand-{index}",
                direction_id="A",
                candidate_type="complete",
                items=[{"product_id": f"sku-{index}", "title": f"Item {index}"}],
                assembly_score=1.0 - (index * 0.01),
            )
            for index in range(1, 8)
        ]
        context = CombinedContext(
            user=UserContext(
                user_id="u1",
                gender="female",
                style_preference={"primaryArchetype": "classic"},
                derived_interpretations={"SeasonalColorGroup": {"value": "Soft Summer"}},
            ),
            live=LiveContext(user_need="Need options", occasion_signal="wedding"),
        )
        plan = RecommendationPlan(plan_type="mixed", directions=[])

        response = formatter.format(evaluated, context, plan, candidates)

        self.assertEqual(3, len(response.outfits))
        self.assertEqual(3, response.metadata["outfit_count"])
        self.assertEqual([1, 2, 3], [outfit.rank for outfit in response.outfits])

    def test_response_formatter_excludes_restricted_candidate_items(self) -> None:
        formatter = ResponseFormatter()
        evaluated = [
            EvaluatedRecommendation(
                candidate_id="cand-1",
                rank=1,
                match_score=0.95,
                title="Unsafe Outfit",
                reasoning="Blocked item.",
                item_ids=["sku-blocked"],
            ),
            EvaluatedRecommendation(
                candidate_id="cand-2",
                rank=2,
                match_score=0.9,
                title="Safe Outfit",
                reasoning="Safe item.",
                item_ids=["sku-safe"],
            ),
        ]
        candidates = [
            OutfitCandidate(
                candidate_id="cand-1",
                direction_id="A",
                candidate_type="complete",
                items=[{"product_id": "sku-blocked", "title": "Lingerie Set", "garment_category": "lingerie"}],
                assembly_score=0.95,
            ),
            OutfitCandidate(
                candidate_id="cand-2",
                direction_id="A",
                candidate_type="complete",
                items=[{"product_id": "sku-safe", "title": "Wool Blazer", "garment_category": "blazer"}],
                assembly_score=0.9,
            ),
        ]
        context = CombinedContext(
            user=UserContext(
                user_id="u1",
                gender="female",
                style_preference={"primaryArchetype": "classic"},
            ),
            live=LiveContext(user_need="Need something polished"),
        )
        plan = RecommendationPlan(plan_type="complete_only", directions=[])

        response = formatter.format(evaluated, context, plan, candidates)

        self.assertEqual(1, len(response.outfits))
        self.assertEqual("Safe Outfit", response.outfits[0].title)
        self.assertEqual(1, response.outfits[0].rank)
        self.assertEqual(1, response.metadata["restricted_item_exclusion_count"])

    def test_resolve_product_url_returns_empty_when_no_canonical_url_exists(self) -> None:
        result = resolve_product_url(
            raw_url="",
            store="andamen",
            handle="palm-green-cotton-resort-shirt",
        )

        self.assertEqual("", result)


    def test_eval_payload_has_enriched_deltas_and_body_context(self) -> None:
        context = CombinedContext(
            user=UserContext(
                user_id="u1",
                gender="female",
                analysis_attributes={
                    "BodyShape": {"value": "Hourglass"},
                },
                derived_interpretations={
                    "HeightCategory": {"value": "Tall"},
                    "FrameStructure": {"value": "Medium and Balanced"},
                },
            ),
            live=LiveContext(
                user_need="Show me something bolder",
                is_followup=True,
                followup_intent="increase_boldness",
            ),
            previous_recommendations=[
                {
                    "candidate_id": "prev-1",
                    "candidate_type": "paired",
                    "primary_colors": ["navy"],
                    "occasion_fits": ["date_night"],
                    "roles": ["top", "bottom"],
                    "formality_levels": ["smart_casual"],
                    "pattern_types": ["solid"],
                    "volume_profiles": ["slim"],
                    "fit_types": ["fitted"],
                    "silhouette_types": ["tailored"],
                }
            ],
        )
        candidates = [
            OutfitCandidate(
                candidate_id="cand-2",
                direction_id="B",
                candidate_type="paired",
                items=[
                    {
                        "product_id": "sku-1",
                        "primary_color": "burgundy",
                        "occasion_fit": "date_night",
                        "role": "top",
                        "garment_category": "top",
                        "formality_level": "formal",
                        "pattern_type": "geometric",
                        "volume_profile": "oversized",
                        "fit_type": "relaxed",
                        "silhouette_type": "draped",
                    },
                    {
                        "product_id": "sku-2",
                        "primary_color": "cream",
                        "occasion_fit": "date_night",
                        "role": "bottom",
                        "garment_category": "bottom",
                        "formality_level": "formal",
                        "pattern_type": "solid",
                        "volume_profile": "slim",
                        "fit_type": "fitted",
                        "silhouette_type": "straight",
                    },
                ],
            )
        ]
        payload = json.loads(
            _build_eval_payload(
                candidates,
                context,
                RecommendationPlan(plan_type="paired_only", retrieval_count=8, directions=[]),
            )
        )

        delta = payload["candidate_deltas"][0]
        self.assertEqual("smart_casual\u2192formal", delta["formality_shift"])
        self.assertEqual(["geometric"], delta["new_patterns"])
        self.assertEqual(["solid"], delta["shared_patterns"])
        self.assertEqual(["oversized"], delta["new_volumes"])
        self.assertEqual(["slim"], delta["shared_volumes"])
        self.assertEqual(["relaxed"], delta["new_fits"])
        self.assertEqual(["fitted"], delta["shared_fits"])
        self.assertEqual(["draped", "straight"], delta["new_silhouettes"])
        self.assertEqual([], delta["shared_silhouettes"])

        body = payload["body_context_summary"]
        self.assertEqual("Tall", body["height_category"])
        self.assertEqual("Medium and Balanced", body["frame_structure"])
        self.assertEqual("Hourglass", body["body_shape"])

    def test_eval_payload_increase_boldness_deltas(self) -> None:
        context = CombinedContext(
            user=UserContext(user_id="u1", gender="female"),
            live=LiveContext(
                user_need="Show me something bolder",
                is_followup=True,
                followup_intent="increase_boldness",
            ),
            previous_recommendations=[
                {
                    "candidate_id": "prev-1",
                    "candidate_type": "paired",
                    "primary_colors": ["navy"],
                    "occasion_fits": ["date_night"],
                    "roles": ["top", "bottom"],
                    "formality_levels": ["smart_casual"],
                    "pattern_types": ["solid"],
                    "volume_profiles": ["slim"],
                    "fit_types": ["fitted"],
                    "silhouette_types": ["tailored"],
                }
            ],
        )
        candidates = [
            OutfitCandidate(
                candidate_id="cand-2",
                direction_id="B",
                candidate_type="paired",
                items=[
                    {
                        "product_id": "sku-1",
                        "primary_color": "red",
                        "occasion_fit": "date_night",
                        "role": "top",
                        "garment_category": "top",
                        "formality_level": "smart_casual",
                        "pattern_type": "animal_print",
                        "volume_profile": "oversized",
                        "fit_type": "relaxed",
                        "silhouette_type": "draped",
                    },
                    {
                        "product_id": "sku-2",
                        "primary_color": "black",
                        "occasion_fit": "date_night",
                        "role": "bottom",
                        "garment_category": "bottom",
                        "formality_level": "smart_casual",
                        "pattern_type": "solid",
                        "volume_profile": "slim",
                        "fit_type": "fitted",
                        "silhouette_type": "straight",
                    },
                ],
            )
        ]
        payload = json.loads(
            _build_eval_payload(
                candidates,
                context,
                RecommendationPlan(plan_type="paired_only", retrieval_count=8, directions=[]),
            )
        )

        delta = payload["candidate_deltas"][0]
        self.assertEqual("increase_boldness", delta["followup_intent"])
        self.assertIn("animal_print", delta["new_patterns"])
        self.assertIn("oversized", delta["new_volumes"])
        self.assertIn("slim", delta["shared_volumes"])
        self.assertTrue(len(delta["formality_shift"]) == 0)

    def test_eval_payload_formality_shift_deltas(self) -> None:
        context_increase = CombinedContext(
            user=UserContext(user_id="u1", gender="female"),
            live=LiveContext(
                user_need="Make it more formal",
                is_followup=True,
                followup_intent="increase_formality",
            ),
            previous_recommendations=[
                {
                    "candidate_id": "prev-1",
                    "candidate_type": "paired",
                    "primary_colors": ["navy"],
                    "formality_levels": ["casual"],
                    "pattern_types": ["solid"],
                    "volume_profiles": ["slim"],
                    "fit_types": ["fitted"],
                    "silhouette_types": ["tailored"],
                }
            ],
        )
        candidates = [
            OutfitCandidate(
                candidate_id="cand-2",
                direction_id="B",
                candidate_type="paired",
                items=[
                    {
                        "product_id": "sku-1",
                        "primary_color": "navy",
                        "role": "top",
                        "garment_category": "top",
                        "formality_level": "formal",
                        "pattern_type": "solid",
                        "volume_profile": "slim",
                        "fit_type": "fitted",
                        "silhouette_type": "tailored",
                    },
                    {
                        "product_id": "sku-2",
                        "primary_color": "charcoal",
                        "role": "bottom",
                        "garment_category": "bottom",
                        "formality_level": "formal",
                        "pattern_type": "solid",
                        "volume_profile": "slim",
                        "fit_type": "fitted",
                        "silhouette_type": "tailored",
                    },
                ],
            )
        ]
        payload_inc = json.loads(
            _build_eval_payload(
                candidates,
                context_increase,
                RecommendationPlan(plan_type="paired_only", retrieval_count=8, directions=[]),
            )
        )
        self.assertEqual("casual\u2192formal", payload_inc["candidate_deltas"][0]["formality_shift"])
        self.assertEqual("increase_formality", payload_inc["candidate_deltas"][0]["followup_intent"])

        # Now test decrease_formality (formal → casual)
        context_decrease = CombinedContext(
            user=UserContext(user_id="u1", gender="female"),
            live=LiveContext(
                user_need="Make it more casual",
                is_followup=True,
                followup_intent="decrease_formality",
            ),
            previous_recommendations=[
                {
                    "candidate_id": "prev-1",
                    "candidate_type": "paired",
                    "primary_colors": ["navy"],
                    "formality_levels": ["formal"],
                    "pattern_types": ["solid"],
                    "volume_profiles": ["slim"],
                    "fit_types": ["fitted"],
                    "silhouette_types": ["tailored"],
                }
            ],
        )
        candidates_dec = [
            OutfitCandidate(
                candidate_id="cand-3",
                direction_id="B",
                candidate_type="paired",
                items=[
                    {
                        "product_id": "sku-3",
                        "primary_color": "navy",
                        "role": "top",
                        "garment_category": "top",
                        "formality_level": "casual",
                        "pattern_type": "solid",
                        "volume_profile": "relaxed",
                        "fit_type": "relaxed",
                        "silhouette_type": "boxy",
                    },
                    {
                        "product_id": "sku-4",
                        "primary_color": "khaki",
                        "role": "bottom",
                        "garment_category": "bottom",
                        "formality_level": "casual",
                        "pattern_type": "solid",
                        "volume_profile": "relaxed",
                        "fit_type": "relaxed",
                        "silhouette_type": "wide",
                    },
                ],
            )
        ]
        payload_dec = json.loads(
            _build_eval_payload(
                candidates_dec,
                context_decrease,
                RecommendationPlan(plan_type="paired_only", retrieval_count=8, directions=[]),
            )
        )
        self.assertEqual("formal\u2192casual", payload_dec["candidate_deltas"][0]["formality_shift"])
        self.assertEqual("decrease_formality", payload_dec["candidate_deltas"][0]["followup_intent"])

    def test_candidate_signature_includes_all_eight_signals(self) -> None:
        from agentic_application.agents.outfit_evaluator import _candidate_signature

        candidate = OutfitCandidate(
            candidate_id="cand-full",
            direction_id="B",
            candidate_type="paired",
            items=[
                {
                    "product_id": "sku-1",
                    "primary_color": "burgundy",
                    "occasion_fit": "date_night",
                    "role": "top",
                    "garment_category": "top",
                    "formality_level": "smart_casual",
                    "pattern_type": "geometric",
                    "volume_profile": "oversized",
                    "fit_type": "relaxed",
                    "silhouette_type": "draped",
                },
                {
                    "product_id": "sku-2",
                    "primary_color": "cream",
                    "occasion_fit": "date_night",
                    "role": "bottom",
                    "garment_category": "bottom",
                    "formality_level": "smart_casual",
                    "pattern_type": "solid",
                    "volume_profile": "slim",
                    "fit_type": "fitted",
                    "silhouette_type": "straight",
                },
            ],
        )
        sig = _candidate_signature(candidate)

        self.assertEqual("cand-full", sig["candidate_id"])
        self.assertEqual("paired", sig["candidate_type"])
        self.assertEqual(["burgundy", "cream"], sig["primary_colors"])
        self.assertEqual(["date_night"], sig["occasion_fits"])
        self.assertEqual(["top", "bottom"], sig["roles"])
        self.assertEqual(["top", "bottom"], sig["garment_categories"])
        self.assertEqual(["smart_casual"], sig["formality_levels"])
        self.assertEqual(["geometric", "solid"], sig["pattern_types"])
        self.assertEqual(["oversized", "slim"], sig["volume_profiles"])
        self.assertEqual(["relaxed", "fitted"], sig["fit_types"])
        self.assertEqual(["draped", "straight"], sig["silhouette_types"])

    # ------------------------------------------------------------------
    # Concept-first paired planning tests
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Edge-case refinement: change_color & similar_to_previous
    # ------------------------------------------------------------------

    def test_assembler_penalizes_color_overlap_for_change_color(self) -> None:
        """Navy+cream pair with prior navy scores lower than burgundy+cream."""
        context = CombinedContext(
            user=UserContext(user_id="u1", gender="female"),
            live=LiveContext(
                user_need="Show me a different color",
                is_followup=True,
                followup_intent="change_color",
            ),
            previous_recommendations=[
                {
                    "candidate_id": "prev-1",
                    "candidate_type": "paired",
                    "primary_colors": ["navy"],
                    "occasion_fits": ["date_night"],
                    "roles": ["top", "bottom"],
                }
            ],
        )
        plan = RecommendationPlan(
            plan_type="paired_only",
            retrieval_count=8,
            directions=[
                DirectionSpec(
                    direction_id="A",
                    direction_type="paired",
                    label="test",
                    queries=[],
                )
            ],
        )

        def _make_product(pid: str, color: str) -> RetrievedProduct:
            return RetrievedProduct(
                product_id=pid,
                similarity=0.85,
                enriched_data={"primary_color": color, "occasion_fit": "date_night"},
                metadata={},
            )

        # Pair 1: overlapping navy top + cream bottom
        overlap_sets = [
            RetrievedSet(direction_id="A", query_id="q1", role="top", products=[_make_product("t1", "navy")]),
            RetrievedSet(direction_id="A", query_id="q2", role="bottom", products=[_make_product("b1", "cream")]),
        ]
        # Pair 2: non-overlapping burgundy top + cream bottom
        fresh_sets = [
            RetrievedSet(direction_id="A", query_id="q1", role="top", products=[_make_product("t2", "burgundy")]),
            RetrievedSet(direction_id="A", query_id="q2", role="bottom", products=[_make_product("b2", "cream")]),
        ]

        assembler = OutfitAssembler()
        overlap_candidates = assembler.assemble(overlap_sets, plan, context)
        fresh_candidates = assembler.assemble(fresh_sets, plan, context)

        self.assertTrue(len(overlap_candidates) > 0)
        self.assertTrue(len(fresh_candidates) > 0)
        # Navy overlaps with previous — should score lower
        self.assertGreater(fresh_candidates[0].assembly_score, overlap_candidates[0].assembly_score)

    def test_assembler_boosts_similar_occasion_for_similar_to_previous(self) -> None:
        """Date_night pair with prior date_night scores higher than office pair."""
        context = CombinedContext(
            user=UserContext(user_id="u1", gender="female"),
            live=LiveContext(
                user_need="Show me something similar",
                is_followup=True,
                followup_intent="similar_to_previous",
            ),
            previous_recommendations=[
                {
                    "candidate_id": "prev-1",
                    "candidate_type": "paired",
                    "primary_colors": ["navy"],
                    "occasion_fits": ["date_night"],
                    "roles": ["top", "bottom"],
                }
            ],
        )
        plan = RecommendationPlan(
            plan_type="paired_only",
            retrieval_count=8,
            directions=[
                DirectionSpec(
                    direction_id="A",
                    direction_type="paired",
                    label="test",
                    queries=[],
                )
            ],
        )

        def _make_product(pid: str, occasion: str, color: str = "navy") -> RetrievedProduct:
            return RetrievedProduct(
                product_id=pid,
                similarity=0.85,
                enriched_data={"primary_color": color, "occasion_fit": occasion},
                metadata={},
            )

        # Pair 1: matching date_night + matching color
        match_sets = [
            RetrievedSet(direction_id="A", query_id="q1", role="top", products=[_make_product("t1", "date_night", "navy")]),
            RetrievedSet(direction_id="A", query_id="q2", role="bottom", products=[_make_product("b1", "date_night", "cream")]),
        ]
        # Pair 2: different occasion, different color
        diff_sets = [
            RetrievedSet(direction_id="A", query_id="q1", role="top", products=[_make_product("t2", "office", "grey")]),
            RetrievedSet(direction_id="A", query_id="q2", role="bottom", products=[_make_product("b2", "office", "white")]),
        ]

        assembler = OutfitAssembler()
        match_candidates = assembler.assemble(match_sets, plan, context)
        diff_candidates = assembler.assemble(diff_sets, plan, context)

        self.assertTrue(len(match_candidates) > 0)
        self.assertTrue(len(diff_candidates) > 0)
        self.assertGreater(match_candidates[0].assembly_score, diff_candidates[0].assembly_score)

    def test_formatter_message_acknowledges_color_change(self) -> None:
        formatter = ResponseFormatter()
        context = CombinedContext(
            user=UserContext(
                user_id="u1",
                gender="female",
                style_preference={"primaryArchetype": "classic"},
                derived_interpretations={"SeasonalColorGroup": {"value": "Soft Summer"}},
            ),
            live=LiveContext(
                user_need="Show me a different color",
                is_followup=True,
                followup_intent="change_color",
            ),
        )
        evaluated = [
            EvaluatedRecommendation(
                candidate_id="cand-1", rank=1, match_score=0.9,
                title="Fresh Look", reasoning="Good", item_ids=["sku-1"],
            )
        ]
        candidates = [
            OutfitCandidate(
                candidate_id="cand-1", direction_id="A", candidate_type="complete",
                items=[{"product_id": "sku-1", "title": "Dress"}], assembly_score=0.9,
            )
        ]
        plan = RecommendationPlan(plan_type="complete_only", retrieval_count=8, directions=[])

        response = formatter.format(evaluated, context, plan, candidates)
        self.assertIn("fresh color direction", response.message)

    def test_formatter_message_acknowledges_similarity(self) -> None:
        formatter = ResponseFormatter()
        context = CombinedContext(
            user=UserContext(
                user_id="u1",
                gender="female",
                style_preference={"primaryArchetype": "classic"},
                derived_interpretations={"SeasonalColorGroup": {"value": "Soft Summer"}},
            ),
            live=LiveContext(
                user_need="Show me something similar",
                is_followup=True,
                followup_intent="similar_to_previous",
            ),
        )
        evaluated = [
            EvaluatedRecommendation(
                candidate_id="cand-1", rank=1, match_score=0.9,
                title="Similar Look", reasoning="Good", item_ids=["sku-1"],
            )
        ]
        candidates = [
            OutfitCandidate(
                candidate_id="cand-1", direction_id="A", candidate_type="complete",
                items=[{"product_id": "sku-1", "title": "Dress"}], assembly_score=0.9,
            )
        ]
        plan = RecommendationPlan(plan_type="complete_only", retrieval_count=8, directions=[])

        response = formatter.format(evaluated, context, plan, candidates)
        self.assertIn("similar style", response.message)

    def test_evaluator_defaults_preserve_non_color_for_change_color(self) -> None:
        """style_note should mention preserved non-color attributes for change_color."""
        delta = {
            "followup_intent": "change_color",
            "new_colors": ["burgundy"],
            "shared_colors": [],
            "preserves_occasion": True,
            "candidate_type_matches_previous": True,
            "formality_shift": "",
            "shared_silhouettes": ["straight"],
            "shared_fits": ["slim"],
            "shared_volumes": ["regular"],
        }
        defaults = _followup_reasoning_defaults(delta)
        self.assertIn("occasion fit", defaults["style_note"])
        self.assertIn("silhouette (straight)", defaults["style_note"])
        self.assertIn("fit (slim)", defaults["style_note"])
        self.assertIn("while shifting colors", defaults["style_note"])

    def test_evaluator_defaults_include_all_shared_for_similar_to_previous(self) -> None:
        """style_note should mention shared colors/patterns/volume/fit/silhouette."""
        delta = {
            "followup_intent": "similar_to_previous",
            "candidate_type_matches_previous": True,
            "preserves_occasion": True,
            "preserves_roles": True,
            "shared_colors": ["navy"],
            "shared_patterns": ["solid"],
            "shared_volumes": ["slim"],
            "shared_fits": ["fitted"],
            "shared_silhouettes": ["straight"],
            "occasion_shift": [],
        }
        defaults = _followup_reasoning_defaults(delta)
        self.assertIn("colors (navy)", defaults["style_note"])
        self.assertIn("patterns (solid)", defaults["style_note"])
        self.assertIn("volume (slim)", defaults["style_note"])
        self.assertIn("fit (fitted)", defaults["style_note"])
        self.assertIn("silhouette (straight)", defaults["style_note"])

    def test_profile_confidence_reports_missing_steps(self) -> None:
        confidence = evaluate_profile_confidence(
            {
                "profile_complete": True,
                "style_preference_complete": False,
                "images_uploaded": ["headshot"],
                "onboarding_complete": False,
            },
            {
                "status": "running",
                "profile": {"style_preference": {}},
                "derived_interpretations": {},
            },
        )
        self.assertLess(confidence.score_pct, 100)
        self.assertIn("style_preference_complete", confidence.missing_factors)
        self.assertIn("full_body_image", confidence.missing_factors)
        self.assertTrue(confidence.improvement_actions)

    def test_build_user_context_includes_wardrobe_items_from_gateway(self) -> None:
        gateway = Mock()
        gateway.get_analysis_status.return_value = {
            "status": "completed",
            "profile": {
                "gender": "female",
                "style_preference": {"primaryArchetype": "classic"},
            },
            "attributes": {"BodyShape": {"value": "Hourglass"}},
            "derived_interpretations": {"SeasonalColorGroup": {"value": "Soft Summer"}},
        }
        gateway.get_effective_seasonal_groups.return_value = []
        gateway.get_wardrobe_items.return_value = [
            {"id": "w1", "title": "Navy Blazer", "garment_category": "outerwear"},
            {"id": "w2", "title": "Cream Trousers", "garment_category": "bottom"},
        ]

        from agentic_application.context.user_context_builder import build_user_context

        user_context = build_user_context("user-1", onboarding_gateway=gateway)
        self.assertEqual(2, len(user_context.wardrobe_items))
        self.assertEqual("Navy Blazer", user_context.wardrobe_items[0]["title"])

    def test_onboarding_gate_blocks_until_analysis_is_complete(self) -> None:
        gate = evaluate_onboarding_gate(
            {
                "profile_complete": True,
                "style_preference_complete": True,
                "images_uploaded": ["full_body", "headshot"],
                "onboarding_complete": True,
            },
            {
                "status": "running",
                "profile": {"style_preference": {"primaryArchetype": "classic"}},
                "derived_interpretations": {},
            },
        )
        self.assertFalse(gate.allowed)
        self.assertEqual("analysis_pending", gate.status)
        self.assertIn("Wait for profile analysis to complete.", gate.missing_steps)

    def test_intent_router_detects_style_and_explanation_intents(self) -> None:
        style = classify_intent("What style would look good on me?")
        self.assertEqual("style_discovery", style.primary_intent)

        explanation = classify_intent(
            "Why did you recommend this?",
            previous_context={"last_recommendations": [{"candidate_id": "cand-1"}]},
        )
        self.assertEqual("explanation_request", explanation.primary_intent)

    def test_extract_sentiment_detects_anxious_language(self) -> None:
        trace = extract_sentiment("I'm nervous and unsure about what to wear for this event.")
        self.assertEqual("anxious", trace["sentiment_label"])
        self.assertLess(trace["sentiment_score"], 0)
        self.assertIn("nervous", trace["cues"])

    def test_shopping_decision_handler_returns_buy_skip_payload(self) -> None:
        user_context = UserContext(
            user_id="u1",
            gender="female",
            style_preference={"primaryArchetype": "classic", "secondaryArchetype": "romantic"},
            derived_interpretations={
                "SeasonalColorGroup": {"value": "Soft Summer"},
                "FrameStructure": {"value": "Medium and Balanced"},
            },
        )
        profile_confidence = evaluate_profile_confidence(
            {
                "profile_complete": True,
                "style_preference_complete": True,
                "images_uploaded": ["full_body", "headshot"],
            },
            {
                "status": "completed",
                "profile": {"style_preference": {"primaryArchetype": "classic"}},
                "derived_interpretations": {"SeasonalColorGroup": {"value": "Soft Summer"}},
            },
        )

        message, suggestions, payload = build_shopping_decision_response(
            message="Should I buy this navy blazer? https://store.example/item",
            user_context=user_context,
            previous_context={"last_occasion": "office"},
            profile_confidence=profile_confidence,
        )

        self.assertIn("buy / skip verdict", message.lower())
        self.assertTrue(suggestions)
        self.assertEqual("buy", payload["verdict"])
        self.assertEqual(["https://store.example/item"], payload["product_urls"])
        self.assertIn("user_profile", payload["memory_sources_read"])

    def test_pairing_request_handler_returns_wardrobe_and_catalog_payload(self) -> None:
        user_context = UserContext(
            user_id="u1",
            gender="female",
            style_preference={"primaryArchetype": "classic"},
            derived_interpretations={"SeasonalColorGroup": {"value": "Soft Summer"}},
            wardrobe_items=[
                {"id": "w1", "title": "Cream Trousers", "garment_category": "bottom", "primary_color": "cream", "occasion_fit": "office"},
                {"id": "w2", "title": "Navy Skirt", "garment_category": "bottom", "primary_color": "navy", "occasion_fit": "office"},
                {"id": "w3", "title": "Black Bag", "garment_category": "bag", "primary_color": "black"},
            ],
        )
        profile_confidence = evaluate_profile_confidence(
            {
                "profile_complete": True,
                "style_preference_complete": True,
                "images_uploaded": ["full_body", "headshot"],
            },
            {
                "status": "completed",
                "profile": {"style_preference": {"primaryArchetype": "classic"}},
                "derived_interpretations": {"SeasonalColorGroup": {"value": "Soft Summer"}},
            },
        )

        message, suggestions, payload = build_pairing_request_response(
            message="What goes with this navy blazer? https://store.example/item",
            user_context=user_context,
            previous_context={"last_occasion": "office"},
            profile_confidence=profile_confidence,
        )

        self.assertIn("pairing", message.lower())
        self.assertTrue(suggestions)
        self.assertEqual("blazer", payload["target_piece"])
        self.assertEqual("top", payload["target_role"])
        self.assertEqual("wardrobe_first", payload["pairing_mode"])
        self.assertEqual(2, len(payload["wardrobe_pairing_candidates"]))
        self.assertEqual("Cream Trousers", payload["wardrobe_pairing_candidates"][0]["title"])
        self.assertIn("complementary role", payload["wardrobe_pairing_candidates"][0]["compatibility_reasons"])
        self.assertTrue(payload["catalog_pairing_available"])
        self.assertTrue(payload["catalog_upsell"]["available"])
        self.assertEqual("Show me better options from the catalog", payload["catalog_upsell"]["cta"])
        self.assertIn("better catalog options", message.lower())
        self.assertIn("Show me better options from the catalog", suggestions)
        self.assertIn("wardrobe_memory", payload["memory_sources_read"])

    def test_outfit_check_handler_returns_assessment_payload(self) -> None:
        user_context = UserContext(
            user_id="u1",
            gender="female",
            style_preference={"primaryArchetype": "classic", "secondaryArchetype": "romantic"},
            derived_interpretations={
                "SeasonalColorGroup": {"value": "Soft Summer"},
                "FrameStructure": {"value": "Medium and Balanced"},
                "ContrastLevel": {"value": "Medium"},
            },
        )
        profile_confidence = evaluate_profile_confidence(
            {
                "profile_complete": True,
                "style_preference_complete": True,
                "images_uploaded": ["full_body", "headshot"],
            },
            {
                "status": "completed",
                "profile": {"style_preference": {"primaryArchetype": "classic"}},
                "derived_interpretations": {"SeasonalColorGroup": {"value": "Soft Summer"}},
            },
        )

        message, suggestions, payload = build_outfit_check_response(
            message="Outfit check: navy blazer, cream trousers, brown heels",
            user_context=user_context,
            previous_context={"last_occasion": "office"},
            profile_confidence=profile_confidence,
        )

        self.assertIn("outfit-check", message.lower())
        self.assertTrue(suggestions)
        self.assertEqual("strong", payload["assessment"])
        self.assertIn("blazer", payload["detected_garments"])
        self.assertTrue(payload["image_required_for_high_confidence"])

    def test_garment_on_me_handler_returns_fit_payload(self) -> None:
        user_context = UserContext(
            user_id="u1",
            gender="female",
            style_preference={"primaryArchetype": "classic", "secondaryArchetype": "romantic"},
            analysis_attributes={"BodyShape": {"value": "Hourglass"}},
            derived_interpretations={
                "SeasonalColorGroup": {"value": "Soft Summer"},
                "FrameStructure": {"value": "Medium and Balanced"},
                "HeightCategory": {"value": "Tall"},
            },
        )
        profile_confidence = evaluate_profile_confidence(
            {
                "profile_complete": True,
                "style_preference_complete": True,
                "images_uploaded": ["full_body", "headshot"],
            },
            {
                "status": "completed",
                "profile": {"style_preference": {"primaryArchetype": "classic"}},
                "derived_interpretations": {"SeasonalColorGroup": {"value": "Soft Summer"}},
            },
        )

        message, suggestions, payload = build_garment_on_me_response(
            message="How will this navy blazer look on me? https://store.example/item",
            user_context=user_context,
            previous_context={"last_occasion": "office"},
            profile_confidence=profile_confidence,
        )

        self.assertIn("look", message.lower())
        self.assertTrue(suggestions)
        self.assertEqual("blazer", payload["target_piece"])
        self.assertEqual("promising", payload["qualitative_fit"])
        self.assertTrue(payload["tryon_eligible"])

    def test_capsule_or_trip_handler_returns_bounded_plan_payload(self) -> None:
        user_context = UserContext(
            user_id="u1",
            gender="female",
            style_preference={"primaryArchetype": "classic", "secondaryArchetype": "romantic"},
            wardrobe_items=[
                {"id": "w1", "title": "Navy Blazer"},
                {"id": "w2", "title": "Cream Trousers"},
                {"id": "w3", "title": "White Shirt"},
            ],
            derived_interpretations={"SeasonalColorGroup": {"value": "Soft Summer"}},
        )
        profile_confidence = evaluate_profile_confidence(
            {
                "profile_complete": True,
                "style_preference_complete": True,
                "images_uploaded": ["full_body", "headshot"],
            },
            {
                "status": "completed",
                "profile": {"style_preference": {"primaryArchetype": "classic"}},
                "derived_interpretations": {"SeasonalColorGroup": {"value": "Soft Summer"}},
            },
        )

        message, suggestions, payload = build_capsule_or_trip_planning_response(
            message="Plan a workweek capsule for my office trip",
            user_context=user_context,
            previous_context={"last_occasion": "office"},
            profile_confidence=profile_confidence,
        )

        self.assertIn("bounded", message.lower())
        self.assertTrue(suggestions)
        self.assertEqual("trip", payload["planning_type"])
        self.assertEqual("5 looks", payload["target_horizon"])
        self.assertEqual(3, payload["wardrobe_anchor_count"])
        self.assertFalse(payload["catalog_gap_fill_needed"])

    def test_wardrobe_ingestion_handler_returns_saved_payload(self) -> None:
        user_context = UserContext(
            user_id="u1",
            gender="female",
            style_preference={"primaryArchetype": "classic"},
        )
        profile_confidence = evaluate_profile_confidence(
            {
                "profile_complete": True,
                "style_preference_complete": True,
                "images_uploaded": ["full_body", "headshot"],
            },
            {
                "status": "completed",
                "profile": {"style_preference": {"primaryArchetype": "classic"}},
                "derived_interpretations": {},
            },
        )

        message, suggestions, payload = build_wardrobe_ingestion_response(
            message="Save this navy blazer to my wardrobe https://store.example/item",
            user_context=user_context,
            profile_confidence=profile_confidence,
            saved_item={"id": "w1"},
        )

        self.assertIn("saved", message.lower())
        self.assertTrue(suggestions)
        self.assertTrue(payload["saved"])
        self.assertEqual("w1", payload["saved_item_id"])
        self.assertIn("blazer", payload["detected_garments"])

    def test_feedback_submission_handler_returns_linked_payload(self) -> None:
        message, suggestions, payload = build_feedback_submission_response(
            message="I like this one",
            previous_context={
                "last_recommendations": [{"rank": 1, "item_ids": ["sku-1", "sku-2"]}],
                "last_response_metadata": {"turn_id": "t-prev"},
            },
        )

        self.assertIn("attached", message.lower())
        self.assertTrue(suggestions)
        self.assertEqual("like", payload["event_type"])
        self.assertTrue(payload["resolved"])
        self.assertEqual(["sku-1", "sku-2"], payload["item_ids"])
        self.assertEqual("t-prev", payload["target_turn_id"])

    def test_virtual_tryon_handler_returns_success_payload(self) -> None:
        message, suggestions, payload = build_virtual_tryon_response(
            message="Show this on me https://store.example/item.jpg",
            success=True,
            product_url="https://store.example/item.jpg",
        )

        self.assertIn("virtual try-on", message.lower())
        self.assertTrue(suggestions)
        self.assertTrue(payload["success"])
        self.assertEqual("https://store.example/item.jpg", payload["product_url"])

    def test_explanation_response_references_recommendation_confidence(self) -> None:
        user_context = UserContext(
            user_id="u1",
            gender="female",
            style_preference={"primaryArchetype": "classic"},
            derived_interpretations={"SeasonalColorGroup": {"value": "Soft Summer"}},
        )
        profile_confidence = evaluate_profile_confidence(
            {
                "profile_complete": True,
                "style_preference_complete": True,
                "images_uploaded": ["full_body", "headshot"],
            },
            {
                "status": "completed",
                "profile": {"style_preference": {"primaryArchetype": "classic"}},
                "derived_interpretations": {"SeasonalColorGroup": {"value": "Soft Summer"}},
            },
        )

        message, _suggestions = build_explanation_response(
            user_context=user_context,
            previous_context={
                "last_recommendations": [{"primary_colors": ["navy"], "garment_categories": ["dress"]}],
                "memory": {"wardrobe_item_count": 6},
                "last_feedback_summary": {"event_type": "dislike", "item_ids": ["sku-1"], "item_count": 1},
                "last_response_metadata": {
                    "answer_source": "wardrobe_first",
                    "answer_components": {
                        "primary_source": "mixed",
                        "wardrobe_item_count": 2,
                        "catalog_item_count": 1,
                    },
                    "catalog_upsell": {"available": True},
                    "recommendation_confidence": {
                        "score_pct": 86,
                        "confidence_band": "high",
                        "summary": "High confidence based on retrieval strength.",
                        "explanation": ["Strongest evidence: Top recommendation match score was 0.94."],
                    }
                },
            },
            profile_confidence=profile_confidence,
        )

        self.assertIn("86%", message)
        self.assertIn("high confidence", message.lower())
        self.assertIn("strongest evidence", message.lower())
        self.assertIn("saved wardrobe", message.lower())
        self.assertIn("catalog fallback", message.lower())
        self.assertIn("negative feedback", message.lower())

    def test_orchestrator_blocks_turn_when_onboarding_is_incomplete(self) -> None:
        repo = Mock()
        onboarding_gateway = Mock()
        repo.client = Mock()
        repo.get_or_create_user.return_value = {"id": "db-user"}
        repo.get_conversation.return_value = {
            "id": "c1",
            "user_id": "db-user",
            "session_context_json": {},
        }
        repo.create_turn.return_value = {"id": "t1"}
        onboarding_gateway.get_onboarding_status.return_value = {
            "profile_complete": True,
            "style_preference_complete": False,
            "images_uploaded": ["headshot"],
            "onboarding_complete": False,
        }
        onboarding_gateway.get_analysis_status.return_value = {"status": "not_started", "profile": {}, "derived_interpretations": {}}

        with patch("agentic_application.orchestrator.ApplicationCatalogRetrievalGateway"):
            orchestrator = AgenticOrchestrator(repo=repo, onboarding_gateway=onboarding_gateway, config=Mock())
            result = orchestrator.process_turn(
                conversation_id="c1",
                external_user_id="user-1",
                message="Help me pick something",
            )

        self.assertEqual("clarification", result["response_type"])
        self.assertTrue(result["metadata"]["onboarding_required"])
        self.assertIn("Complete mandatory onboarding", result["assistant_message"])
        repo.create_sentiment_trace.assert_called_once()
        repo.create_confidence_history.assert_called_once()
        self.assertEqual("profile", repo.create_confidence_history.call_args.kwargs["confidence_type"])
        repo.create_policy_event.assert_called_once()
        self.assertEqual("onboarding_gate", repo.create_policy_event.call_args.kwargs["policy_event_type"])

    def test_orchestrator_handles_shopping_decision_without_planning_pipeline(self) -> None:
        repo = Mock()
        onboarding_gateway = Mock()
        onboarding_gateway.get_onboarding_status.return_value = {
            "profile_complete": True,
            "style_preference_complete": True,
            "images_uploaded": ["full_body", "headshot"],
            "onboarding_complete": True,
        }
        onboarding_gateway.get_analysis_status.return_value = {
            "status": "completed",
            "profile": {
                "gender": "female",
                "style_preference": {
                    "primaryArchetype": "classic",
                    "secondaryArchetype": "romantic",
                },
            },
            "attributes": {"BodyShape": {"value": "Hourglass"}},
            "derived_interpretations": {
                "SeasonalColorGroup": {"value": "Soft Summer"},
                "FrameStructure": {"value": "Medium and Balanced"},
            },
        }
        repo.client = Mock()
        repo.get_or_create_user.return_value = {"id": "db-user"}
        repo.get_conversation.return_value = {
            "id": "c1",
            "user_id": "db-user",
            "session_context_json": {"last_occasion": "office"},
        }
        repo.create_turn.return_value = {"id": "t1"}

        with patch("agentic_application.orchestrator.ApplicationCatalogRetrievalGateway"), patch(
            "agentic_application.orchestrator.OutfitArchitect"
        ) as architect_cls:
            orchestrator = AgenticOrchestrator(repo=repo, onboarding_gateway=onboarding_gateway, config=Mock())
            result = orchestrator.process_turn(
                conversation_id="c1",
                external_user_id="user-1",
                message="Should I buy this navy blazer? https://store.example/item",
            )

        architect_cls.return_value.plan.assert_not_called()
        self.assertEqual("shopping_decision", result["metadata"]["primary_intent"])
        self.assertEqual([], result["outfits"])
        self.assertIn("buy / skip", result["assistant_message"].lower())
        resolved_context = repo.finalize_turn.call_args.kwargs["resolved_context"]
        self.assertEqual("buy", resolved_context["handler_payload"]["verdict"])
        self.assertEqual("shopping_decision", resolved_context["routing_metadata"]["primary_intent"])
        self.assertIn("user_profile", resolved_context["routing_metadata"]["memory_sources_read"])
        self.assertIn("routing_metadata", result["metadata"])

    def test_orchestrator_handles_pairing_request_without_planning_pipeline(self) -> None:
        repo = Mock()
        onboarding_gateway = Mock()
        onboarding_gateway.get_onboarding_status.return_value = {
            "profile_complete": True,
            "style_preference_complete": True,
            "images_uploaded": ["full_body", "headshot"],
            "onboarding_complete": True,
        }
        onboarding_gateway.get_analysis_status.return_value = {
            "status": "completed",
            "profile": {
                "gender": "female",
                "style_preference": {
                    "primaryArchetype": "classic",
                },
            },
            "attributes": {"BodyShape": {"value": "Hourglass"}},
            "derived_interpretations": {
                "SeasonalColorGroup": {"value": "Soft Summer"},
            },
        }
        onboarding_gateway.get_wardrobe_items.return_value = [
            {"id": "w1", "title": "Cream Trousers", "garment_category": "bottom"},
        ]
        repo.client = Mock()
        repo.get_or_create_user.return_value = {"id": "db-user"}
        repo.get_conversation.return_value = {
            "id": "c1",
            "user_id": "db-user",
            "session_context_json": {"last_occasion": "office"},
        }
        repo.create_turn.return_value = {"id": "t1"}

        with patch("agentic_application.orchestrator.ApplicationCatalogRetrievalGateway"), patch(
            "agentic_application.orchestrator.OutfitArchitect"
        ) as architect_cls:
            orchestrator = AgenticOrchestrator(repo=repo, onboarding_gateway=onboarding_gateway, config=Mock())
            result = orchestrator.process_turn(
                conversation_id="c1",
                external_user_id="user-1",
                message="What goes with this blazer? https://store.example/item",
            )

        architect_cls.return_value.plan.assert_not_called()
        self.assertEqual("pairing_request", result["metadata"]["primary_intent"])
        self.assertEqual([], result["outfits"])
        self.assertIn("pair", result["assistant_message"].lower())
        resolved_context = repo.finalize_turn.call_args.kwargs["resolved_context"]
        self.assertEqual("blazer", resolved_context["handler_payload"]["target_piece"])

    def test_orchestrator_handles_outfit_check_without_planning_pipeline(self) -> None:
        repo = Mock()
        onboarding_gateway = Mock()
        onboarding_gateway.get_onboarding_status.return_value = {
            "profile_complete": True,
            "style_preference_complete": True,
            "images_uploaded": ["full_body", "headshot"],
            "onboarding_complete": True,
        }
        onboarding_gateway.get_analysis_status.return_value = {
            "status": "completed",
            "profile": {
                "gender": "female",
                "style_preference": {
                    "primaryArchetype": "classic",
                    "secondaryArchetype": "romantic",
                },
            },
            "attributes": {"BodyShape": {"value": "Hourglass"}},
            "derived_interpretations": {
                "SeasonalColorGroup": {"value": "Soft Summer"},
                "FrameStructure": {"value": "Medium and Balanced"},
                "ContrastLevel": {"value": "Medium"},
            },
        }
        repo.client = Mock()
        repo.get_or_create_user.return_value = {"id": "db-user"}
        repo.get_conversation.return_value = {
            "id": "c1",
            "user_id": "db-user",
            "session_context_json": {"last_occasion": "office"},
        }
        repo.create_turn.return_value = {"id": "t1"}

        with patch("agentic_application.orchestrator.ApplicationCatalogRetrievalGateway"), patch(
            "agentic_application.orchestrator.OutfitArchitect"
        ) as architect_cls:
            orchestrator = AgenticOrchestrator(repo=repo, onboarding_gateway=onboarding_gateway, config=Mock())
            result = orchestrator.process_turn(
                conversation_id="c1",
                external_user_id="user-1",
                message="Outfit check: navy blazer, cream trousers, brown heels",
            )

        architect_cls.return_value.plan.assert_not_called()
        self.assertEqual("outfit_check", result["metadata"]["primary_intent"])
        self.assertEqual([], result["outfits"])
        self.assertIn("outfit-check", result["assistant_message"].lower())
        resolved_context = repo.finalize_turn.call_args.kwargs["resolved_context"]
        self.assertEqual("strong", resolved_context["handler_payload"]["assessment"])

    def test_orchestrator_handles_garment_on_me_without_planning_pipeline(self) -> None:
        repo = Mock()
        onboarding_gateway = Mock()
        onboarding_gateway.get_onboarding_status.return_value = {
            "profile_complete": True,
            "style_preference_complete": True,
            "images_uploaded": ["full_body", "headshot"],
            "onboarding_complete": True,
        }
        onboarding_gateway.get_analysis_status.return_value = {
            "status": "completed",
            "profile": {
                "gender": "female",
                "style_preference": {
                    "primaryArchetype": "classic",
                    "secondaryArchetype": "romantic",
                },
            },
            "attributes": {"BodyShape": {"value": "Hourglass"}},
            "derived_interpretations": {
                "SeasonalColorGroup": {"value": "Soft Summer"},
                "FrameStructure": {"value": "Medium and Balanced"},
                "HeightCategory": {"value": "Tall"},
            },
        }
        repo.client = Mock()
        repo.get_or_create_user.return_value = {"id": "db-user"}
        repo.get_conversation.return_value = {
            "id": "c1",
            "user_id": "db-user",
            "session_context_json": {"last_occasion": "office"},
        }
        repo.create_turn.return_value = {"id": "t1"}

        with patch("agentic_application.orchestrator.ApplicationCatalogRetrievalGateway"), patch(
            "agentic_application.orchestrator.OutfitArchitect"
        ) as architect_cls:
            orchestrator = AgenticOrchestrator(repo=repo, onboarding_gateway=onboarding_gateway, config=Mock())
            result = orchestrator.process_turn(
                conversation_id="c1",
                external_user_id="user-1",
                message="How will this navy blazer look on me? https://store.example/item",
            )

        architect_cls.return_value.plan.assert_not_called()
        self.assertEqual("garment_on_me_request", result["metadata"]["primary_intent"])
        self.assertEqual([], result["outfits"])
        self.assertIn("look", result["assistant_message"].lower())
        resolved_context = repo.finalize_turn.call_args.kwargs["resolved_context"]
        self.assertEqual("promising", resolved_context["handler_payload"]["qualitative_fit"])
        self.assertTrue(resolved_context["handler_payload"]["tryon_eligible"])

    def test_orchestrator_handles_capsule_or_trip_without_planning_pipeline(self) -> None:
        repo = Mock()
        onboarding_gateway = Mock()
        onboarding_gateway.get_onboarding_status.return_value = {
            "profile_complete": True,
            "style_preference_complete": True,
            "images_uploaded": ["full_body", "headshot"],
            "onboarding_complete": True,
        }
        onboarding_gateway.get_analysis_status.return_value = {
            "status": "completed",
            "profile": {
                "gender": "female",
                "style_preference": {
                    "primaryArchetype": "classic",
                    "secondaryArchetype": "romantic",
                },
            },
            "attributes": {"BodyShape": {"value": "Hourglass"}},
            "derived_interpretations": {
                "SeasonalColorGroup": {"value": "Soft Summer"},
            },
        }
        onboarding_gateway.get_wardrobe_items.return_value = [
            {"id": "w1", "title": "Navy Blazer"},
            {"id": "w2", "title": "Cream Trousers"},
        ]
        repo.client = Mock()
        repo.get_or_create_user.return_value = {"id": "db-user"}
        repo.get_conversation.return_value = {
            "id": "c1",
            "user_id": "db-user",
            "session_context_json": {"last_occasion": "office"},
        }
        repo.create_turn.return_value = {"id": "t1"}

        with patch("agentic_application.orchestrator.ApplicationCatalogRetrievalGateway"), patch(
            "agentic_application.orchestrator.OutfitArchitect"
        ) as architect_cls:
            orchestrator = AgenticOrchestrator(repo=repo, onboarding_gateway=onboarding_gateway, config=Mock())
            result = orchestrator.process_turn(
                conversation_id="c1",
                external_user_id="user-1",
                message="Plan a workweek capsule for my office trip",
            )

        architect_cls.return_value.plan.assert_not_called()
        self.assertEqual("capsule_or_trip_planning", result["metadata"]["primary_intent"])
        self.assertEqual("wardrobe_first", result["metadata"]["answer_source"])
        self.assertEqual("wardrobe", result["metadata"]["answer_components"]["primary_source"])
        self.assertIn("recommendation_confidence", result["metadata"])
        self.assertTrue(result["outfits"])
        self.assertEqual("Wardrobe Plan 1", result["outfits"][0]["title"])
        self.assertTrue(result["outfits"][0]["items"])
        self.assertEqual("wardrobe", result["outfits"][0]["items"][0]["source"])
        self.assertIn("bounded", result["assistant_message"].lower())
        self.assertIn("better catalog options", result["assistant_message"].lower())
        self.assertTrue(result["metadata"]["catalog_upsell"]["available"])
        self.assertIn("Show me better options from the catalog", result["follow_up_suggestions"])
        resolved_context = repo.finalize_turn.call_args.kwargs["resolved_context"]
        self.assertEqual("trip", resolved_context["handler_payload"]["planning_type"])
        self.assertEqual("wardrobe_first", resolved_context["handler_payload"]["answer_source"])
        self.assertTrue(resolved_context["handler_payload"]["catalog_upsell"]["available"])
        self.assertGreaterEqual(resolved_context["handler_payload"]["wardrobe_plan_count"], 1)

    def test_orchestrator_handles_wardrobe_ingestion_without_planning_pipeline(self) -> None:
        repo = Mock()
        onboarding_gateway = Mock()
        onboarding_gateway.get_onboarding_status.return_value = {
            "profile_complete": True,
            "style_preference_complete": True,
            "images_uploaded": ["full_body", "headshot"],
            "onboarding_complete": True,
        }
        onboarding_gateway.get_analysis_status.return_value = {
            "status": "completed",
            "profile": {
                "gender": "female",
                "style_preference": {
                    "primaryArchetype": "classic",
                },
            },
            "attributes": {"BodyShape": {"value": "Hourglass"}},
            "derived_interpretations": {
                "SeasonalColorGroup": {"value": "Soft Summer"},
            },
        }
        onboarding_gateway.save_chat_wardrobe_item.return_value = {"id": "w1"}
        repo.client = Mock()
        repo.get_or_create_user.return_value = {"id": "db-user"}
        repo.get_conversation.return_value = {
            "id": "c1",
            "user_id": "db-user",
            "session_context_json": {},
        }
        repo.create_turn.return_value = {"id": "t1"}

        with patch("agentic_application.orchestrator.ApplicationCatalogRetrievalGateway"), patch(
            "agentic_application.orchestrator.OutfitArchitect"
        ) as architect_cls:
            orchestrator = AgenticOrchestrator(repo=repo, onboarding_gateway=onboarding_gateway, config=Mock())
            result = orchestrator.process_turn(
                conversation_id="c1",
                external_user_id="user-1",
                message="Save this navy blazer to my wardrobe https://store.example/item",
            )

        architect_cls.return_value.plan.assert_not_called()
        onboarding_gateway.save_chat_wardrobe_item.assert_called_once()
        self.assertEqual("wardrobe_ingestion", result["metadata"]["primary_intent"])
        self.assertEqual([], result["outfits"])
        self.assertIn("saved", result["assistant_message"].lower())
        resolved_context = repo.finalize_turn.call_args.kwargs["resolved_context"]
        self.assertTrue(resolved_context["handler_payload"]["saved"])
        self.assertEqual("w1", resolved_context["handler_payload"]["saved_item_id"])

    def test_orchestrator_handles_feedback_submission_without_planning_pipeline(self) -> None:
        repo = Mock()
        onboarding_gateway = Mock()
        onboarding_gateway.get_onboarding_status.return_value = {
            "profile_complete": True,
            "style_preference_complete": True,
            "images_uploaded": ["full_body", "headshot"],
            "onboarding_complete": True,
        }
        onboarding_gateway.get_analysis_status.return_value = {
            "status": "completed",
            "profile": {
                "gender": "female",
                "style_preference": {
                    "primaryArchetype": "classic",
                },
            },
            "attributes": {"BodyShape": {"value": "Hourglass"}},
            "derived_interpretations": {
                "SeasonalColorGroup": {"value": "Soft Summer"},
            },
        }
        repo.client = Mock()
        repo.get_or_create_user.return_value = {"id": "db-user"}
        repo.get_conversation.return_value = {
            "id": "c1",
            "user_id": "db-user",
            "session_context_json": {
                "last_recommendations": [{"rank": 1, "item_ids": ["sku-1", "sku-2"]}],
                "last_response_metadata": {"turn_id": "t-prev"},
            },
        }
        repo.create_turn.return_value = {"id": "t1"}

        with patch("agentic_application.orchestrator.ApplicationCatalogRetrievalGateway"), patch(
            "agentic_application.orchestrator.OutfitArchitect"
        ) as architect_cls:
            orchestrator = AgenticOrchestrator(repo=repo, onboarding_gateway=onboarding_gateway, config=Mock())
            result = orchestrator.process_turn(
                conversation_id="c1",
                external_user_id="user-1",
                message="I dislike this one",
            )

        architect_cls.return_value.plan.assert_not_called()
        self.assertEqual("feedback_submission", result["metadata"]["primary_intent"])
        self.assertEqual([], result["outfits"])
        self.assertIn("feedback", result["assistant_message"].lower())
        self.assertEqual(2, repo.create_feedback_event.call_count)
        self.assertEqual(2, repo.create_catalog_interaction.call_count)
        resolved_context = repo.finalize_turn.call_args.kwargs["resolved_context"]
        self.assertEqual("dislike", resolved_context["handler_payload"]["event_type"])

    def test_orchestrator_handles_virtual_tryon_without_planning_pipeline(self) -> None:
        repo = Mock()
        onboarding_gateway = Mock()
        onboarding_gateway.get_onboarding_status.return_value = {
            "profile_complete": True,
            "style_preference_complete": True,
            "images_uploaded": ["full_body", "headshot"],
            "onboarding_complete": True,
        }
        onboarding_gateway.get_analysis_status.return_value = {
            "status": "completed",
            "profile": {
                "gender": "female",
                "style_preference": {
                    "primaryArchetype": "classic",
                },
            },
            "attributes": {"BodyShape": {"value": "Hourglass"}},
            "derived_interpretations": {
                "SeasonalColorGroup": {"value": "Soft Summer"},
            },
        }
        onboarding_gateway.get_person_image_path.return_value = "/tmp/person.jpg"
        repo.client = Mock()
        repo.get_or_create_user.return_value = {"id": "db-user"}
        repo.get_conversation.return_value = {
            "id": "c1",
            "user_id": "db-user",
            "session_context_json": {},
        }
        repo.create_turn.return_value = {"id": "t1"}

        with patch("agentic_application.orchestrator.ApplicationCatalogRetrievalGateway"), patch(
            "agentic_application.orchestrator.OutfitArchitect"
        ) as architect_cls:
            orchestrator = AgenticOrchestrator(repo=repo, onboarding_gateway=onboarding_gateway, config=Mock())
            orchestrator.tryon_service = Mock()
            orchestrator.tryon_quality_gate = Mock()
            orchestrator.tryon_service.generate_tryon.return_value = {
                "success": True,
                "data_url": "data:image/png;base64,abc",
            }
            orchestrator.tryon_quality_gate.evaluate.return_value = {
                "passed": True,
                "quality_score_pct": 88,
                "reason_code": "",
                "message": "Passed quality checks.",
                "factors": [],
            }
            result = orchestrator.process_turn(
                conversation_id="c1",
                external_user_id="user-1",
                message="Show this on me https://store.example/item.jpg",
            )

        architect_cls.return_value.plan.assert_not_called()
        self.assertEqual("virtual_tryon_request", result["metadata"]["primary_intent"])
        self.assertEqual([], result["outfits"])
        resolved_context = repo.finalize_turn.call_args.kwargs["resolved_context"]
        self.assertTrue(resolved_context["handler_payload"]["success"])
        self.assertEqual("data:image/png;base64,abc", resolved_context["handler_payload"]["tryon_image"])
        self.assertTrue(resolved_context["handler_payload"]["quality_gate"]["passed"])
        self.assertEqual("virtual_tryon_guardrail", repo.create_policy_event.call_args.kwargs["policy_event_type"])
        self.assertEqual("allowed", repo.create_policy_event.call_args.kwargs["decision"])
        self.assertEqual("quality_gate_passed", repo.create_policy_event.call_args.kwargs["reason_code"])

    def test_orchestrator_virtual_tryon_blocks_failed_quality_gate(self) -> None:
        repo = Mock()
        onboarding_gateway = Mock()
        onboarding_gateway.get_onboarding_status.return_value = {
            "profile_complete": True,
            "style_preference_complete": True,
            "images_uploaded": ["full_body", "headshot"],
            "onboarding_complete": True,
        }
        onboarding_gateway.get_analysis_status.return_value = {
            "status": "completed",
            "profile": {"gender": "female", "style_preference": {"primaryArchetype": "classic"}},
            "attributes": {"BodyShape": {"value": "Hourglass"}},
            "derived_interpretations": {"SeasonalColorGroup": {"value": "Soft Summer"}},
        }
        onboarding_gateway.get_person_image_path.return_value = "/tmp/person.jpg"
        repo.client = Mock()
        repo.get_or_create_user.return_value = {"id": "db-user"}
        repo.get_conversation.return_value = {"id": "c1", "user_id": "db-user", "session_context_json": {}}
        repo.create_turn.return_value = {"id": "t1"}

        with patch("agentic_application.orchestrator.ApplicationCatalogRetrievalGateway"), patch(
            "agentic_application.orchestrator.OutfitArchitect"
        ):
            orchestrator = AgenticOrchestrator(repo=repo, onboarding_gateway=onboarding_gateway, config=Mock())
            orchestrator.tryon_service = Mock()
            orchestrator.tryon_quality_gate = Mock()
            orchestrator.tryon_service.generate_tryon.return_value = {
                "success": True,
                "data_url": "data:image/png;base64,abc",
            }
            orchestrator.tryon_quality_gate.evaluate.return_value = {
                "passed": False,
                "quality_score_pct": 0,
                "reason_code": "low_detail_output",
                "message": "Generated try-on output lacks enough visual detail.",
                "factors": [],
            }
            result = orchestrator.process_turn(
                conversation_id="c1",
                external_user_id="user-1",
                message="Show this on me https://store.example/item.jpg",
            )

        self.assertEqual("virtual_tryon_request", result["metadata"]["primary_intent"])
        self.assertIn("cleaner product image", result["assistant_message"].lower())
        resolved_context = repo.finalize_turn.call_args.kwargs["resolved_context"]
        self.assertFalse(resolved_context["handler_payload"]["success"])
        self.assertNotIn("tryon_image", resolved_context["handler_payload"])
        self.assertEqual("low_detail_output", resolved_context["handler_payload"]["quality_gate"]["reason_code"])
        self.assertEqual("virtual_tryon_guardrail", repo.create_policy_event.call_args.kwargs["policy_event_type"])

    def test_orchestrator_virtual_tryon_returns_graceful_failure_without_person_image(self) -> None:
        repo = Mock()
        onboarding_gateway = Mock()
        onboarding_gateway.get_onboarding_status.return_value = {
            "profile_complete": True,
            "style_preference_complete": True,
            "images_uploaded": ["full_body", "headshot"],
            "onboarding_complete": True,
        }
        onboarding_gateway.get_analysis_status.return_value = {
            "status": "completed",
            "profile": {
                "gender": "female",
                "style_preference": {
                    "primaryArchetype": "classic",
                },
            },
            "attributes": {"BodyShape": {"value": "Hourglass"}},
            "derived_interpretations": {
                "SeasonalColorGroup": {"value": "Soft Summer"},
            },
        }
        onboarding_gateway.get_person_image_path.return_value = ""
        repo.client = Mock()
        repo.get_or_create_user.return_value = {"id": "db-user"}
        repo.get_conversation.return_value = {
            "id": "c1",
            "user_id": "db-user",
            "session_context_json": {},
        }
        repo.create_turn.return_value = {"id": "t1"}

        with patch("agentic_application.orchestrator.ApplicationCatalogRetrievalGateway"), patch(
            "agentic_application.orchestrator.OutfitArchitect"
        ) as architect_cls:
            orchestrator = AgenticOrchestrator(repo=repo, onboarding_gateway=onboarding_gateway, config=Mock())
            result = orchestrator.process_turn(
                conversation_id="c1",
                external_user_id="user-1",
                message="Show this on me https://store.example/item.jpg",
            )

        architect_cls.return_value.plan.assert_not_called()
        self.assertEqual("virtual_tryon_request", result["metadata"]["primary_intent"])
        self.assertIn("full-body photo", result["assistant_message"].lower())
        resolved_context = repo.finalize_turn.call_args.kwargs["resolved_context"]
        self.assertFalse(resolved_context["handler_payload"]["success"])

    def test_orchestrator_returns_wardrobe_first_occasion_recommendation(self) -> None:
        repo = Mock()
        onboarding_gateway = Mock()
        onboarding_gateway.get_onboarding_status.return_value = {
            "profile_complete": True,
            "style_preference_complete": True,
            "images_uploaded": ["full_body", "headshot"],
            "onboarding_complete": True,
        }
        onboarding_gateway.get_analysis_status.return_value = {
            "status": "completed",
            "profile": {
                "gender": "female",
                "style_preference": {
                    "primaryArchetype": "classic",
                },
            },
            "attributes": {"BodyShape": {"value": "Hourglass"}},
            "derived_interpretations": {
                "SeasonalColorGroup": {"value": "Soft Summer"},
            },
        }
        onboarding_gateway.get_wardrobe_items.return_value = [
            {"id": "w1", "title": "Navy Blazer", "garment_category": "top", "occasion_fit": "office", "formality_level": "business_casual"},
            {"id": "w2", "title": "Cream Trousers", "garment_category": "bottom", "occasion_fit": "office", "formality_level": "business_casual"},
        ]
        repo.client = Mock()
        repo.get_or_create_user.return_value = {"id": "db-user"}
        repo.get_conversation.return_value = {
            "id": "c1",
            "user_id": "db-user",
            "session_context_json": {},
        }
        repo.create_turn.return_value = {"id": "t1"}

        with patch("agentic_application.orchestrator.ApplicationCatalogRetrievalGateway"), patch(
            "agentic_application.orchestrator.OutfitArchitect"
        ) as architect_cls:
            orchestrator = AgenticOrchestrator(repo=repo, onboarding_gateway=onboarding_gateway, config=Mock())
            result = orchestrator.process_turn(
                conversation_id="c1",
                external_user_id="user-1",
                message="What should I wear to the office tomorrow?",
            )

        architect_cls.return_value.plan.assert_not_called()
        self.assertEqual("occasion_recommendation", result["metadata"]["primary_intent"])
        self.assertEqual("wardrobe_first", result["metadata"]["answer_source"])
        self.assertEqual("wardrobe", result["metadata"]["answer_components"]["primary_source"])
        self.assertIn("recommendation_confidence", result["metadata"])
        self.assertEqual(1, len(result["outfits"]))
        self.assertEqual(2, len(result["outfits"][0]["items"]))
        self.assertTrue(all(item["source"] == "wardrobe" for item in result["outfits"][0]["items"]))
        self.assertTrue(result["metadata"]["catalog_upsell"]["available"])
        self.assertIn("better catalog options", result["assistant_message"].lower())
        self.assertIn("Show me better options from the catalog", result["follow_up_suggestions"])
        resolved_context = repo.finalize_turn.call_args.kwargs["resolved_context"]
        self.assertEqual("occasion_recommendation_wardrobe_first", resolved_context["handler"])
        self.assertEqual(["w1", "w2"], resolved_context["handler_payload"]["selected_item_ids"])
        self.assertEqual("wardrobe", resolved_context["handler_payload"]["answer_components"]["primary_source"])
        self.assertTrue(resolved_context["handler_payload"]["catalog_upsell"]["available"])

    def test_orchestrator_handles_style_discovery_without_planning_pipeline(self) -> None:
        repo = Mock()
        onboarding_gateway = Mock()
        onboarding_gateway.get_onboarding_status.return_value = {
            "profile_complete": True,
            "style_preference_complete": True,
            "images_uploaded": ["full_body", "headshot"],
            "onboarding_complete": True,
        }
        onboarding_gateway.get_analysis_status.return_value = {
            "status": "completed",
            "profile": {
                "gender": "female",
                "style_preference": {
                    "primaryArchetype": "classic",
                    "secondaryArchetype": "romantic",
                },
            },
            "attributes": {"BodyShape": {"value": "Hourglass"}},
            "derived_interpretations": {
                "SeasonalColorGroup": {"value": "Soft Summer"},
                "ContrastLevel": {"value": "Medium"},
                "FrameStructure": {"value": "Medium and Balanced"},
                "HeightCategory": {"value": "Tall"},
            },
        }
        repo.client = Mock()
        repo.get_or_create_user.return_value = {"id": "db-user"}
        repo.get_conversation.return_value = {
            "id": "c1",
            "user_id": "db-user",
            "session_context_json": {},
        }
        repo.create_turn.return_value = {"id": "t1"}

        with patch("agentic_application.orchestrator.ApplicationCatalogRetrievalGateway"), patch(
            "agentic_application.orchestrator.OutfitArchitect"
        ) as architect_cls:
            orchestrator = AgenticOrchestrator(repo=repo, onboarding_gateway=onboarding_gateway, config=Mock())
            result = orchestrator.process_turn(
                conversation_id="c1",
                external_user_id="user-1",
                message="What style would look good on me?",
            )

        architect_cls.return_value.plan.assert_not_called()
        self.assertEqual("style_discovery", result["metadata"]["primary_intent"])
        self.assertIn("style direction", result["assistant_message"])
        resolved_context = repo.finalize_turn.call_args.kwargs["resolved_context"]
        self.assertEqual("style_discovery", resolved_context["routing_metadata"]["primary_intent"])
        self.assertIn("derived_interpretations", resolved_context["routing_metadata"]["memory_sources_read"])
        self.assertIn("confidence_history", resolved_context["routing_metadata"]["memory_sources_written"])


if __name__ == "__main__":
    unittest.main()
