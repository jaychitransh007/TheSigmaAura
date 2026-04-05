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
from agentic_application.agents.outfit_check_agent import OutfitCheckAgent
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
from agentic_application.onboarding_gate import evaluate as evaluate_onboarding_gate
from agentic_application.orchestrator import AgenticOrchestrator
from agentic_application.profile_confidence import evaluate_profile_confidence
from agentic_application.recommendation_confidence import evaluate_recommendation_confidence
from agentic_application.product_links import resolve_product_url
from agentic_application.services.dependency_reporting import build_dependency_report
from agentic_application.services.tryon_quality_gate import TryonQualityGate
from agentic_application.agents.response_formatter import _build_zero_result_fallback
from agentic_application.intent_registry import Action, FollowUpIntent, Intent
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

    def test_dependency_report_summarizes_repeat_usage_cohorts_and_memory_lift(self) -> None:
        report = build_dependency_report(
            onboarding_profiles=[
                {"user_id": "user-1", "onboarding_complete": True, "acquisition_source": "instagram"},
                {"user_id": "user-2", "onboarding_complete": True, "acquisition_source": "organic"},
            ],
            dependency_events=[
                {
                    "user_id": "user-1",
                    "event_type": "turn_completed",
                    "source_channel": "web",
                    "primary_intent": Intent.OCCASION_RECOMMENDATION,
                    "metadata_json": {"memory_sources_read": ["user_profile", "wardrobe_memory"]},
                    "created_at": "2026-03-01T10:00:00+00:00",
                },
                {
                    "user_id": "user-1",
                    "event_type": "turn_completed",
                    "source_channel": "web",
                    "primary_intent": Intent.PAIRING_REQUEST,
                    "metadata_json": {"memory_sources_read": ["wardrobe_memory"]},
                    "created_at": "2026-03-03T10:00:00+00:00",
                },
                {
                    "user_id": "user-1",
                    "event_type": "turn_completed",
                    "source_channel": "web",
                    "primary_intent": Intent.PAIRING_REQUEST,
                    "metadata_json": {"memory_sources_read": ["wardrobe_memory"]},
                    "created_at": "2026-03-10T10:00:00+00:00",
                },
                {
                    "user_id": "user-2",
                    "event_type": "turn_completed",
                    "source_channel": "web",
                    "primary_intent": Intent.STYLE_DISCOVERY,
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
        self.assertEqual("instagram", report["acquisition_sources"][0]["key"])
        self.assertEqual(Intent.PAIRING_REQUEST, report["recurring_anchor_intents_by_cohort"]["instagram"][0]["key"])
        wardrobe_lift = next(item for item in report["memory_input_retention_lift"] if item["memory_input"] == "wardrobe_items")
        self.assertGreater(wardrobe_lift["lift_pct_points"], 0)

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
            followup_intent=FollowUpIntent.INCREASE_BOLDNESS,
        )
        memory = build_conversation_memory(previous_context, live_context)
        effective = apply_conversation_memory(live_context, memory)

        self.assertTrue(effective.is_followup)
        self.assertEqual("wedding", effective.occasion_signal)
        self.assertEqual("formal", effective.formality_hint)
        self.assertIn("elongation", effective.specific_needs)
        self.assertEqual(2, memory.followup_count)

    def test_conversation_memory_tracks_intent_channel_and_wardrobe(self) -> None:
        previous_context = {
            "memory": {
                "recent_intents": [Intent.SHOPPING_DECISION],
                "recent_channels": ["web"],
                "wardrobe_item_count": 1,
                "wardrobe_memory_enabled": True,
            },
        }

        live_context = LiveContext(user_need="Need help for office tomorrow", occasion_signal="office")
        memory = build_conversation_memory(
            previous_context,
            live_context,
            current_intent=Intent.OCCASION_RECOMMENDATION,
            channel="web",
            wardrobe_item_count=3,
        )

        self.assertEqual([Intent.SHOPPING_DECISION, Intent.OCCASION_RECOMMENDATION], memory.recent_intents)
        self.assertEqual(["web"], memory.recent_channels)
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
                followup_intent=FollowUpIntent.INCREASE_BOLDNESS,
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
        self.assertEqual([Intent.OCCASION_RECOMMENDATION], session_context["memory"]["recent_intents"])
        self.assertEqual(["web"], session_context["memory"]["recent_channels"])
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
                "primary_intent": Intent.OCCASION_RECOMMENDATION,
                "title": "Evening Dress",
            },
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
                followup_intent=FollowUpIntent.SIMILAR_TO_PREVIOUS,
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
                followup_intent=FollowUpIntent.CHANGE_COLOR,
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
                followup_intent=FollowUpIntent.SIMILAR_TO_PREVIOUS,
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
                followup_intent=FollowUpIntent.SIMILAR_TO_PREVIOUS,
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
                followup_intent=FollowUpIntent.INCREASE_BOLDNESS,
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
                followup_intent=FollowUpIntent.INCREASE_BOLDNESS,
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
        self.assertEqual(FollowUpIntent.INCREASE_BOLDNESS, delta["followup_intent"])
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
                followup_intent=FollowUpIntent.INCREASE_FORMALITY,
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
        self.assertEqual(FollowUpIntent.INCREASE_FORMALITY, payload_inc["candidate_deltas"][0]["followup_intent"])

        # Now test decrease_formality (formal → casual)
        context_decrease = CombinedContext(
            user=UserContext(user_id="u1", gender="female"),
            live=LiveContext(
                user_need="Make it more casual",
                is_followup=True,
                followup_intent=FollowUpIntent.DECREASE_FORMALITY,
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
        self.assertEqual(FollowUpIntent.DECREASE_FORMALITY, payload_dec["candidate_deltas"][0]["followup_intent"])

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
                followup_intent=FollowUpIntent.CHANGE_COLOR,
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
                followup_intent=FollowUpIntent.SIMILAR_TO_PREVIOUS,
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
                followup_intent=FollowUpIntent.CHANGE_COLOR,
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
                followup_intent=FollowUpIntent.SIMILAR_TO_PREVIOUS,
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
            "followup_intent": FollowUpIntent.CHANGE_COLOR,
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
            "followup_intent": FollowUpIntent.SIMILAR_TO_PREVIOUS,
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
        repo.create_confidence_history.assert_called_once()
        self.assertEqual("profile", repo.create_confidence_history.call_args.kwargs["confidence_type"])
        repo.create_policy_event.assert_called_once()
        self.assertEqual("onboarding_gate", repo.create_policy_event.call_args.kwargs["policy_event_type"])

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
        self.assertEqual(Intent.VIRTUAL_TRYON_REQUEST, result["metadata"]["primary_intent"])
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

        self.assertEqual(Intent.VIRTUAL_TRYON_REQUEST, result["metadata"]["primary_intent"])
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
        self.assertEqual(Intent.VIRTUAL_TRYON_REQUEST, result["metadata"]["primary_intent"])
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
        self.assertEqual(Intent.OCCASION_RECOMMENDATION, result["metadata"]["primary_intent"])
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
        self.assertEqual("wardrobe_first", resolved_context["response_metadata"]["answer_source"])
        self.assertEqual(["w1", "w2"], resolved_context["handler_payload"]["selected_item_ids"])
        self.assertEqual("wardrobe", resolved_context["handler_payload"]["answer_components"]["primary_source"])
        self.assertTrue(resolved_context["handler_payload"]["catalog_upsell"]["available"])
        self.assertEqual("auto", result["metadata"]["source_selection"]["preferred_source"])
        self.assertEqual("wardrobe", result["metadata"]["source_selection"]["fulfilled_source"])

    def test_explicit_wardrobe_occasion_request_prefers_saved_wardrobe(self) -> None:
        repo = Mock()
        repo.client = Mock()
        repo.get_or_create_user.return_value = {"id": "db-user"}
        repo.get_conversation.return_value = {
            "id": "c1",
            "user_id": "db-user",
            "session_context_json": {},
        }
        repo.create_turn.return_value = {"id": "t1"}
        gw = Mock()
        gw.get_onboarding_status.return_value = {
            "profile_complete": True,
            "style_preference_complete": True,
            "images_uploaded": ["full_body", "headshot"],
            "onboarding_complete": True,
        }
        gw.get_analysis_status.return_value = {
            "status": "completed",
            "profile": {"gender": "female", "style_preference": {"primaryArchetype": "classic"}},
            "attributes": {"BodyShape": {"value": "Hourglass"}},
            "derived_interpretations": {"SeasonalColorGroup": {"value": "Soft Summer"}},
        }
        gw.get_wardrobe_items.return_value = [
            {"id": "w1", "title": "Navy Blazer", "garment_category": "top", "occasion_fit": "office", "formality_level": "business_casual"},
            {"id": "w2", "title": "Cream Trousers", "garment_category": "bottom", "occasion_fit": "office", "formality_level": "business_casual"},
        ]
        planner_mock = Mock()
        from agentic_application.schemas import CopilotPlanResult, CopilotResolvedContext, CopilotActionParameters
        planner_mock.plan.return_value = CopilotPlanResult(
            intent=Intent.OCCASION_RECOMMENDATION,
            intent_confidence=0.95,
            action=Action.RUN_RECOMMENDATION_PIPELINE,
            context_sufficient=True,
            assistant_message="Let me build that.",
            follow_up_suggestions=["Show me more"],
            resolved_context=CopilotResolvedContext(
                occasion_signal="office",
                formality_hint="business_casual",
            ),
            action_parameters=CopilotActionParameters(),
        )

        with patch("agentic_application.orchestrator.ApplicationCatalogRetrievalGateway"), patch(
            "agentic_application.orchestrator.OutfitArchitect"
        ) as architect_cls, patch("agentic_application.orchestrator.CopilotPlanner", return_value=planner_mock):
            orchestrator = AgenticOrchestrator(repo=repo, onboarding_gateway=gw, config=Mock())
            result = orchestrator.process_turn(
                conversation_id="c1",
                external_user_id="user-1",
                message="Build me an office outfit from my wardrobe",
            )

        architect_cls.return_value.plan.assert_not_called()
        self.assertEqual("wardrobe_first", result["metadata"]["answer_source"])
        self.assertEqual("wardrobe", result["metadata"]["source_selection"]["preferred_source"])
        self.assertEqual("wardrobe", result["metadata"]["source_selection"]["fulfilled_source"])
        self.assertIn("wardrobe_source_override", result["metadata"]["intent_reason_codes"])

    def test_single_item_wardrobe_first_does_not_short_circuit_catalog_pipeline(self) -> None:
        from agentic_application.schemas import (
            CopilotPlanResult, CopilotResolvedContext, CopilotActionParameters,
            RecommendationPlan, DirectionSpec, QuerySpec, ResolvedContextBlock,
            OutfitCard, RecommendationResponse,
        )
        repo = Mock()
        repo.client = Mock()
        repo.get_or_create_user.return_value = {"id": "db-user"}
        repo.get_conversation.return_value = {
            "id": "c1",
            "user_id": "db-user",
            "session_context_json": {},
        }
        repo.create_turn.return_value = {"id": "t1"}
        gw = Mock()
        gw.get_onboarding_status.return_value = {
            "profile_complete": True,
            "style_preference_complete": True,
            "images_uploaded": ["full_body", "headshot"],
            "onboarding_complete": True,
        }
        gw.get_analysis_status.return_value = {
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
                "SeasonalColorGroup": {"value": "Autumn"},
                "ContrastLevel": {"value": "High"},
                "FrameStructure": {"value": "Medium and Balanced"},
                "HeightCategory": {"value": "Tall"},
            },
        }
        gw.get_person_image_path.return_value = None
        gw.get_wardrobe_items.return_value = [
            {
                "id": "w1",
                "title": "Cream Shirt",
                "garment_category": "top",
                "garment_subtype": "shirt",
                "primary_color": "cream",
                "occasion_fit": "casual",
                "formality_level": "casual",
            }
        ]
        planner_mock = Mock()
        planner_mock.plan.return_value = CopilotPlanResult(
            intent=Intent.OCCASION_RECOMMENDATION,
            intent_confidence=0.95,
            action=Action.RUN_RECOMMENDATION_PIPELINE,
            context_sufficient=True,
            assistant_message="Let me refine that.",
            follow_up_suggestions=["Show me more"],
            resolved_context=CopilotResolvedContext(
                occasion_signal="casual",
                formality_hint="smart_casual",
                specific_needs=["polish", "refined_minimalism"],
                is_followup=True,
                followup_intent=FollowUpIntent.INCREASE_FORMALITY,
            ),
            action_parameters=CopilotActionParameters(),
        )
        fake_plan = RecommendationPlan(
            plan_type="paired_only",
            retrieval_count=12,
            directions=[
                DirectionSpec(
                    direction_id="A",
                    direction_type="paired",
                    label="Polished casual direction",
                    queries=[
                        QuerySpec(query_id="A1", role="top", hard_filters={}, query_document="smart casual top"),
                        QuerySpec(query_id="A2", role="bottom", hard_filters={}, query_document="smart casual bottom"),
                    ],
                )
            ],
            resolved_context=ResolvedContextBlock(
                occasion_signal="casual",
                formality_hint="smart_casual",
                specific_needs=["polish", "refined_minimalism"],
                is_followup=True,
                followup_intent=FollowUpIntent.INCREASE_FORMALITY,
            ),
        )

        with patch("agentic_application.orchestrator.ApplicationCatalogRetrievalGateway") as _gateway_cls, \
             patch("agentic_application.orchestrator.OutfitArchitect") as architect_cls, \
             patch("agentic_application.orchestrator.CopilotPlanner", return_value=planner_mock):
            architect_cls.return_value.plan.return_value = fake_plan
            orchestrator = AgenticOrchestrator(
                repo=repo,
                onboarding_gateway=gw,
                config=Mock(),
            )
            orchestrator.catalog_search_agent.search = Mock(return_value=[])
            orchestrator.outfit_assembler.assemble = Mock(return_value=[])
            orchestrator.outfit_evaluator.evaluate = Mock(return_value=[])
            orchestrator.response_formatter.format = Mock(
                return_value=RecommendationResponse(
                    message="Catalog pipeline took over.",
                    outfits=[OutfitCard(rank=1, title="Catalog Look", reasoning="Polished upgrade.", items=[])],
                    follow_up_suggestions=["Show me more"],
                    metadata={"answer_source": "catalog_only", "primary_intent": Intent.OCCASION_RECOMMENDATION},
                )
            )

            result = orchestrator.process_turn(
                conversation_id="c1",
                external_user_id="user-1",
                message="Make it a bit smarter",
            )

        self.assertNotEqual("wardrobe_first", result["metadata"]["answer_source"])
        self.assertEqual("Catalog pipeline took over.", result["assistant_message"])
        self.assertNotEqual(
            "occasion_recommendation_wardrobe_first",
            repo.finalize_turn.call_args.kwargs["resolved_context"].get("handler"),
        )

    def test_product_browse_routes_to_handler_and_skips_architect(self) -> None:
        """Product browse intent uses direct catalog search, not the outfit architect pipeline."""
        from agentic_application.schemas import (
            CopilotPlanResult, CopilotResolvedContext, CopilotActionParameters,
        )
        repo = Mock()
        repo.client = Mock()
        repo.get_or_create_user.return_value = {"id": "db-user"}
        repo.get_conversation.return_value = {
            "id": "c1",
            "user_id": "db-user",
            "session_context_json": {},
        }
        repo.create_turn.return_value = {"id": "t1"}
        gw = Mock()
        gw.get_onboarding_status.return_value = {
            "profile_complete": True,
            "style_preference_complete": True,
            "images_uploaded": ["full_body", "headshot"],
            "onboarding_complete": True,
        }
        gw.get_analysis_status.return_value = {
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
                "SeasonalColorGroup": {"value": "Autumn"},
                "ContrastLevel": {"value": "High"},
                "FrameStructure": {"value": "Medium and Balanced"},
                "HeightCategory": {"value": "Tall"},
            },
        }
        gw.get_person_image_path.return_value = None
        gw.get_wardrobe_items.return_value = []
        planner_mock = Mock()
        planner_mock.plan.return_value = CopilotPlanResult(
            intent=Intent.PRODUCT_BROWSE,
            intent_confidence=0.95,
            action=Action.RUN_PRODUCT_BROWSE,
            context_sufficient=True,
            assistant_message="Let me search for printed shirts that suit your profile.",
            follow_up_suggestions=["Show me more"],
            resolved_context=CopilotResolvedContext(
                style_goal="product_browse",
            ),
            action_parameters=CopilotActionParameters(
                detected_garments=["shirt"],
                detected_colors=[],
            ),
        )

        with patch("agentic_application.orchestrator.ApplicationCatalogRetrievalGateway") as _gateway_cls, \
             patch("agentic_application.orchestrator.OutfitArchitect") as architect_cls, \
             patch("agentic_application.orchestrator.CopilotPlanner", return_value=planner_mock):
            orchestrator = AgenticOrchestrator(
                repo=repo,
                onboarding_gateway=gw,
                config=Mock(),
            )
            orchestrator.catalog_search_agent.search = Mock(return_value=[])

            result = orchestrator.process_turn(
                conversation_id="c1",
                external_user_id="user-1",
                message="Can you suggest subtle printed shirts for me?",
            )

        # Architect should NOT have been called — product_browse skips it
        architect_cls.return_value.plan.assert_not_called()
        # Handler should persist with product_browse handler tag
        self.assertEqual(
            Intent.PRODUCT_BROWSE,
            repo.finalize_turn.call_args.kwargs["resolved_context"].get("handler"),
        )
        self.assertEqual("product_browse", result["response_type"])
        self.assertEqual("product_browse_handler", result["metadata"]["answer_source"])

    def test_make_it_smarter_with_complete_wardrobe_uses_richer_refinement_path_and_preserves_anchor_context(self) -> None:
        from agentic_application.schemas import (
            CopilotPlanResult, CopilotResolvedContext, CopilotActionParameters,
            RecommendationPlan, DirectionSpec, QuerySpec, ResolvedContextBlock,
            OutfitCard, RecommendationResponse,
        )
        repo = Mock()
        repo.client = Mock()
        repo.get_or_create_user.return_value = {"id": "db-user"}
        repo.get_conversation.return_value = {
            "id": "c1",
            "user_id": "db-user",
            "session_context_json": {
                "last_user_message": "Start with the cream shirt and olive trousers.",
                "last_live_context": {
                    "user_need": "Start with the cream shirt and olive trousers. Attached garment context: Cream Shirt, top, shirt, cream, solid, casual, casual.",
                    "occasion_signal": "casual",
                    "formality_hint": "casual",
                    "specific_needs": ["minimal", "clean"],
                    "is_followup": True,
                    "followup_intent": FollowUpIntent.MORE_OPTIONS,
                },
            },
        }
        repo.create_turn.return_value = {"id": "t1"}
        gw = Mock()
        gw.get_onboarding_status.return_value = {
            "profile_complete": True,
            "style_preference_complete": True,
            "images_uploaded": ["full_body", "headshot"],
            "onboarding_complete": True,
        }
        gw.get_analysis_status.return_value = {
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
                "SeasonalColorGroup": {"value": "Autumn"},
                "ContrastLevel": {"value": "High"},
                "FrameStructure": {"value": "Medium and Balanced"},
                "HeightCategory": {"value": "Tall"},
            },
        }
        gw.get_person_image_path.return_value = None
        gw.get_wardrobe_items.return_value = [
            {
                "id": "w1",
                "title": "Cream Shirt",
                "garment_category": "top",
                "garment_subtype": "shirt",
                "primary_color": "cream",
                "occasion_fit": "casual",
                "formality_level": "casual",
            },
            {
                "id": "w2",
                "title": "Olive Trousers",
                "garment_category": "bottom",
                "garment_subtype": "trousers",
                "primary_color": "olive",
                "occasion_fit": "casual",
                "formality_level": "casual",
            },
            {
                "id": "w3",
                "title": "Tan Loafers",
                "garment_category": "shoe",
                "garment_subtype": "loafer",
                "primary_color": "tan",
                "occasion_fit": "casual",
                "formality_level": "smart_casual",
            },
        ]
        planner_mock = Mock()
        planner_mock.plan.return_value = CopilotPlanResult(
            intent=Intent.OCCASION_RECOMMENDATION,
            intent_confidence=0.95,
            action=Action.RUN_RECOMMENDATION_PIPELINE,
            context_sufficient=True,
            assistant_message="Let me sharpen that up.",
            follow_up_suggestions=["Show me more"],
            resolved_context=CopilotResolvedContext(
                occasion_signal="casual",
                formality_hint="smart_casual",
                specific_needs=["polish"],
                is_followup=True,
                followup_intent=FollowUpIntent.INCREASE_BOLDNESS,
            ),
            action_parameters=CopilotActionParameters(),
        )
        fake_plan = RecommendationPlan(
            plan_type="paired_only",
            retrieval_count=12,
            directions=[
                DirectionSpec(
                    direction_id="A",
                    direction_type="paired",
                    label="Smarter refinement",
                    queries=[
                        QuerySpec(query_id="A1", role="top", hard_filters={}, query_document="smarter refinement top"),
                        QuerySpec(query_id="A2", role="bottom", hard_filters={}, query_document="smarter refinement bottom"),
                    ],
                )
            ],
            resolved_context=ResolvedContextBlock(
                occasion_signal="casual",
                formality_hint="smart_casual",
                specific_needs=["polish", "refined_minimalism"],
                is_followup=True,
                followup_intent=FollowUpIntent.INCREASE_FORMALITY,
            ),
        )

        with patch("agentic_application.orchestrator.ApplicationCatalogRetrievalGateway") as _gateway_cls, \
             patch("agentic_application.orchestrator.OutfitArchitect") as architect_cls, \
             patch("agentic_application.orchestrator.CopilotPlanner", return_value=planner_mock):
            architect_cls.return_value.plan.return_value = fake_plan
            orchestrator = AgenticOrchestrator(
                repo=repo,
                onboarding_gateway=gw,
                config=Mock(),
            )
            orchestrator.catalog_search_agent.search = Mock(return_value=[])
            orchestrator.outfit_assembler.assemble = Mock(return_value=[])
            orchestrator.outfit_evaluator.evaluate = Mock(return_value=[])
            orchestrator.response_formatter.format = Mock(
                return_value=RecommendationResponse(
                    message="Here are sharper options.",
                    outfits=[OutfitCard(rank=1, title="Sharper Look", reasoning="Polished follow-up.", items=[])],
                    follow_up_suggestions=["Show me more"],
                    metadata={"answer_source": "catalog_only", "primary_intent": Intent.OCCASION_RECOMMENDATION},
                )
            )

            result = orchestrator.process_turn(
                conversation_id="c1",
                external_user_id="user-1",
                message="Make it a bit smarter",
            )

        architect_cls.return_value.plan.assert_called_once()
        architect_context = architect_cls.return_value.plan.call_args.args[0]
        self.assertEqual(FollowUpIntent.INCREASE_FORMALITY, architect_context.live.followup_intent)
        self.assertIn("Follow-up anchor context:", architect_context.live.user_need)
        self.assertIn("Cream Shirt", architect_context.live.user_need)
        self.assertEqual("Here are sharper options.", result["assistant_message"])
        self.assertNotEqual(
            "occasion_recommendation_wardrobe_first",
            repo.finalize_turn.call_args.kwargs["resolved_context"].get("handler"),
        )

    def test_explicit_wardrobe_occasion_request_returns_gap_fallback_when_coverage_is_missing(self) -> None:
        repo = Mock()
        repo.client = Mock()
        repo.get_or_create_user.return_value = {"id": "db-user"}
        repo.get_conversation.return_value = {
            "id": "c1",
            "user_id": "db-user",
            "session_context_json": {},
        }
        repo.create_turn.return_value = {"id": "t1"}
        gw = Mock()
        gw.get_onboarding_status.return_value = {
            "profile_complete": True,
            "style_preference_complete": True,
            "images_uploaded": ["full_body", "headshot"],
            "onboarding_complete": True,
        }
        gw.get_analysis_status.return_value = {
            "status": "completed",
            "profile": {"gender": "female", "style_preference": {"primaryArchetype": "classic"}},
            "attributes": {"BodyShape": {"value": "Hourglass"}},
            "derived_interpretations": {"SeasonalColorGroup": {"value": "Soft Summer"}},
        }
        gw.get_wardrobe_items.return_value = []
        planner_mock = Mock()
        from agentic_application.schemas import CopilotPlanResult, CopilotResolvedContext, CopilotActionParameters
        planner_mock.plan.return_value = CopilotPlanResult(
            intent=Intent.OCCASION_RECOMMENDATION,
            intent_confidence=0.95,
            action=Action.RUN_RECOMMENDATION_PIPELINE,
            context_sufficient=True,
            assistant_message="Let me build that.",
            follow_up_suggestions=[],
            resolved_context=CopilotResolvedContext(
                occasion_signal="office",
                formality_hint="business_casual",
            ),
            action_parameters=CopilotActionParameters(),
        )

        with patch("agentic_application.orchestrator.ApplicationCatalogRetrievalGateway"), patch(
            "agentic_application.orchestrator.OutfitArchitect"
        ) as architect_cls, patch("agentic_application.orchestrator.CopilotPlanner", return_value=planner_mock):
            orchestrator = AgenticOrchestrator(repo=repo, onboarding_gateway=gw, config=Mock())
            result = orchestrator.process_turn(
                conversation_id="c1",
                external_user_id="user-1",
                message="What should I wear to the office from my wardrobe?",
            )

        architect_cls.return_value.plan.assert_not_called()
        self.assertEqual("wardrobe_unavailable", result["metadata"]["answer_source"])
        self.assertEqual("wardrobe", result["metadata"]["source_selection"]["preferred_source"])
        self.assertEqual("wardrobe_unavailable", result["metadata"]["source_selection"]["fulfilled_source"])
        self.assertIn("Show me better options from the catalog", result["follow_up_suggestions"])

    def test_explicit_catalog_occasion_request_skips_wardrobe_first_and_returns_catalog_only(self) -> None:
        from agentic_application.schemas import (
            CopilotPlanResult, CopilotResolvedContext, CopilotActionParameters,
            RecommendationPlan, DirectionSpec, QuerySpec, ResolvedContextBlock,
        )
        repo = Mock()
        repo.client = Mock()
        repo.get_or_create_user.return_value = {"id": "db-user"}
        repo.get_conversation.return_value = {
            "id": "c1",
            "user_id": "db-user",
            "session_context_json": {},
        }
        repo.create_turn.return_value = {"id": "t1"}
        gw = Mock()
        gw.get_onboarding_status.return_value = {
            "profile_complete": True,
            "style_preference_complete": True,
            "images_uploaded": ["full_body", "headshot"],
            "onboarding_complete": True,
        }
        gw.get_analysis_status.return_value = {
            "status": "completed",
            "profile": {"gender": "female", "style_preference": {"primaryArchetype": "classic"}},
            "attributes": {"BodyShape": {"value": "Hourglass"}},
            "derived_interpretations": {"SeasonalColorGroup": {"value": "Soft Summer"}},
        }
        gw.get_wardrobe_items.return_value = [
            {"id": "w1", "title": "Navy Blazer", "garment_category": "top", "occasion_fit": "office", "formality_level": "business_casual"},
            {"id": "w2", "title": "Cream Trousers", "garment_category": "bottom", "occasion_fit": "office", "formality_level": "business_casual"},
        ]
        planner_mock = Mock()
        planner_mock.plan.return_value = CopilotPlanResult(
            intent=Intent.OCCASION_RECOMMENDATION,
            intent_confidence=0.97,
            action=Action.RUN_RECOMMENDATION_PIPELINE,
            context_sufficient=True,
            assistant_message="Let me find catalog options.",
            follow_up_suggestions=["Show me more"],
            resolved_context=CopilotResolvedContext(
                occasion_signal="office",
                formality_hint="business_casual",
            ),
            action_parameters=CopilotActionParameters(),
        )
        fake_plan = RecommendationPlan(
            plan_type="complete_only",
            retrieval_count=12,
            directions=[
                DirectionSpec(
                    direction_id="A",
                    direction_type="complete",
                    label="Catalog direction",
                    queries=[
                        QuerySpec(
                            query_id="A1",
                            role="complete",
                            hard_filters={},
                            query_document="office catalog outfit",
                        )
                    ],
                )
            ],
            resolved_context=ResolvedContextBlock(
                occasion_signal="office",
                formality_hint="business_casual",
                specific_needs=["catalog_only"],
            ),
        )

        with patch("agentic_application.orchestrator.ApplicationCatalogRetrievalGateway") as _gateway_cls, \
             patch("agentic_application.orchestrator.OutfitArchitect") as architect_cls, \
             patch("agentic_application.orchestrator.CopilotPlanner", return_value=planner_mock):
            architect_cls.return_value.plan.return_value = fake_plan
            orchestrator = AgenticOrchestrator(
                repo=repo,
                onboarding_gateway=gw,
                config=Mock(),
            )
            orchestrator.catalog_search_agent.search = Mock(return_value=[])
            orchestrator.outfit_assembler.assemble = Mock(return_value=[])
            orchestrator.outfit_evaluator.evaluate = Mock(return_value=[])
            orchestrator.response_formatter.format = Mock(
                return_value=RecommendationResponse(
                    success=True,
                    message="Here are catalog-first office options.",
                    outfits=[
                        OutfitCard(
                            rank=1,
                            title="Catalog Office Look",
                            reasoning="Catalog only",
                            items=[{"product_id": "c1", "title": "Wool Trouser", "source": "catalog"}],
                        )
                    ],
                    follow_up_suggestions=["Show me more"],
                    metadata={"answer_components": {"primary_source": "catalog", "catalog_item_count": 1, "wardrobe_item_count": 0}},
                )
            )

            result = orchestrator.process_turn(
                conversation_id="c1",
                external_user_id="user-1",
                message="Show me an office outfit from the catalog",
            )

        architect_cls.return_value.plan.assert_called_once()
        self.assertEqual("catalog_only", result["metadata"]["answer_source"])
        self.assertEqual("catalog", result["metadata"]["source_selection"]["preferred_source"])
        self.assertEqual("catalog", result["metadata"]["source_selection"]["fulfilled_source"])
        self.assertIn("catalog_source_override", result["metadata"]["intent_reason_codes"])



