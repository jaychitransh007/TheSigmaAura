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
                "recent_intents": [Intent.GARMENT_EVALUATION],
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

        self.assertEqual([Intent.GARMENT_EVALUATION, Intent.OCCASION_RECOMMENDATION], memory.recent_intents)
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

    # ------------------------------------------------------------------
    # P0: Silent empty response on pipeline failure
    # ------------------------------------------------------------------

    def _build_minimal_orchestrator_repo_and_gateway(self):
        """Common scaffolding for orchestrator integration tests below."""
        repo = Mock()
        repo.client = Mock()
        repo.get_or_create_user.return_value = {"id": "db-user"}
        repo.get_conversation.return_value = {
            "id": "c1",
            "user_id": "db-user",
            "session_context_json": {},
        }
        repo.create_turn.return_value = {"id": "t1"}
        repo.list_disliked_product_ids_for_user.return_value = []

        gw = Mock()
        gw.get_effective_seasonal_groups.return_value = None
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
        gw.get_wardrobe_items.return_value = []  # force the catalog pipeline path
        return repo, gw

    def test_pipeline_crash_in_assembler_returns_user_facing_fallback(self) -> None:
        """If the assembler crashes mid-pipeline, the orchestrator must return a graceful
        fallback message, not an empty assistant_message."""
        repo, gw = self._build_minimal_orchestrator_repo_and_gateway()

        plan = RecommendationPlan(
            plan_type="paired_only",
            retrieval_count=8,
            plan_source="llm",
            directions=[
                DirectionSpec(
                    direction_id="A",
                    direction_type="paired",
                    label="Paired",
                    queries=[QuerySpec(query_id="A1", role="top", query_document="navy shirt")],
                )
            ],
        )
        retrieved_sets = [
            RetrievedSet(direction_id="A", query_id="A1", role="top", products=[]),
        ]

        with patch("agentic_application.orchestrator.ApplicationCatalogRetrievalGateway"), patch(
            "agentic_application.orchestrator.OutfitArchitect"
        ) as architect_cls, patch(
            "agentic_application.orchestrator.CatalogSearchAgent"
        ) as search_cls, patch(
            "agentic_application.orchestrator.OutfitAssembler"
        ) as assembler_cls, patch(
            "agentic_application.orchestrator.OutfitEvaluator"
        ), patch(
            "agentic_application.orchestrator.ResponseFormatter"
        ):
            architect_cls.return_value.plan.return_value = plan
            search_cls.return_value.search.return_value = retrieved_sets
            # Simulate the failure mode from the live conversation review:
            # assembler crashes with an unhandled exception mid-pipeline.
            assembler_cls.return_value.assemble.side_effect = RuntimeError(
                "boom: simulated assembler crash"
            )

            orchestrator = AgenticOrchestrator(
                repo=repo, onboarding_gateway=gw, config=Mock()
            )
            result = orchestrator.process_turn(
                conversation_id="c1",
                external_user_id="user-1",
                message="What should I wear to dinner tonight?",
            )

        # The user-facing message must be non-empty and a graceful fallback.
        self.assertTrue(result.get("assistant_message"))
        self.assertIn("wasn't able to put together", result["assistant_message"])
        self.assertEqual("error", result["response_type"])
        self.assertTrue(result["metadata"].get("error"))
        self.assertEqual("planner_pipeline", result["metadata"].get("error_stage"))
        # And finalize_turn must have been called with the same fallback,
        # NOT with an empty string.
        finalize_args = repo.finalize_turn.call_args
        self.assertTrue(finalize_args.kwargs["assistant_message"])
        self.assertIn(
            "wasn't able to put together",
            finalize_args.kwargs["assistant_message"],
        )

    def test_pipeline_empty_response_message_is_replaced_with_fallback(self) -> None:
        """Even if the formatter completes but produces an empty message, the post-pipeline
        guard must rewrite it to a graceful fallback before returning."""
        repo, gw = self._build_minimal_orchestrator_repo_and_gateway()

        plan = RecommendationPlan(
            plan_type="paired_only",
            retrieval_count=8,
            plan_source="llm",
            directions=[
                DirectionSpec(
                    direction_id="A",
                    direction_type="paired",
                    label="Paired",
                    queries=[QuerySpec(query_id="A1", role="top", query_document="navy shirt")],
                )
            ],
        )
        retrieved_sets = [
            RetrievedSet(direction_id="A", query_id="A1", role="top", products=[]),
        ]
        empty_response = RecommendationResponse(
            success=True,
            message="",   # ← deliberately empty
            outfits=[],
            follow_up_suggestions=[],
            metadata={"plan_type": "paired_only", "plan_source": "llm"},
        )

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
            assembler_cls.return_value.assemble.return_value = []
            evaluator_cls.return_value.evaluate.return_value = []
            formatter_cls.return_value.format.return_value = empty_response

            orchestrator = AgenticOrchestrator(
                repo=repo, onboarding_gateway=gw, config=Mock()
            )
            result = orchestrator.process_turn(
                conversation_id="c1",
                external_user_id="user-1",
                message="What should I wear to dinner tonight?",
            )

        # The post-pipeline guard must have rewritten the empty message.
        self.assertTrue(
            result.get("assistant_message"),
            "Empty assistant_message was returned to the user — fallback guard did not fire",
        )
        self.assertIn("wasn't able to put together", result["assistant_message"])

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

    # ------------------------------------------------------------------
    # P1: Cross-outfit diversity enforcement
    #
    # Contract: every product_id appears in AT MOST ONE accepted candidate,
    # and that candidate is the one where the product scored highest
    # ("the best it pairs with"). Over-cap candidates are DROPPED, not
    # deferred — the evaluator must never see duplicates.
    # ------------------------------------------------------------------

    def test_assembler_caps_product_id_to_single_accepted_candidate(self) -> None:
        """Each product_id appears in at most one accepted candidate, and it's
        the highest-scoring pairing for that product."""
        from agentic_application.agents.outfit_assembler import OutfitAssembler

        context = CombinedContext(
            user=UserContext(user_id="u1", gender="female"),
            live=LiveContext(user_need="Office look"),
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

        # One dominant top + several different bottoms of varying similarity.
        # Naive scoring would put the same top in every candidate; the
        # diversity pass should drop all but the highest-scoring pair.
        dominant_top = RetrievedProduct(
            product_id="dominant_top",
            similarity=0.99,
            enriched_data={"primary_color": "navy", "occasion_fit": "office"},
            metadata={},
        )
        # Give the bottoms different similarities so we can verify the
        # accepted candidate is the one that pairs *best* (highest score).
        bottoms = [
            RetrievedProduct(
                product_id=f"bottom_{i}",
                similarity=0.90 - (i * 0.05),  # 0.90, 0.85, 0.80, 0.75, 0.70
                enriched_data={"primary_color": "cream", "occasion_fit": "office"},
                metadata={},
            )
            for i in range(5)
        ]

        retrieved_sets = [
            RetrievedSet(direction_id="A", query_id="q1", role="top", products=[dominant_top]),
            RetrievedSet(direction_id="A", query_id="q2", role="bottom", products=bottoms),
        ]

        assembler = OutfitAssembler()
        candidates = assembler.assemble(retrieved_sets, plan, context)

        # With 1 dominant top and 5 bottoms, there are 5 raw pairings but
        # each re-uses dominant_top. The diversity pass must collapse to 1
        # accepted candidate — the best pairing.
        self.assertEqual(
            1, len(candidates),
            f"expected exactly 1 accepted candidate (dominant_top pairs with "
            f"best bottom only), got {len(candidates)}",
        )
        accepted = candidates[0]
        # The accepted candidate must pair dominant_top with bottom_0
        # (similarity 0.90, the highest-scoring bottom).
        item_ids = sorted(str(item.get("product_id") or "") for item in accepted.items)
        self.assertEqual(
            ["bottom_0", "dominant_top"],
            item_ids,
            f"expected dominant_top × bottom_0 (best pairing), got {item_ids}",
        )
        # The assembly notes should record that 4 duplicates were dropped
        self.assertTrue(
            any("dropped 4 duplicate" in note for note in accepted.assembly_notes),
            f"expected drop counter in assembly_notes, got {accepted.assembly_notes}",
        )

    def test_assembler_diversity_rule_applies_symmetrically_to_both_items(self) -> None:
        """With 3 tops × 3 bottoms (9 raw pairings), the diversity rule
        forces each product to appear in exactly one outfit. With 3 of each
        role the maximum diverse set is min(tops, bottoms) = 3 outfits."""
        from agentic_application.agents.outfit_assembler import OutfitAssembler

        context = CombinedContext(
            user=UserContext(user_id="u1", gender="female"),
            live=LiveContext(user_need="Office look"),
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
        tops = [
            RetrievedProduct(
                product_id=f"top_{i}",
                similarity=0.90 - (i * 0.02),  # 0.90, 0.88, 0.86
                enriched_data={"primary_color": "navy", "occasion_fit": "office"},
                metadata={},
            )
            for i in range(3)
        ]
        bottoms = [
            RetrievedProduct(
                product_id=f"bottom_{i}",
                similarity=0.90 - (i * 0.02),
                enriched_data={"primary_color": "cream", "occasion_fit": "office"},
                metadata={},
            )
            for i in range(3)
        ]
        retrieved_sets = [
            RetrievedSet(direction_id="A", query_id="q1", role="top", products=tops),
            RetrievedSet(direction_id="A", query_id="q2", role="bottom", products=bottoms),
        ]
        assembler = OutfitAssembler()
        candidates = assembler.assemble(retrieved_sets, plan, context)

        # The diversity rule can produce at most min(#tops, #bottoms) = 3
        # non-overlapping pairings. It may produce fewer if score ordering
        # forces a top to pair with its same-ranked bottom first.
        self.assertLessEqual(len(candidates), 3)
        self.assertGreater(len(candidates), 0)
        # Each product appears in exactly one accepted candidate.
        usage: Dict[str, int] = {}
        for c in candidates:
            for item in c.items:
                pid = str(item.get("product_id") or "")
                usage[pid] = usage.get(pid, 0) + 1
        for pid, count in usage.items():
            self.assertEqual(
                1, count,
                f"product {pid} used {count} times in accepted set — must be exactly 1",
            )

    def test_assembler_diversity_pass_is_noop_when_no_repetition_possible(self) -> None:
        """If every candidate has fully unique products (disjoint pairings),
        the diversity pass doesn't drop anything."""
        from agentic_application.agents.outfit_assembler import OutfitAssembler

        context = CombinedContext(
            user=UserContext(user_id="u1", gender="female"),
            live=LiveContext(user_need="Office look"),
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
        # Two disjoint "lanes": (top_0, bottom_0) and (top_1, bottom_1).
        # There are 4 raw pairings but only 2 are truly disjoint.
        tops = [
            RetrievedProduct(
                product_id=f"top_{i}",
                similarity=0.90,
                enriched_data={"primary_color": "navy", "occasion_fit": "office"},
                metadata={},
            )
            for i in range(2)
        ]
        bottoms = [
            RetrievedProduct(
                product_id=f"bottom_{i}",
                similarity=0.90,
                enriched_data={"primary_color": "cream", "occasion_fit": "office"},
                metadata={},
            )
            for i in range(2)
        ]
        retrieved_sets = [
            RetrievedSet(direction_id="A", query_id="q1", role="top", products=tops),
            RetrievedSet(direction_id="A", query_id="q2", role="bottom", products=bottoms),
        ]
        assembler = OutfitAssembler()
        candidates = assembler.assemble(retrieved_sets, plan, context)
        # Maximum matching on a 2×2 complete bipartite graph is 2 outfits.
        self.assertLessEqual(len(candidates), 2)
        self.assertGreater(len(candidates), 0)
        # Verify no product_id repeats.
        seen: set[str] = set()
        for c in candidates:
            for item in c.items:
                pid = str(item.get("product_id") or "")
                self.assertNotIn(pid, seen, f"{pid} appeared in 2 candidates")
                seen.add(pid)

    # ------------------------------------------------------------------
    # P1: Disliked product suppression
    # ------------------------------------------------------------------

    def test_catalog_search_excludes_disliked_product_ids(self) -> None:
        """Products whose product_id is in CombinedContext.disliked_product_ids are filtered out."""
        from agentic_application.agents.catalog_search_agent import CatalogSearchAgent

        gateway = Mock()
        gateway.embed_texts.return_value = [[0.1] * 8]
        gateway.similarity_search.return_value = [
            {"product_id": "good_1", "similarity": 0.9, "metadata_json": {}},
            {"product_id": "disliked_1", "similarity": 0.92, "metadata_json": {}},
            {"product_id": "good_2", "similarity": 0.88, "metadata_json": {}},
        ]
        client = Mock()
        client.select_many.return_value = [
            {"product_id": "good_1"},
            {"product_id": "disliked_1"},
            {"product_id": "good_2"},
        ]
        agent = CatalogSearchAgent(retrieval_gateway=gateway, client=client)

        context = CombinedContext(
            user=UserContext(user_id="u1", gender="female"),
            live=LiveContext(user_need="something"),
            disliked_product_ids=["disliked_1"],
        )
        plan = RecommendationPlan(
            plan_type="paired_only",
            retrieval_count=8,
            directions=[
                DirectionSpec(
                    direction_id="A",
                    direction_type="paired",
                    label="test",
                    queries=[
                        QuerySpec(query_id="q1", role="top", query_document="navy shirt"),
                    ],
                )
            ],
        )

        results = agent.search(plan, context)
        all_ids = [p.product_id for rs in results for p in rs.products]
        self.assertIn("good_1", all_ids)
        self.assertIn("good_2", all_ids)
        self.assertNotIn(
            "disliked_1", all_ids,
            "Disliked product was returned despite being in CombinedContext.disliked_product_ids",
        )
        # And the applied_filters should record that suppression happened
        self.assertEqual(
            "excluded",
            results[0].applied_filters.get("disliked_product_policy"),
        )
        self.assertEqual(
            "1",
            results[0].applied_filters.get("disliked_excluded_count"),
        )

    def test_catalog_search_no_disliked_filter_when_list_empty(self) -> None:
        """When disliked_product_ids is empty, applied_filters should not advertise suppression."""
        from agentic_application.agents.catalog_search_agent import CatalogSearchAgent

        gateway = Mock()
        gateway.embed_texts.return_value = [[0.1] * 8]
        gateway.similarity_search.return_value = [
            {"product_id": "good_1", "similarity": 0.9, "metadata_json": {}},
        ]
        client = Mock()
        client.select_many.return_value = [{"product_id": "good_1"}]
        agent = CatalogSearchAgent(retrieval_gateway=gateway, client=client)
        context = CombinedContext(
            user=UserContext(user_id="u1", gender="female"),
            live=LiveContext(user_need="something"),
        )
        plan = RecommendationPlan(
            plan_type="paired_only",
            retrieval_count=8,
            directions=[
                DirectionSpec(
                    direction_id="A",
                    direction_type="paired",
                    label="test",
                    queries=[QuerySpec(query_id="q1", role="top", query_document="navy")],
                )
            ],
        )
        results = agent.search(plan, context)
        self.assertNotIn("disliked_product_policy", results[0].applied_filters)

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
                source_preference="wardrobe",
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
                source_preference="wardrobe",
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
                source_preference="catalog",
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
             patch("agentic_application.orchestrator.VisualEvaluatorAgent"), \
             patch("agentic_application.orchestrator.StyleAdvisorAgent"), \
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

    def test_style_discovery_general_question_delegates_to_style_advisor(self):
        """Phase 12C: open-ended style_discovery questions that don't match
        any topical helper (collar, color, pattern, silhouette, archetype)
        should delegate to StyleAdvisorAgent in 'discovery' mode."""
        from agentic_application.schemas import CopilotPlanResult, CopilotResolvedContext, CopilotActionParameters
        from agentic_application.agents.style_advisor_agent import StyleAdvice
        repo = self._standard_repo()
        gw = self._standard_onboarding_gateway()
        planner_mock = Mock()
        planner_mock.plan.return_value = CopilotPlanResult(
            intent=Intent.STYLE_DISCOVERY,
            intent_confidence=0.94,
            action=Action.RESPOND_DIRECTLY,
            context_sufficient=True,
            assistant_message="",  # Phase 12C — planner leaves this empty for advisory intents
            follow_up_suggestions=["What colors suit me?", "What's my style archetype?"],
            resolved_context=CopilotResolvedContext(style_goal=Intent.STYLE_DISCOVERY),
            action_parameters=CopilotActionParameters(),
        )
        orchestrator = self._build_orchestrator(repo, gw, planner_mock)
        orchestrator.style_advisor.advise.return_value = StyleAdvice({
            "assistant_message": (
                "Your style sits in a classic + romantic blend, anchored by your "
                "Autumn palette and balanced frame. Lead with structure, soften "
                "with texture."
            ),
            "bullet_points": [
                "Anchor outfits with warm neutrals from your Autumn base",
                "Layer romantic textures — silk, drape, velvet — over classic shapes",
                "Use accent colors for statement pieces",
            ],
            "cited_attributes": ["primary_archetype", "secondary_archetype", "seasonal_color_group"],
            "dominant_directions": ["physical+color", "comfort"],
        })

        result = orchestrator.process_turn(
            conversation_id="c1",
            external_user_id="user-1",
            message="What defines my style?",
        )

        # Topic detected as "general" → advisor takes over
        self.assertEqual("general", result["metadata"][Intent.STYLE_DISCOVERY]["advice_topic"])
        self.assertTrue(result["metadata"][Intent.STYLE_DISCOVERY]["advisor_used"])
        self.assertEqual("style_advisor_agent", result["metadata"]["answer_source"])
        # Advisor was called with mode="discovery"
        orchestrator.style_advisor.advise.assert_called_once()
        advise_kwargs = orchestrator.style_advisor.advise.call_args.kwargs
        self.assertEqual("discovery", advise_kwargs["mode"])
        self.assertEqual("What defines my style?", advise_kwargs["query"])
        # Bullet-pointed assistant message contains the advisor's content
        self.assertIn("classic + romantic blend", result["assistant_message"])
        self.assertIn("•", result["assistant_message"])

    def test_style_discovery_topical_question_keeps_deterministic_helper(self):
        """Phase 12C layered routing: a collar question still uses the
        deterministic helper, not the StyleAdvisorAgent. This preserves the
        Phase 11 evidence-backed regression coverage."""
        from agentic_application.schemas import CopilotPlanResult, CopilotResolvedContext, CopilotActionParameters
        repo = self._standard_repo()
        gw = self._standard_onboarding_gateway()
        planner_mock = Mock()
        planner_mock.plan.return_value = CopilotPlanResult(
            intent=Intent.STYLE_DISCOVERY,
            intent_confidence=0.95,
            action=Action.RESPOND_DIRECTLY,
            context_sufficient=True,
            assistant_message="",
            follow_up_suggestions=[],
            resolved_context=CopilotResolvedContext(style_goal=Intent.STYLE_DISCOVERY),
            action_parameters=CopilotActionParameters(),
        )
        orchestrator = self._build_orchestrator(repo, gw, planner_mock)

        result = orchestrator.process_turn(
            conversation_id="c1",
            external_user_id="user-1",
            message="What collar will look good on me?",
        )

        # Topical → deterministic path
        self.assertEqual("collar", result["metadata"][Intent.STYLE_DISCOVERY]["advice_topic"])
        self.assertFalse(result["metadata"][Intent.STYLE_DISCOVERY]["advisor_used"])
        self.assertEqual("style_discovery_handler", result["metadata"]["answer_source"])
        # Advisor was NOT called for the topical question
        orchestrator.style_advisor.advise.assert_not_called()
        # The deterministic helper output is in the assistant message
        self.assertIn("open, elongated shape", result["assistant_message"])

    def test_explanation_request_falls_back_when_no_previous_recommendation(self):
        """Phase 12C: explanation_request falls back to the deterministic
        summary when there's no previous_recommendation in session_context
        for the advisor to reason about."""
        from agentic_application.schemas import CopilotPlanResult, CopilotResolvedContext, CopilotActionParameters
        repo = self._standard_repo()
        # No last_recommendations in session_context
        gw = self._standard_onboarding_gateway()
        planner_mock = Mock()
        planner_mock.plan.return_value = CopilotPlanResult(
            intent=Intent.EXPLANATION_REQUEST,
            intent_confidence=0.9,
            action=Action.RESPOND_DIRECTLY,
            context_sufficient=True,
            assistant_message="",
            follow_up_suggestions=[],
            resolved_context=CopilotResolvedContext(style_goal="explanation"),
            action_parameters=CopilotActionParameters(),
        )
        orchestrator = self._build_orchestrator(repo, gw, planner_mock)

        result = orchestrator.process_turn(
            conversation_id="c1",
            external_user_id="user-1",
            message="Why did you recommend that?",
        )

        # Without prior recommendations, advisor is NOT called and the
        # answer_source is the deterministic explanation_handler.
        self.assertEqual("explanation_handler", result["metadata"]["answer_source"])
        orchestrator.style_advisor.advise.assert_not_called()
        # Some assistant message is still rendered
        self.assertTrue(len(result["assistant_message"]) > 0)

    # ------------------------------------------------------------------
    # P1: Metadata persistence consistency
    # ------------------------------------------------------------------

    def test_style_discovery_persists_response_metadata_in_resolved_context(self):
        """Style-discovery turns must persist response_metadata into resolved_context_json
        so review tools can read primary_intent / answer_source / confidence payloads
        from the turn record without falling back to session_context."""
        from agentic_application.schemas import CopilotPlanResult, CopilotResolvedContext, CopilotActionParameters
        repo = self._standard_repo()
        gw = self._standard_onboarding_gateway()
        planner_mock = Mock()
        planner_mock.plan.return_value = CopilotPlanResult(
            intent=Intent.STYLE_DISCOVERY,
            intent_confidence=0.95,
            action=Action.RESPOND_DIRECTLY,
            context_sufficient=True,
            assistant_message="Let me explain.",
            follow_up_suggestions=[],
            resolved_context=CopilotResolvedContext(style_goal=Intent.STYLE_DISCOVERY),
            action_parameters=CopilotActionParameters(),
        )
        orchestrator = self._build_orchestrator(repo, gw, planner_mock)

        orchestrator.process_turn(
            conversation_id="c1",
            external_user_id="user-1",
            message="What collar will look good on me?",
        )

        finalize_args = repo.finalize_turn.call_args
        resolved_context = finalize_args.kwargs["resolved_context"]
        self.assertIn(
            "response_metadata", resolved_context,
            "style_discovery handler did not persist response_metadata in resolved_context",
        )
        rm = resolved_context["response_metadata"]
        # The aligned fields specified in the doc must all be present
        self.assertEqual(Intent.STYLE_DISCOVERY, rm.get("primary_intent"))
        self.assertEqual("style_discovery_handler", rm.get("answer_source"))
        self.assertIn("intent_confidence", rm)
        self.assertIn("profile_confidence", rm)

    def test_wardrobe_first_occasion_persists_response_metadata_in_resolved_context(self):
        """Wardrobe-first occasion turns must persist response_metadata in resolved_context_json
        so the same review tooling works for the wardrobe-first short-circuit path."""
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
        onboarding_gateway.get_wardrobe_items.return_value = [
            {"id": "w1", "title": "Navy Blazer", "garment_category": "top",
             "occasion_fit": "office", "formality_level": "business_casual"},
            {"id": "w2", "title": "Cream Trousers", "garment_category": "bottom",
             "occasion_fit": "office", "formality_level": "business_casual"},
        ]
        repo.client = Mock()
        repo.get_or_create_user.return_value = {"id": "db-user"}
        repo.get_conversation.return_value = {
            "id": "c1", "user_id": "db-user", "session_context_json": {},
        }
        repo.create_turn.return_value = {"id": "t1"}
        repo.list_disliked_product_ids_for_user.return_value = []

        with patch("agentic_application.orchestrator.ApplicationCatalogRetrievalGateway"), patch(
            "agentic_application.orchestrator.OutfitArchitect"
        ):
            orchestrator = AgenticOrchestrator(
                repo=repo, onboarding_gateway=onboarding_gateway, config=Mock()
            )
            orchestrator.process_turn(
                conversation_id="c1",
                external_user_id="user-1",
                message="What should I wear to the office tomorrow?",
            )

        finalize_args = repo.finalize_turn.call_args
        resolved_context = finalize_args.kwargs["resolved_context"]
        self.assertIn(
            "response_metadata", resolved_context,
            "wardrobe-first occasion handler did not persist response_metadata",
        )
        rm = resolved_context["response_metadata"]
        self.assertEqual(Intent.OCCASION_RECOMMENDATION, rm.get("primary_intent"))
        self.assertEqual("wardrobe_first", rm.get("answer_source"))
        self.assertIn("intent_confidence", rm)
        self.assertIn("recommendation_confidence", rm)

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
        # Phase 12C: explanation_request now delegates to StyleAdvisorAgent
        # when previous_recommendations is present. Mock the advisor with a
        # real StyleAdvice that contains the expected content.
        from agentic_application.agents.style_advisor_agent import StyleAdvice
        orchestrator.style_advisor.advise.return_value = StyleAdvice({
            "assistant_message": (
                "I picked Elegant Wedding Look because it matched the occasion "
                "and your color story. My confidence on that answer was high "
                "because the profile signals lined up cleanly."
            ),
            "bullet_points": [
                "Burgundy and cream are strong accents in your Autumn palette",
                "The dress silhouette suits your hourglass frame",
                "Confidence: high — your profile has clear evidence",
            ],
            "cited_attributes": ["seasonal_color_group", "body_shape", "occasion_fit"],
            "dominant_directions": ["physical+color", "occasion"],
        })

        result = orchestrator.process_turn(
            conversation_id="c1",
            external_user_id="user-1",
            message="Why did you recommend that?",
        )

        self.assertEqual(Intent.EXPLANATION_REQUEST, result["metadata"]["primary_intent"])
        # Phase 12C: answer_source flips to style_advisor_agent when the
        # advisor produced the response. The deterministic explanation_handler
        # remains the fallback when the advisor fails or there are no
        # previous_recommendations to reason about.
        self.assertEqual("style_advisor_agent", result["metadata"]["answer_source"])
        self.assertIn("Elegant Wedding Look", result["assistant_message"])
        self.assertIn("confidence", result["assistant_message"].lower())
        self.assertEqual([], result["outfits"])
        # Verify the advisor was called with the prior recommendation as context
        orchestrator.style_advisor.advise.assert_called_once()
        advise_kwargs = orchestrator.style_advisor.advise.call_args.kwargs
        self.assertEqual("explanation", advise_kwargs["mode"])
        self.assertEqual("Elegant Wedding Look", advise_kwargs["previous_recommendation_focus"]["title"])

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

    def test_attached_garment_pairing_request_runs_full_pipeline(self):
        """Pairing requests always run the full pipeline (architect → search → evaluate → tryon)."""
        from agentic_application.schemas import (
            CopilotPlanResult, CopilotResolvedContext, CopilotActionParameters,
            RecommendationPlan, DirectionSpec, QuerySpec, ResolvedContextBlock,
            OutfitCard, RecommendationResponse,
        )
        repo = self._standard_repo()
        gw = self._standard_onboarding_gateway()
        gw.save_uploaded_chat_wardrobe_item.return_value = {
            "id": "w-anchor", "title": "White Shirt",
            "garment_category": "top", "garment_subtype": "shirt",
            "primary_color": "white", "occasion_fit": "smart_casual",
        }
        gw.get_wardrobe_items.return_value = []
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
        fake_plan = RecommendationPlan(
            plan_type="paired_only", retrieval_count=12,
            directions=[DirectionSpec(
                direction_id="A", direction_type="paired", label="Pairing",
                queries=[QuerySpec(query_id="A1", role="bottom", hard_filters={}, query_document="trousers to pair with white shirt")],
            )],
            resolved_context=ResolvedContextBlock(occasion_signal="smart_casual", formality_hint="smart_casual"),
        )
        with patch("agentic_application.orchestrator.ApplicationCatalogRetrievalGateway") as _gw_cls, \
             patch("agentic_application.orchestrator.OutfitArchitect") as architect_cls, \
             patch("agentic_application.orchestrator.CopilotPlanner", return_value=planner_mock):
            architect_cls.return_value.plan.return_value = fake_plan
            orchestrator = AgenticOrchestrator(repo=repo, onboarding_gateway=gw, config=Mock())
            orchestrator.catalog_search_agent.search = Mock(return_value=[])
            orchestrator.outfit_assembler.assemble = Mock(return_value=[])
            orchestrator.outfit_evaluator.evaluate = Mock(return_value=[])
            orchestrator.response_formatter.format = Mock(
                return_value=RecommendationResponse(
                    message="Here are pairing options for your shirt.",
                    outfits=[OutfitCard(rank=1, title="Smart Pairing", items=[])],
                    follow_up_suggestions=["Show me more"],
                    metadata={"answer_source": "catalog_pipeline", "primary_intent": Intent.PAIRING_REQUEST},
                )
            )
            result = orchestrator.process_turn(
                conversation_id="c1", external_user_id="user-1",
                message="Find me a perfect outfit with this shirt.",
                image_data="data:image/png;base64,AAAA",
            )

        # Architect MUST be called (full pipeline, not short-circuited)
        architect_cls.return_value.plan.assert_called_once()
        self.assertEqual(Intent.PAIRING_REQUEST, result["metadata"]["primary_intent"])
        self.assertIn("pairing_request_override", result["metadata"]["intent_reason_codes"])

    def test_pairing_override_uses_previous_attached_garment_context_when_no_new_image(self):
        from agentic_application.schemas import (
            CopilotPlanResult, CopilotResolvedContext, CopilotActionParameters,
            RecommendationPlan, DirectionSpec, QuerySpec, ResolvedContextBlock,
            OutfitCard, RecommendationResponse,
        )
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
        fake_plan = RecommendationPlan(
            plan_type="paired_only", retrieval_count=12,
            directions=[DirectionSpec(
                direction_id="A", direction_type="paired", label="Pairing",
                queries=[QuerySpec(query_id="A1", role="shoe", hard_filters={}, query_document="shoes for date night smart casual")],
            )],
            resolved_context=ResolvedContextBlock(occasion_signal="date_night", formality_hint="smart_casual"),
        )
        with patch("agentic_application.orchestrator.ApplicationCatalogRetrievalGateway") as _gw_cls, \
             patch("agentic_application.orchestrator.OutfitArchitect") as architect_cls, \
             patch("agentic_application.orchestrator.CopilotPlanner", return_value=planner_mock):
            architect_cls.return_value.plan.return_value = fake_plan
            orchestrator = AgenticOrchestrator(repo=repo, onboarding_gateway=gw, config=Mock())
            orchestrator.catalog_search_agent.search = Mock(return_value=[])
            orchestrator.outfit_assembler.assemble = Mock(return_value=[])
            orchestrator.outfit_evaluator.evaluate = Mock(return_value=[])
            orchestrator.response_formatter.format = Mock(
                return_value=RecommendationResponse(
                    message="Here are pairing options.",
                    outfits=[OutfitCard(rank=1, title="Date Night Pairing", items=[])],
                    follow_up_suggestions=["Show me more"],
                    metadata={"answer_source": "catalog_pipeline", "primary_intent": Intent.PAIRING_REQUEST},
                )
            )
            result = orchestrator.process_turn(
                conversation_id="c1",
                external_user_id="user-1",
                message="What shoes would work best with this?",
            )

        # Architect MUST be called (full pipeline, not short-circuited)
        architect_cls.return_value.plan.assert_called_once()
        self.assertEqual(Intent.PAIRING_REQUEST, result["metadata"]["primary_intent"])

    def test_catalog_garment_image_pairing_runs_full_pipeline(self):
        """Catalog image pairing now runs full pipeline (architect → search → evaluate → tryon)."""
        from agentic_application.schemas import (
            CopilotPlanResult, CopilotResolvedContext, CopilotActionParameters,
            RecommendationPlan, DirectionSpec, QuerySpec, ResolvedContextBlock,
            OutfitCard, RecommendationResponse,
        )
        repo = self._standard_repo()
        gw = self._standard_onboarding_gateway()
        gw.save_uploaded_chat_wardrobe_item.return_value = {
            "id": "img-anchor", "title": "White Shirt",
            "garment_category": "top", "garment_subtype": "shirt",
            "primary_color": "white", "occasion_fit": "smart_casual",
        }
        gw.get_wardrobe_items.return_value = []
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
        fake_plan = RecommendationPlan(
            plan_type="paired_only", retrieval_count=12,
            directions=[DirectionSpec(
                direction_id="A", direction_type="paired", label="Catalog pairing",
                queries=[QuerySpec(query_id="A1", role="bottom", hard_filters={}, query_document="trousers for smart casual")],
            )],
            resolved_context=ResolvedContextBlock(occasion_signal="smart_casual"),
        )
        with patch("agentic_application.orchestrator.ApplicationCatalogRetrievalGateway") as _gw_cls, \
             patch("agentic_application.orchestrator.OutfitArchitect") as architect_cls, \
             patch("agentic_application.orchestrator.CopilotPlanner", return_value=planner_mock):
            architect_cls.return_value.plan.return_value = fake_plan
            orchestrator = AgenticOrchestrator(repo=repo, onboarding_gateway=gw, config=Mock())
            orchestrator.catalog_search_agent.search = Mock(return_value=[])
            orchestrator.outfit_assembler.assemble = Mock(return_value=[])
            orchestrator.outfit_evaluator.evaluate = Mock(return_value=[])
            orchestrator.response_formatter.format = Mock(
                return_value=RecommendationResponse(
                    message="Here are catalog pairings for your shirt.",
                    outfits=[OutfitCard(rank=1, title="Catalog Pairing", items=[])],
                    follow_up_suggestions=["Show me more"],
                    metadata={"answer_source": "catalog_pipeline", "primary_intent": Intent.PAIRING_REQUEST},
                )
            )
            result = orchestrator.process_turn(
                conversation_id="c1", external_user_id="user-1",
                message="Pair this from the catalog for smart casual",
                image_data="data:image/png;base64,AAAA",
            )

        # Architect MUST be called (full pipeline)
        architect_cls.return_value.plan.assert_called_once()
        self.assertEqual(Intent.PAIRING_REQUEST, result["metadata"]["primary_intent"])

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
        orchestrator.visual_evaluator.evaluate_candidate.return_value = EvaluatedRecommendation(
            candidate_id='outfit-check-1',
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
            classic_pct=78,
            dramatic_pct=20,
            romantic_pct=32,
            natural_pct=44,
            minimalist_pct=60,
            creative_pct=18,
            sporty_pct=12,
            edgy_pct=10,
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

    def test_rate_my_outfit_routes_to_outfit_check_handler(self):
        from agentic_application.schemas import CopilotPlanResult, CopilotResolvedContext, CopilotActionParameters
        repo = self._standard_repo()
        gw = self._standard_onboarding_gateway()
        planner_mock = Mock()
        planner_mock.plan.return_value = CopilotPlanResult(
            intent=Intent.OUTFIT_CHECK,
            intent_confidence=0.95,
            action=Action.RUN_OUTFIT_CHECK,
            context_sufficient=True,
            assistant_message="Let me take a look at your outfit.",
            follow_up_suggestions=["Show me more"],
            resolved_context=CopilotResolvedContext(
                occasion_signal="dinner",
                style_goal=Intent.OUTFIT_CHECK,
            ),
            action_parameters=CopilotActionParameters(),
        )
        orchestrator = self._build_orchestrator(repo, gw, planner_mock)
        orchestrator.visual_evaluator.evaluate_candidate.return_value = EvaluatedRecommendation(
            candidate_id='outfit-check-1',
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
        )

        result = orchestrator.process_turn(
            conversation_id="c1",
            external_user_id="user-1",
            message="Rate my outfit for dinner tonight",
        )

        self.assertEqual(Intent.OUTFIT_CHECK, result["metadata"]["primary_intent"])
        self.assertEqual(Intent.OUTFIT_CHECK, repo.finalize_turn.call_args.kwargs["resolved_context"]["handler"])

    def test_planner_garment_evaluation_runs_tryon_visual_eval_pipeline(self):
        """Phase 12B: garment_evaluation runs tryon → visual evaluator →
        formatter on an uploaded garment photo, with the deterministic
        purchase verdict gated by `purchase_intent`. The merged intent
        absorbs shopping_decision + garment_on_me_request + virtual_tryon_request."""
        from agentic_application.schemas import CopilotPlanResult, CopilotResolvedContext, CopilotActionParameters
        repo = self._standard_repo()
        gw = self._standard_onboarding_gateway()
        gw.save_uploaded_chat_wardrobe_item.return_value = {
            "id": "garment-1",
            "image_path": "/tmp/garment.jpg",
            "garment_category": "top",
            "garment_subtype": "shirt",
            "title": "Olive Linen Shirt",
            "primary_color": "olive",
            "formality_level": "smart_casual",
        }
        gw.get_wardrobe_items.return_value = []
        gw.get_person_image_path.return_value = "/tmp/person.jpg"
        planner_mock = Mock()
        planner_mock.plan.return_value = CopilotPlanResult(
            intent=Intent.GARMENT_EVALUATION,
            intent_confidence=0.96,
            action=Action.RUN_GARMENT_EVALUATION,
            context_sufficient=True,
            assistant_message="Let me try this on you and tell you if it works.",
            follow_up_suggestions=["What goes with this?", "Show me alternatives"],
            resolved_context=CopilotResolvedContext(
                occasion_signal=None,
                style_goal=Intent.GARMENT_EVALUATION,
            ),
            action_parameters=CopilotActionParameters(purchase_intent=True),
        )
        orchestrator = self._build_orchestrator(repo, gw, planner_mock)
        orchestrator.tryon_service.generate_tryon = Mock(return_value={
            "success": True,
            "image_base64": "iVBORw0KGgo=",  # 1×1 PNG header bytes
            "mime_type": "image/png",
        })
        orchestrator.tryon_quality_gate.evaluate = Mock(return_value={
            "passed": True,
            "quality_score_pct": 88,
        })
        orchestrator.visual_evaluator.evaluate_candidate.return_value = EvaluatedRecommendation(
            candidate_id="garment-eval-1",
            overall_verdict="great_choice",
            overall_note="This olive shirt sits well against your Autumn palette and frame.",
            body_harmony_pct=82,
            color_suitability_pct=88,
            style_fit_pct=80,
            pairing_coherence_pct=75,
            occasion_pct=78,
            weather_time_pct=72,
            strengths=["The color reads strong against your warm tones."],
            improvements=[],
        )

        result = orchestrator.process_turn(
            conversation_id="c1",
            external_user_id="user-1",
            message="Should I buy this?",
            image_data="data:image/jpeg;base64,/9j/4AAQ",
        )

        # Intent classification is preserved as garment_evaluation
        self.assertEqual(Intent.GARMENT_EVALUATION, result["metadata"]["primary_intent"])
        self.assertEqual("garment_evaluation_handler", result["metadata"]["answer_source"])
        # The visual evaluator was actually called
        orchestrator.visual_evaluator.evaluate_candidate.assert_called_once()
        # purchase_intent=True → verdict block populated by deterministic formatter logic
        self.assertEqual(True, result["metadata"]["garment_evaluation"]["purchase_intent"])
        self.assertIn(result["metadata"]["garment_evaluation"]["verdict"], {"buy", "skip", "conditional"})
        # Single OutfitCard returned with all 9 dim scores
        self.assertEqual(1, len(result["outfits"]))
        self.assertEqual(82, result["outfits"][0]["body_harmony_pct"])
        self.assertEqual(72, result["outfits"][0]["weather_time_pct"])

    def test_garment_evaluation_no_image_returns_clarification(self):
        """When the user's garment_evaluation request has no attached image,
        the handler should return an ask_clarification asking for the photo
        rather than running the visual evaluator on nothing."""
        from agentic_application.schemas import CopilotPlanResult, CopilotResolvedContext, CopilotActionParameters
        repo = self._standard_repo()
        gw = self._standard_onboarding_gateway()
        gw.get_person_image_path.return_value = "/tmp/person.jpg"
        planner_mock = Mock()
        planner_mock.plan.return_value = CopilotPlanResult(
            intent=Intent.GARMENT_EVALUATION,
            intent_confidence=0.95,
            action=Action.RUN_GARMENT_EVALUATION,
            context_sufficient=True,
            assistant_message="",
            follow_up_suggestions=[],
            resolved_context=CopilotResolvedContext(),
            action_parameters=CopilotActionParameters(purchase_intent=False),
        )
        orchestrator = self._build_orchestrator(repo, gw, planner_mock)
        result = orchestrator.process_turn(
            conversation_id="c1",
            external_user_id="user-1",
            message="Would this suit me?",
        )
        self.assertEqual("clarification", result["response_type"])
        self.assertIn("Upload a photo", result["assistant_message"])
        # Visual evaluator must not run when there's nothing to evaluate
        orchestrator.visual_evaluator.evaluate_candidate.assert_not_called()

    def test_garment_evaluation_strong_wardrobe_overlap_drives_skip_verdict(self):
        """When the user has a near-duplicate of the candidate piece,
        the deterministic verdict computation should override score-based
        ratings and produce a skip recommendation regardless of how high
        the visual evaluator scored the piece."""
        from agentic_application.schemas import CopilotPlanResult, CopilotResolvedContext, CopilotActionParameters
        repo = self._standard_repo()
        gw = self._standard_onboarding_gateway()
        # User already owns an olive shirt — duplicate of the uploaded piece
        gw.get_wardrobe_items.return_value = [
            {
                "id": "w-olive-shirt",
                "title": "Olive Linen Shirt",
                "garment_category": "top",
                "garment_subtype": "shirt",
                "primary_color": "olive",
                "formality_level": "smart_casual",
            }
        ]
        gw.save_uploaded_chat_wardrobe_item.return_value = {
            "id": "garment-2",
            "image_path": "/tmp/garment.jpg",
            "garment_category": "top",
            "garment_subtype": "shirt",
            "title": "Olive Linen Shirt",
            "primary_color": "olive",
            "formality_level": "smart_casual",
        }
        gw.get_person_image_path.return_value = "/tmp/person.jpg"
        planner_mock = Mock()
        planner_mock.plan.return_value = CopilotPlanResult(
            intent=Intent.GARMENT_EVALUATION,
            intent_confidence=0.96,
            action=Action.RUN_GARMENT_EVALUATION,
            context_sufficient=True,
            assistant_message="Let me try this on you.",
            follow_up_suggestions=[],
            resolved_context=CopilotResolvedContext(),
            action_parameters=CopilotActionParameters(purchase_intent=True),
        )
        orchestrator = self._build_orchestrator(repo, gw, planner_mock)
        orchestrator.tryon_service.generate_tryon = Mock(return_value={
            "success": True,
            "image_base64": "iVBORw0KGgo=",
            "mime_type": "image/png",
        })
        orchestrator.tryon_quality_gate.evaluate = Mock(return_value={"passed": True, "quality_score_pct": 90})
        orchestrator.visual_evaluator.evaluate_candidate.return_value = EvaluatedRecommendation(
            candidate_id="garment-eval-1",
            overall_verdict="great_choice",
            overall_note="The piece is a great fit for your palette.",
            body_harmony_pct=92,
            color_suitability_pct=95,
            style_fit_pct=88,
            occasion_pct=90,
            weather_time_pct=85,
            pairing_coherence_pct=80,
        )

        result = orchestrator.process_turn(
            conversation_id="c1",
            external_user_id="user-1",
            message="Should I buy this?",
            image_data="data:image/jpeg;base64,/9j/4AAQ",
        )

        eval_meta = result["metadata"]["garment_evaluation"]
        # Even with high scores, the duplicate triggers skip
        self.assertEqual("skip", eval_meta["verdict"])
        self.assertEqual("strong", eval_meta["wardrobe_overlap"]["overlap_level"])
        self.assertTrue(eval_meta["wardrobe_overlap"]["has_duplicate"])
        self.assertIn("already has", result["assistant_message"])

    def test_garment_evaluation_purchase_intent_false_suppresses_verdict(self):
        """purchase_intent=False (suitability framing) should NOT produce a
        buy/skip verdict even if all scores would otherwise pass thresholds."""
        from agentic_application.schemas import CopilotPlanResult, CopilotResolvedContext, CopilotActionParameters
        repo = self._standard_repo()
        gw = self._standard_onboarding_gateway()
        gw.get_wardrobe_items.return_value = []
        gw.save_uploaded_chat_wardrobe_item.return_value = {
            "id": "garment-3",
            "image_path": "/tmp/garment.jpg",
            "garment_category": "top",
            "title": "Cream Sweater",
            "primary_color": "cream",
        }
        gw.get_person_image_path.return_value = "/tmp/person.jpg"
        planner_mock = Mock()
        planner_mock.plan.return_value = CopilotPlanResult(
            intent=Intent.GARMENT_EVALUATION,
            intent_confidence=0.9,
            action=Action.RUN_GARMENT_EVALUATION,
            context_sufficient=True,
            assistant_message="Let me see how this looks on you.",
            follow_up_suggestions=[],
            resolved_context=CopilotResolvedContext(),
            action_parameters=CopilotActionParameters(purchase_intent=False),
        )
        orchestrator = self._build_orchestrator(repo, gw, planner_mock)
        orchestrator.tryon_service.generate_tryon = Mock(return_value={
            "success": True,
            "image_base64": "iVBORw0KGgo=",
            "mime_type": "image/png",
        })
        orchestrator.tryon_quality_gate.evaluate = Mock(return_value={"passed": True, "quality_score_pct": 88})
        orchestrator.visual_evaluator.evaluate_candidate.return_value = EvaluatedRecommendation(
            candidate_id="garment-eval-1",
            overall_verdict="great_choice",
            overall_note="This sweater looks lovely on you.",
            body_harmony_pct=90,
            color_suitability_pct=92,
            style_fit_pct=88,
            occasion_pct=85,
            weather_time_pct=80,
        )

        result = orchestrator.process_turn(
            conversation_id="c1",
            external_user_id="user-1",
            message="Would this suit me?",
            image_data="data:image/jpeg;base64,/9j/4AAQ",
        )

        eval_meta = result["metadata"]["garment_evaluation"]
        self.assertEqual(False, eval_meta["purchase_intent"])
        # Verdict should NOT be populated when purchase_intent=False
        self.assertIsNone(eval_meta["verdict"])
        # Verdict label phrases must NOT appear in the assistant message
        self.assertNotIn("Buy it", result["assistant_message"])
        self.assertNotIn("I'd skip it", result["assistant_message"])

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
        orchestrator.visual_evaluator.evaluate_candidate.return_value = EvaluatedRecommendation(
            candidate_id='outfit-check-1',
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

    def test_planner_pairing_request_uses_wardrobe_first_pairing_handler(self):
        from agentic_application.schemas import (
            CopilotPlanResult, CopilotResolvedContext, CopilotActionParameters,
            RecommendationPlan, DirectionSpec, QuerySpec, ResolvedContextBlock,
            OutfitCard, RecommendationResponse,
        )
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
        fake_plan = RecommendationPlan(
            plan_type="paired_only", retrieval_count=12,
            directions=[DirectionSpec(
                direction_id="A", direction_type="paired", label="Blazer Pairing",
                queries=[QuerySpec(query_id="A1", role="bottom", hard_filters={}, query_document="trousers to pair with navy blazer")],
            )],
            resolved_context=ResolvedContextBlock(occasion_signal="office", formality_hint="smart_casual"),
        )
        with patch("agentic_application.orchestrator.ApplicationCatalogRetrievalGateway") as _gw_cls, \
             patch("agentic_application.orchestrator.OutfitArchitect") as architect_cls, \
             patch("agentic_application.orchestrator.CopilotPlanner", return_value=planner_mock):
            architect_cls.return_value.plan.return_value = fake_plan
            orchestrator = AgenticOrchestrator(repo=repo, onboarding_gateway=gw, config=Mock())
            orchestrator.catalog_search_agent.search = Mock(return_value=[])
            orchestrator.outfit_assembler.assemble = Mock(return_value=[])
            orchestrator.outfit_evaluator.evaluate = Mock(return_value=[])
            orchestrator.response_formatter.format = Mock(
                return_value=RecommendationResponse(
                    message="Here are pairing options for your blazer.",
                    outfits=[OutfitCard(rank=1, title="Blazer Pairing", items=[])],
                    follow_up_suggestions=["Show me more"],
                    metadata={"answer_source": "catalog_pipeline", "primary_intent": Intent.PAIRING_REQUEST},
                )
            )
            result = orchestrator.process_turn(
                conversation_id="c1",
                external_user_id="user-1",
                message="What goes with my navy blazer?",
            )

        # Architect MUST be called (full pipeline, not short-circuited)
        architect_cls.return_value.plan.assert_called_once()
        self.assertEqual(Intent.PAIRING_REQUEST, result["metadata"]["primary_intent"])

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
        orchestrator.visual_evaluator.evaluate_candidate.return_value = EvaluatedRecommendation(
            candidate_id='outfit-check-1',
            overall_verdict="great_choice",
            overall_note="Great look.",
            body_harmony_pct=85, color_suitability_pct=80, style_fit_pct=82,
            pairing_coherence_pct=84, occasion_pct=88, overall_score_pct=84,
            strengths=["Balanced silhouette."],
            improvements=[],
            classic_pct=70,
            dramatic_pct=10,
            romantic_pct=10,
            natural_pct=10,
            minimalist_pct=0,
            creative_pct=0,
            sporty_pct=0,
            edgy_pct=0,
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
            eval_kwargs = orchestrator.visual_evaluator.evaluate_candidate.call_args.kwargs
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
        orchestrator.visual_evaluator.evaluate_candidate.return_value = EvaluatedRecommendation(
            candidate_id='outfit-check-1',
            overall_verdict="great_choice",
            overall_note="Great look.",
            body_harmony_pct=85, color_suitability_pct=80, style_fit_pct=82,
            pairing_coherence_pct=84, occasion_pct=88, overall_score_pct=84,
            strengths=["Balanced."],
            improvements=[],
            classic_pct=70,
            dramatic_pct=10,
            romantic_pct=10,
            natural_pct=10,
            minimalist_pct=0,
            creative_pct=0,
            sporty_pct=0,
            edgy_pct=0,
        )

        with patch("agentic_application.orchestrator.Thread") as mock_thread:
            result = orchestrator.process_turn(
                conversation_id="c1",
                external_user_id="user-1",
                message="Outfit check my navy blazer with trousers",
            )

            # No image → no background decomposition
            mock_thread.assert_not_called()


class Phase12BBuildingBlockTests(unittest.TestCase):
    """Phase 12B: unit tests for the new building blocks (Reranker,
    deterministic verdict, wardrobe overlap, versatility).

    These don't construct an orchestrator — they test the deterministic
    helpers in isolation so the test suite has fast, focused coverage of
    each new piece independent of LLM mocking."""

    def test_reranker_sorts_by_assembly_score_and_caps_to_pool_size(self):
        from agentic_application.agents.reranker import Reranker

        r = Reranker(final_top_n=3, pool_top_n=5)
        candidates = [
            OutfitCandidate(candidate_id=f"c{i}", direction_id="A", candidate_type="paired",
                           items=[], assembly_score=score)
            for i, score in enumerate([0.4, 0.9, 0.7, 0.5, 0.95, 0.6, 0.8])
        ]
        ranked = r.rerank(candidates)
        # Should keep top 5 in score order (0.95, 0.9, 0.8, 0.7, 0.6)
        self.assertEqual(5, len(ranked))
        self.assertEqual([0.95, 0.9, 0.8, 0.7, 0.6], [c.assembly_score for c in ranked])

    def test_reranker_with_explicit_limit_returns_top_n(self):
        from agentic_application.agents.reranker import Reranker

        r = Reranker(final_top_n=3, pool_top_n=5)
        candidates = [
            OutfitCandidate(candidate_id=f"c{i}", direction_id="A", candidate_type="paired",
                           items=[], assembly_score=score)
            for i, score in enumerate([0.5, 0.9, 0.7])
        ]
        ranked = r.rerank(candidates, limit=2)
        self.assertEqual(2, len(ranked))
        self.assertEqual(0.9, ranked[0].assembly_score)
        self.assertEqual(0.7, ranked[1].assembly_score)

    def test_reranker_rejects_invalid_top_n(self):
        from agentic_application.agents.reranker import Reranker

        with self.assertRaises(ValueError):
            Reranker(final_top_n=0, pool_top_n=5)
        with self.assertRaises(ValueError):
            Reranker(final_top_n=5, pool_top_n=3)

    def test_compute_purchase_verdict_strong_overlap_forces_skip(self):
        from agentic_application.orchestrator import AgenticOrchestrator

        ev = EvaluatedRecommendation(
            candidate_id="c1",
            body_harmony_pct=95, color_suitability_pct=95,
            style_fit_pct=95, occasion_pct=95, weather_time_pct=95,
        )
        verdict = AgenticOrchestrator._compute_purchase_verdict(
            evaluation=ev,
            wardrobe_overlap={"overlap_level": "strong", "has_duplicate": True, "duplicate_detail": "your olive shirt"},
        )
        self.assertEqual("skip", verdict)

    def test_compute_purchase_verdict_high_scores_become_buy(self):
        from agentic_application.orchestrator import AgenticOrchestrator

        ev = EvaluatedRecommendation(
            candidate_id="c1",
            body_harmony_pct=82, color_suitability_pct=85,
            style_fit_pct=78, occasion_pct=80, weather_time_pct=75,
        )
        verdict = AgenticOrchestrator._compute_purchase_verdict(
            evaluation=ev,
            wardrobe_overlap={"overlap_level": "none", "has_duplicate": False, "duplicate_detail": None},
        )
        self.assertEqual("buy", verdict)

    def test_compute_purchase_verdict_mid_scores_become_conditional(self):
        from agentic_application.orchestrator import AgenticOrchestrator

        ev = EvaluatedRecommendation(
            candidate_id="c1",
            body_harmony_pct=65, color_suitability_pct=68,
            style_fit_pct=60, occasion_pct=62, weather_time_pct=60,
        )
        verdict = AgenticOrchestrator._compute_purchase_verdict(
            evaluation=ev,
            wardrobe_overlap={"overlap_level": "none", "has_duplicate": False, "duplicate_detail": None},
        )
        self.assertEqual("conditional", verdict)

    def test_compute_purchase_verdict_low_scores_become_skip(self):
        from agentic_application.orchestrator import AgenticOrchestrator

        ev = EvaluatedRecommendation(
            candidate_id="c1",
            body_harmony_pct=40, color_suitability_pct=45,
            style_fit_pct=50, occasion_pct=42, weather_time_pct=38,
        )
        verdict = AgenticOrchestrator._compute_purchase_verdict(
            evaluation=ev,
            wardrobe_overlap={"overlap_level": "none", "has_duplicate": False, "duplicate_detail": None},
        )
        self.assertEqual("skip", verdict)

    def test_compute_wardrobe_overlap_detects_strong_match(self):
        from agentic_application.orchestrator import AgenticOrchestrator

        attached = {
            "garment_category": "top",
            "garment_subtype": "shirt",
            "primary_color": "olive",
            "title": "Olive Linen Shirt",
        }
        wardrobe = [
            {"garment_category": "top", "garment_subtype": "shirt", "primary_color": "olive", "title": "Olive Cotton Shirt"},
            {"garment_category": "bottom", "garment_subtype": "trouser", "primary_color": "navy", "title": "Navy Trouser"},
        ]
        result = AgenticOrchestrator._compute_wardrobe_overlap(
            attached_item=attached, wardrobe_items=wardrobe,
        )
        self.assertEqual("strong", result["overlap_level"])
        self.assertTrue(result["has_duplicate"])
        self.assertIn("Olive Cotton Shirt", result["duplicate_detail"])

    def test_compute_wardrobe_overlap_detects_moderate_match_on_category_only(self):
        from agentic_application.orchestrator import AgenticOrchestrator

        attached = {
            "garment_category": "top",
            "garment_subtype": "shirt",
            "primary_color": "olive",
            "title": "Olive Shirt",
        }
        wardrobe = [
            {"garment_category": "top", "garment_subtype": "shirt", "primary_color": "navy", "title": "Navy Shirt"},
        ]
        result = AgenticOrchestrator._compute_wardrobe_overlap(
            attached_item=attached, wardrobe_items=wardrobe,
        )
        self.assertEqual("moderate", result["overlap_level"])
        self.assertTrue(result["has_duplicate"])
        self.assertIn("different color", result["duplicate_detail"])

    def test_compute_wardrobe_overlap_returns_none_when_no_match(self):
        from agentic_application.orchestrator import AgenticOrchestrator

        attached = {"garment_category": "top", "primary_color": "olive", "title": "Olive Shirt"}
        wardrobe = [{"garment_category": "shoe", "primary_color": "tan", "title": "Tan Loafer"}]
        result = AgenticOrchestrator._compute_wardrobe_overlap(
            attached_item=attached, wardrobe_items=wardrobe,
        )
        self.assertEqual("none", result["overlap_level"])
        self.assertFalse(result["has_duplicate"])

    def test_compute_wardrobe_versatility_high_when_many_pairs(self):
        from agentic_application.orchestrator import AgenticOrchestrator

        attached = {"garment_category": "top", "formality_level": "smart_casual"}
        wardrobe = [
            {"garment_category": "bottom", "formality_level": "smart_casual"},
            {"garment_category": "bottom", "formality_level": "casual"},
            {"garment_category": "shoe", "formality_level": "smart_casual"},
            {"garment_category": "shoe", "formality_level": "smart_casual"},
            {"garment_category": "shoe", "formality_level": "casual"},
            {"garment_category": "bottom", "formality_level": "business_casual"},
        ]
        result = AgenticOrchestrator._compute_wardrobe_versatility(
            attached_item=attached, wardrobe_items=wardrobe,
        )
        self.assertEqual("high", result["rating"])
        self.assertGreaterEqual(result["compatible_count"], 5)

    def test_compute_wardrobe_versatility_none_when_unknown_category(self):
        from agentic_application.orchestrator import AgenticOrchestrator

        attached = {"garment_category": "scarf", "formality_level": "casual"}
        wardrobe = [{"garment_category": "top"}, {"garment_category": "bottom"}]
        result = AgenticOrchestrator._compute_wardrobe_versatility(
            attached_item=attached, wardrobe_items=wardrobe,
        )
        self.assertEqual("none", result["rating"])
        self.assertEqual(0, result["compatible_count"])

    # ── Phase 12B follow-ups (April 9 2026): contextual evaluation ──
    #
    # The visual evaluator must score 5 dimensions always and 4 dimensions
    # only when their gating condition is met. The 4 context-gated
    # dimensions (pairing_coherence_pct, occasion_pct, weather_time_pct,
    # specific_needs_pct) are nullable in the JSON schema and propagate
    # as None all the way through to the OutfitCard.
    # pairing_coherence_pct is intent-gated (null for garment_evaluation /
    # style_discovery / explanation_request); the other 3 are gated on
    # live_context inputs.

    def test_evaluator_omits_occasion_when_no_occasion_signal(self):
        """When the model returns null for occasion_pct (because the
        live_context had no occasion_signal), `_to_evaluated_recommendation`
        must preserve None on the EvaluatedRecommendation. Coercing it
        to 0 would re-introduce the phantom-default bug this fix is
        targeting."""
        from agentic_application.agents.visual_evaluator_agent import _to_evaluated_recommendation
        from agentic_application.schemas import OutfitCandidate

        candidate = OutfitCandidate(
            candidate_id="c1", direction_id="A", candidate_type="single_garment",
            items=[{"product_id": "p1", "title": "Jeans"}],
        )
        raw = {
            "candidate_id": "c1",
            "match_score": 0.74,
            "title": "Jeans",
            "reasoning": "ok",
            "body_note": "", "color_note": "", "style_note": "", "occasion_note": "",
            "body_harmony_pct": 80, "color_suitability_pct": 65, "style_fit_pct": 75,
            "risk_tolerance_pct": 85, "comfort_boundary_pct": 90, "pairing_coherence_pct": 78,
            "occasion_pct": None,
            "weather_time_pct": None,
            "specific_needs_pct": None,
            "classic_pct": 60, "dramatic_pct": 10, "romantic_pct": 5, "natural_pct": 40,
            "minimalist_pct": 70, "creative_pct": 5, "sporty_pct": 25, "edgy_pct": 15,
            "item_ids": ["p1"],
            "overall_verdict": "good_with_tweaks",
            "overall_note": "",
            "strengths": [],
            "improvements": [],
        }
        result = _to_evaluated_recommendation(raw, candidate)
        self.assertIsNone(result.occasion_pct)
        self.assertIsNone(result.weather_time_pct)
        self.assertIsNone(result.specific_needs_pct)
        # 5 always-evaluated dimensions still come through as ints
        self.assertEqual(80, result.body_harmony_pct)
        self.assertEqual(85, result.risk_tolerance_pct)
        self.assertEqual(90, result.comfort_boundary_pct)

    def test_evaluator_keeps_all_three_when_inputs_present(self):
        """When the model returns integer scores for the 3 live-context-gated
        dimensions (because live_context had occasion + weather + specific
        needs), they propagate through as integers, not None.
        pairing_coherence_pct is intent-gated and tested separately."""
        from agentic_application.agents.visual_evaluator_agent import _to_evaluated_recommendation
        from agentic_application.schemas import OutfitCandidate

        candidate = OutfitCandidate(
            candidate_id="c1", direction_id="A", candidate_type="paired",
            items=[{"product_id": "p1", "title": "Top"}],
        )
        raw = {
            "candidate_id": "c1",
            "match_score": 0.92,
            "title": "Office look",
            "reasoning": "ok",
            "body_note": "", "color_note": "", "style_note": "", "occasion_note": "",
            "body_harmony_pct": 85, "color_suitability_pct": 90, "style_fit_pct": 78,
            "risk_tolerance_pct": 80, "comfort_boundary_pct": 88, "pairing_coherence_pct": 82,
            "occasion_pct": 95,
            "weather_time_pct": 72,
            "specific_needs_pct": 70,
            "classic_pct": 75, "dramatic_pct": 20, "romantic_pct": 10, "natural_pct": 30,
            "minimalist_pct": 60, "creative_pct": 15, "sporty_pct": 5, "edgy_pct": 10,
            "item_ids": ["p1"],
            "overall_verdict": "",
            "overall_note": "",
            "strengths": [],
            "improvements": [],
        }
        result = _to_evaluated_recommendation(raw, candidate)
        self.assertEqual(95, result.occasion_pct)
        self.assertEqual(72, result.weather_time_pct)
        self.assertEqual(70, result.specific_needs_pct)

    def test_evaluator_handles_missing_context_gated_keys(self):
        """If the model omits the 4 context-gated keys entirely (rather
        than returning null), the parser still produces None — same
        behavior as explicit null. This is defensive: in case a future
        prompt revision moves to true omission rather than null."""
        from agentic_application.agents.visual_evaluator_agent import _to_evaluated_recommendation
        from agentic_application.schemas import OutfitCandidate

        candidate = OutfitCandidate(
            candidate_id="c1", direction_id="A", candidate_type="single_garment",
            items=[{"product_id": "p1", "title": "Jeans"}],
        )
        raw = {
            "candidate_id": "c1", "match_score": 0.6, "title": "x", "reasoning": "",
            "body_note": "", "color_note": "", "style_note": "", "occasion_note": "",
            "body_harmony_pct": 70, "color_suitability_pct": 70, "style_fit_pct": 70,
            "risk_tolerance_pct": 70, "comfort_boundary_pct": 70,
            # All 4 context-gated keys absent: pairing_coherence_pct,
            # occasion_pct, weather_time_pct, specific_needs_pct
            "classic_pct": 50, "dramatic_pct": 0, "romantic_pct": 0, "natural_pct": 0,
            "minimalist_pct": 50, "creative_pct": 0, "sporty_pct": 0, "edgy_pct": 0,
            "item_ids": ["p1"],
            "overall_verdict": "", "overall_note": "", "strengths": [], "improvements": [],
        }
        result = _to_evaluated_recommendation(raw, candidate)
        self.assertIsNone(result.pairing_coherence_pct)
        self.assertIsNone(result.occasion_pct)
        self.assertIsNone(result.weather_time_pct)
        self.assertIsNone(result.specific_needs_pct)

    def test_purchase_verdict_skips_none_dimensions(self):
        """`_compute_purchase_verdict` averages over only the dimensions
        that were actually evaluated. With occasion_pct=None and
        weather_time_pct=None, the average is over body+color+style only;
        the 3-dim average must be high enough to flip the verdict to
        'buy' even though the legacy 5-dim average (with synthetic 0s)
        would have skipped."""
        from agentic_application.orchestrator import AgenticOrchestrator
        from agentic_application.schemas import EvaluatedRecommendation

        # Body / color / style all 80 — strong scores. With Nones, the
        # 3-dim average is 80 → verdict "buy". Under the old code, the
        # 5-dim average was (80+80+80+0+0)/5 = 48 → "skip".
        eval_no_context = EvaluatedRecommendation(
            candidate_id="c1",
            body_harmony_pct=80, color_suitability_pct=80, style_fit_pct=80,
            risk_tolerance_pct=70, comfort_boundary_pct=70, pairing_coherence_pct=70,
            occasion_pct=None, weather_time_pct=None, specific_needs_pct=None,
        )
        verdict = AgenticOrchestrator._compute_purchase_verdict(
            evaluation=eval_no_context,
            wardrobe_overlap={"overlap_level": "none"},
        )
        self.assertEqual("buy", verdict)

    def test_purchase_verdict_with_full_context(self):
        """When occasion + weather are present, the average is over 5
        dimensions and reflects all of them."""
        from agentic_application.orchestrator import AgenticOrchestrator
        from agentic_application.schemas import EvaluatedRecommendation

        # 5-dim average = (80+80+80+50+50)/5 = 68 → "conditional"
        eval_full = EvaluatedRecommendation(
            candidate_id="c1",
            body_harmony_pct=80, color_suitability_pct=80, style_fit_pct=80,
            risk_tolerance_pct=70, comfort_boundary_pct=70, pairing_coherence_pct=70,
            occasion_pct=50, weather_time_pct=50, specific_needs_pct=70,
        )
        verdict = AgenticOrchestrator._compute_purchase_verdict(
            evaluation=eval_full,
            wardrobe_overlap={"overlap_level": "none"},
        )
        self.assertEqual("conditional", verdict)

    def test_outfit_card_serializes_none_dimensions(self):
        """The OutfitCard schema must accept None for the 4 context-gated
        fields and serialize them as null in JSON, so the frontend
        receives the signal to drop the radar slice."""
        import json
        from agentic_application.schemas import OutfitCard

        card = OutfitCard(
            rank=1,
            title="Test",
            body_harmony_pct=80, color_suitability_pct=70, style_fit_pct=75,
            risk_tolerance_pct=85, comfort_boundary_pct=90,
            occasion_pct=None, weather_time_pct=None, specific_needs_pct=None,
            pairing_coherence_pct=None,
        )
        payload = json.loads(card.model_dump_json())
        self.assertIsNone(payload["occasion_pct"])
        self.assertIsNone(payload["weather_time_pct"])
        self.assertIsNone(payload["specific_needs_pct"])
        self.assertIsNone(payload["pairing_coherence_pct"])
        self.assertEqual(80, payload["body_harmony_pct"])

    def test_evaluator_omits_pairing_for_garment_evaluation(self):
        """Phase 12B follow-up (April 9 2026): pairing_coherence_pct is
        intent-gated. For garment_evaluation / style_discovery /
        explanation_request the model should return null because there's
        no outfit being paired this turn. The parser must preserve None,
        not coerce to 0."""
        from agentic_application.agents.visual_evaluator_agent import _to_evaluated_recommendation
        from agentic_application.schemas import OutfitCandidate

        candidate = OutfitCandidate(
            candidate_id="c1", direction_id="A", candidate_type="single_garment",
            items=[{"product_id": "p1", "title": "Jeans"}],
        )
        raw = {
            "candidate_id": "c1", "match_score": 0.7, "title": "Jeans", "reasoning": "ok",
            "body_note": "", "color_note": "", "style_note": "", "occasion_note": "",
            "body_harmony_pct": 80, "color_suitability_pct": 70, "style_fit_pct": 75,
            "risk_tolerance_pct": 85, "comfort_boundary_pct": 90,
            "pairing_coherence_pct": None,  # ← intent-gated null for garment_evaluation
            "occasion_pct": None, "weather_time_pct": None, "specific_needs_pct": None,
            "classic_pct": 60, "dramatic_pct": 10, "romantic_pct": 5, "natural_pct": 40,
            "minimalist_pct": 70, "creative_pct": 5, "sporty_pct": 25, "edgy_pct": 15,
            "item_ids": ["p1"],
            "overall_verdict": "good_with_tweaks", "overall_note": "",
            "strengths": [], "improvements": [],
        }
        result = _to_evaluated_recommendation(raw, candidate)
        self.assertIsNone(result.pairing_coherence_pct)
        # The other always-evaluated dimensions still come through
        self.assertEqual(80, result.body_harmony_pct)
        self.assertEqual(85, result.risk_tolerance_pct)

    def test_evaluator_keeps_pairing_for_outfit_intents(self):
        """For occasion_recommendation / pairing_request / outfit_check
        the model returns an integer score for pairing_coherence_pct,
        and the parser preserves it."""
        from agentic_application.agents.visual_evaluator_agent import _to_evaluated_recommendation
        from agentic_application.schemas import OutfitCandidate

        candidate = OutfitCandidate(
            candidate_id="c1", direction_id="A", candidate_type="paired",
            items=[{"product_id": "p1", "title": "Top"}, {"product_id": "p2", "title": "Pant"}],
        )
        raw = {
            "candidate_id": "c1", "match_score": 0.85, "title": "Office look", "reasoning": "ok",
            "body_note": "", "color_note": "", "style_note": "", "occasion_note": "",
            "body_harmony_pct": 85, "color_suitability_pct": 90, "style_fit_pct": 78,
            "risk_tolerance_pct": 80, "comfort_boundary_pct": 88,
            "pairing_coherence_pct": 82,  # ← real score for a pairing intent
            "occasion_pct": 95, "weather_time_pct": 72, "specific_needs_pct": 70,
            "classic_pct": 75, "dramatic_pct": 20, "romantic_pct": 10, "natural_pct": 30,
            "minimalist_pct": 60, "creative_pct": 15, "sporty_pct": 5, "edgy_pct": 10,
            "item_ids": ["p1", "p2"],
            "overall_verdict": "", "overall_note": "",
            "strengths": [], "improvements": [],
        }
        result = _to_evaluated_recommendation(raw, candidate)
        self.assertEqual(82, result.pairing_coherence_pct)


class Phase12DAnchorAndEnrichmentTests(unittest.TestCase):
    """Phase 12D regression tests:
    - cross-outfit diversity exempts anchors
    - cross-outfit diversity still drops non-anchor duplicates
    - failed wardrobe enrichment surfaces a clarification (not silent
      generic recommendations)
    - the staging-case scenario from user_03026279ecd6 conv 721e1963 no
      longer reproduces (image upload → enriched anchor → pairing returns
      complementary items, not a self-echo)"""

    def test_diversity_pass_keeps_all_pairing_candidates_when_anchor_is_marked(self):
        """Pairing requests inject the user's anchor into every paired
        candidate. Without the is_anchor exemption, the diversity pass
        would drop all but the first candidate, collapsing pairing turns
        to a single outfit instead of 3."""
        from agentic_application.agents.outfit_assembler import OutfitAssembler

        anchor_id = "anchor_white_shirt"
        candidates = [
            OutfitCandidate(
                candidate_id=f"c{i}",
                direction_id="A",
                candidate_type="paired",
                items=[
                    {"product_id": anchor_id, "title": "White Shirt", "role": "top", "is_anchor": True},
                    {"product_id": f"trouser_{i}", "title": f"Trouser {i}", "role": "bottom"},
                ],
                assembly_score=0.9 - i * 0.05,
            )
            for i in range(3)
        ]
        result = OutfitAssembler._enforce_cross_outfit_diversity(candidates)
        self.assertEqual(3, len(result))
        # All 3 candidates carry the same anchor product
        for c in result:
            anchor_items = [item for item in c.items if item.get("is_anchor")]
            self.assertEqual(1, len(anchor_items))
            self.assertEqual(anchor_id, anchor_items[0]["product_id"])

    def test_diversity_pass_still_drops_non_anchor_duplicates(self):
        """The Phase 12D anchor exemption must NOT break the original
        cross-outfit diversity rule for non-anchor products. A shared
        non-anchor product across candidates should still cause the
        lower-scoring candidate to be dropped."""
        from agentic_application.agents.outfit_assembler import OutfitAssembler

        candidates = [
            OutfitCandidate(
                candidate_id="c1",
                direction_id="A",
                candidate_type="paired",
                items=[
                    {"product_id": "shared_top"},
                    {"product_id": "trouser_a"},
                ],
                assembly_score=0.9,
            ),
            OutfitCandidate(
                candidate_id="c2",
                direction_id="A",
                candidate_type="paired",
                items=[
                    {"product_id": "shared_top"},
                    {"product_id": "trouser_b"},
                ],
                assembly_score=0.85,
            ),
            OutfitCandidate(
                candidate_id="c3",
                direction_id="A",
                candidate_type="paired",
                items=[
                    {"product_id": "different_top"},
                    {"product_id": "trouser_c"},
                ],
                assembly_score=0.8,
            ),
        ]
        result = OutfitAssembler._enforce_cross_outfit_diversity(candidates)
        # c1 and c3 should survive; c2 dropped because of shared_top
        self.assertEqual(2, len(result))
        result_ids = {c.candidate_id for c in result}
        self.assertEqual({"c1", "c3"}, result_ids)

    def test_failed_enrichment_surfaces_clarification_for_pairing(self):
        """Phase 12D regression of the staging bug from
        user_03026279ecd6 conv 721e1963: when the upload's enrichment
        returns empty critical fields (vision API hiccup, malformed
        image, etc.), the orchestrator must NOT proceed to the pipeline
        with an empty-attribute anchor. It must surface a clarification
        asking the user to retry with a clearer photo."""
        from agentic_application.schemas import CopilotPlanResult, CopilotResolvedContext, CopilotActionParameters
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
            "derived_interpretations": {"SeasonalColorGroup": {"value": "Autumn"}},
        }
        gw.get_wardrobe_items.return_value = []
        gw.get_person_image_path.return_value = None
        # Simulate the staging bug: enrichment failed, the row was saved
        # but with empty critical fields and the new enrichment_status
        # marker.
        gw.save_uploaded_chat_wardrobe_item.return_value = {
            "id": "garment-broken",
            "image_path": "/tmp/garment.jpg",
            "title": "",
            "garment_category": "",
            "garment_subtype": "",
            "primary_color": "",
            "enrichment_status": "failed",
            "enrichment_error": "OpenAI API timeout",
        }
        planner_mock = Mock()
        planner_mock.plan.return_value = CopilotPlanResult(
            intent=Intent.PAIRING_REQUEST,
            intent_confidence=0.95,
            action=Action.RUN_RECOMMENDATION_PIPELINE,
            context_sufficient=True,
            assistant_message="",
            follow_up_suggestions=[],
            resolved_context=CopilotResolvedContext(),
            action_parameters=CopilotActionParameters(target_piece="this shirt"),
        )
        with patch("agentic_application.orchestrator.ApplicationCatalogRetrievalGateway"), \
             patch("agentic_application.orchestrator.OutfitArchitect") as architect_cls, \
             patch("agentic_application.orchestrator.OutfitCheckAgent"), \
             patch("agentic_application.orchestrator.VisualEvaluatorAgent"), \
             patch("agentic_application.orchestrator.StyleAdvisorAgent"), \
             patch("agentic_application.orchestrator.CopilotPlanner", return_value=planner_mock):
            orchestrator = AgenticOrchestrator(repo=repo, onboarding_gateway=gw, config=Mock())
            result = orchestrator.process_turn(
                conversation_id="c1",
                external_user_id="user-1",
                message="What goes with this shirt?",
                image_data="data:image/jpeg;base64,/9j/4AAQ",
            )

        # Architect MUST NOT have been called — we short-circuit before
        # the pipeline runs because the anchor is unenriched.
        architect_cls.return_value.plan.assert_not_called()
        # The clarification reason code is set
        self.assertIn(
            "wardrobe_enrichment_failed",
            result["metadata"]["intent_reason_codes"],
        )
        # User-facing message asks for a clearer photo
        self.assertIn("clearer", result["assistant_message"].lower())

    def test_garment_evaluation_proceeds_even_with_failed_enrichment(self):
        """garment_evaluation is exempt from the failed-enrichment guard
        because the visual evaluator works on the image bytes directly
        and doesn't need attribute enrichment."""
        from agentic_application.schemas import CopilotPlanResult, CopilotResolvedContext, CopilotActionParameters
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
            "derived_interpretations": {"SeasonalColorGroup": {"value": "Autumn"}},
        }
        gw.get_wardrobe_items.return_value = []
        gw.get_person_image_path.return_value = "/tmp/person.jpg"
        gw.save_uploaded_chat_wardrobe_item.return_value = {
            "id": "garment-broken-2",
            "image_path": "/tmp/garment.jpg",
            "title": "",
            "garment_category": "",
            "primary_color": "",
            "enrichment_status": "failed",
        }
        planner_mock = Mock()
        planner_mock.plan.return_value = CopilotPlanResult(
            intent=Intent.GARMENT_EVALUATION,
            intent_confidence=0.96,
            action=Action.RUN_GARMENT_EVALUATION,
            context_sufficient=True,
            assistant_message="",
            follow_up_suggestions=[],
            resolved_context=CopilotResolvedContext(),
            action_parameters=CopilotActionParameters(purchase_intent=False),
        )
        with patch("agentic_application.orchestrator.ApplicationCatalogRetrievalGateway"), \
             patch("agentic_application.orchestrator.OutfitArchitect"), \
             patch("agentic_application.orchestrator.OutfitCheckAgent"), \
             patch("agentic_application.orchestrator.VisualEvaluatorAgent"), \
             patch("agentic_application.orchestrator.StyleAdvisorAgent"), \
             patch("agentic_application.orchestrator.CopilotPlanner", return_value=planner_mock):
            orchestrator = AgenticOrchestrator(repo=repo, onboarding_gateway=gw, config=Mock())
            orchestrator.tryon_service.generate_tryon = Mock(return_value={
                "success": True,
                "image_base64": "iVBORw0KGgo=",
                "mime_type": "image/png",
            })
            orchestrator.tryon_quality_gate.evaluate = Mock(return_value={"passed": True, "quality_score_pct": 88})
            orchestrator.visual_evaluator.evaluate_candidate.return_value = EvaluatedRecommendation(
                candidate_id="garment-eval-1",
                overall_verdict="good_with_tweaks",
                overall_note="Honest assessment from the rendered image.",
                body_harmony_pct=78,
                color_suitability_pct=82,
                style_fit_pct=80,
                occasion_pct=75,
                weather_time_pct=70,
                pairing_coherence_pct=72,
            )
            result = orchestrator.process_turn(
                conversation_id="c1",
                external_user_id="user-1",
                message="Would this suit me?",
                image_data="data:image/jpeg;base64,/9j/4AAQ",
            )

        # garment_evaluation must NOT trigger the wardrobe_enrichment_failed override
        self.assertNotIn(
            "wardrobe_enrichment_failed",
            result["metadata"]["intent_reason_codes"],
        )
        # Visual evaluator should have been called (the image bytes are
        # all the agent needs)
        orchestrator.visual_evaluator.evaluate_candidate.assert_called_once()
        # Response is the garment_evaluation card, not a clarification
        self.assertEqual("recommendation", result["response_type"])
        self.assertEqual(1, len(result["outfits"]))

    def test_product_to_item_resolves_wardrobe_image_path_and_tags_source(self):
        """Phase 12D follow-up regression: a wardrobe row passed to
        ``_product_to_item`` (e.g. via the orchestrator's anchor injection
        for pairing requests) must resolve ``image_url`` from
        ``image_path`` and tag ``source="wardrobe"``. Without this, the
        try-on render path skips the wardrobe pullover when building
        ``garment_urls`` and Gemini hallucinates a stand-in garment from
        the prompt text instead of using the user's actual photo.
        Verified against staging turn 9dff6f7e-9146-4d66-a277-a835e484334d
        of user_03026279ecd6 where all 3 try-on outputs showed a
        plausible-but-not-the-user's chocolate brown sweater."""
        from agentic_application.agents.outfit_assembler import OutfitAssembler
        from agentic_application.schemas import RetrievedProduct

        wardrobe_row = {
            "id": "754d88f7-2b71-46b4-a018-37bc731673d4",
            "title": "Chocolate Brown Sweater",
            "image_url": "",
            "image_path": "data/onboarding/images/wardrobe/55213c9a.jpg",
            "garment_category": "top",
            "garment_subtype": "sweater",
            "primary_color": "chocolate_brown",
            "is_anchor": True,
        }
        anchor_product = RetrievedProduct(
            product_id=wardrobe_row["id"],
            similarity=1.0,
            metadata={},
            enriched_data=wardrobe_row,
        )
        item = OutfitAssembler._product_to_item(anchor_product, role="top")

        self.assertEqual(
            "data/onboarding/images/wardrobe/55213c9a.jpg",
            item["image_url"],
            "image_url must resolve from image_path so the try-on render path "
            "doesn't drop the wardrobe anchor",
        )
        self.assertEqual("wardrobe", item.get("source"))
        self.assertTrue(item.get("is_anchor"))
        self.assertEqual("top", item.get("role"))

    def test_product_to_item_keeps_catalog_source_for_catalog_rows(self):
        """The wardrobe-detection heuristic in ``_product_to_item`` must
        not mislabel real catalog rows. Catalog rows carry handle / store /
        images__0__src and should keep ``source`` unset (or "catalog"),
        which makes ``_detect_garment_source`` return "catalog"."""
        from agentic_application.agents.outfit_assembler import OutfitAssembler
        from agentic_application.schemas import RetrievedProduct

        catalog_row = {
            "id": "SHOWOFFFF_9856072188180_50510889910548",
            "title": "Brown Wide-Leg Trouser",
            "primary_image_url": "https://cdn.example.com/trouser.jpg",
            "handle": "brown-wide-leg-trouser",
            "store": "showofff",
            "garment_category": "bottom",
        }
        catalog_product = RetrievedProduct(
            product_id=catalog_row["id"],
            similarity=0.9,
            metadata={},
            enriched_data=catalog_row,
        )
        item = OutfitAssembler._product_to_item(catalog_product, role="bottom")

        self.assertEqual("https://cdn.example.com/trouser.jpg", item["image_url"])
        # Catalog rows should NOT be tagged source="wardrobe"
        self.assertNotEqual("wardrobe", item.get("source"))

    def test_diversity_pass_marks_anchor_via_product_to_item_chain(self):
        """End-to-end check that an anchor wardrobe row (built by the
        orchestrator's anchor injection) flows through ``_product_to_item``
        with the is_anchor flag intact, so the diversity pass exempts it.
        This is the data-flow piece between orchestrator anchor injection
        and the assembler's diversity rule."""
        from agentic_application.agents.outfit_assembler import OutfitAssembler
        from agentic_application.schemas import RetrievedProduct

        wardrobe_row = dict(
            id="anchor_wardrobe_pullover",
            title="Pullover",
            image_path="data/onboarding/images/wardrobe/abc.jpg",
            garment_category="top",
            is_anchor=True,
        )
        anchor_product = RetrievedProduct(
            product_id=wardrobe_row["id"],
            similarity=1.0,
            metadata={},
            enriched_data=wardrobe_row,
        )
        anchor_item = OutfitAssembler._product_to_item(anchor_product, role="top")
        # Build 3 paired candidates that all share the wardrobe anchor.
        candidates = [
            OutfitCandidate(
                candidate_id=f"c{i}",
                direction_id="A",
                candidate_type="paired",
                items=[
                    anchor_item,
                    {"product_id": f"trouser_{i}", "title": f"Trouser {i}", "role": "bottom"},
                ],
                assembly_score=0.9 - i * 0.05,
            )
            for i in range(3)
        ]
        result = OutfitAssembler._enforce_cross_outfit_diversity(candidates)
        # All 3 must survive — the anchor exemption requires is_anchor=True
        # to have made it through _product_to_item.
        self.assertEqual(3, len(result))

    def test_compute_wardrobe_overlap_excludes_attached_item_id(self):
        """Phase 12D follow-up regression: _compute_wardrobe_overlap must
        skip the attached item itself even if it appears in
        wardrobe_items (e.g. because the upload was persisted before the
        check ran). Without this, a self-match produces a false positive
        "your wardrobe already has X" line on the user's first upload of
        a piece they don't own."""
        from agentic_application.orchestrator import AgenticOrchestrator

        attached = {
            "id": "wardrobe-row-just-saved",
            "garment_category": "bottom",
            "garment_subtype": "jeans",
            "primary_color": "charcoal",
            "title": "Charcoal Jeans",
        }
        wardrobe = [
            # The just-saved row, identical to the upload — this should
            # be skipped, not matched.
            {
                "id": "wardrobe-row-just-saved",
                "garment_category": "bottom",
                "garment_subtype": "jeans",
                "primary_color": "charcoal",
                "title": "Charcoal Jeans",
            },
        ]
        result = AgenticOrchestrator._compute_wardrobe_overlap(
            attached_item=attached,
            wardrobe_items=wardrobe,
        )
        self.assertFalse(result["has_duplicate"])
        self.assertEqual("none", result["overlap_level"])
        self.assertIsNone(result["duplicate_detail"])

    def test_compute_wardrobe_overlap_still_finds_real_duplicates(self):
        """Sanity: a genuinely separate wardrobe row with the same
        category + subtype + color should still be reported as a
        duplicate. The Phase 12D follow-up exclusion only covers the
        attached item's OWN id."""
        from agentic_application.orchestrator import AgenticOrchestrator

        attached = {
            "id": "upload-pending",
            "garment_category": "bottom",
            "garment_subtype": "jeans",
            "primary_color": "charcoal",
            "title": "Charcoal Jeans",
        }
        wardrobe = [
            {
                "id": "old-wardrobe-row",
                "garment_category": "bottom",
                "garment_subtype": "jeans",
                "primary_color": "charcoal",
                "title": "Old Charcoal Jeans",
            },
        ]
        result = AgenticOrchestrator._compute_wardrobe_overlap(
            attached_item=attached,
            wardrobe_items=wardrobe,
        )
        self.assertTrue(result["has_duplicate"])
        self.assertEqual("strong", result["overlap_level"])

    def test_attached_item_to_outfit_item_uses_browser_safe_image_url(self):
        """Phase 12D follow-up regression: the PDP card thumbnail of an
        uploaded garment must use a URL the browser can fetch. Wardrobe
        rows store the file at a relative `image_path` (e.g.
        `data/onboarding/images/wardrobe/abc.jpg`); without the
        `_browser_safe_image_url` wrapper, the `<img>` tag tries to load
        the relative path as a URL and the thumbnail breaks."""
        from agentic_application.orchestrator import AgenticOrchestrator

        attached = {
            "id": "upload-1",
            "title": "Charcoal Jeans",
            "image_url": "",
            "image_path": "data/onboarding/images/wardrobe/abc123.jpg",
            "garment_category": "bottom",
        }
        item = AgenticOrchestrator._attached_item_to_outfit_item(attached)
        self.assertTrue(
            item["image_url"].startswith("/v1/onboarding/images/local?path="),
            f"expected browser-safe URL, got {item['image_url']!r}",
        )
        self.assertIn("data/onboarding/images/wardrobe/abc123.jpg", item["image_url"])

    def test_garment_evaluation_does_not_persist_uploaded_item(self):
        """Phase 12D follow-up regression: an upload paired with a
        `garment_evaluation` ("Should I buy this?") turn must NOT be
        written to user_wardrobe_items. The user is asking about a piece
        they don't own. Verifies the orchestrator calls
        save_uploaded_chat_wardrobe_item with persist=False and never
        promotes the pending dict to a real row."""
        from agentic_application.schemas import CopilotPlanResult, CopilotResolvedContext, CopilotActionParameters
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
            "derived_interpretations": {"SeasonalColorGroup": {"value": "Autumn"}},
        }
        gw.get_wardrobe_items.return_value = []
        gw.get_person_image_path.return_value = "/tmp/person.jpg"
        # The "pending" dict shape returned by save_uploaded_chat_wardrobe_item
        # when persist=False — note id=None and the _pending_persist marker.
        gw.save_uploaded_chat_wardrobe_item.return_value = {
            "id": None,
            "title": "Charcoal Jeans",
            "image_path": "data/onboarding/images/wardrobe/abc.jpg",
            "garment_category": "bottom",
            "garment_subtype": "jeans",
            "primary_color": "charcoal",
            "enrichment_status": "ok",
            "_pending_persist": True,
        }
        planner_mock = Mock()
        planner_mock.plan.return_value = CopilotPlanResult(
            intent=Intent.GARMENT_EVALUATION,
            intent_confidence=0.95,
            action=Action.RUN_GARMENT_EVALUATION,
            context_sufficient=True,
            assistant_message="",
            follow_up_suggestions=[],
            resolved_context=CopilotResolvedContext(),
            action_parameters=CopilotActionParameters(purchase_intent=True),
        )
        with patch("agentic_application.orchestrator.ApplicationCatalogRetrievalGateway"), \
             patch("agentic_application.orchestrator.OutfitArchitect"), \
             patch("agentic_application.orchestrator.OutfitCheckAgent"), \
             patch("agentic_application.orchestrator.VisualEvaluatorAgent") as ve_cls, \
             patch("agentic_application.orchestrator.StyleAdvisorAgent"), \
             patch("agentic_application.orchestrator.CopilotPlanner", return_value=planner_mock):
            ve_inst = ve_cls.return_value
            # Phase 12B follow-ups (April 9 2026): the orchestrator's
            # garment_evaluation OutfitCard plumbs through all 5 always-
            # evaluated dimensions plus the 4 context-gated ones. For a
            # garment_evaluation turn ("Should I buy these jeans?") with
            # no occasion / weather / specific needs, all 4 context-gated
            # dimensions are None — including pairing_coherence_pct,
            # which is intent-gated to null for garment_evaluation since
            # we're not pairing anything.
            ve_inst.evaluate_candidate.return_value = Mock(
                body_harmony_pct=80, color_suitability_pct=70, style_fit_pct=75,
                risk_tolerance_pct=85, comfort_boundary_pct=90,
                pairing_coherence_pct=None,
                occasion_pct=None, weather_time_pct=None, specific_needs_pct=None,
                classic_pct=60, dramatic_pct=10, romantic_pct=20, natural_pct=40,
                minimalist_pct=70, creative_pct=15, sporty_pct=10, edgy_pct=10,
                overall_note="These would work with caveats.",
                overall_verdict="good_with_tweaks",
                body_note="", color_note="", style_note="", occasion_note="",
                strengths=[], improvements=[], reasoning="",
            )
            orchestrator = AgenticOrchestrator(repo=repo, onboarding_gateway=gw, config=Mock())
            orchestrator.process_turn(
                conversation_id="c1",
                external_user_id="user-1",
                message="Should I buy these jeans?",
                image_data="data:image/jpeg;base64,/9j/4AAQ",
            )

        # Critical assertion: the orchestrator must have called the save
        # function with persist=False.
        save_call = gw.save_uploaded_chat_wardrobe_item.call_args
        self.assertIsNotNone(save_call)
        self.assertEqual(False, save_call.kwargs.get("persist"),
                         "garment_evaluation upload must be enriched without persisting")
        # And it must NEVER have called persist_pending_wardrobe_item.
        gw.persist_pending_wardrobe_item.assert_not_called()

    def test_pairing_request_persists_uploaded_item(self):
        """Phase 12D follow-up regression: pairing_request is one of the
        two intents allowed to write the upload to user_wardrobe_items
        (the other is outfit_check). Without persistence, the anchor
        injection in `_handle_planner_pipeline` has no real wardrobe row
        id to use as the anchor product_id."""
        from agentic_application.schemas import CopilotPlanResult, CopilotResolvedContext, CopilotActionParameters
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
            "derived_interpretations": {"SeasonalColorGroup": {"value": "Autumn"}},
        }
        gw.get_wardrobe_items.return_value = []
        gw.get_person_image_path.return_value = None
        gw.save_uploaded_chat_wardrobe_item.return_value = {
            "id": None,
            "title": "Pullover",
            "image_path": "data/onboarding/images/wardrobe/xyz.jpg",
            "garment_category": "top",
            "garment_subtype": "sweater",
            "primary_color": "brown",
            "enrichment_status": "ok",
            "_pending_persist": True,
        }
        gw.persist_pending_wardrobe_item.return_value = {
            "id": "real-row-uuid",
            "title": "Pullover",
            "image_path": "data/onboarding/images/wardrobe/xyz.jpg",
            "garment_category": "top",
            "garment_subtype": "sweater",
            "primary_color": "brown",
            "enrichment_status": "ok",
        }
        planner_mock = Mock()
        planner_mock.plan.return_value = CopilotPlanResult(
            intent=Intent.PAIRING_REQUEST,
            intent_confidence=0.95,
            action=Action.RUN_RECOMMENDATION_PIPELINE,
            context_sufficient=True,
            assistant_message="",
            follow_up_suggestions=[],
            resolved_context=CopilotResolvedContext(),
            action_parameters=CopilotActionParameters(target_piece="this pullover"),
        )
        with patch("agentic_application.orchestrator.ApplicationCatalogRetrievalGateway"), \
             patch("agentic_application.orchestrator.OutfitArchitect") as architect_cls, \
             patch("agentic_application.orchestrator.OutfitCheckAgent"), \
             patch("agentic_application.orchestrator.VisualEvaluatorAgent"), \
             patch("agentic_application.orchestrator.StyleAdvisorAgent"), \
             patch("agentic_application.orchestrator.CopilotPlanner", return_value=planner_mock):
            architect_cls.return_value.plan.side_effect = RuntimeError("stop after persist check")
            orchestrator = AgenticOrchestrator(repo=repo, onboarding_gateway=gw, config=Mock())
            try:
                orchestrator.process_turn(
                    conversation_id="c1",
                    external_user_id="user-1",
                    message="What goes with this?",
                    image_data="data:image/jpeg;base64,/9j/4AAQ",
                )
            except Exception:
                pass

        # The save must have been called with persist=False…
        save_call = gw.save_uploaded_chat_wardrobe_item.call_args
        self.assertEqual(False, save_call.kwargs.get("persist"))
        # …and the pending dict must have been promoted to a real row
        # because the planner classified the intent as pairing_request.
        gw.persist_pending_wardrobe_item.assert_called_once()


class Phase12EStageEmissionTests(unittest.TestCase):
    """Phase 12E end-to-end stage emission tests.

    These tests capture the orchestrator's stage_callback output and
    assert the canonical stage skeleton per intent. Locks in the Phase
    12 pipeline shapes so a future refactor that changes the order or
    skips a stage breaks the test loudly. Each test mocks the per-intent
    LLM agents but exercises the real dispatch + emit code path.

    The stages we care about (per intent):
    - validate_request, onboarding_gate, user_context, copilot_planner
      always run first.
    - occasion_recommendation / pairing_request: outfit_architect →
      catalog_search → outfit_assembly → reranker → visual_evaluation
      (or outfit_evaluation legacy) → response_formatting → virtual_tryon
    - garment_evaluation: no architect/assembler/search; just runs the
      handler-internal try-on + visual evaluator
    - outfit_check: no architect/assembler/search; visual evaluator on
      the user photo
    - style_discovery / explanation_request: validate → gate → planner →
      direct response handler (no pipeline stages)
    """

    @staticmethod
    def _capture_stages():
        """Returns a (callback, stages_list) tuple for use as stage_callback."""
        stages: List[Dict[str, str]] = []

        def callback(stage: str, detail: str, message: str) -> None:
            stages.append({"stage": stage, "detail": detail, "message": message})

        return callback, stages

    @staticmethod
    def _build_orchestrator_with_legacy_path(repo, gw, planner_mock):
        """Build an orchestrator that takes the legacy text evaluator path
        (no person photo) so the test doesn't need to mock try-on or the
        visual evaluator."""
        with patch("agentic_application.orchestrator.ApplicationCatalogRetrievalGateway"), \
             patch("agentic_application.orchestrator.OutfitArchitect"), \
             patch("agentic_application.orchestrator.OutfitCheckAgent"), \
             patch("agentic_application.orchestrator.VisualEvaluatorAgent"), \
             patch("agentic_application.orchestrator.StyleAdvisorAgent"), \
             patch("agentic_application.orchestrator.CopilotPlanner", return_value=planner_mock):
            return AgenticOrchestrator(repo=repo, onboarding_gateway=gw, config=Mock())

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

    @staticmethod
    def _standard_gateway_no_photo():
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
            "derived_interpretations": {"SeasonalColorGroup": {"value": "Autumn"}},
        }
        gw.get_wardrobe_items.return_value = []
        gw.get_person_image_path.return_value = None
        return gw

    def test_style_discovery_emits_lean_stage_skeleton(self):
        """style_discovery should emit only the entry stages plus the
        copilot_planner stage — no pipeline stages."""
        from agentic_application.schemas import CopilotPlanResult, CopilotResolvedContext, CopilotActionParameters
        repo = self._standard_repo()
        gw = self._standard_gateway_no_photo()
        planner_mock = Mock()
        planner_mock.plan.return_value = CopilotPlanResult(
            intent=Intent.STYLE_DISCOVERY,
            intent_confidence=0.95,
            action=Action.RESPOND_DIRECTLY,
            context_sufficient=True,
            assistant_message="",
            follow_up_suggestions=[],
            resolved_context=CopilotResolvedContext(style_goal=Intent.STYLE_DISCOVERY),
            action_parameters=CopilotActionParameters(),
        )
        orchestrator = self._build_orchestrator_with_legacy_path(repo, gw, planner_mock)
        callback, stages = self._capture_stages()
        orchestrator.process_turn(
            conversation_id="c1",
            external_user_id="user-1",
            message="What collar will look good on me?",
            stage_callback=callback,
        )

        stage_names = [s["stage"] for s in stages]
        # Entry stages always run
        self.assertIn("validate_request", stage_names)
        self.assertIn("onboarding_gate", stage_names)
        self.assertIn("user_context", stage_names)
        self.assertIn("copilot_planner", stage_names)
        # NO pipeline stages — style_discovery doesn't go near search/assemble/evaluate
        self.assertNotIn("outfit_architect", stage_names)
        self.assertNotIn("catalog_search", stage_names)
        self.assertNotIn("outfit_assembly", stage_names)
        self.assertNotIn("outfit_evaluation", stage_names)
        self.assertNotIn("visual_evaluation", stage_names)
        self.assertNotIn("virtual_tryon", stage_names)

    def test_explanation_request_emits_lean_stage_skeleton(self):
        """explanation_request should emit the same lean entry skeleton
        as style_discovery — no pipeline stages."""
        from agentic_application.schemas import CopilotPlanResult, CopilotResolvedContext, CopilotActionParameters
        repo = self._standard_repo()
        gw = self._standard_gateway_no_photo()
        planner_mock = Mock()
        planner_mock.plan.return_value = CopilotPlanResult(
            intent=Intent.EXPLANATION_REQUEST,
            intent_confidence=0.9,
            action=Action.RESPOND_DIRECTLY,
            context_sufficient=True,
            assistant_message="",
            follow_up_suggestions=[],
            resolved_context=CopilotResolvedContext(),
            action_parameters=CopilotActionParameters(),
        )
        orchestrator = self._build_orchestrator_with_legacy_path(repo, gw, planner_mock)
        callback, stages = self._capture_stages()
        orchestrator.process_turn(
            conversation_id="c1",
            external_user_id="user-1",
            message="Why did you recommend that?",
            stage_callback=callback,
        )

        stage_names = [s["stage"] for s in stages]
        self.assertIn("copilot_planner", stage_names)
        self.assertNotIn("outfit_architect", stage_names)
        self.assertNotIn("catalog_search", stage_names)
        self.assertNotIn("visual_evaluation", stage_names)

    def test_occasion_recommendation_legacy_path_emits_text_evaluator_stage(self):
        """When the user has no full-body photo, occasion_recommendation
        runs the legacy text evaluator path: architect → search →
        assemble → reranker → outfit_evaluation (legacy) → format. The
        visual_evaluation stage is NOT emitted."""
        from agentic_application.schemas import (
            CopilotPlanResult, CopilotResolvedContext, CopilotActionParameters,
            RecommendationPlan, DirectionSpec, QuerySpec, ResolvedContextBlock,
            RecommendationResponse,
        )
        repo = self._standard_repo()
        gw = self._standard_gateway_no_photo()
        # No wardrobe items so the wardrobe-first short circuit doesn't fire
        gw.get_wardrobe_items.return_value = []
        planner_mock = Mock()
        planner_mock.plan.return_value = CopilotPlanResult(
            intent=Intent.OCCASION_RECOMMENDATION,
            intent_confidence=0.95,
            action=Action.RUN_RECOMMENDATION_PIPELINE,
            context_sufficient=True,
            assistant_message="Let me put together options.",
            follow_up_suggestions=[],
            resolved_context=CopilotResolvedContext(
                occasion_signal="office",
                formality_hint="business_casual",
            ),
            action_parameters=CopilotActionParameters(),
        )
        orchestrator = self._build_orchestrator_with_legacy_path(repo, gw, planner_mock)
        # Architect, search, assembler, evaluator, formatter all mocked.
        orchestrator.outfit_architect.plan = Mock(return_value=RecommendationPlan(
            plan_type="paired_only",
            retrieval_count=12,
            directions=[DirectionSpec(
                direction_id="A",
                direction_type="paired",
                label="Office",
                queries=[QuerySpec(query_id="A1", role="top", hard_filters={}, query_document="office shirt")],
            )],
            resolved_context=ResolvedContextBlock(
                occasion_signal="office",
                formality_hint="business_casual",
            ),
        ))
        orchestrator.catalog_search_agent.search = Mock(return_value=[])
        orchestrator.outfit_assembler.assemble = Mock(return_value=[])
        orchestrator.outfit_evaluator.evaluate = Mock(return_value=[])
        orchestrator.response_formatter.format = Mock(
            return_value=RecommendationResponse(
                message="Here are some office options.",
                outfits=[],
                follow_up_suggestions=[],
                metadata={"answer_components": {"primary_source": "catalog", "catalog_item_count": 0, "wardrobe_item_count": 0}},
            )
        )

        callback, stages = self._capture_stages()
        orchestrator.process_turn(
            conversation_id="c1",
            external_user_id="user-1",
            message="What should I wear to the office tomorrow?",
            stage_callback=callback,
        )

        stage_names = [s["stage"] for s in stages]
        # Entry skeleton
        self.assertIn("copilot_planner", stage_names)
        # Pipeline stages in legacy text path
        self.assertIn("outfit_architect", stage_names)
        self.assertIn("catalog_search", stage_names)
        self.assertIn("outfit_assembly", stage_names)
        self.assertIn("reranker", stage_names)
        self.assertIn("outfit_evaluation", stage_names)
        self.assertIn("response_formatting", stage_names)
        # The visual_evaluation stage is NOT emitted because there's no person photo
        self.assertNotIn("visual_evaluation", stage_names)
        # Legacy path metadata records the evaluator path
        finalize_call = repo.finalize_turn.call_args
        self.assertIsNotNone(finalize_call)


if __name__ == "__main__":
    unittest.main()