class TestProfileGuidanceRouting(unittest.TestCase):
    """Tests for zero-result fallback and profile-grounded responses."""

    # ---- Zero-result fallback: profile-grounded ----

    def _make_user_context(self) -> UserContext:
        return UserContext(
            user_id="u1",
            gender="female",
            style_preference={"primaryArchetype": "classic", "secondaryArchetype": "romantic"},
            derived_interpretations={
                "SeasonalColorGroup": {"value": "Autumn"},
                "ContrastLevel": {"value": "High"},
                "FrameStructure": {"value": "Medium and Balanced"},
                "HeightCategory": {"value": "Average"},
            },
        )

    def test_zero_result_fallback_with_profile(self) -> None:
        ctx = CombinedContext(
            user=self._make_user_context(),
            live=LiveContext(user_need="Show me an outfit for a wedding"),
            hard_filters={"gender_expression": "female"},
        )
        message, suggestions = _build_zero_result_fallback(ctx)
        self.assertIn("profile", message.lower())
        self.assertIn("Autumn", message)
        self.assertIn("high contrast", message.lower())
        self.assertNotIn("broaden your requirements", message.lower())

    def test_zero_result_fallback_without_profile(self) -> None:
        ctx = CombinedContext(
            user=UserContext(user_id="u1", gender="female"),
            live=LiveContext(user_need="Show me an outfit"),
            hard_filters={"gender_expression": "female"},
        )
        message, suggestions = _build_zero_result_fallback(ctx)
        self.assertIn("broadening your requirements", message.lower())



class CopilotPlannerTests(unittest.TestCase):
    """Tests for the CopilotPlanner-based orchestrator path."""

    @staticmethod
    def _make_planner_config():
        """Create a standard config for the planner path."""
        from platform_core.config import AuraRuntimeConfig
        return AuraRuntimeConfig(
            supabase_rest_url="http://localhost/rest/v1",
            supabase_service_role_key="test-key",
        )

    @staticmethod
    def _standard_onboarding_gateway():
        gw = Mock()
        gw.get_onboarding_status.return_value = {
            "profile_complete": True,
            "style_preference_complete": True,
            "images_uploaded": ["full_body", "headshot"],
            "onboarding_complete": True,
        }
        gw.get_analysis_status.return_value = {
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
                "SeasonalColorGroup": {"value": "Autumn"},
                "ContrastLevel": {"value": "High"},
                "FrameStructure": {"value": "Medium and Balanced"},
                "HeightCategory": {"value": "Tall"},
            },
        }
        gw.get_wardrobe_items.return_value = []
        gw.get_person_image_path.return_value = None
        return gw

    @staticmethod
    def _standard_repo():
        repo = Mock()
        repo.client = Mock()
        repo.get_or_create_user.return_value = {"id": "db-user"}
        repo.get_conversation.return_value = {
            "id": "c1",
            "user_id": "db-user",
            "session_context_json": {},
        }
        repo.create_turn.return_value = {"id": "t1"}
        return repo

    def _build_orchestrator(self, repo, gw, planner_mock):
        with patch("agentic_application.orchestrator.ApplicationCatalogRetrievalGateway"), \
             patch("agentic_application.orchestrator.OutfitArchitect"), \
             patch("agentic_application.orchestrator.OutfitCheckAgent"), \
             patch("agentic_application.orchestrator.ShoppingDecisionAgent"), \
             patch("agentic_application.orchestrator.CopilotPlanner", return_value=planner_mock):
            return AgenticOrchestrator(
                repo=repo,
                onboarding_gateway=gw,
                config=self._make_planner_config(),
            )

    def test_planner_respond_directly_for_style_discovery(self):
        from agentic_application.schemas import CopilotPlanResult, CopilotResolvedContext, CopilotActionParameters
        repo = self._standard_repo()
        gw = self._standard_onboarding_gateway()
        planner_mock = Mock()
        planner_mock.plan.return_value = CopilotPlanResult(
            intent=Intent.STYLE_DISCOVERY,
            intent_confidence=0.95,
            action=Action.RESPOND_DIRECTLY,
            context_sufficient=True,
            assistant_message="As an Autumn with high contrast, warm earthy tones and bold pairings are your strongest direction.",
            follow_up_suggestions=["What colors should I avoid?", "Show me outfits for work"],
            resolved_context=CopilotResolvedContext(style_goal="color_direction"),
            action_parameters=CopilotActionParameters(),
        )
        orchestrator = self._build_orchestrator(repo, gw, planner_mock)
        result = orchestrator.process_turn(
            conversation_id="c1",
            external_user_id="user-1",
            message="What colors suit me best?",
        )

        planner_mock.plan.assert_called_once()
        self.assertEqual(Intent.STYLE_DISCOVERY, result["metadata"]["primary_intent"])
        self.assertEqual("style_discovery_handler", result["metadata"]["answer_source"])
        self.assertIn("Autumn", result["assistant_message"])
        self.assertIn("confident", result["assistant_message"].lower())
        self.assertEqual("recommendation", result["response_type"])
        self.assertEqual([], result["outfits"])
        self.assertIn("What colors should I avoid?", result["follow_up_suggestions"])
        self.assertEqual("color", result["metadata"][Intent.STYLE_DISCOVERY]["advice_topic"])
        persisted_context = repo.finalize_turn.call_args.kwargs["resolved_context"]
        self.assertEqual("style_discovery_handler", persisted_context["response_metadata"]["answer_source"])

    def test_style_discovery_returns_profile_grounded_collar_advice(self):
        from agentic_application.schemas import CopilotPlanResult, CopilotResolvedContext, CopilotActionParameters
        repo = self._standard_repo()
        gw = self._standard_onboarding_gateway()
        planner_mock = Mock()
        planner_mock.plan.return_value = CopilotPlanResult(
            intent=Intent.STYLE_DISCOVERY,
            intent_confidence=0.95,
            action=Action.RESPOND_DIRECTLY,
            context_sufficient=True,
            assistant_message="I’ll break down the best collar direction for you.",
            follow_up_suggestions=["What necklines suit me?", "Show me shirt ideas"],
            resolved_context=CopilotResolvedContext(style_goal=Intent.STYLE_DISCOVERY),
            action_parameters=CopilotActionParameters(),
        )
        orchestrator = self._build_orchestrator(repo, gw, planner_mock)

        result = orchestrator.process_turn(
            conversation_id="c1",
            external_user_id="user-1",
            message="What collar will look good on me?",
        )

        self.assertEqual("style_discovery_handler", result["metadata"]["answer_source"])
        self.assertEqual("collar", result["metadata"][Intent.STYLE_DISCOVERY]["advice_topic"])
        self.assertIn("open, elongated shape", result["assistant_message"])
        self.assertIn("hourglass", result["assistant_message"].lower())

    def test_style_discovery_returns_profile_grounded_pattern_advice(self):
        from agentic_application.schemas import CopilotPlanResult, CopilotResolvedContext, CopilotActionParameters
        repo = self._standard_repo()
        gw = self._standard_onboarding_gateway()
        planner_mock = Mock()
        planner_mock.plan.return_value = CopilotPlanResult(
            intent=Intent.STYLE_DISCOVERY,
            intent_confidence=0.94,
            action=Action.RESPOND_DIRECTLY,
            context_sufficient=True,
            assistant_message="I’ll break down patterns for you.",
            follow_up_suggestions=["What colors suit me?", "Show me printed pieces"],
            resolved_context=CopilotResolvedContext(style_goal=Intent.STYLE_DISCOVERY),
            action_parameters=CopilotActionParameters(),
        )
        orchestrator = self._build_orchestrator(repo, gw, planner_mock)

        result = orchestrator.process_turn(
            conversation_id="c1",
            external_user_id="user-1",
            message="What patterns work on me?",
        )

        self.assertEqual("pattern", result["metadata"][Intent.STYLE_DISCOVERY]["advice_topic"])
        self.assertIn("medium-scale patterns", result["assistant_message"])
        self.assertIn("classic", result["assistant_message"].lower())
        self.assertIn("romantic", result["assistant_message"].lower())

    def test_style_discovery_returns_profile_grounded_silhouette_advice(self):
        from agentic_application.schemas import CopilotPlanResult, CopilotResolvedContext, CopilotActionParameters
        repo = self._standard_repo()
        gw = self._standard_onboarding_gateway()
        planner_mock = Mock()
        planner_mock.plan.return_value = CopilotPlanResult(
            intent=Intent.STYLE_DISCOVERY,
            intent_confidence=0.94,
            action=Action.RESPOND_DIRECTLY,
            context_sufficient=True,
            assistant_message="I’ll explain the best silhouettes for you.",
            follow_up_suggestions=["What collars suit me?", "Show me outfit ideas"],
            resolved_context=CopilotResolvedContext(style_goal=Intent.STYLE_DISCOVERY),
            action_parameters=CopilotActionParameters(),
        )
        orchestrator = self._build_orchestrator(repo, gw, planner_mock)

        result = orchestrator.process_turn(
            conversation_id="c1",
            external_user_id="user-1",
            message="What silhouette works best on me?",
        )

        self.assertEqual("silhouette", result["metadata"][Intent.STYLE_DISCOVERY]["advice_topic"])
        self.assertIn("waist definition", result["assistant_message"].lower())
        self.assertIn("boxy", result["assistant_message"].lower())

    def test_style_discovery_returns_profile_grounded_archetype_advice(self):
        from agentic_application.schemas import CopilotPlanResult, CopilotResolvedContext, CopilotActionParameters
        repo = self._standard_repo()
        gw = self._standard_onboarding_gateway()
        planner_mock = Mock()
        planner_mock.plan.return_value = CopilotPlanResult(
            intent=Intent.STYLE_DISCOVERY,
            intent_confidence=0.94,
            action=Action.RESPOND_DIRECTLY,
            context_sufficient=True,
            assistant_message="I’ll explain your archetype blend.",
            follow_up_suggestions=["What colors suit me?", "Show me outfits for work"],
            resolved_context=CopilotResolvedContext(style_goal=Intent.STYLE_DISCOVERY),
            action_parameters=CopilotActionParameters(),
        )
        orchestrator = self._build_orchestrator(repo, gw, planner_mock)

        result = orchestrator.process_turn(
            conversation_id="c1",
            external_user_id="user-1",
            message="Which style archetypes fit me?",
        )

        self.assertEqual("archetype", result["metadata"][Intent.STYLE_DISCOVERY]["advice_topic"])
        self.assertIn("classic", result["assistant_message"].lower())
        self.assertIn("romantic", result["assistant_message"].lower())
        self.assertIn("accent", result["assistant_message"].lower())

    def test_planner_respond_directly_for_explanation_request(self):
        from agentic_application.schemas import CopilotPlanResult, CopilotResolvedContext, CopilotActionParameters
        repo = self._standard_repo()
        repo.get_conversation.return_value = {
            "id": "c1",
            "user_id": "db-user",
            "session_context_json": {
                "last_recommendations": [
                    {
                        "rank": 1,
                        "title": "Elegant Wedding Look",
                        "primary_colors": ["burgundy", "cream"],
                        "garment_categories": ["dress"],
                        "occasion_fits": ["wedding"],
                    }
                ],
                "last_response_metadata": {
                    "recommendation_confidence": {
                        "confidence_band": "high",
                        "explanation": [
                            "Strongest evidence: the occasion and profile aligned cleanly.",
                            "Also helpful: the retrieved options had clear metadata coverage.",
                        ],
                    }
                },
            },
        }
        gw = self._standard_onboarding_gateway()
        planner_mock = Mock()
        planner_mock.plan.return_value = CopilotPlanResult(
            intent=Intent.EXPLANATION_REQUEST,
            intent_confidence=0.94,
            action=Action.RESPOND_DIRECTLY,
            context_sufficient=True,
            assistant_message="I’ll break down why that recommendation worked.",
            follow_up_suggestions=["Show me something bolder", "Explain another option"],
            resolved_context=CopilotResolvedContext(style_goal="explanation"),
            action_parameters=CopilotActionParameters(),
        )
        orchestrator = self._build_orchestrator(repo, gw, planner_mock)
        result = orchestrator.process_turn(
            conversation_id="c1",
            external_user_id="user-1",
            message="Why did you recommend that?",
        )

        self.assertEqual(Intent.EXPLANATION_REQUEST, result["metadata"]["primary_intent"])
        self.assertEqual("explanation_handler", result["metadata"]["answer_source"])
        self.assertIn("Elegant Wedding Look", result["assistant_message"])
        self.assertIn("confidence", result["assistant_message"].lower())
        self.assertEqual([], result["outfits"])

    def test_planner_ask_clarification(self):
        from agentic_application.schemas import CopilotPlanResult, CopilotResolvedContext, CopilotActionParameters
        repo = self._standard_repo()
        gw = self._standard_onboarding_gateway()
        planner_mock = Mock()
        planner_mock.plan.return_value = CopilotPlanResult(
            intent=Intent.OCCASION_RECOMMENDATION,
            intent_confidence=0.6,
            action=Action.ASK_CLARIFICATION,
            context_sufficient=False,
            assistant_message="What's the occasion? That'll help me nail the right direction for you.",
            follow_up_suggestions=["Date night", "Office meeting", "Casual weekend", "Wedding guest"],
            resolved_context=CopilotResolvedContext(),
            action_parameters=CopilotActionParameters(),
        )
        orchestrator = self._build_orchestrator(repo, gw, planner_mock)
        result = orchestrator.process_turn(
            conversation_id="c1",
            external_user_id="user-1",
            message="I need something",
        )

        self.assertEqual("clarification", result["response_type"])
        self.assertIn("occasion", result["assistant_message"].lower())
        self.assertTrue(result["follow_up_suggestions"])

    def test_planner_run_pipeline_calls_architect(self):
        from agentic_application.schemas import (
            CopilotPlanResult, CopilotResolvedContext, CopilotActionParameters,
            RecommendationPlan, DirectionSpec, QuerySpec, ResolvedContextBlock,
            EvaluatedRecommendation,
        )
        repo = self._standard_repo()
        gw = self._standard_onboarding_gateway()
        planner_mock = Mock()
        planner_mock.plan.return_value = CopilotPlanResult(
            intent=Intent.OCCASION_RECOMMENDATION,
            intent_confidence=0.95,
            action=Action.RUN_RECOMMENDATION_PIPELINE,
            context_sufficient=True,
            assistant_message="Let me find some wedding options with your Autumn palette in mind.",
            follow_up_suggestions=["Show me something bolder", "Different color direction"],
            resolved_context=CopilotResolvedContext(
                occasion_signal="wedding",
                formality_hint="formal",
                style_goal="wedding guest outfit",
            ),
            action_parameters=CopilotActionParameters(),
        )

        fake_plan = RecommendationPlan(
            plan_type="complete_only",
            retrieval_count=12,
            directions=[
                DirectionSpec(
                    direction_id="A",
                    direction_type="complete",
                    label="Formal Wedding",
                    queries=[
                        QuerySpec(
                            query_id="A1",
                            role="complete",
                            hard_filters={},
                            query_document="formal wedding dress",
                        )
                    ],
                )
            ],
            resolved_context=ResolvedContextBlock(
                occasion_signal="wedding",
                formality_hint="formal",
            ),
        )
        fake_eval = EvaluatedRecommendation(
            candidate_id="cand-1",
            rank=1,
            match_score=0.88,
            title="Elegant Wedding Look",
            reasoning="Great for a formal wedding.",
            item_ids=["prod-1"],
        )

        with patch("agentic_application.orchestrator.ApplicationCatalogRetrievalGateway") as _gateway_cls, \
             patch("agentic_application.orchestrator.OutfitArchitect") as architect_cls, \
             patch("agentic_application.orchestrator.CopilotPlanner", return_value=planner_mock):
            architect_cls.return_value.plan.return_value = fake_plan
            orchestrator = AgenticOrchestrator(
                repo=repo,
                onboarding_gateway=gw,
                config=Mock(),
            )
            # Mock the remaining pipeline components
            orchestrator.catalog_search_agent.search = Mock(return_value=[])
            orchestrator.outfit_assembler.assemble = Mock(return_value=[])
            orchestrator.outfit_evaluator.evaluate = Mock(return_value=[])

            result = orchestrator.process_turn(
                conversation_id="c1",
                external_user_id="user-1",
                message="Show me something for a wedding",
            )

        planner_mock.plan.assert_called_once()
        architect_cls.return_value.plan.assert_called_once()
        self.assertEqual(Intent.OCCASION_RECOMMENDATION, result["metadata"]["primary_intent"])

    def test_planner_save_feedback(self):
        from agentic_application.schemas import CopilotPlanResult, CopilotResolvedContext, CopilotActionParameters
        repo = self._standard_repo()
        repo.get_conversation.return_value = {
            "id": "c1",
            "user_id": "db-user",
            "session_context_json": {
                "last_recommendations": [
                    {"rank": 1, "title": "Look 1", "item_ids": ["p1", "p2"]},
                ],
                "last_response_metadata": {"turn_id": "t0"},
            },
        }
        gw = self._standard_onboarding_gateway()
        planner_mock = Mock()
        planner_mock.plan.return_value = CopilotPlanResult(
            intent=Intent.FEEDBACK_SUBMISSION,
            intent_confidence=0.92,
            action=Action.SAVE_FEEDBACK,
            context_sufficient=True,
            assistant_message="Got it — I'll steer away from that direction next time.",
            follow_up_suggestions=["Show me something different", "What should I try next?"],
            resolved_context=CopilotResolvedContext(),
            action_parameters=CopilotActionParameters(feedback_event_type="dislike"),
        )
        orchestrator = self._build_orchestrator(repo, gw, planner_mock)
        result = orchestrator.process_turn(
            conversation_id="c1",
            external_user_id="user-1",
            message="I don't like this outfit",
        )

        self.assertEqual(Intent.FEEDBACK_SUBMISSION, result["metadata"]["primary_intent"])
        self.assertIn("steer away", result["assistant_message"])
        # Verify feedback was persisted
        repo.create_feedback_event.assert_called()

    def test_planner_save_wardrobe_item(self):
        from agentic_application.schemas import CopilotPlanResult, CopilotResolvedContext, CopilotActionParameters
        repo = self._standard_repo()
        gw = self._standard_onboarding_gateway()
        gw.save_chat_wardrobe_item.return_value = {"id": "w-new", "title": "Navy Blazer"}
        planner_mock = Mock()
        planner_mock.plan.return_value = CopilotPlanResult(
            intent=Intent.WARDROBE_INGESTION,
            intent_confidence=0.9,
            action=Action.SAVE_WARDROBE_ITEM,
            context_sufficient=True,
            assistant_message="I've saved your navy blazer to your wardrobe.",
            follow_up_suggestions=["What goes with this piece?", "Save another item"],
            resolved_context=CopilotResolvedContext(),
            action_parameters=CopilotActionParameters(
                wardrobe_item_title="Navy Blazer",
                detected_garments=["blazer"],
                detected_colors=["navy"],
            ),
        )
        orchestrator = self._build_orchestrator(repo, gw, planner_mock)
        result = orchestrator.process_turn(
            conversation_id="c1",
            external_user_id="user-1",
            message="Add my navy blazer to wardrobe",
        )

        self.assertEqual(Intent.WARDROBE_INGESTION, result["metadata"]["primary_intent"])
        self.assertIn("saved", result["assistant_message"].lower())
        gw.save_chat_wardrobe_item.assert_called_once()

    def test_attached_chat_image_is_ingested_before_planning(self):
        from agentic_application.schemas import CopilotPlanResult, CopilotResolvedContext, CopilotActionParameters
        repo = self._standard_repo()
        gw = self._standard_onboarding_gateway()
        gw.save_uploaded_chat_wardrobe_item.return_value = {
            "id": "w-upload",
            "title": "Navy Shirt",
            "garment_category": "top",
            "garment_subtype": "shirt",
            "primary_color": "navy",
            "pattern_type": "solid",
            "occasion_fit": "workwear",
            "formality_level": "smart_casual",
            "metadata_json": {
                "catalog_attributes": {
                    "GarmentCategory": "top",
                    "GarmentSubtype": "shirt",
                    "PrimaryColor": "navy",
                    "PatternType": "solid",
                    "OccasionFit": "workwear",
                    "FormalityLevel": "smart_casual",
                }
            },
        }
        planner_mock = Mock()
        planner_mock.plan.return_value = CopilotPlanResult(
            intent=Intent.PAIRING_REQUEST,
            intent_confidence=0.94,
            action=Action.RESPOND_DIRECTLY,
            context_sufficient=True,
            assistant_message="Use a cream trouser or dark denim bottom.",
            follow_up_suggestions=["Show me options"],
            resolved_context=CopilotResolvedContext(),
            action_parameters=CopilotActionParameters(),
        )
        orchestrator = self._build_orchestrator(repo, gw, planner_mock)
        result = orchestrator.process_turn(
            conversation_id="c1",
            external_user_id="user-1",
            message="What goes with this?",
            image_data="data:image/png;base64,AAAA",
        )

        self.assertEqual(Intent.PAIRING_REQUEST, result["metadata"]["primary_intent"])
        gw.save_uploaded_chat_wardrobe_item.assert_called_once()
        planner_message = planner_mock.plan.call_args.args[0]["user_message"]
        self.assertIn("Attached garment context:", planner_message)
        self.assertIn("Navy Shirt", planner_message)
        self.assertIn("shirt", planner_message.lower())
        self.assertIn("Image anchor source: wardrobe image.", planner_message)

    def test_attached_garment_pairing_request_overrides_misclassified_planner_intent(self):
        from agentic_application.schemas import CopilotPlanResult, CopilotResolvedContext, CopilotActionParameters
        repo = self._standard_repo()
        repo.client.select_many.return_value = [
            {
                "product_id": "c1",
                "title": "Stone Pleated Trousers",
                "garment_category": "trousers",
                "garment_subtype": "trousers",
                "primary_color": "stone",
                "occasion_fit": "smart_casual",
                "formality_level": "smart_casual",
                "url": "https://store.example/stone-trousers",
            }
        ]
        gw = self._standard_onboarding_gateway()
        gw.save_uploaded_chat_wardrobe_item.return_value = {
            "id": "w-anchor",
            "title": "White Shirt",
            "garment_category": "top",
            "garment_subtype": "shirt",
            "primary_color": "white",
            "occasion_fit": "smart_casual",
            "formality_level": "smart_casual",
        }
        gw.get_wardrobe_items.return_value = [
            {
                "id": "w-anchor",
                "title": "White Shirt",
                "garment_category": "top",
                "garment_subtype": "shirt",
                "primary_color": "white",
                "occasion_fit": "smart_casual",
                "formality_level": "smart_casual",
            },
            {
                "id": "w-bottom",
                "title": "Navy Trousers",
                "garment_category": "trousers",
                "garment_subtype": "trousers",
                "primary_color": "navy",
                "occasion_fit": "smart_casual",
                "formality_level": "smart_casual",
            },
        ]
        planner_mock = Mock()
        planner_mock.plan.return_value = CopilotPlanResult(
            intent=Intent.OCCASION_RECOMMENDATION,
            intent_confidence=0.97,
            action=Action.RUN_RECOMMENDATION_PIPELINE,
            context_sufficient=True,
            assistant_message="Let me put together options.",
            follow_up_suggestions=["Show me more"],
            resolved_context=CopilotResolvedContext(
                occasion_signal="smart_casual",
                formality_hint="smart_casual",
            ),
            action_parameters=CopilotActionParameters(),
        )
        orchestrator = self._build_orchestrator(repo, gw, planner_mock)
        orchestrator.outfit_architect.plan = Mock(side_effect=AssertionError("catalog pipeline should not run"))

        result = orchestrator.process_turn(
            conversation_id="c1",
            external_user_id="user-1",
            message="Find me a perfect outfit with this shirt.",
            image_data="data:image/png;base64,AAAA",
        )

        self.assertEqual(Intent.PAIRING_REQUEST, result["metadata"]["primary_intent"])
        self.assertEqual("pairing_request_wardrobe_first", repo.finalize_turn.call_args.kwargs["resolved_context"]["handler"])
        self.assertIn("White Shirt", result["assistant_message"])
        self.assertIn("Navy Trousers", result["assistant_message"])
        self.assertIn("pairing_request_override", result["metadata"]["intent_reason_codes"])

    def test_pairing_override_uses_previous_attached_garment_context_when_no_new_image(self):
        from agentic_application.schemas import CopilotPlanResult, CopilotResolvedContext, CopilotActionParameters
        repo = self._standard_repo()
        repo.get_conversation.return_value = {
            "id": "c1",
            "user_id": "db-user",
            "session_context_json": {
                "last_live_context": {
                    "user_need": "How is my outfit for date evening? Attached garment context: Brown Co Ord Set, set, co_ord_set, brown, textured, smart_casual, smart_casual."
                },
                "last_user_message": "How is my outfit for date evening? Attached garment context: Brown Co Ord Set, set, co_ord_set, brown, textured, smart_casual, smart_casual.",
            },
        }
        gw = self._standard_onboarding_gateway()
        gw.get_wardrobe_items.return_value = [
            {
                "id": "w1",
                "title": "Brown Co Ord Set",
                "garment_category": "set",
                "garment_subtype": "co_ord_set",
                "primary_color": "brown",
                "occasion_fit": "smart_casual",
                "formality_level": "smart_casual",
            },
            {
                "id": "w2",
                "title": "Tan Loafers",
                "garment_category": "shoe",
                "garment_subtype": "loafer",
                "primary_color": "tan",
                "occasion_fit": "smart_casual",
                "formality_level": "smart_casual",
            },
        ]
        planner_mock = Mock()
        planner_mock.plan.return_value = CopilotPlanResult(
            intent=Intent.OCCASION_RECOMMENDATION,
            intent_confidence=0.88,
            action=Action.RUN_RECOMMENDATION_PIPELINE,
            context_sufficient=True,
            assistant_message="Let me think about that.",
            follow_up_suggestions=["Show me more"],
            resolved_context=CopilotResolvedContext(
                occasion_signal="date_night",
                formality_hint="smart_casual",
            ),
            action_parameters=CopilotActionParameters(),
        )
        orchestrator = self._build_orchestrator(repo, gw, planner_mock)
        orchestrator.outfit_architect.plan = Mock(side_effect=AssertionError("catalog pipeline should not run"))

        result = orchestrator.process_turn(
            conversation_id="c1",
            external_user_id="user-1",
            message="What shoes would work best with this?",
        )

        self.assertEqual(Intent.PAIRING_REQUEST, result["metadata"]["primary_intent"])
        self.assertEqual("pairing_request_wardrobe_first", repo.finalize_turn.call_args.kwargs["resolved_context"]["handler"])
        self.assertIn("Brown Co Ord Set", result["assistant_message"])
        self.assertIn("Tan Loafers", result["assistant_message"])

    def test_catalog_garment_image_pairing_uses_catalog_handler_with_complementary_items(self):
        from agentic_application.schemas import CopilotPlanResult, CopilotResolvedContext, CopilotActionParameters
        repo = self._standard_repo()
        repo.client.select_many.return_value = [
            {
                "product_id": "c1",
                "title": "Stone Pleated Trousers",
                "garment_category": "trousers",
                "garment_subtype": "trousers",
                "primary_color": "stone",
                "occasion_fit": "smart_casual",
                "formality_level": "smart_casual",
                "url": "https://store.example/stone-trousers",
            },
            {
                "product_id": "c2",
                "title": "Brown Penny Loafers",
                "garment_category": "shoe",
                "garment_subtype": "loafer",
                "primary_color": "brown",
                "occasion_fit": "smart_casual",
                "formality_level": "smart_casual",
                "url": "https://store.example/brown-loafers",
            },
        ]
        gw = self._standard_onboarding_gateway()
        gw.save_uploaded_chat_wardrobe_item.return_value = {
            "id": "img-anchor",
            "title": "White Shirt",
            "garment_category": "top",
            "garment_subtype": "shirt",
            "primary_color": "white",
            "occasion_fit": "smart_casual",
            "formality_level": "smart_casual",
        }
        planner_mock = Mock()
        planner_mock.plan.return_value = CopilotPlanResult(
            intent=Intent.OCCASION_RECOMMENDATION,
            intent_confidence=0.96,
            action=Action.RUN_RECOMMENDATION_PIPELINE,
            context_sufficient=True,
            assistant_message="Let me build around it.",
            follow_up_suggestions=["Show me more"],
            resolved_context=CopilotResolvedContext(
                occasion_signal="smart_casual",
                formality_hint="smart_casual",
            ),
            action_parameters=CopilotActionParameters(),
        )
        orchestrator = self._build_orchestrator(repo, gw, planner_mock)
        orchestrator.outfit_architect.plan = Mock(side_effect=AssertionError("catalog image pairing should not hit architect"))

        result = orchestrator.process_turn(
            conversation_id="c1",
            external_user_id="user-1",
            message="Pair this from the catalog for smart casual",
            image_data="data:image/png;base64,AAAA",
        )

        self.assertEqual(Intent.PAIRING_REQUEST, result["metadata"]["primary_intent"])
        self.assertEqual("catalog_image_pairing", result["metadata"]["answer_source"])
        self.assertEqual("catalog", result["metadata"]["source_selection"]["preferred_source"])
        self.assertEqual("catalog", result["metadata"]["source_selection"]["fulfilled_source"])
        self.assertEqual("pairing_request_catalog_image", repo.finalize_turn.call_args.kwargs["resolved_context"]["handler"])
        self.assertEqual(1, len(result["outfits"]))
        self.assertGreater(len(result["outfits"][0]["items"]), 1)
        self.assertTrue(all(item["source"] == "catalog" for item in result["outfits"][0]["items"]))
        self.assertIn("Stone Pleated Trousers", result["assistant_message"])
        planner_message = planner_mock.plan.call_args.args[0]["user_message"]
        self.assertIn("Image anchor source: catalog image.", planner_message)

    def test_catalog_followup_overrides_wardrobe_first_short_circuit(self):
        from agentic_application.schemas import (
            CopilotPlanResult, CopilotResolvedContext, CopilotActionParameters,
            RecommendationPlan, DirectionSpec, QuerySpec, ResolvedContextBlock,
        )
        repo = self._standard_repo()
        repo.get_conversation.return_value = {
            "id": "c1",
            "user_id": "db-user",
            "session_context_json": {
                "last_response_metadata": {
                    "answer_source": "wardrobe_first",
                    "catalog_upsell": {
                        "available": True,
                        "cta": "Show me better options from the catalog",
                    },
                },
            },
        }
        gw = self._standard_onboarding_gateway()
        gw.get_wardrobe_items.return_value = [
            {
                "id": "w1",
                "title": "Cream Shirt",
                "garment_category": "top",
                "garment_subtype": "shirt",
                "primary_color": "cream",
                "occasion_fit": "casual",
                "formality_level": "casual",
            }
        ]
        planner_mock = Mock()
        planner_mock.plan.return_value = CopilotPlanResult(
            intent=Intent.OCCASION_RECOMMENDATION,
            intent_confidence=0.99,
            action=Action.RUN_RECOMMENDATION_PIPELINE,
            context_sufficient=True,
            assistant_message="Let me find better options.",
            follow_up_suggestions=["Show me more"],
            resolved_context=CopilotResolvedContext(
                occasion_signal="casual",
                formality_hint="casual",
            ),
            action_parameters=CopilotActionParameters(),
        )
        fake_plan = RecommendationPlan(
            plan_type="complete_only",
            retrieval_count=12,
            directions=[
                DirectionSpec(
                    direction_id="A",
                    direction_type="complete",
                    label="Catalog direction",
                    queries=[
                        QuerySpec(
                            query_id="A1",
                            role="complete",
                            hard_filters={},
                            query_document="casual smart-casual catalog look",
                        )
                    ],
                )
            ],
            resolved_context=ResolvedContextBlock(
                occasion_signal="casual",
                formality_hint="casual",
            ),
        )

        with patch("agentic_application.orchestrator.ApplicationCatalogRetrievalGateway") as _gateway_cls, \
             patch("agentic_application.orchestrator.OutfitArchitect") as architect_cls, \
             patch("agentic_application.orchestrator.CopilotPlanner", return_value=planner_mock):
            architect_cls.return_value.plan.return_value = fake_plan
            orchestrator = AgenticOrchestrator(
                repo=repo,
                onboarding_gateway=gw,
                config=self._make_planner_config(),
            )
            orchestrator.catalog_search_agent.search = Mock(return_value=[])
            orchestrator.outfit_assembler.assemble = Mock(return_value=[])
            orchestrator.outfit_evaluator.evaluate = Mock(return_value=[])
            orchestrator.response_formatter.format = Mock(
                return_value=RecommendationResponse(
                    success=True,
                    message="Here are stronger catalog-led options.",
                    outfits=[
                        OutfitCard(
                            rank=1,
                            title="Catalog Look",
                            reasoning="Built from catalog alternatives.",
                            items=[
                                {
                                    "product_id": "c1",
                                    "title": "Stone Trousers",
                                    "source": "catalog",
                                    "role": "bottom",
                                }
                            ],
                        )
                    ],
                    follow_up_suggestions=["Show me more"],
                    metadata={"answer_source": "catalog"},
                )
            )

            result = orchestrator.process_turn(
                conversation_id="c1",
                external_user_id="user-1",
                message="Show me better options from the catalog",
            )

        architect_cls.return_value.plan.assert_called_once()
        self.assertEqual(1, len(result["outfits"]))
        self.assertEqual("catalog", result["outfits"][0]["items"][0]["source"])
        self.assertIn("catalog-led options", result["assistant_message"])

    def test_catalog_followup_preserves_previous_anchor_context(self):
        from agentic_application.schemas import (
            CopilotPlanResult, CopilotResolvedContext, CopilotActionParameters,
            RecommendationPlan, DirectionSpec, QuerySpec, ResolvedContextBlock,
        )
        repo = self._standard_repo()
        repo.get_conversation.return_value = {
            "id": "c1",
            "user_id": "db-user",
            "session_context_json": {
                "last_user_message": "Find me a perfect outfit with this shirt. Attached garment context: White Shirt, top, shirt, white, solid, smart_casual, smart_casual.",
                "last_live_context": {
                    "user_need": "Find me a perfect outfit with this shirt. Attached garment context: White Shirt, top, shirt, white, solid, smart_casual, smart_casual.",
                    "occasion_signal": "smart_casual",
                    "formality_hint": "smart_casual",
                    "time_hint": None,
                    "specific_needs": ["versatility", "polished_minimalism"],
                    "is_followup": True,
                    "followup_intent": FollowUpIntent.MORE_OPTIONS,
                },
                "last_response_metadata": {
                    "answer_source": "wardrobe_first",
                    "catalog_upsell": {
                        "available": True,
                        "cta": "Show me better options from the catalog",
                    },
                },
            },
        }
        gw = self._standard_onboarding_gateway()
        gw.get_wardrobe_items.return_value = [
            {
                "id": "w1",
                "title": "White Shirt",
                "garment_category": "top",
                "garment_subtype": "shirt",
                "primary_color": "white",
                "occasion_fit": "smart_casual",
                "formality_level": "smart_casual",
            }
        ]
        planner_mock = Mock()
        planner_mock.plan.return_value = CopilotPlanResult(
            intent=Intent.OCCASION_RECOMMENDATION,
            intent_confidence=0.99,
            action=Action.RUN_RECOMMENDATION_PIPELINE,
            context_sufficient=True,
            assistant_message="Let me find stronger catalog options.",
            follow_up_suggestions=["Show me more"],
            resolved_context=CopilotResolvedContext(
                occasion_signal="smart_casual",
                formality_hint="smart_casual",
            ),
            action_parameters=CopilotActionParameters(),
        )
        fake_plan = RecommendationPlan(
            plan_type="complete_only",
            retrieval_count=12,
            directions=[
                DirectionSpec(
                    direction_id="A",
                    direction_type="complete",
                    label="Catalog direction",
                    queries=[
                        QuerySpec(
                            query_id="A1",
                            role="complete",
                            hard_filters={},
                            query_document="smart casual outfit around a white shirt",
                        )
                    ],
                )
            ],
            resolved_context=ResolvedContextBlock(
                occasion_signal="smart_casual",
                formality_hint="smart_casual",
            ),
        )

        with patch("agentic_application.orchestrator.ApplicationCatalogRetrievalGateway") as _gateway_cls, \
             patch("agentic_application.orchestrator.OutfitArchitect") as architect_cls, \
             patch("agentic_application.orchestrator.CopilotPlanner", return_value=planner_mock):
            architect_cls.return_value.plan.return_value = fake_plan
            orchestrator = AgenticOrchestrator(
                repo=repo,
                onboarding_gateway=gw,
                config=self._make_planner_config(),
            )
            orchestrator.catalog_search_agent.search = Mock(return_value=[])
            orchestrator.outfit_assembler.assemble = Mock(return_value=[])
            orchestrator.outfit_evaluator.evaluate = Mock(return_value=[])

            orchestrator.process_turn(
                conversation_id="c1",
                external_user_id="user-1",
                message="Show me better options from the catalog",
            )

        combined_context = architect_cls.return_value.plan.call_args.args[0]
        self.assertIn("White Shirt", combined_context.live.user_need)
        self.assertIn("Catalog follow-up requested", combined_context.live.user_need)
        self.assertEqual("smart_casual", combined_context.live.occasion_signal)
        self.assertIn("catalog_followup", combined_context.live.specific_needs)

    def test_planner_run_outfit_check_returns_structured_scoring(self):
        from agentic_application.schemas import CopilotPlanResult, CopilotResolvedContext, CopilotActionParameters
        repo = self._standard_repo()
        gw = self._standard_onboarding_gateway()
        gw.get_wardrobe_items.return_value = [
            {
                "id": "w1",
                "title": "Tan Loafers",
                "garment_category": "shoe",
                "garment_subtype": "loafer",
                "primary_color": "tan",
                "occasion_fit": "office",
                "formality_level": "smart_casual",
            },
            {
                "id": "w2",
                "title": "Charcoal Trousers",
                "garment_category": "trousers",
                "garment_subtype": "trousers",
                "primary_color": "charcoal",
                "occasion_fit": "office",
                "formality_level": "smart_casual",
            },
        ]
        planner_mock = Mock()
        planner_mock.plan.return_value = CopilotPlanResult(
            intent=Intent.OUTFIT_CHECK,
            intent_confidence=0.96,
            action=Action.RUN_OUTFIT_CHECK,
            context_sufficient=True,
            assistant_message="Let me assess this look.",
            follow_up_suggestions=["What would improve this look?", "Use my wardrobe first"],
            resolved_context=CopilotResolvedContext(
                occasion_signal="office",
                style_goal=Intent.OUTFIT_CHECK,
            ),
            action_parameters=CopilotActionParameters(),
        )
        orchestrator = self._build_orchestrator(repo, gw, planner_mock)
        orchestrator.outfit_check_agent.evaluate.return_value = Mock(
            overall_verdict="good_with_tweaks",
            overall_note="This is a polished base that works well for your profile.",
            body_harmony_pct=82,
            color_suitability_pct=76,
            style_fit_pct=80,
            pairing_coherence_pct=84,
            occasion_pct=88,
            overall_score_pct=82,
            strengths=[
                "The silhouette feels balanced on your frame.",
                "The navy works with your Autumn depth.",
            ],
            improvements=[
                {
                    "area": "color",
                    "suggestion": "Swap the stark white shoe for a warmer neutral.",
                    "reason": "A softer warm neutral will sit better with your palette.",
                    "swap_source": "wardrobe",
                    "swap_detail": "your tan loafers",
                }
            ],
            style_archetype_read={
                "classic_pct": 78,
                "dramatic_pct": 20,
                "romantic_pct": 32,
                "natural_pct": 44,
                "minimalist_pct": 60,
                "creative_pct": 18,
                "sporty_pct": 12,
                "edgy_pct": 10,
            },
            to_dict=Mock(return_value={"overall_verdict": "good_with_tweaks"}),
        )

        result = orchestrator.process_turn(
            conversation_id="c1",
            external_user_id="user-1",
            message="Outfit check this navy blazer with white tee and trousers",
        )

        self.assertEqual(Intent.OUTFIT_CHECK, result["metadata"]["primary_intent"])
        self.assertEqual("outfit_check_handler", result["metadata"]["answer_source"])
        self.assertEqual(1, len(result["outfits"]))
        self.assertEqual(82, result["outfits"][0]["body_harmony_pct"])
        self.assertEqual(76, result["outfits"][0]["color_suitability_pct"])
        self.assertEqual(84, result["outfits"][0]["pairing_coherence_pct"])
        self.assertIn("What works:", result["assistant_message"])
        self.assertIn("Tweaks:", result["assistant_message"])
        self.assertIn("From your wardrobe, try:", result["assistant_message"])
        self.assertEqual(1, result["assistant_message"].lower().count("your tan loafers"))
        self.assertNotIn("Wardrobe gap to close next:", result["assistant_message"])
        self.assertIn("wardrobe_gap_analysis", result["metadata"][Intent.OUTFIT_CHECK])
        self.assertTrue(result["metadata"][Intent.OUTFIT_CHECK]["wardrobe_suggestions"])
        self.assertEqual("your tan loafers", result["metadata"][Intent.OUTFIT_CHECK]["wardrobe_suggestions"][0]["title"])
        self.assertTrue(result["metadata"]["catalog_upsell"]["available"])
        self.assertEqual(Intent.OUTFIT_CHECK, result["metadata"]["catalog_upsell"]["entry_intent"])
        self.assertIn("Show me better options from the catalog", result["follow_up_suggestions"])
        persisted_context = repo.finalize_turn.call_args.kwargs["resolved_context"]
        self.assertEqual(Intent.OUTFIT_CHECK, persisted_context["response_metadata"]["primary_intent"])
        self.assertEqual("outfit_check_handler", persisted_context["response_metadata"]["answer_source"])
        session_context = repo.update_conversation_context.call_args.kwargs["session_context"]
        self.assertEqual(
            "Outfit check this navy blazer with white tee and trousers",
            session_context["last_live_context"]["user_need"],
        )
        self.assertEqual(
            "good_with_tweaks",
            result["metadata"][Intent.OUTFIT_CHECK]["overall_verdict"],
        )
        repo.log_model_call.assert_called()

    @patch("agentic_application.agents.outfit_check_agent.OpenAI")
    @patch("agentic_application.agents.outfit_check_agent.get_api_key", return_value="test-key")
    def test_outfit_check_agent_uses_responses_api_with_json_schema(self, _get_api_key, openai_cls):
        client = Mock()
        client.responses.create.return_value = Mock(
            output_text=json.dumps(
                {
                    "overall_verdict": "great_choice",
                    "overall_note": "Strong look.",
                    "scores": {
                    "body_harmony_pct": 90,
                    "color_suitability_pct": 91,
                    "style_fit_pct": 92,
                    "pairing_coherence_pct": 89,
                    "occasion_pct": 93,
                },
                    "strengths": ["Balanced silhouette."],
                    "improvements": [],
                    "style_archetype_read": {
                        "classic_pct": 70,
                        "dramatic_pct": 10,
                        "romantic_pct": 5,
                        "natural_pct": 20,
                        "minimalist_pct": 80,
                        "creative_pct": 10,
                        "sporty_pct": 5,
                        "edgy_pct": 5,
                    },
                }
            )
        )
        openai_cls.return_value = client

        agent = OutfitCheckAgent()
        user_context = Mock(
            gender="masculine",
            derived_interpretations={},
            style_preference={},
            analysis_attributes={},
            wardrobe_items=[],
        )

        result = agent.evaluate(
            user_context=user_context,
            outfit_description="Check this look.",
            occasion_signal="date_night",
            profile_confidence_pct=100,
        )

        self.assertEqual("great_choice", result.overall_verdict)
        openai_cls.assert_called_once_with(api_key="test-key")
        kwargs = client.responses.create.call_args.kwargs
        self.assertEqual("gpt-5.4", kwargs["model"])
        self.assertIn("format", kwargs["text"])
        self.assertEqual("outfit_check_result", kwargs["text"]["format"]["name"])
        self.assertEqual(89, result.pairing_coherence_pct)

    def test_rate_my_outfit_overrides_planner_into_outfit_check(self):
        from agentic_application.schemas import CopilotPlanResult, CopilotResolvedContext, CopilotActionParameters
        repo = self._standard_repo()
        gw = self._standard_onboarding_gateway()
        planner_mock = Mock()
        planner_mock.plan.return_value = CopilotPlanResult(
            intent=Intent.OCCASION_RECOMMENDATION,
            intent_confidence=0.92,
            action=Action.RUN_RECOMMENDATION_PIPELINE,
            context_sufficient=True,
            assistant_message="Let me think about that look.",
            follow_up_suggestions=["Show me more"],
            resolved_context=CopilotResolvedContext(
                occasion_signal="dinner",
                style_goal=Intent.OCCASION_RECOMMENDATION,
            ),
            action_parameters=CopilotActionParameters(),
        )
        orchestrator = self._build_orchestrator(repo, gw, planner_mock)
        orchestrator.outfit_check_agent.evaluate.return_value = Mock(
            overall_verdict="good_with_tweaks",
            overall_note="This works, but a warmer shoe would improve it.",
            body_harmony_pct=78,
            color_suitability_pct=74,
            style_fit_pct=79,
            pairing_coherence_pct=81,
            occasion_pct=82,
            overall_score_pct=79,
            strengths=["The proportions are balanced."],
            improvements=[],
            style_archetype_read={},
            to_dict=Mock(return_value={"overall_verdict": "good_with_tweaks"}),
        )

        result = orchestrator.process_turn(
            conversation_id="c1",
            external_user_id="user-1",
            message="Rate my outfit for dinner tonight",
        )

        self.assertEqual(Intent.OUTFIT_CHECK, result["metadata"]["primary_intent"])
        self.assertIn("outfit_check_override", result["metadata"]["intent_reason_codes"])
        self.assertEqual(Intent.OUTFIT_CHECK, repo.finalize_turn.call_args.kwargs["resolved_context"]["handler"])

    def test_outfit_check_attaches_anchor_wardrobe_item_for_preview(self):
        from agentic_application.schemas import CopilotPlanResult, CopilotResolvedContext, CopilotActionParameters
        repo = self._standard_repo()
        gw = self._standard_onboarding_gateway()
        gw.get_wardrobe_items.return_value = [
            {
                "id": "w-brown-set",
                "title": "Brown Co Ord Set",
                "garment_category": "set",
                "garment_subtype": "co_ord_set",
                "primary_color": "brown",
                "occasion_fit": "smart_casual",
                "formality_level": "smart_casual",
                "image_path": "data/onboarding/images/wardrobe/brown-set.avif",
            }
        ]
        planner_mock = Mock()
        planner_mock.plan.return_value = CopilotPlanResult(
            intent=Intent.OUTFIT_CHECK,
            intent_confidence=0.98,
            action=Action.RUN_OUTFIT_CHECK,
            context_sufficient=True,
            assistant_message="Let me assess this look.",
            follow_up_suggestions=["What would improve this look?"],
            resolved_context=CopilotResolvedContext(
                occasion_signal="date_night",
                style_goal=Intent.OUTFIT_CHECK,
            ),
            action_parameters=CopilotActionParameters(),
        )
        orchestrator = self._build_orchestrator(repo, gw, planner_mock)
        orchestrator.outfit_check_agent.evaluate.return_value = Mock(
            overall_verdict="good_with_tweaks",
            overall_note="Strong base for date night.",
            body_harmony_pct=86,
            color_suitability_pct=90,
            style_fit_pct=92,
            pairing_coherence_pct=88,
            occasion_pct=78,
            overall_score_pct=86,
            strengths=["The brown tone suits your palette."],
            improvements=[],
            style_archetype_read={},
            to_dict=Mock(return_value={"overall_verdict": "good_with_tweaks"}),
        )

        result = orchestrator.process_turn(
            conversation_id="c1",
            external_user_id="user-1",
            message="How is my outfit for date evening? Attached garment context: Brown Co Ord Set, set, co_ord_set, brown, textured, smart_casual, smart_casual.",
        )

        self.assertEqual(1, len(result["outfits"]))
        self.assertEqual("w-brown-set", result["outfits"][0]["items"][0]["product_id"])
        self.assertEqual(
            "/v1/onboarding/images/local?path=data/onboarding/images/wardrobe/brown-set.avif",
            result["outfits"][0]["items"][0]["image_url"],
        )
        self.assertEqual("wardrobe", result["outfits"][0]["items"][0]["source"])

    def test_outfit_check_catalog_followup_preserves_context_for_catalog_pivot(self):
        from agentic_application.schemas import (
            CopilotPlanResult, CopilotResolvedContext, CopilotActionParameters,
            RecommendationPlan, DirectionSpec, QuerySpec, ResolvedContextBlock,
        )
        repo = self._standard_repo()
        repo.get_conversation.return_value = {
            "id": "c1",
            "user_id": "db-user",
            "session_context_json": {
                "last_user_message": "Rate my outfit for dinner tonight",
                "last_live_context": {
                    "user_need": "Rate my outfit for dinner tonight",
                    "occasion_signal": "dinner",
                    "formality_hint": None,
                    "time_hint": None,
                    "specific_needs": [Intent.OUTFIT_CHECK],
                    "is_followup": False,
                    "followup_intent": None,
                },
                "last_response_metadata": {
                    "answer_source": "outfit_check_handler",
                    "catalog_upsell": {
                        "available": True,
                        "entry_intent": Intent.OUTFIT_CHECK,
                        "cta": "Show me better options from the catalog",
                    },
                },
            },
        }
        gw = self._standard_onboarding_gateway()
        planner_mock = Mock()
        planner_mock.plan.return_value = CopilotPlanResult(
            intent=Intent.OCCASION_RECOMMENDATION,
            intent_confidence=0.94,
            action=Action.RUN_RECOMMENDATION_PIPELINE,
            context_sufficient=True,
            assistant_message="Let me find stronger options.",
            follow_up_suggestions=["Show me more"],
            resolved_context=CopilotResolvedContext(
                occasion_signal="dinner",
                style_goal=Intent.OCCASION_RECOMMENDATION,
            ),
            action_parameters=CopilotActionParameters(),
        )
        fake_plan = RecommendationPlan(
            plan_type="complete_only",
            retrieval_count=12,
            directions=[
                DirectionSpec(
                    direction_id="A",
                    direction_type="complete",
                    label="Catalog direction",
                    queries=[
                        QuerySpec(
                            query_id="A1",
                            role="complete",
                            hard_filters={},
                            query_document="dinner outfit alternatives",
                        )
                    ],
                )
            ],
            resolved_context=ResolvedContextBlock(
                occasion_signal="dinner",
                specific_needs=[Intent.OUTFIT_CHECK, "catalog_followup"],
                followup_intent="catalog_followup",
            ),
        )

        with patch("agentic_application.orchestrator.ApplicationCatalogRetrievalGateway") as _gateway_cls, \
             patch("agentic_application.orchestrator.OutfitArchitect") as architect_cls, \
             patch("agentic_application.orchestrator.CopilotPlanner", return_value=planner_mock):
            architect_cls.return_value.plan.return_value = fake_plan
            orchestrator = AgenticOrchestrator(
                repo=repo,
                onboarding_gateway=gw,
                config=self._make_planner_config(),
            )
            orchestrator.catalog_search_agent.search = Mock(return_value=[])
            orchestrator.outfit_assembler.assemble = Mock(return_value=[])
            orchestrator.outfit_evaluator.evaluate = Mock(return_value=[])
            orchestrator.response_formatter.format = Mock(
                return_value=RecommendationResponse(
                    success=True,
                    message="Here are catalog alternatives for the same styling problem.",
                    outfits=[
                        OutfitCard(
                            rank=1,
                            title="Dinner Alternative",
                            reasoning="Catalog pivot",
                            items=[{"product_id": "c1", "title": "Silk Camp Shirt", "source": "catalog"}],
                        )
                    ],
                    follow_up_suggestions=["Show me more"],
                    metadata={"answer_source": "catalog"},
                )
            )

            result = orchestrator.process_turn(
                conversation_id="c1",
                external_user_id="user-1",
                message="Show me better options from the catalog",
            )

        combined_context = architect_cls.return_value.plan.call_args.args[0]
        self.assertIn("Rate my outfit for dinner tonight", combined_context.live.user_need)
        self.assertIn("Catalog follow-up requested", combined_context.live.user_need)
        self.assertEqual("dinner", combined_context.live.occasion_signal)
        self.assertIn("catalog_followup", combined_context.live.specific_needs)
        self.assertEqual("catalog", result["outfits"][0]["items"][0]["source"])

    def test_planner_run_shopping_decision_returns_verdict_and_overlap(self):
        from agentic_application.schemas import CopilotPlanResult, CopilotResolvedContext, CopilotActionParameters
        repo = self._standard_repo()
        gw = self._standard_onboarding_gateway()
        gw.get_wardrobe_items.return_value = [
            {
                "id": "w1",
                "title": "Navy Blazer",
                "garment_category": "blazer",
                "garment_subtype": "blazer",
                "primary_color": "navy",
                "occasion_fit": "office",
                "formality_level": "smart_casual",
            },
            {
                "id": "w2",
                "title": "Cream Trousers",
                "garment_category": "trousers",
                "garment_subtype": "trousers",
                "primary_color": "cream",
                "occasion_fit": "office",
                "formality_level": "smart_casual",
            },
        ]
        planner_mock = Mock()
        planner_mock.plan.return_value = CopilotPlanResult(
            intent=Intent.SHOPPING_DECISION,
            intent_confidence=0.97,
            action=Action.RUN_SHOPPING_DECISION,
            context_sufficient=True,
            assistant_message="Let me evaluate this against your profile and wardrobe.",
            follow_up_suggestions=["What goes with this?", "Show me better options"],
            resolved_context=CopilotResolvedContext(
                occasion_signal="office",
                style_goal=Intent.SHOPPING_DECISION,
            ),
            action_parameters=CopilotActionParameters(
                detected_garments=["blazer"],
                detected_colors=["navy"],
                product_urls=["https://store.example/navy-blazer"],
            ),
        )
        orchestrator = self._build_orchestrator(repo, gw, planner_mock)
        orchestrator.shopping_decision_agent.evaluate.return_value = Mock(
            verdict="skip",
            verdict_confidence="high",
            verdict_note="This feels too close to what you already own.",
            color_suitability_pct=82,
            body_harmony_pct=78,
            style_fit_pct=75,
            wardrobe_versatility_pct=72,
            wardrobe_gap_pct=28,
            strengths=["The color works for your Autumn palette."],
            concerns=["It overlaps heavily with your existing blazer."],
            wardrobe_overlap={
                "has_duplicate": True,
                "duplicate_detail": "Navy Blazer",
                "overlap_level": "strong",
            },
            pairing_suggestions=[
                {"wardrobe_item": "Cream Trousers", "pairing_note": "They lighten the navy and keep it office-ready."}
            ],
            if_you_buy="Wear it with warmer neutrals so it feels distinct.",
            instead_consider="a warm brown textured blazer instead",
            to_dict=Mock(return_value={"verdict": "skip", "verdict_confidence": "high"}),
        )

        result = orchestrator.process_turn(
            conversation_id="c1",
            external_user_id="user-1",
            message="Should I buy this navy blazer? https://store.example/navy-blazer",
        )

        self.assertEqual(Intent.SHOPPING_DECISION, result["metadata"]["primary_intent"])
        self.assertEqual("shopping_decision_handler", result["metadata"]["answer_source"])
        self.assertIn("My verdict: SKIP.", result["assistant_message"])
        self.assertIn("You already own something similar", result["assistant_message"])
        self.assertEqual("skip", result["metadata"][Intent.SHOPPING_DECISION]["verdict"])
        self.assertEqual(
            ["https://store.example/navy-blazer"],
            result["metadata"][Intent.SHOPPING_DECISION]["product_urls"],
        )
        repo.log_model_call.assert_called()

    def test_planner_pairing_request_uses_wardrobe_first_pairing_handler(self):
        from agentic_application.schemas import CopilotPlanResult, CopilotResolvedContext, CopilotActionParameters
        repo = self._standard_repo()
        repo.client.select_many.return_value = [
            {
                "product_id": "c1",
                "title": "Stone Pleated Trousers",
                "garment_category": "trousers",
                "garment_subtype": "trousers",
                "primary_color": "stone",
                "occasion_fit": "office",
                "formality_level": "smart_casual",
                "url": "https://store.example/stone-trousers",
            },
            {
                "product_id": "c2",
                "title": "Brown Penny Loafers",
                "garment_category": "loafer",
                "garment_subtype": "loafer",
                "primary_color": "brown",
                "occasion_fit": "office",
                "formality_level": "smart_casual",
                "url": "https://store.example/brown-loafers",
            },
        ]
        gw = self._standard_onboarding_gateway()
        gw.get_wardrobe_items.return_value = [
            {
                "id": "w1",
                "title": "Navy Blazer",
                "garment_category": "blazer",
                "garment_subtype": "blazer",
                "primary_color": "navy",
                "occasion_fit": "office",
                "formality_level": "smart_casual",
            },
            {
                "id": "w2",
                "title": "Cream Trousers",
                "garment_category": "trousers",
                "garment_subtype": "trousers",
                "primary_color": "cream",
                "occasion_fit": "office",
                "formality_level": "smart_casual",
            },
            {
                "id": "w3",
                "title": "Tan Loafers",
                "garment_category": "shoe",
                "garment_subtype": "loafer",
                "primary_color": "tan",
                "occasion_fit": "office",
                "formality_level": "smart_casual",
            },
        ]
        planner_mock = Mock()
        planner_mock.plan.return_value = CopilotPlanResult(
            intent=Intent.PAIRING_REQUEST,
            intent_confidence=0.95,
            action=Action.RUN_RECOMMENDATION_PIPELINE,
            context_sufficient=True,
            assistant_message="Let me find great pairings for your blazer.",
            follow_up_suggestions=["Show me more from my wardrobe", "Show me catalog alternatives"],
            resolved_context=CopilotResolvedContext(style_goal=Intent.PAIRING_REQUEST),
            action_parameters=CopilotActionParameters(target_piece="navy blazer"),
        )
        orchestrator = self._build_orchestrator(repo, gw, planner_mock)
        orchestrator.outfit_architect.plan = Mock(side_effect=AssertionError("catalog pipeline should not run"))

        result = orchestrator.process_turn(
            conversation_id="c1",
            external_user_id="user-1",
            message="What goes with my navy blazer?",
        )

        self.assertEqual(Intent.PAIRING_REQUEST, result["metadata"]["primary_intent"])
        self.assertEqual("wardrobe_first_pairing_hybrid", result["metadata"]["answer_source"])
        self.assertIn("wardrobe_gap_analysis", result["metadata"])
        self.assertEqual(2, len(result["outfits"]))
        self.assertEqual("wardrobe", result["outfits"][0]["items"][0]["source"])
        self.assertEqual("catalog", result["outfits"][1]["items"][1]["source"])
        self.assertIn("Navy Blazer", result["assistant_message"])
        self.assertIn("Cream Trousers", result["assistant_message"])
        self.assertIn("Stone Pleated Trousers", result["assistant_message"])
        self.assertEqual("pairing_request_wardrobe_first", repo.finalize_turn.call_args.kwargs["resolved_context"]["handler"])

    def test_planner_capsule_or_trip_planning_returns_capsule_and_packing_list(self):
        from agentic_application.schemas import CopilotPlanResult, CopilotResolvedContext, CopilotActionParameters
        repo = self._standard_repo()
        gw = self._standard_onboarding_gateway()
        gw.get_wardrobe_items.return_value = [
            {
                "id": "w1",
                "title": "Navy Blazer",
                "garment_category": "blazer",
                "garment_subtype": "blazer",
                "primary_color": "navy",
                "occasion_fit": "office",
                "formality_level": "smart_casual",
            },
            {
                "id": "w2",
                "title": "White Shirt",
                "garment_category": "shirt",
                "garment_subtype": "shirt",
                "primary_color": "white",
                "occasion_fit": "office",
                "formality_level": "smart_casual",
            },
            {
                "id": "w3",
                "title": "Cream Trousers",
                "garment_category": "trousers",
                "garment_subtype": "trousers",
                "primary_color": "cream",
                "occasion_fit": "office",
                "formality_level": "smart_casual",
            },
            {
                "id": "w4",
                "title": "Tan Loafers",
                "garment_category": "shoe",
                "garment_subtype": "loafer",
                "primary_color": "tan",
                "occasion_fit": "office",
                "formality_level": "smart_casual",
            },
        ]
        planner_mock = Mock()
        planner_mock.plan.return_value = CopilotPlanResult(
            intent=Intent.CAPSULE_OR_TRIP_PLANNING,
            intent_confidence=0.93,
            action=Action.RESPOND_DIRECTLY,
            context_sufficient=True,
            assistant_message="Let me map out a compact workweek capsule.",
            follow_up_suggestions=["Build a shopping list", "Show me catalog gap fillers"],
            resolved_context=CopilotResolvedContext(style_goal="workweek capsule"),
            action_parameters=CopilotActionParameters(),
        )
        orchestrator = self._build_orchestrator(repo, gw, planner_mock)
        result = orchestrator.process_turn(
            conversation_id="c1",
            external_user_id="user-1",
            message="Plan me a 3-day work trip capsule",
        )

        self.assertEqual(Intent.CAPSULE_OR_TRIP_PLANNING, result["metadata"]["primary_intent"])
        self.assertEqual("capsule_planning_handler", result["metadata"]["answer_source"])
        self.assertIn("wardrobe_gap_analysis", result["metadata"])
        self.assertGreaterEqual(len(result["outfits"]), 3)
        self.assertEqual(3, result["metadata"]["capsule_plan"]["trip_days"])
        self.assertGreaterEqual(result["metadata"]["capsule_plan"]["target_outfit_count"], 6)
        self.assertGreaterEqual(len(result["metadata"]["capsule_plan"]["packing_list"]), 1)
        self.assertIn("look", result["assistant_message"].lower())
        self.assertTrue(result["metadata"]["capsule_plan"]["contexts"])
        self.assertEqual(Intent.CAPSULE_OR_TRIP_PLANNING, repo.finalize_turn.call_args.kwargs["resolved_context"]["handler"])

    def test_planner_capsule_or_trip_planning_scales_output_for_multi_day_trip(self):
        from agentic_application.schemas import CopilotPlanResult, CopilotResolvedContext, CopilotActionParameters
        repo = self._standard_repo()
        gw = self._standard_onboarding_gateway()
        gw.get_wardrobe_items.return_value = [
            {
                "id": "w1",
                "title": "Navy Blazer",
                "garment_category": "blazer",
                "garment_subtype": "blazer",
                "primary_color": "navy",
                "occasion_fit": "work_trip",
                "formality_level": "smart_casual",
            },
            {
                "id": "w2",
                "title": "White Shirt",
                "garment_category": "shirt",
                "garment_subtype": "shirt",
                "primary_color": "white",
                "occasion_fit": "work_trip",
                "formality_level": "smart_casual",
            },
            {
                "id": "w3",
                "title": "Blue Oxford Shirt",
                "garment_category": "shirt",
                "garment_subtype": "shirt",
                "primary_color": "blue",
                "occasion_fit": "work_trip",
                "formality_level": "smart_casual",
            },
            {
                "id": "w4",
                "title": "Cream Trousers",
                "garment_category": "trousers",
                "garment_subtype": "trousers",
                "primary_color": "cream",
                "occasion_fit": "work_trip",
                "formality_level": "smart_casual",
            },
            {
                "id": "w5",
                "title": "Charcoal Trousers",
                "garment_category": "trousers",
                "garment_subtype": "trousers",
                "primary_color": "charcoal",
                "occasion_fit": "work_trip",
                "formality_level": "smart_casual",
            },
            {
                "id": "w6",
                "title": "Tan Loafers",
                "garment_category": "shoe",
                "garment_subtype": "loafer",
                "primary_color": "tan",
                "occasion_fit": "work_trip",
                "formality_level": "smart_casual",
            },
        ]
        planner_mock = Mock()
        planner_mock.plan.return_value = CopilotPlanResult(
            intent=Intent.CAPSULE_OR_TRIP_PLANNING,
            intent_confidence=0.93,
            action=Action.RESPOND_DIRECTLY,
            context_sufficient=True,
            assistant_message="Let me map out the trip.",
            follow_up_suggestions=["Build a shopping list", "Show me catalog gap fillers"],
            resolved_context=CopilotResolvedContext(style_goal="trip capsule", occasion_signal="work_trip"),
            action_parameters=CopilotActionParameters(),
        )
        orchestrator = self._build_orchestrator(repo, gw, planner_mock)

        result = orchestrator.process_turn(
            conversation_id="c1",
            external_user_id="user-1",
            message="Plan me a 5-day work trip capsule",
        )

        self.assertEqual(5, result["metadata"]["capsule_plan"]["trip_days"])
        self.assertEqual(10, result["metadata"]["capsule_plan"]["target_outfit_count"])
        self.assertGreaterEqual(len(result["outfits"]), 6)
        self.assertGreaterEqual(len(set(outfit["title"] for outfit in result["outfits"])), 4)

    def test_planner_capsule_or_trip_planning_returns_catalog_gap_fillers(self):
        from agentic_application.schemas import CopilotPlanResult, CopilotResolvedContext, CopilotActionParameters
        repo = self._standard_repo()
        repo.client.select_many.return_value = [
            {
                "product_id": "c1",
                "title": "Espresso Loafers",
                "garment_category": "loafer",
                "garment_subtype": "loafer",
                "primary_color": "brown",
                "occasion_fit": "work_trip",
                "formality_level": "smart_casual",
                "url": "https://store.example/espresso-loafers",
            },
            {
                "product_id": "c2",
                "title": "Textured Overshirt",
                "garment_category": "overshirt",
                "garment_subtype": "overshirt",
                "primary_color": "olive",
                "occasion_fit": "work_trip",
                "formality_level": "smart_casual",
                "url": "https://store.example/textured-overshirt",
            },
        ]
        gw = self._standard_onboarding_gateway()
        gw.get_wardrobe_items.return_value = [
            {
                "id": "w1",
                "title": "White Shirt",
                "garment_category": "shirt",
                "garment_subtype": "shirt",
                "primary_color": "white",
                "occasion_fit": "work_trip",
                "formality_level": "smart_casual",
            },
            {
                "id": "w2",
                "title": "Navy Trousers",
                "garment_category": "trousers",
                "garment_subtype": "trousers",
                "primary_color": "navy",
                "occasion_fit": "work_trip",
                "formality_level": "smart_casual",
            },
        ]
        planner_mock = Mock()
        planner_mock.plan.return_value = CopilotPlanResult(
            intent=Intent.CAPSULE_OR_TRIP_PLANNING,
            intent_confidence=0.93,
            action=Action.RESPOND_DIRECTLY,
            context_sufficient=True,
            assistant_message="Let me map out a compact workweek capsule.",
            follow_up_suggestions=["Build a shopping list", "Show me catalog gap fillers"],
            resolved_context=CopilotResolvedContext(style_goal="workweek capsule", occasion_signal="work_trip"),
            action_parameters=CopilotActionParameters(),
        )
        orchestrator = self._build_orchestrator(repo, gw, planner_mock)

        result = orchestrator.process_turn(
            conversation_id="c1",
            external_user_id="user-1",
            message="Plan me a compact work trip capsule",
        )

        fillers = result["metadata"]["capsule_plan"]["catalog_gap_fillers"]
        self.assertGreaterEqual(len(fillers), 1)
        self.assertEqual("catalog", fillers[0]["source"])
        self.assertIn("Espresso Loafers", result["assistant_message"])
        self.assertTrue(any(any(item["source"] == "catalog" for item in outfit["items"]) for outfit in result["outfits"]))

    def test_planner_virtual_tryon(self):
        from agentic_application.schemas import CopilotPlanResult, CopilotResolvedContext, CopilotActionParameters
        repo = self._standard_repo()
        gw = self._standard_onboarding_gateway()
        gw.get_person_image_path.return_value = "/fake/person.png"
        planner_mock = Mock()
        planner_mock.plan.return_value = CopilotPlanResult(
            intent=Intent.VIRTUAL_TRYON_REQUEST,
            intent_confidence=0.97,
            action=Action.RUN_VIRTUAL_TRYON,
            context_sufficient=True,
            assistant_message="Let me generate a try-on preview for you.",
            follow_up_suggestions=["Should I buy this?", "What would pair with it?"],
            resolved_context=CopilotResolvedContext(),
            action_parameters=CopilotActionParameters(
                product_urls=["https://store.example/blazer"],
            ),
        )
        orchestrator = self._build_orchestrator(repo, gw, planner_mock)
        # Mock tryon service to return failure (no real service)
        orchestrator.tryon_service.generate_tryon = Mock(return_value={"success": False, "error": "Test mode"})
        result = orchestrator.process_turn(
            conversation_id="c1",
            external_user_id="user-1",
            message="Try this on me https://store.example/blazer",
        )

        self.assertEqual(Intent.VIRTUAL_TRYON_REQUEST, result["metadata"]["primary_intent"])

    def test_planner_error_fallback(self):
        repo = self._standard_repo()
        gw = self._standard_onboarding_gateway()
        planner_mock = Mock()
        planner_mock.plan.side_effect = RuntimeError("LLM unavailable")
        orchestrator = self._build_orchestrator(repo, gw, planner_mock)
        result = orchestrator.process_turn(
            conversation_id="c1",
            external_user_id="user-1",
            message="What colors suit me?",
        )

        self.assertIn("trouble", result["assistant_message"].lower())
        self.assertEqual("error", result["response_type"])

    def test_copilot_plan_result_schema(self):
        from agentic_application.schemas import CopilotPlanResult, CopilotResolvedContext, CopilotActionParameters
        plan = CopilotPlanResult(
            intent=Intent.STYLE_DISCOVERY,
            intent_confidence=0.95,
            action=Action.RESPOND_DIRECTLY,
            context_sufficient=True,
            assistant_message="Your Autumn palette means warm tones are your best friend.",
            follow_up_suggestions=["Show me outfits", "What should I avoid?"],
            resolved_context=CopilotResolvedContext(style_goal="color_direction"),
            action_parameters=CopilotActionParameters(detected_colors=["navy", "burgundy"]),
        )
        dumped = plan.model_dump()
        self.assertEqual(Intent.STYLE_DISCOVERY, dumped["intent"])
        self.assertEqual(["navy", "burgundy"], dumped["action_parameters"]["detected_colors"])
        self.assertEqual("color_direction", dumped["resolved_context"]["style_goal"])

    def test_build_planner_input_structure(self):
        from agentic_application.agents.copilot_planner import build_planner_input
        user_context = UserContext(
            user_id="u1",
            gender="female",
            derived_interpretations={
                "SeasonalColorGroup": {"value": "Autumn"},
                "ContrastLevel": {"value": "High"},
            },
            style_preference={"primaryArchetype": "classic", "secondaryArchetype": "romantic"},
            profile_richness="full",
            wardrobe_items=[{"title": "Navy Blazer", "garment_category": "outerwear", "primary_color": "navy"}],
        )
        result = build_planner_input(
            message="What colors suit me?",
            user_context=user_context,
            conversation_history=[],
            previous_context={"last_intent": Intent.STYLE_DISCOVERY},
            profile_confidence_pct=85,
            has_person_image=True,
        )
        self.assertEqual("What colors suit me?", result["user_message"])
        self.assertEqual("female", result["user_profile"]["gender"])
        self.assertEqual("Autumn", result["user_profile"]["seasonal_color_group"])
        self.assertEqual("classic", result["user_profile"]["primary_archetype"])
        self.assertEqual(1, result["wardrobe_summary"]["count"])
        self.assertEqual(85, result["profile_confidence_pct"])
        self.assertTrue(result["has_person_image"])
        self.assertEqual(Intent.STYLE_DISCOVERY, result["previous_intent"])


    @patch("agentic_application.services.outfit_decomposition.OpenAI")
    @patch("agentic_application.services.outfit_decomposition.get_api_key", return_value="test-key")
    @patch("agentic_application.services.outfit_decomposition._image_to_input_url", return_value="data:image/jpeg;base64,abc")
    def test_decompose_outfit_image_returns_garment_list(self, _img_url, _api_key, openai_cls):
        from agentic_application.services.outfit_decomposition import decompose_outfit_image

        client = Mock()
        client.responses.create.return_value = Mock(
            output_text=json.dumps({
                "garments": [
                    {
                        "garment_category": "outerwear",
                        "garment_subtype": "blazer",
                        "primary_color": "navy",
                        "secondary_color": "",
                        "pattern_type": "solid",
                        "formality_level": "smart_casual",
                        "occasion_fit": "office",
                        "title": "Navy Blazer",
                        "visibility_pct": 95,
                        "bbox_top_pct": 10, "bbox_left_pct": 15, "bbox_height_pct": 45, "bbox_width_pct": 70,
                    },
                    {
                        "garment_category": "top",
                        "garment_subtype": "t-shirt",
                        "primary_color": "white",
                        "secondary_color": "",
                        "pattern_type": "solid",
                        "formality_level": "casual",
                        "occasion_fit": "casual",
                        "title": "White T-Shirt",
                        "visibility_pct": 90,
                        "bbox_top_pct": 15, "bbox_left_pct": 20, "bbox_height_pct": 35, "bbox_width_pct": 60,
                    },
                    {
                        "garment_category": "bottom",
                        "garment_subtype": "jeans",
                        "primary_color": "blue",
                        "secondary_color": "",
                        "pattern_type": "solid",
                        "formality_level": "casual",
                        "occasion_fit": "casual",
                        "title": "Blue Jeans",
                        "visibility_pct": 40,
                        "bbox_top_pct": 50, "bbox_left_pct": 20, "bbox_height_pct": 30, "bbox_width_pct": 60,
                    },
                ]
            })
        )
        openai_cls.return_value = client

        garments = decompose_outfit_image("/tmp/outfit.jpg")

        self.assertEqual(2, len(garments))  # Blue Jeans (40% visibility) filtered out
        self.assertEqual("Navy Blazer", garments[0]["title"])
        self.assertEqual("outerwear", garments[0]["garment_category"])
        self.assertEqual("White T-Shirt", garments[1]["title"])
        self.assertNotIn("Blue Jeans", [g["title"] for g in garments])

    def test_outfit_check_passes_image_to_agent_and_decomposes_async(self):
        from agentic_application.schemas import CopilotPlanResult, CopilotResolvedContext, CopilotActionParameters
        repo = self._standard_repo()
        gw = self._standard_onboarding_gateway()
        gw.get_wardrobe_items.return_value = []
        planner_mock = Mock()
        planner_mock.plan.return_value = CopilotPlanResult(
            intent=Intent.OUTFIT_CHECK,
            intent_confidence=0.96,
            action=Action.RUN_OUTFIT_CHECK,
            context_sufficient=True,
            assistant_message="Let me assess this look.",
            resolved_context=CopilotResolvedContext(occasion_signal="office"),
            action_parameters=CopilotActionParameters(),
        )
        orchestrator = self._build_orchestrator(repo, gw, planner_mock)
        orchestrator.outfit_check_agent.evaluate.return_value = Mock(
            overall_verdict="great_choice",
            overall_note="Great look.",
            body_harmony_pct=85, color_suitability_pct=80, style_fit_pct=82,
            pairing_coherence_pct=84, occasion_pct=88, overall_score_pct=84,
            strengths=["Balanced silhouette."],
            improvements=[],
            style_archetype_read={"classic_pct": 70, "dramatic_pct": 10, "romantic_pct": 10, "natural_pct": 10, "minimalist_pct": 0, "creative_pct": 0, "sporty_pct": 0, "edgy_pct": 0},
            to_dict=Mock(return_value={}),
        )

        gw.save_uploaded_chat_wardrobe_item.return_value = {
            "id": "attached-1",
            "image_path": "/tmp/outfit.jpg",
            "garment_category": "dress",
            "title": "Full Outfit",
        }

        with patch("agentic_application.orchestrator.Thread") as mock_thread:
            result = orchestrator.process_turn(
                conversation_id="c1",
                external_user_id="user-1",
                message="Outfit check this",
                image_data="data:image/jpeg;base64,/9j/4AAQ",
            )

            # Agent receives image_path
            eval_kwargs = orchestrator.outfit_check_agent.evaluate.call_args.kwargs
            self.assertEqual("/tmp/outfit.jpg", eval_kwargs["image_path"])

            # Decomposition launched in background thread
            mock_thread.assert_called_once()
            self.assertEqual(mock_thread.return_value.start.call_count, 1)

    def test_outfit_check_without_image_skips_decomposition(self):
        from agentic_application.schemas import CopilotPlanResult, CopilotResolvedContext, CopilotActionParameters
        repo = self._standard_repo()
        gw = self._standard_onboarding_gateway()
        gw.get_wardrobe_items.return_value = []
        planner_mock = Mock()
        planner_mock.plan.return_value = CopilotPlanResult(
            intent=Intent.OUTFIT_CHECK,
            intent_confidence=0.96,
            action=Action.RUN_OUTFIT_CHECK,
            context_sufficient=True,
            assistant_message="Let me assess this look.",
            resolved_context=CopilotResolvedContext(occasion_signal="office"),
            action_parameters=CopilotActionParameters(),
        )
        orchestrator = self._build_orchestrator(repo, gw, planner_mock)
        orchestrator.outfit_check_agent.evaluate.return_value = Mock(
            overall_verdict="great_choice",
            overall_note="Great look.",
            body_harmony_pct=85, color_suitability_pct=80, style_fit_pct=82,
            pairing_coherence_pct=84, occasion_pct=88, overall_score_pct=84,
            strengths=["Balanced."],
            improvements=[],
            style_archetype_read={"classic_pct": 70, "dramatic_pct": 10, "romantic_pct": 10, "natural_pct": 10, "minimalist_pct": 0, "creative_pct": 0, "sporty_pct": 0, "edgy_pct": 0},
            to_dict=Mock(return_value={}),
        )

        with patch("agentic_application.orchestrator.Thread") as mock_thread:
            result = orchestrator.process_turn(
                conversation_id="c1",
                external_user_id="user-1",
                message="Outfit check my navy blazer with trousers",
            )

            # No image → no background decomposition
            mock_thread.assert_not_called()


if __name__ == "__main__":
    unittest.main()
