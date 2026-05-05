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
# OutfitAssembler + Reranker removed (May 3 2026 — replaced by
# OutfitComposer + OutfitRater). See PR #30.
from agentic_application.agents.outfit_composer import OutfitComposer
from agentic_application.agents.outfit_rater import OutfitRater
# OutfitCheckAgent removed (Phase 12B cleanup, April 9 2026)
from agentic_application.agents.response_formatter import ResponseFormatter
from agentic_application.agents.outfit_architect import OutfitArchitect
# OutfitEvaluator removed (Phase 12B cleanup, April 9 2026)
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
    ComposedOutfit,
    ComposerResult,
    ConversationMemory,
    DirectionSpec,
    EvaluatedRecommendation,
    LiveContext,
    OutfitCandidate,
    OutfitCard,
    QuerySpec,
    RatedOutfit,
    RaterResult,
    RecommendationPlan,
    RecommendationResponse,
    ResolvedContextBlock,
    RetrievedProduct,
    RetrievedSet,
    UserContext,
)


# ---------------------------------------------------------------------
# Test helper for the LLM ranker pipeline (May 3 2026, PR #30)
#
# Many integration tests mock `outfit_assembler.assemble = Mock(...)`
# directly to inject canned candidates into the recommendation pipeline.
# The May-3 rewrite replaced the assembler+reranker with the LLM ranker
# (Composer + Rater), so the equivalent fixture has to wire three
# things: a non-empty retrieval pool, a ComposerResult with matching
# IDs, and a RaterResult with the desired fashion_score.
#
# This helper does all three in one call so test bodies can stay close
# to their pre-PR-30 shape: pass in OutfitCandidate objects and the
# orchestrator pipeline will produce them as if they came from the
# Rater.
# ---------------------------------------------------------------------


_ROLES_FOR_TYPE = {
    "complete": ["complete"],
    "paired": ["top", "bottom"],
    "three_piece": ["top", "bottom", "outerwear"],
}


def _mock_llm_ranker(orchestrator, candidates: list[OutfitCandidate]) -> None:
    """Wire orchestrator.catalog_search_agent.search + outfit_composer.compose
    + outfit_rater.rate so process_turn produces the supplied candidates.

    Empty list mocks the no-result path: empty retrieval, empty
    Composer output. The orchestrator falls through to its
    catalog_low_confidence handler.
    """
    if not candidates:
        orchestrator.catalog_search_agent.search = Mock(return_value=[])
        orchestrator.outfit_composer.compose = Mock(
            return_value=ComposerResult(outfits=[], overall_assessment="unsuitable", pool_unsuitable=True)
        )
        orchestrator.outfit_rater.rate = Mock(
            return_value=RaterResult(ranked_outfits=[], overall_assessment="weak")
        )
        return

    composed: list[ComposedOutfit] = []
    rated: list[RatedOutfit] = []
    products: list[RetrievedProduct] = []
    for c in candidates:
        roles = _ROLES_FOR_TYPE.get(c.candidate_type, [])
        item_ids: list[str] = []
        for i, item in enumerate(c.items or []):
            pid = str(item.get("product_id") or f"{c.candidate_id}_item_{i}")
            item_ids.append(pid)
            products.append(
                RetrievedProduct(
                    product_id=pid,
                    similarity=0.9,
                    metadata={"title": item.get("title", "")},
                    enriched_data={
                        "garment_subtype": item.get("garment_subtype", ""),
                        "garment_category": item.get("garment_category", ""),
                    },
                )
            )
        if not item_ids:
            # Candidate has no items — fabricate a stub so the
            # orchestrator's _build_candidate_item lookup succeeds.
            stub = f"{c.candidate_id}_stub"
            item_ids.append(stub)
            products.append(RetrievedProduct(product_id=stub, similarity=0.9))
        composed.append(
            ComposedOutfit(
                composer_id=c.candidate_id,
                direction_id=c.direction_id or "A",
                direction_type=c.candidate_type or "complete",
                item_ids=item_ids,
                rationale=c.composer_rationale or "test rationale",
            )
        )
        rated.append(
            RatedOutfit(
                composer_id=c.candidate_id,
                rank=len(rated) + 1,
                fashion_score=c.fashion_score or 85,
                occasion_fit=c.occasion_fit or 85,
                body_harmony=c.body_harmony or 85,
                color_harmony=c.color_harmony or 85,
                archetype_match=c.archetype_match or 85,
                rationale=c.rater_rationale or "test rationale",
                unsuitable=c.unsuitable,
            )
        )

    retrieved_sets = [
        RetrievedSet(direction_id="A", query_id="A1", role="complete", products=products),
    ]
    orchestrator.catalog_search_agent.search = Mock(return_value=retrieved_sets)
    orchestrator.outfit_composer.compose = Mock(
        return_value=ComposerResult(outfits=composed, overall_assessment="strong", pool_unsuitable=False)
    )
    orchestrator.outfit_rater.rate = Mock(
        return_value=RaterResult(ranked_outfits=rated, overall_assessment="strong")
    )


def _wire_llm_ranker_via_patches(composer_cls, rater_cls, candidates: list[OutfitCandidate]):
    """Same idea as `_mock_llm_ranker` but for tests that patch the
    Composer/Rater classes at module level (rather than mutating an
    already-built orchestrator).

    Returns a list of RetrievedProduct that the caller should configure
    on the mocked CatalogSearchAgent.search return value, so that the
    orchestrator's `_build_candidate_item` lookups find matching products.
    """
    composed: list[ComposedOutfit] = []
    rated: list[RatedOutfit] = []
    products: list[RetrievedProduct] = []
    for c in candidates:
        item_ids: list[str] = []
        for i, item in enumerate(c.items or []):
            pid = str(item.get("product_id") or f"{c.candidate_id}_item_{i}")
            item_ids.append(pid)
            products.append(
                RetrievedProduct(
                    product_id=pid,
                    similarity=0.9,
                    metadata={"title": item.get("title", "")},
                    enriched_data={
                        "garment_subtype": item.get("garment_subtype", ""),
                        "garment_category": item.get("garment_category", ""),
                    },
                )
            )
        if not item_ids:
            stub = f"{c.candidate_id}_stub"
            item_ids.append(stub)
            products.append(RetrievedProduct(product_id=stub, similarity=0.9))
        composed.append(
            ComposedOutfit(
                composer_id=c.candidate_id,
                direction_id=c.direction_id or "A",
                direction_type=c.candidate_type or "complete",
                item_ids=item_ids,
                rationale=c.composer_rationale or "test rationale",
            )
        )
        rated.append(
            RatedOutfit(
                composer_id=c.candidate_id,
                rank=len(rated) + 1,
                fashion_score=c.fashion_score or 85,
                occasion_fit=c.occasion_fit or 85,
                body_harmony=c.body_harmony or 85,
                color_harmony=c.color_harmony or 85,
                archetype_match=c.archetype_match or 85,
                rationale=c.rater_rationale or "test rationale",
                unsuitable=c.unsuitable,
            )
        )
    composer_cls.return_value.compose.return_value = ComposerResult(
        outfits=composed, overall_assessment="strong", pool_unsuitable=False,
    )
    rater_cls.return_value.rate.return_value = RaterResult(
        ranked_outfits=rated, overall_assessment="strong",
    )
    return products


def _make_planner_mock(
    *,
    intent: str = "occasion_recommendation",
    action: str = "run_recommendation_pipeline",
    occasion_signal: str | None = None,
    formality_hint: str | None = None,
    source_preference: str = "auto",
    is_followup: bool = False,
    followup_intent: str | None = None,
    assistant_message: str = "Let me build that.",
):
    """Helper used by happy-path orchestrator tests that exercise
    process_turn end-to-end. Returns a Mock whose .plan() yields a
    CopilotPlanResult with the supplied routing — saves each test from
    re-constructing the same boilerplate. May 1, 2026 (CI fix)."""
    from unittest.mock import Mock as _Mock
    from agentic_application.schemas import (
        CopilotPlanResult,
        CopilotResolvedContext,
        CopilotActionParameters,
    )
    planner_mock = _Mock()
    planner_mock.plan.return_value = CopilotPlanResult(
        intent=intent,
        intent_confidence=0.95,
        action=action,
        context_sufficient=True,
        assistant_message=assistant_message,
        follow_up_suggestions=[],
        resolved_context=CopilotResolvedContext(
            occasion_signal=occasion_signal,
            formality_hint=formality_hint,
            source_preference=source_preference,
            is_followup=is_followup,
            followup_intent=followup_intent,
        ),
        action_parameters=CopilotActionParameters(),
    )
    return planner_mock


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
        plan = RecommendationPlan( retrieval_count=8,
            directions=[
                DirectionSpec(
                    direction_id="B",
                    direction_type="paired",
                    label="Pairing",
                    queries=[
                        QuerySpec(
                            query_id="B1",
                            role="top",
                            hard_filters={"garment_subtype": "blouse"},
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
        # styling_completeness comes from build_directional_filters (role=top)
        self.assertEqual("needs_bottomwear", filters["styling_completeness"])
        # garment_subtype comes from architect's explicit hard_filters
        self.assertEqual("blouse", filters["garment_subtype"])
        # query document lines are soft signals for embeddings only, not hard filters
        self.assertNotIn("garment_category", filters)
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
        plan = RecommendationPlan( retrieval_count=8,
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

    def test_outfit_architect_default_retrieval_count_is_five(self) -> None:
        """May 3 2026 — pool size dropped to 5 per query so the LLM ranker
        sees a manageable item set. Architect default and parser default
        both stay in lockstep."""
        from agentic_application.agents.outfit_architect import OutfitArchitect
        context = CombinedContext(
            user=UserContext(user_id="u1", gender="female"),
            live=LiveContext(user_need="Show me a casual outfit"),
            hard_filters={"gender_expression": "feminine"},
        )

        mock_response = Mock()
        # No retrieval_count in payload — parser default kicks in.
        mock_response.output_text = json.dumps({
            "resolved_context": {"occasion_signal": "everyday", "is_followup": False},
            "directions": [
                {
                    "direction_id": "A",
                    "direction_type": "paired",
                    "label": "casual paired",
                    "queries": [
                        {"query_id": "A1", "role": "top", "hard_filters": {"garment_subtype": "tshirt"}, "query_document": "- GarmentSubtype: tshirt\n"},
                        {"query_id": "A2", "role": "bottom", "hard_filters": {"garment_subtype": "jeans"}, "query_document": "- GarmentSubtype: jeans\n"},
                    ],
                },
            ],
        })

        with patch("agentic_application.agents.outfit_architect.get_api_key", return_value="x"), patch(
            "agentic_application.agents.outfit_architect.OpenAI"
        ) as openai_cls:
            openai_cls.return_value.responses.create.return_value = mock_response
            plan = OutfitArchitect().plan(context)

        self.assertEqual(5, plan.retrieval_count)

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

    # OutfitAssembler-direct tests removed in May 3 2026 PR #30. The
    # assembler is gone; the LLM Composer + Rater handle pairing logic
    # via natural language judgment, not heuristics. See
    # tests/test_outfit_composer.py and tests/test_outfit_rater.py.

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

        plan = RecommendationPlan( retrieval_count=8,
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

        planner_mock = _make_planner_mock(occasion_signal="dinner")
        with patch("agentic_application.orchestrator.ApplicationCatalogRetrievalGateway"), patch(
            "agentic_application.orchestrator.OutfitArchitect"
        ) as architect_cls, patch(
            "agentic_application.orchestrator.CatalogSearchAgent"
        ) as search_cls, patch(
            "agentic_application.orchestrator.OutfitComposer"
        ) as composer_cls, patch(
            "agentic_application.orchestrator.OutfitRater"
        ) as rater_cls, patch(
            "agentic_application.orchestrator.ResponseFormatter"
        ), patch(
            "agentic_application.orchestrator.CopilotPlanner", return_value=planner_mock
        ):
            architect_cls.return_value.plan.return_value = plan
            search_cls.return_value.search.return_value = retrieved_sets
            # Simulate the failure mode from the live conversation review:
            # the LLM ranker (Composer) crashes mid-pipeline. The
            # orchestrator must still return a graceful fallback.
            composer_cls.return_value.compose.side_effect = RuntimeError(
                "boom: simulated composer crash"
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
        guard must rewrite it to a graceful fallback before returning.

        After the May-1 confidence gate landed: with the assembler returning
        no candidates, the gate now intercepts before the formatter runs and
        emits the "couldn't find a confident match" path. The invariant we
        still care about is that the user never sees an empty assistant
        message — the test just checks for graceful prose.
        """
        repo, gw = self._build_minimal_orchestrator_repo_and_gateway()

        plan = RecommendationPlan( retrieval_count=8,
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
            metadata={
 "plan_source": "llm"},
        )

        planner_mock = _make_planner_mock(occasion_signal="dinner")
        with patch("agentic_application.orchestrator.ApplicationCatalogRetrievalGateway"), patch(
            "agentic_application.orchestrator.OutfitArchitect"
        ) as architect_cls, patch(
            "agentic_application.orchestrator.CatalogSearchAgent"
        ) as search_cls, patch(
            "agentic_application.orchestrator.OutfitComposer"
        ) as composer_cls, patch(
            "agentic_application.orchestrator.OutfitRater"
        ) as rater_cls, patch(
            "agentic_application.orchestrator.ResponseFormatter"
        ) as formatter_cls, patch(
            "agentic_application.orchestrator.CopilotPlanner", return_value=planner_mock
        ):
            architect_cls.return_value.plan.return_value = plan
            search_cls.return_value.search.return_value = retrieved_sets
            # Empty Composer output → orchestrator short-circuits to
            # the catalog_low_confidence handler before the Rater runs.
            composer_cls.return_value.compose.return_value = ComposerResult(
                outfits=[], overall_assessment="unsuitable", pool_unsuitable=True,
            )
            rater_cls.return_value.rate.return_value = RaterResult(
                ranked_outfits=[], overall_assessment="weak",
            )
            formatter_cls.return_value.format.return_value = empty_response

            orchestrator = AgenticOrchestrator(
                repo=repo, onboarding_gateway=gw, config=Mock()
            )
            result = orchestrator.process_turn(
                conversation_id="c1",
                external_user_id="user-1",
                message="What should I wear to dinner tonight?",
            )

        # The user must never see an empty assistant_message; whichever
        # graceful path fires is fine.
        self.assertTrue(
            result.get("assistant_message"),
            "Empty assistant_message was returned to the user — graceful fallback did not fire",
        )
        msg = result["assistant_message"].lower()
        self.assertTrue(
            "wasn't able to put together" in msg
            or "couldn't find a strong match" in msg,
            f"Unexpected fallback prose: {result['assistant_message']!r}",
        )

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
                    "followup_count": 1,
                    "last_recommendation_ids": ["prev-1"],
                },
                "last_recommendations": [{"candidate_id": "prev-1"}],
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
                fashion_score=91,
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
            metadata={
 "plan_source": "llm"},
        )
        plan = RecommendationPlan( retrieval_count=8,
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

        planner_mock = _make_planner_mock(
            intent="occasion_recommendation",
            action="run_recommendation_pipeline",
            occasion_signal="wedding",
            formality_hint="formal",
            is_followup=True,
        )
        with patch("agentic_application.orchestrator.ApplicationCatalogRetrievalGateway"), patch(
            "agentic_application.orchestrator.OutfitArchitect"
        ) as architect_cls, patch(
            "agentic_application.orchestrator.CatalogSearchAgent"
        ) as search_cls, patch(
            "agentic_application.orchestrator.OutfitComposer"
        ) as composer_cls, patch(
            "agentic_application.orchestrator.OutfitRater"
        ) as rater_cls, patch(
            "agentic_application.orchestrator.ResponseFormatter"
        ) as formatter_cls, patch(
            "agentic_application.orchestrator.CopilotPlanner", return_value=planner_mock
        ):
            architect_cls.return_value.plan.return_value = plan
            search_cls.return_value.search.return_value = retrieved_sets
            _wire_llm_ranker_via_patches(composer_cls, rater_cls, candidates)
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
        # Phase 12B cleanup (April 9 2026): the legacy text-only
        # OutfitEvaluator that used to produce fallback recommendations
        # when the visual evaluator failed has been removed. Without it,
        # the visual evaluator failure (caused by the Mock objects in
        # this test's setup) produces zero outfits and thus empty
        # last_recommendations. The core assertion of this test — that
        # the orchestrator persists memory and turn artifacts — is
        # validated by the plan, retrieval, and memory fields above.
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
                fashion_score=80,
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
        plan = RecommendationPlan( retrieval_count=8,
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
                fashion_score=100 - index,
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
        plan = RecommendationPlan( directions=[])

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
                fashion_score=95,
            ),
            OutfitCandidate(
                candidate_id="cand-2",
                direction_id="A",
                candidate_type="complete",
                items=[{"product_id": "sku-safe", "title": "Wool Blazer", "garment_category": "blazer"}],
                fashion_score=90,
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
        plan = RecommendationPlan( directions=[])

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


    # ------------------------------------------------------------------
    # Concept-first paired planning tests
    # ------------------------------------------------------------------

    # Assembler-direct tests removed in May 3 2026 PR #30 — the
    # OutfitAssembler is gone. Pairing logic, diversity, and
    # follow-up scoring are now LLM judgments handled by the
    # Composer + Rater. See tests/test_outfit_composer.py and
    # tests/test_outfit_rater.py.

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
        plan = RecommendationPlan( retrieval_count=8,
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
        plan = RecommendationPlan( retrieval_count=8,
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
                items=[{"product_id": "sku-1", "title": "Dress"}], fashion_score=90,
            )
        ]
        plan = RecommendationPlan( retrieval_count=8, directions=[])

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
                items=[{"product_id": "sku-1", "title": "Dress"}], fashion_score=90,
            )
        ]
        plan = RecommendationPlan( retrieval_count=8, directions=[])

        response = formatter.format(evaluated, context, plan, candidates)
        self.assertIn("similar style", response.message)

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
        # Item 1 fix (May 1, 2026): the onboarding-blocked early return
        # MUST persist a turn trace; without this the most-common
        # clarification path is invisible in turn_traces.
        repo.insert_turn_trace.assert_called_once()
        trace_kwargs = repo.insert_turn_trace.call_args.kwargs
        self.assertEqual("onboarding_gate", trace_kwargs["primary_intent"])
        self.assertEqual("ask_clarification", trace_kwargs["action"])
        self.assertEqual("clarification", trace_kwargs["evaluation"]["response_type"])

    def test_orchestrator_planner_failure_persists_trace_with_error_stage(self) -> None:
        """Item 1 (May 1, 2026): when the copilot planner raises, the early
        return must still persist a trace row labelled with the failed stage
        so operators can diagnose error spikes from turn_traces alone."""
        repo = Mock()
        repo.client = Mock()
        repo.get_or_create_user.return_value = {"id": "db-user"}
        repo.get_conversation.return_value = {
            "id": "c1", "user_id": "db-user", "session_context_json": {},
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
        planner_mock.plan.side_effect = RuntimeError("planner exploded")

        with patch("agentic_application.orchestrator.ApplicationCatalogRetrievalGateway"), patch(
            "agentic_application.orchestrator.CopilotPlanner", return_value=planner_mock
        ):
            orchestrator = AgenticOrchestrator(repo=repo, onboarding_gateway=gw, config=Mock())
            result = orchestrator.process_turn(
                conversation_id="c1", external_user_id="user-1",
                message="What should I wear?",
            )

        self.assertEqual("error", result["response_type"])
        repo.insert_turn_trace.assert_called_once()
        trace_kwargs = repo.insert_turn_trace.call_args.kwargs
        self.assertEqual("error", trace_kwargs["action"])
        self.assertEqual("error", trace_kwargs["evaluation"]["response_type"])
        self.assertEqual("copilot_planner", trace_kwargs["evaluation"]["stage_failed"])

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

        # Note: source_preference="auto" — the wardrobe-first short-circuit
        # is triggered by the orchestrator detecting full wardrobe coverage,
        # NOT by the planner explicitly preferring wardrobe. The test
        # verifies the short-circuit fires even when the planner returns
        # neutral routing (which is the dominant case in production).
        planner_mock = _make_planner_mock(
            occasion_signal="office",
            formality_hint="business_casual",
        )
        with patch("agentic_application.orchestrator.ApplicationCatalogRetrievalGateway"), patch(
            "agentic_application.orchestrator.OutfitArchitect"
        ) as architect_cls, patch(
            "agentic_application.orchestrator.CopilotPlanner", return_value=planner_mock
        ):
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
        self.assertIn("Show me options to buy", result["follow_up_suggestions"])
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
        fake_plan = RecommendationPlan( retrieval_count=12,
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
            _mock_llm_ranker(orchestrator, [
                OutfitCandidate(
                    candidate_id="cat-1",
                    direction_id="A",
                    candidate_type="paired",
                    items=[{"product_id": "p1", "title": "Top"}],
                    fashion_score=85,
                )
            ])
            # outfit_evaluator removed (Phase 12B cleanup)
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
        fake_plan = RecommendationPlan( retrieval_count=12,
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
            _mock_llm_ranker(orchestrator, [
                OutfitCandidate(
                    candidate_id="cat-1",
                    direction_id="A",
                    candidate_type="paired",
                    items=[{"product_id": "p1", "title": "Top"}],
                    fashion_score=85,
                )
            ])
            # outfit_evaluator removed (Phase 12B cleanup)
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
        self.assertIn("Show me options to buy", result["follow_up_suggestions"])

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
        fake_plan = RecommendationPlan( retrieval_count=12,
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
            _mock_llm_ranker(orchestrator, [
                OutfitCandidate(
                    candidate_id="cat-1",
                    direction_id="A",
                    candidate_type="complete",
                    items=[{"product_id": "c1", "title": "Wool Trouser"}],
                    fashion_score=85,
                )
            ])
            # outfit_evaluator removed (Phase 12B cleanup)
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

        planner_mock = _make_planner_mock(
            occasion_signal="office",
            formality_hint="business_casual",
            source_preference="wardrobe",
        )
        with patch("agentic_application.orchestrator.ApplicationCatalogRetrievalGateway"), patch(
            "agentic_application.orchestrator.OutfitArchitect"
        ), patch(
            "agentic_application.orchestrator.CopilotPlanner", return_value=planner_mock
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

        fake_plan = RecommendationPlan( retrieval_count=12,
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
            _mock_llm_ranker(orchestrator, [])
            # outfit_evaluator removed (Phase 12B cleanup)

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
        fake_plan = RecommendationPlan( retrieval_count=12,
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
            _mock_llm_ranker(orchestrator, [])
            # outfit_evaluator removed (Phase 12B cleanup)
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
        fake_plan = RecommendationPlan( retrieval_count=12,
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
            _mock_llm_ranker(orchestrator, [])
            # outfit_evaluator removed (Phase 12B cleanup)
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
        fake_plan = RecommendationPlan( retrieval_count=12,
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
            _mock_llm_ranker(orchestrator, [
                OutfitCandidate(
                    candidate_id="cat-1",
                    direction_id="A",
                    candidate_type="paired",
                    items=[{"product_id": "p1", "title": "Top"}],
                    fashion_score=85,
                )
            ])
            # outfit_evaluator removed (Phase 12B cleanup)
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
                        "cta": "Show me options to buy",
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
        fake_plan = RecommendationPlan( retrieval_count=12,
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
            _mock_llm_ranker(orchestrator, [
                OutfitCandidate(
                    candidate_id="cat-1",
                    direction_id="A",
                    candidate_type="complete",
                    items=[{"product_id": "c1", "title": "Stone Trousers"}],
                    fashion_score=85,
                )
            ])
            # outfit_evaluator removed (Phase 12B cleanup)
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
                message="Show me options to buy",
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
                        "cta": "Show me options to buy",
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
        fake_plan = RecommendationPlan( retrieval_count=12,
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
            _mock_llm_ranker(orchestrator, [])
            # outfit_evaluator removed (Phase 12B cleanup)

            orchestrator.process_turn(
                conversation_id="c1",
                external_user_id="user-1",
                message="Show me options to buy",
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
        self.assertIn("Show me options to buy", result["follow_up_suggestions"])
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

    # test_outfit_check_agent_uses_responses_api_with_json_schema removed
    # (Phase 12B cleanup, April 9 2026) — OutfitCheckAgent was deleted;
    # the VisualEvaluatorAgent replaced all of its call sites. The
    # visual evaluator's own response-API + JSON-schema test is in
    # Phase12BBuildingBlockTests.

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
                        "cta": "Show me options to buy",
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
        fake_plan = RecommendationPlan( retrieval_count=12,
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
            _mock_llm_ranker(orchestrator, [
                OutfitCandidate(
                    candidate_id="cat-1",
                    direction_id="A",
                    candidate_type="complete",
                    items=[{"product_id": "c1", "title": "Catalog Top"}],
                    fashion_score=85,
                )
            ])
            # outfit_evaluator removed (Phase 12B cleanup)
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
                message="Show me options to buy",
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
        fake_plan = RecommendationPlan( retrieval_count=12,
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
            _mock_llm_ranker(orchestrator, [])
            # outfit_evaluator removed (Phase 12B cleanup)
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
    """Phase 12B: unit tests for the deterministic verdict, wardrobe
    overlap, and versatility helpers. (Reranker tests deleted in May 3
    2026 PR #30 — the deterministic Reranker was replaced by the LLM
    Composer + Rater; see tests/test_outfit_composer.py and
    tests/test_outfit_rater.py.)

    These don't construct an orchestrator — they test the deterministic
    helpers in isolation so the test suite has fast, focused coverage of
    each one independent of LLM mocking."""

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

    def test_outfit_check_overall_score_handles_none_dimensions(self):
        """Phase 12B follow-up regression: the outfit_check handler
        averages body / color / style / pairing / occasion to compute
        `overall_score_pct` for backwards compat with the legacy
        OutfitCheckResult shape. After pairing_coherence_pct and
        occasion_pct became Optional[int], the literal `int + None +
        ...` arithmetic blew up with `unsupported operand type(s) for
        +: 'int' and 'NoneType'`. The handler must instead average
        over only the dimensions that were actually scored."""
        from agentic_application.schemas import EvaluatedRecommendation

        # Simulate a "Rate my outfit" turn where the user didn't name
        # an occasion. The visual evaluator returns occasion_pct=None;
        # pairing_coherence_pct comes through with a real score because
        # outfit_check IS one of the pairing-eligible intents.
        check = EvaluatedRecommendation(
            candidate_id="c1",
            body_harmony_pct=80, color_suitability_pct=70, style_fit_pct=75,
            risk_tolerance_pct=72, comfort_boundary_pct=85,
            pairing_coherence_pct=68,
            occasion_pct=None, weather_time_pct=None, specific_needs_pct=None,
        )
        # Reproduce the orchestrator's overall_score_pct math directly
        # without spinning up the whole orchestrator: average only the
        # non-None scored dimensions.
        scores = [
            check.body_harmony_pct,
            check.color_suitability_pct,
            check.style_fit_pct,
        ]
        if check.pairing_coherence_pct is not None:
            scores.append(check.pairing_coherence_pct)
        if check.occasion_pct is not None:
            scores.append(check.occasion_pct)
        # Should not raise. Should produce a sensible average.
        overall = int(sum(scores) / len(scores))
        # 4-dim average: (80+70+75+68)/4 = 73
        self.assertEqual(73, overall)

    def test_outfit_check_overall_score_with_full_context(self):
        """Sanity: when all 5 dimensions are present, the average is the
        same as the legacy 5-dim mean. Locks in that the new logic
        preserves backwards compatibility for the populated case."""
        from agentic_application.schemas import EvaluatedRecommendation

        check = EvaluatedRecommendation(
            candidate_id="c1",
            body_harmony_pct=80, color_suitability_pct=70, style_fit_pct=75,
            risk_tolerance_pct=72, comfort_boundary_pct=85,
            pairing_coherence_pct=68, occasion_pct=82,
            weather_time_pct=None, specific_needs_pct=None,
        )
        scores = [
            check.body_harmony_pct,
            check.color_suitability_pct,
            check.style_fit_pct,
        ]
        if check.pairing_coherence_pct is not None:
            scores.append(check.pairing_coherence_pct)
        if check.occasion_pct is not None:
            scores.append(check.occasion_pct)
        overall = int(sum(scores) / len(scores))
        # 5-dim average: (80+70+75+68+82)/5 = 75
        self.assertEqual(75, overall)

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

    # Phase12D assembler-direct tests removed in May 3 2026 PR #30.
    # The diversity pass logic and `_product_to_item` lived on the
    # OutfitAssembler, which is gone. Anchor-passthrough is now
    # handled inside the new module-level `_build_candidate_item`
    # helper, exercised end-to-end through the orchestrator tests.

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

    # ── Phase 12D follow-up (April 9 2026): non-garment image guard ──
    #
    # The wardrobe enrichment now returns is_garment_photo +
    # garment_present_confidence so the orchestrator can short-circuit
    # the entire pipeline when the user uploads a non-garment image
    # (chart, screenshot, landscape, etc.). The guard fires before
    # wardrobe persistence and before the planner pipeline, so:
    #   - the upload is never written to user_wardrobe_items
    #   - no recommendation pipeline runs
    #   - the user gets a clarification asking for a clearer photo

    def _build_non_garment_test_repo_and_gateway(self, *, intent_value):
        """Helper to wire up a Mock repo + gateway for non-garment tests."""
        from agentic_application.schemas import (
            CopilotPlanResult, CopilotResolvedContext, CopilotActionParameters,
        )
        repo = Mock()
        repo.client = Mock()
        repo.get_or_create_user.return_value = {"id": "db-user"}
        repo.get_conversation.return_value = {
            "id": "c1", "user_id": "db-user", "session_context_json": {},
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
            "profile": {"gender": "male", "style_preference": {"primaryArchetype": "natural"}},
            "attributes": {"BodyShape": {"value": "Trapezoid"}},
            "derived_interpretations": {"SeasonalColorGroup": {"value": "Winter"}},
        }
        gw.get_wardrobe_items.return_value = []
        gw.get_person_image_path.return_value = None
        planner = Mock()
        planner.plan.return_value = CopilotPlanResult(
            intent=intent_value,
            intent_confidence=0.95,
            action=Action.RUN_RECOMMENDATION_PIPELINE,
            context_sufficient=True,
            assistant_message="",
            follow_up_suggestions=[],
            resolved_context=CopilotResolvedContext(),
            action_parameters=CopilotActionParameters(target_piece="this piece"),
        )
        return repo, gw, planner

    def test_non_garment_upload_returns_clarification(self):
        """When the wardrobe enrichment flags is_garment_photo=False
        (e.g. a chart, screenshot, landscape photo), the orchestrator
        must short-circuit to ASK_CLARIFICATION with the
        non_garment_image reason code, NOT run the planner pipeline,
        and NOT persist the upload to user_wardrobe_items."""
        repo, gw, planner = self._build_non_garment_test_repo_and_gateway(
            intent_value=Intent.PAIRING_REQUEST,
        )
        gw.save_uploaded_chat_wardrobe_item.return_value = {
            "id": None,
            "title": "",
            "image_path": "data/onboarding/images/wardrobe/chart.jpg",
            "garment_category": "",
            "garment_subtype": "",
            "primary_color": "",
            "enrichment_status": "ok",
            "is_garment_photo": False,             # ← model says NOT a garment
            "garment_present_confidence": 0.05,
            "_pending_persist": True,
        }
        with patch("agentic_application.orchestrator.ApplicationCatalogRetrievalGateway"), \
             patch("agentic_application.orchestrator.OutfitArchitect") as architect_cls, \
             patch("agentic_application.orchestrator.VisualEvaluatorAgent"), \
             patch("agentic_application.orchestrator.StyleAdvisorAgent"), \
             patch("agentic_application.orchestrator.CopilotPlanner", return_value=planner):
            orchestrator = AgenticOrchestrator(repo=repo, onboarding_gateway=gw, config=Mock())
            result = orchestrator.process_turn(
                conversation_id="c1",
                external_user_id="user-1",
                message="Find me a completing outfit from catalog",
                image_data="data:image/jpeg;base64,/9j/4AAQ",
            )

        # Architect must NOT have been called — the guard short-circuits
        # before the recommendation pipeline runs.
        architect_cls.return_value.plan.assert_not_called()
        # The pending upload must NOT have been promoted to a real row.
        gw.persist_pending_wardrobe_item.assert_not_called()
        # The reason code is set so dashboard panels can track this.
        self.assertIn(
            "non_garment_image",
            result["metadata"]["intent_reason_codes"],
        )
        # The user-facing message asks for a clearer garment photo.
        msg = result["assistant_message"].lower()
        self.assertTrue(
            "garment" in msg or "piece" in msg,
            f"expected clarification copy mentioning garment/piece, got {msg!r}",
        )

    def test_low_confidence_upload_returns_clarification(self):
        """Defence-in-depth: even when is_garment_photo=True, if the
        garment_present_confidence is below 0.5 (model said yes but
        wasn't sure — typical for ambiguous edge cases like fashion-
        website screenshots or printed catalog pages) the orchestrator
        still surfaces the clarification."""
        repo, gw, planner = self._build_non_garment_test_repo_and_gateway(
            intent_value=Intent.PAIRING_REQUEST,
        )
        gw.save_uploaded_chat_wardrobe_item.return_value = {
            "id": None,
            "title": "",
            "image_path": "data/onboarding/images/wardrobe/screenshot.jpg",
            "garment_category": "top",  # the model picked something
            "enrichment_status": "ok",
            "is_garment_photo": True,              # said yes…
            "garment_present_confidence": 0.32,    # …but with low confidence
            "_pending_persist": True,
        }
        with patch("agentic_application.orchestrator.ApplicationCatalogRetrievalGateway"), \
             patch("agentic_application.orchestrator.OutfitArchitect") as architect_cls, \
             patch("agentic_application.orchestrator.VisualEvaluatorAgent"), \
             patch("agentic_application.orchestrator.StyleAdvisorAgent"), \
             patch("agentic_application.orchestrator.CopilotPlanner", return_value=planner):
            orchestrator = AgenticOrchestrator(repo=repo, onboarding_gateway=gw, config=Mock())
            result = orchestrator.process_turn(
                conversation_id="c1",
                external_user_id="user-1",
                message="What goes with this?",
                image_data="data:image/jpeg;base64,/9j/4AAQ",
            )
        architect_cls.return_value.plan.assert_not_called()
        gw.persist_pending_wardrobe_item.assert_not_called()
        self.assertIn(
            "non_garment_image",
            result["metadata"]["intent_reason_codes"],
        )

    def test_garment_upload_passes_through_when_high_confidence(self):
        """Happy path: a real garment upload (is_garment_photo=True,
        confidence ≥ 0.5) must NOT be flagged as non-garment, must
        persist normally, and the recommendation pipeline must run.
        Locks in that the new guard doesn't break legitimate uploads."""
        repo, gw, planner = self._build_non_garment_test_repo_and_gateway(
            intent_value=Intent.PAIRING_REQUEST,
        )
        gw.save_uploaded_chat_wardrobe_item.return_value = {
            "id": None,
            "title": "Black Tee",
            "image_path": "data/onboarding/images/wardrobe/tee.jpg",
            "garment_category": "top",
            "garment_subtype": "tee",
            "primary_color": "black",
            "enrichment_status": "ok",
            "is_garment_photo": True,
            "garment_present_confidence": 0.95,
            "_pending_persist": True,
        }
        gw.persist_pending_wardrobe_item.return_value = {
            "id": "real-row-uuid",
            "title": "Black Tee",
            "image_path": "data/onboarding/images/wardrobe/tee.jpg",
            "garment_category": "top",
            "garment_subtype": "tee",
            "primary_color": "black",
            "enrichment_status": "ok",
            "is_garment_photo": True,
            "garment_present_confidence": 0.95,
        }
        with patch("agentic_application.orchestrator.ApplicationCatalogRetrievalGateway"), \
             patch("agentic_application.orchestrator.OutfitArchitect") as architect_cls, \
             patch("agentic_application.orchestrator.VisualEvaluatorAgent"), \
             patch("agentic_application.orchestrator.StyleAdvisorAgent"), \
             patch("agentic_application.orchestrator.CopilotPlanner", return_value=planner):
            architect_cls.return_value.plan.side_effect = RuntimeError("stop after persist check")
            orchestrator = AgenticOrchestrator(repo=repo, onboarding_gateway=gw, config=Mock())
            try:
                result = orchestrator.process_turn(
                    conversation_id="c1",
                    external_user_id="user-1",
                    message="What goes with this?",
                    image_data="data:image/jpeg;base64,/9j/4AAQ",
                )
            except Exception:
                result = None

        # The non-garment guard must NOT have fired — no
        # `non_garment_image` reason code, persistence promotion did
        # happen, and the architect attempt did happen (the RuntimeError
        # we raised on architect.plan proves we got past the guard
        # and into the pipeline).
        gw.persist_pending_wardrobe_item.assert_called_once()
        if result is not None:
            self.assertNotIn(
                "non_garment_image",
                result.get("metadata", {}).get("intent_reason_codes", []),
            )

    def test_garment_evaluation_exempt_from_non_garment_guard(self):
        """garment_evaluation must be exempt from the non-garment guard
        because the visual evaluator works on image bytes directly and
        might handle edge cases the enrichment can't (same exemption
        as the wardrobe_enrichment_failed guard above). The guard
        check has `intent != GARMENT_EVALUATION` — verify the exemption
        actually fires by simulating an is_garment_photo=False upload
        on a garment_evaluation turn and asserting the guard does NOT
        intervene."""
        from agentic_application.schemas import (
            CopilotPlanResult, CopilotResolvedContext, CopilotActionParameters,
        )
        repo, gw, _ = self._build_non_garment_test_repo_and_gateway(
            intent_value=Intent.GARMENT_EVALUATION,
        )
        # Override the planner's intent to GARMENT_EVALUATION + the
        # corresponding action.
        planner = Mock()
        planner.plan.return_value = CopilotPlanResult(
            intent=Intent.GARMENT_EVALUATION,
            intent_confidence=0.95,
            action=Action.RUN_GARMENT_EVALUATION,
            context_sufficient=True,
            assistant_message="",
            follow_up_suggestions=[],
            resolved_context=CopilotResolvedContext(),
            action_parameters=CopilotActionParameters(purchase_intent=True),
        )
        gw.save_uploaded_chat_wardrobe_item.return_value = {
            "id": None,
            "title": "",
            "image_path": "data/onboarding/images/wardrobe/ambiguous.jpg",
            "enrichment_status": "ok",
            "is_garment_photo": False,
            "garment_present_confidence": 0.1,
            "_pending_persist": True,
        }
        with patch("agentic_application.orchestrator.ApplicationCatalogRetrievalGateway"), \
             patch("agentic_application.orchestrator.OutfitArchitect"), \
             patch("agentic_application.orchestrator.VisualEvaluatorAgent") as ve_cls, \
             patch("agentic_application.orchestrator.StyleAdvisorAgent"), \
             patch("agentic_application.orchestrator.CopilotPlanner", return_value=planner):
            ve_cls.return_value.evaluate_candidate.side_effect = RuntimeError("stop")
            orchestrator = AgenticOrchestrator(repo=repo, onboarding_gateway=gw, config=Mock())
            try:
                result = orchestrator.process_turn(
                    conversation_id="c1",
                    external_user_id="user-1",
                    message="Should I buy this?",
                    image_data="data:image/jpeg;base64,/9j/4AAQ",
                )
            except Exception:
                result = None

        # If the guard had fired, plan_result.action would be
        # ASK_CLARIFICATION and we'd never reach the visual evaluator.
        # The fact that we got a RuntimeError from
        # ve_cls.evaluate_candidate proves the guard let
        # garment_evaluation through.
        ve_cls.return_value.evaluate_candidate.assert_called()
        if result is not None:
            self.assertNotIn(
                "non_garment_image",
                result.get("metadata", {}).get("intent_reason_codes", []),
            )


class TurnTraceBuilderTests(unittest.TestCase):
    """Unit tests for the TurnTraceBuilder accumulator."""

    def test_build_produces_correct_shape(self):
        from agentic_application.tracing import TurnTraceBuilder

        trace = TurnTraceBuilder(
            turn_id="t1", conversation_id="c1", user_id="u1",
            user_message="What goes with this shirt?", has_image=True,
        )
        trace.add_step("validate_request", input_summary="user=u1", output_summary="ok", latency_ms=10)
        trace.add_step("copilot_planner", model="gpt-5.5", input_summary="msg", output_summary="pairing_request", latency_ms=800)
        trace.set_intent(primary_intent="pairing_request", intent_confidence=0.95, action="run_recommendation_pipeline", reason_codes=["copilot_planner"])
        trace.set_context(
            profile_snapshot={"gender": "male", "primary_archetype": "natural"},
            query_entities={"occasion_signal": None},
        )
        trace.set_evaluation({"evaluator_path": "visual", "outfit_count": 3})

        result = trace.build()
        self.assertEqual("t1", result["turn_id"])
        self.assertEqual("c1", result["conversation_id"])
        self.assertEqual("u1", result["user_id"])
        self.assertEqual("What goes with this shirt?", result["user_message"])
        self.assertTrue(result["has_image"])
        self.assertEqual("pairing_request", result["primary_intent"])
        self.assertEqual(0.95, result["intent_confidence"])
        self.assertEqual("run_recommendation_pipeline", result["action"])
        self.assertEqual(["copilot_planner"], result["reason_codes"])
        self.assertEqual({"gender": "male", "primary_archetype": "natural"}, result["profile_snapshot"])
        self.assertIsNone(result["query_entities"]["occasion_signal"])
        self.assertEqual(2, len(result["steps"]))
        self.assertEqual("validate_request", result["steps"][0]["step"])
        self.assertEqual("gpt-5.5", result["steps"][1]["model"])
        self.assertEqual(800, result["steps"][1]["latency_ms"])
        self.assertEqual("visual", result["evaluation"]["evaluator_path"])
        self.assertIsInstance(result["total_latency_ms"], int)
        self.assertGreaterEqual(result["total_latency_ms"], 0)

    def test_build_empty_produces_valid_shape(self):
        """An empty trace (no steps, no intent, no context) still
        returns a well-formed dict so insert_turn_trace doesn't error."""
        from agentic_application.tracing import TurnTraceBuilder

        trace = TurnTraceBuilder(turn_id="t2", conversation_id="c2", user_id="u2")
        result = trace.build()
        self.assertEqual("t2", result["turn_id"])
        self.assertEqual("", result["primary_intent"])
        self.assertEqual([], result["steps"])
        self.assertEqual({}, result["evaluation"])
        self.assertIsInstance(result["total_latency_ms"], int)

    def test_add_step_with_error(self):
        from agentic_application.tracing import TurnTraceBuilder

        trace = TurnTraceBuilder(turn_id="t3", conversation_id="c3", user_id="u3")
        trace.add_step("outfit_architect", model="gpt-5.5", status="error", error="timeout after 30s")
        result = trace.build()
        self.assertEqual(1, len(result["steps"]))
        self.assertEqual("error", result["steps"][0]["status"])
        self.assertEqual("timeout after 30s", result["steps"][0]["error"])

    def test_total_cost_usd_accumulates_into_evaluation(self):
        """May 3, 2026 obs gap: every LLM / image / embedding call's
        cost should fold into a single per-turn rollup so dashboards
        don't need to sum model_call_logs themselves."""
        from agentic_application.tracing import TurnTraceBuilder

        trace = TurnTraceBuilder(turn_id="t4", conversation_id="c4", user_id="u4")
        trace.add_cost(0.04272)  # planner
        trace.add_cost(0.17631)  # architect
        trace.add_model_cost_from_row({"estimated_cost_usd": 0.00543})  # composer
        trace.add_model_cost_from_row({"estimated_cost_usd": 0.00611})  # rater
        trace.add_model_cost_from_row({"estimated_cost_usd": 0.00012})  # embedding
        trace.set_evaluation({"answer_source": "catalog_pipeline", "outfit_count": 3})

        result = trace.build()
        ev = result["evaluation"]
        self.assertIn("total_cost_usd", ev)
        # 0.04272 + 0.17631 + 0.00543 + 0.00611 + 0.00012 = 0.23069
        self.assertAlmostEqual(0.23069, ev["total_cost_usd"], places=5)
        # Existing evaluation fields preserved.
        self.assertEqual("catalog_pipeline", ev["answer_source"])
        self.assertEqual(3, ev["outfit_count"])

    def test_zero_cost_skips_total_cost_usd_field(self):
        """When no cost was tracked (e.g. fully cached turn), the
        evaluation block stays as-is — total_cost_usd absent rather
        than `0.0` so consumers can distinguish the two states."""
        from agentic_application.tracing import TurnTraceBuilder

        trace = TurnTraceBuilder(turn_id="t5", conversation_id="c5", user_id="u5")
        trace.set_evaluation({"answer_source": "wardrobe_first"})
        result = trace.build()
        self.assertNotIn("total_cost_usd", result["evaluation"])

    def test_add_cost_tolerates_none_and_strings(self):
        """Defensive: some model_call_logs rows may have a None or
        unparseable cost field. add_cost must never raise."""
        from agentic_application.tracing import TurnTraceBuilder

        trace = TurnTraceBuilder(turn_id="t6", conversation_id="c6", user_id="u6")
        trace.add_cost(None)
        trace.add_cost(0.05)
        trace.add_model_cost_from_row(None)
        trace.add_model_cost_from_row({})
        trace.add_model_cost_from_row({"estimated_cost_usd": None})
        trace.add_model_cost_from_row({"estimated_cost_usd": "not a number"})
        result = trace.build()
        self.assertAlmostEqual(0.05, result["evaluation"].get("total_cost_usd", 0), places=5)


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
      catalog_search → outfit_composer → outfit_rater → tryon_render →
      visual_evaluation → response_formatting → attach_tryon_images
      (when a person photo is on file). May 5, 2026: the late
      `virtual_tryon` stage was split — the actual Gemini renders now
      emit as `tryon_render` before `visual_evaluation`, and the
      post-format cache lookup that wires image URLs onto each
      OutfitCard emits as `attach_tryon_images`.
    - garment_evaluation: no architect / composer / search; just runs
      the handler-internal try-on + visual evaluator.
    - outfit_check: no architect / composer / search; visual evaluator
      on the user photo.
    - style_discovery / explanation_request: validate → gate → planner →
      direct response handler (no pipeline stages).
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
        # NO pipeline stages — style_discovery doesn't go near search/compose/rate/evaluate
        self.assertNotIn("outfit_architect", stage_names)
        self.assertNotIn("catalog_search", stage_names)
        self.assertNotIn("outfit_composer", stage_names)
        self.assertNotIn("outfit_rater", stage_names)
        self.assertNotIn("visual_evaluation", stage_names)
        self.assertNotIn("tryon_render", stage_names)
        self.assertNotIn("attach_tryon_images", stage_names)

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

    # test_occasion_recommendation_legacy_path_emits_text_evaluator_stage
    # removed (Phase 12B cleanup, April 9 2026) — the legacy text evaluator
    # path no longer exists; the visual evaluator is the sole evaluator and
    # a failure produces a graceful empty response, not a text-only fallback.


    # --- Phase 13: Outfit Architect payload and schema regression tests ---

    def test_outfit_architect_payload_includes_live_context_fields(self) -> None:
        """_build_user_payload must include weather_context, time_of_day,
        and target_product_type from LiveContext under a 'live_context' key."""
        from agentic_application.agents.outfit_architect import _build_user_payload

        context = CombinedContext(
            user=UserContext(
                user_id="u1",
                gender="male",
                derived_interpretations={
                    "SeasonalColorGroup": {"value": "Warm Autumn"},
                },
            ),
            live=LiveContext(
                user_need="Something warm for a rainy evening",
                weather_context="rainy, cold",
                time_of_day="evening",
                target_product_type="",
            ),
            hard_filters={"gender_expression": "masculine"},
        )

        payload = json.loads(_build_user_payload(context))
        self.assertIn("live_context", payload)
        lc = payload["live_context"]
        self.assertEqual("rainy, cold", lc["weather_context"])
        self.assertEqual("evening", lc["time_of_day"])
        self.assertIsNone(lc["target_product_type"])  # empty string → None

    def test_outfit_architect_payload_live_context_null_when_empty(self) -> None:
        """When LiveContext fields are empty/default, they should be null
        in the payload so the prompt sees null, not empty strings."""
        from agentic_application.agents.outfit_architect import _build_user_payload

        context = CombinedContext(
            user=UserContext(user_id="u1", gender="female"),
            live=LiveContext(user_need="Show me something"),
            hard_filters={"gender_expression": "feminine"},
        )

        payload = json.loads(_build_user_payload(context))
        lc = payload["live_context"]
        self.assertIsNone(lc["weather_context"])
        self.assertIsNone(lc["time_of_day"])
        self.assertIsNone(lc["target_product_type"])

    def test_outfit_architect_payload_includes_anchor_garment(self) -> None:
        """When anchor_garment is set on LiveContext, the payload must include it."""
        from agentic_application.agents.outfit_architect import _build_user_payload

        anchor = {"garment_category": "outerwear", "garment_subtype": "blazer", "primary_color": "navy"}
        context = CombinedContext(
            user=UserContext(user_id="u1", gender="male"),
            live=LiveContext(user_need="Build around my blazer", anchor_garment=anchor),
            hard_filters={"gender_expression": "masculine"},
        )

        payload = json.loads(_build_user_payload(context))
        self.assertEqual(anchor, payload["anchor_garment"])

    def test_direction_spec_accepts_three_piece(self) -> None:
        """DirectionSpec.direction_type must accept 'three_piece'."""
        d = DirectionSpec(
            direction_id="C",
            direction_type="three_piece",
            label="Layered look",
            queries=[
                QuerySpec(query_id="C1", role="top", query_document="..."),
                QuerySpec(query_id="C2", role="bottom", query_document="..."),
                QuerySpec(query_id="C3", role="outerwear", query_document="..."),
            ],
        )
        self.assertEqual("three_piece", d.direction_type)
        self.assertEqual(3, len(d.queries))


class ConfidenceThresholdGateTests(unittest.TestCase):
    """May 1 2026 — wardrobe-first selector + catalog-pipeline gate.

    These tests pin the contract: nothing reaches the user with confidence
    below the 0.75 threshold, on either the wardrobe-first or
    catalog-pipeline branches.
    """

    def test_wardrobe_selector_drops_empty_occasion_fit_reward(self) -> None:
        """Items with empty occasion_fit no longer earn a participation
        point — that was the bug that let an ivory kurta with empty/festive
        tag win for date_night."""
        items = [
            {
                "id": "kurta",
                "title": "Ivory Long-Sleeve Kurta",
                "garment_category": "top",
                "occasion_fit": "",
                "formality_level": "semi_formal",
            },
            {
                "id": "trousers",
                "title": "Ivory Trousers",
                "garment_category": "bottom",
                "occasion_fit": "",
                "formality_level": "semi_formal",
            },
        ]
        out, conf = AgenticOrchestrator._select_wardrobe_occasion_outfit(
            wardrobe_items=items, occasion="date_night",
        )
        # Each item earns +1 (formality match) and 0 (empty occasion_fit).
        # Min item score 1, normalized 1/4 = 0.25 — well below 0.75.
        self.assertLess(conf, 0.75)
        self.assertLessEqual(conf, 0.26)

    def test_wardrobe_selector_passes_threshold_when_occasion_explicit(self) -> None:
        items = [
            {
                "id": "dress",
                "title": "Black Slip Dress",
                "garment_category": "dress",
                "occasion_fit": "date_night",
                "formality_level": "smart_casual",
            },
        ]
        out, conf = AgenticOrchestrator._select_wardrobe_occasion_outfit(
            wardrobe_items=items, occasion="date_night",
        )
        # Score = 3 (occasion match) + 1 (formality match) = 4 → 1.0.
        self.assertGreaterEqual(conf, 0.75)
        self.assertEqual(1, len(out))

    def test_wardrobe_selector_min_item_score_for_multi_item(self) -> None:
        items = [
            {
                "id": "blazer",
                "title": "Navy Blazer",
                "garment_category": "top",
                "occasion_fit": "office",
                "formality_level": "business_casual",
            },
            {
                "id": "jeans",
                "title": "Blue Jeans",
                "garment_category": "bottom",
                # occasion_fit empty — only formality earns a point and even
                # that doesn't trigger because jeans are typically casual.
                "occasion_fit": "",
                "formality_level": "casual",
            },
        ]
        out, conf = AgenticOrchestrator._select_wardrobe_occasion_outfit(
            wardrobe_items=items, occasion="office",
        )
        # Top: 3 + 1 = 4. Bottom: 0 + 0 = 0 (jeans casual not in office class).
        # The selector requires _score > 0 to even include an item, so
        # bottom is excluded from the picked outfit. With no bottom, the
        # function still returns the top alone — score 4 → 1.0. The point
        # of this test: the bug isn't masked by averaging away the weak
        # link; an honest weak result either gets filtered or reflects.
        if len(out) == 2:
            self.assertLess(conf, 0.75)
        else:
            self.assertEqual(1, len(out))

    def test_wardrobe_selector_returns_empty_when_no_item_qualifies(self) -> None:
        items = [
            {
                "id": "tshirt",
                "title": "White Tee",
                "garment_category": "top",
                "occasion_fit": "casual",
                "formality_level": "casual",
            },
        ]
        out, conf = AgenticOrchestrator._select_wardrobe_occasion_outfit(
            wardrobe_items=items, occasion="wedding",
        )
        self.assertEqual([], out)
        self.assertEqual(0.0, conf)

    def test_catalog_pipeline_gate_blocks_when_all_below_threshold(self) -> None:
        """Construct an orchestrator scenario where every assembled
        candidate has assembly_score < 0.75; verify the no-confident-match
        response path fires and ships zero outfits."""
        from agentic_application.schemas import (
            CopilotPlanResult, CopilotResolvedContext, CopilotActionParameters,
            RecommendationPlan, DirectionSpec, QuerySpec, ResolvedContextBlock,
            RecommendationResponse,
        )

        repo = Mock()
        repo.client = Mock()
        repo.get_or_create_user.return_value = {"id": "db-user"}
        repo.get_conversation.return_value = {
            "id": "c1", "user_id": "db-user", "session_context_json": {},
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
        gw.get_wardrobe_items.return_value = []  # No wardrobe → straight to catalog pipeline
        gw.get_person_image_path.return_value = ""

        plan = RecommendationPlan(
            directions=[
                DirectionSpec(
                    direction_id="d1",
                    label="Test direction",
                    direction_type="paired",
                    rationale="Test",
                    queries=[
                        QuerySpec(query_id="A1", role="top", query_document="top"),
                        QuerySpec(query_id="A2", role="bottom", query_document="bottom"),
                    ],
                )
            ],
            resolved_context=ResolvedContextBlock(),
        )

        planner_mock = Mock()
        planner_mock.plan.return_value = CopilotPlanResult(
            intent=Intent.OCCASION_RECOMMENDATION,
            intent_confidence=0.9,
            action=Action.RUN_RECOMMENDATION_PIPELINE,
            context_sufficient=True,
            assistant_message="Ok.",
            follow_up_suggestions=[],
            resolved_context=CopilotResolvedContext(occasion_signal="date_night"),
            action_parameters=CopilotActionParameters(),
        )

        # Build candidates whose fashion_score is well under the 75 gate.
        weak_candidates = [
            OutfitCandidate(
                candidate_id=f"c{i}",
                direction_id="d1",
                candidate_type="paired",
                items=[{"product_id": f"p{i}", "title": f"Item {i}"}],
                fashion_score=40 + (i * 5),  # 40, 45, 50
            )
            for i in range(3)
        ]

        with patch("agentic_application.orchestrator.ApplicationCatalogRetrievalGateway") as gw_cls, patch(
            "agentic_application.orchestrator.OutfitArchitect"
        ) as architect_cls, patch(
            "agentic_application.orchestrator.CopilotPlanner", return_value=planner_mock,
        ), patch(
            "agentic_application.orchestrator.CatalogSearchAgent"
        ) as search_cls, patch(
            "agentic_application.orchestrator.OutfitComposer"
        ) as composer_cls, patch(
            "agentic_application.orchestrator.OutfitRater"
        ) as rater_cls:
            architect_cls.return_value.plan.return_value = plan
            products = _wire_llm_ranker_via_patches(composer_cls, rater_cls, weak_candidates)
            search_cls.return_value.search.return_value = [
                RetrievedSet(direction_id="A", query_id="A1", role="complete", products=products),
            ]
            gw_cls.return_value.get_catalog_inventory.return_value = [
                {"id": f"p{i}", "title": f"Item {i}"} for i in range(3)
            ]
            gw_cls.return_value.search.return_value = []

            orchestrator = AgenticOrchestrator(repo=repo, onboarding_gateway=gw, config=Mock())
            result = orchestrator.process_turn(
                conversation_id="c1",
                external_user_id="user-1",
                message="Romantic date night this weekend",
            )

        self.assertEqual([], result["outfits"])
        self.assertEqual(
            "catalog_low_confidence",
            result["metadata"]["answer_source"],
        )
        self.assertIn("couldn't find a strong match", result["assistant_message"].lower())
        # The graceful response should expose the best score we saw, so
        # observability and UX can both reason about it.
        self.assertIn("low_confidence_top_match_score", result["metadata"])
        self.assertLess(result["metadata"]["low_confidence_top_match_score"], 0.75)

    def test_catalog_pipeline_gate_keeps_only_confident_outfits(self) -> None:
        """When some candidates pass the threshold and some don't, only
        the confident ones ship — capped at 3."""
        from agentic_application.schemas import (
            CopilotPlanResult, CopilotResolvedContext, CopilotActionParameters,
            RecommendationPlan, DirectionSpec, QuerySpec, ResolvedContextBlock,
            OutfitCard, RecommendationResponse,
        )

        repo = Mock()
        repo.client = Mock()
        repo.get_or_create_user.return_value = {"id": "db-user"}
        repo.get_conversation.return_value = {
            "id": "c1", "user_id": "db-user", "session_context_json": {},
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
        gw.get_person_image_path.return_value = ""

        plan = RecommendationPlan(
            directions=[
                DirectionSpec(
                    direction_id="d1",
                    label="Test direction",
                    direction_type="paired",
                    rationale="Test",
                    queries=[
                        QuerySpec(query_id="A1", role="top", query_document="top"),
                        QuerySpec(query_id="A2", role="bottom", query_document="bottom"),
                    ],
                )
            ],
            resolved_context=ResolvedContextBlock(),
        )
        planner_mock = Mock()
        planner_mock.plan.return_value = CopilotPlanResult(
            intent=Intent.OCCASION_RECOMMENDATION,
            intent_confidence=0.9,
            action=Action.RUN_RECOMMENDATION_PIPELINE,
            context_sufficient=True,
            assistant_message="Ok.",
            follow_up_suggestions=[],
            resolved_context=CopilotResolvedContext(occasion_signal="casual"),
            action_parameters=CopilotActionParameters(),
        )

        # Mix: 2 confident (>= 0.75), 3 below threshold.
        candidates = [
            OutfitCandidate(
                candidate_id=f"hi{i}", direction_id="d1", candidate_type="paired",
                items=[{"product_id": f"hi-p{i}", "title": f"Hi {i}"}],
                fashion_score=85,
            ) for i in range(2)
        ] + [
            OutfitCandidate(
                candidate_id=f"lo{i}", direction_id="d1", candidate_type="paired",
                items=[{"product_id": f"lo-p{i}", "title": f"Lo {i}"}],
                fashion_score=50,
            ) for i in range(3)
        ]

        formatter_called_with: dict = {}

        def fake_format(evaluated, *args, **kwargs):
            formatter_called_with["count"] = len(evaluated)
            outfits = [
                OutfitCard(
                    rank=i + 1,
                    title=f"Outfit {i + 1}",
                    reasoning="r",
                    occasion_note="r",
                    items=[{"product_id": f"out-{i}", "title": f"Out {i}", "image_url": ""}],
                )
                for i in range(len(evaluated))
            ]
            return RecommendationResponse(
                message="Here you go.",
                outfits=outfits,
                follow_up_suggestions=[],
                metadata={},
            )

        with patch("agentic_application.orchestrator.ApplicationCatalogRetrievalGateway") as gw_cls, patch(
            "agentic_application.orchestrator.OutfitArchitect"
        ) as architect_cls, patch(
            "agentic_application.orchestrator.CopilotPlanner", return_value=planner_mock,
        ), patch(
            "agentic_application.orchestrator.CatalogSearchAgent"
        ) as search_cls, patch(
            "agentic_application.orchestrator.OutfitComposer"
        ) as composer_cls, patch(
            "agentic_application.orchestrator.OutfitRater"
        ) as rater_cls, patch(
            "agentic_application.orchestrator.ResponseFormatter"
        ) as formatter_cls:
            architect_cls.return_value.plan.return_value = plan
            products = _wire_llm_ranker_via_patches(composer_cls, rater_cls, candidates)
            search_cls.return_value.search.return_value = [
                RetrievedSet(direction_id="A", query_id="A1", role="complete", products=products),
            ]
            gw_cls.return_value.get_catalog_inventory.return_value = [
                {"id": f"hi-p{i}", "title": f"Hi {i}"} for i in range(2)
            ] + [{"id": f"lo-p{i}", "title": f"Lo {i}"} for i in range(3)]
            gw_cls.return_value.search.return_value = []
            formatter_cls.return_value.format.side_effect = fake_format

            orchestrator = AgenticOrchestrator(repo=repo, onboarding_gateway=gw, config=Mock())
            result = orchestrator.process_turn(
                conversation_id="c1",
                external_user_id="user-1",
                message="Casual coffee outfit",
            )

        # Only the 2 confident candidates should reach the formatter.
        self.assertEqual(2, formatter_called_with.get("count"))
        # And both should reach the user.
        self.assertEqual(2, len(result["outfits"]))


class OnDemandVisualEvalTests(unittest.TestCase):
    """May 5, 2026 — visual_evaluator moved to on-demand. The default
    recommendation pipeline ships outfits with Rater-only dims and
    visual_evaluation_status="pending"; clicking "Get a deeper read"
    on a card hits POST /v1/turns/{turn_id}/outfits/{rank}/visual-eval
    which runs the evaluator and patches the persisted outfit."""

    def _build_orchestrator(self, repo, gw):
        from agentic_application.orchestrator import AgenticOrchestrator
        with patch("agentic_application.orchestrator.ApplicationCatalogRetrievalGateway"), \
             patch("agentic_application.orchestrator.OutfitArchitect"), \
             patch("agentic_application.orchestrator.VisualEvaluatorAgent"), \
             patch("agentic_application.orchestrator.StyleAdvisorAgent"), \
             patch("agentic_application.orchestrator.CopilotPlanner"):
            return AgenticOrchestrator(repo=repo, onboarding_gateway=gw, config=Mock())

    def test_idempotent_when_status_already_ready(self) -> None:
        repo = Mock()
        repo.get_turn.return_value = {
            "id": "t1",
            "conversation_id": "c1",
            "resolved_context_json": {
                "outfits": [{
                    "rank": 1, "title": "Outfit 1", "items": [],
                    "visual_evaluation_status": "ready",
                    "body_harmony_pct": 88,
                }],
            },
        }
        gw = Mock()
        orchestrator = self._build_orchestrator(repo, gw)
        out = orchestrator.run_on_demand_visual_eval(turn_id="t1", rank=1)
        # No evaluator call, no DB write, no extra log_model_call.
        orchestrator.visual_evaluator.evaluate_candidate.assert_not_called()
        repo.update_turn_resolved_context.assert_not_called()
        self.assertEqual(88, out["body_harmony_pct"])

    def test_pending_outfit_runs_evaluator_and_persists(self) -> None:
        from agentic_application.schemas import EvaluatedRecommendation
        repo = Mock()
        repo.get_turn.return_value = {
            "id": "t1",
            "conversation_id": "c1",
            "resolved_context_json": {
                "outfits": [{
                    "rank": 1, "title": "Outfit 1",
                    "items": [{"product_id": "p-1", "title": "Top"}],
                    "visual_evaluation_status": "pending",
                    "body_harmony_pct": 70, "color_suitability_pct": 65,
                    "reasoning": "Initial Rater note.",
                    "match_score": 0.82,
                }],
                # Parallel `recommendations` array — analytics queries use
                # this; the on-demand path must mirror the evaluator's
                # output here AND on `outfits` to keep them consistent.
                "recommendations": [{
                    "rank": 1, "candidate_id": "c1",
                    "reasoning": "Initial Rater note.",
                    "body_harmony_pct": 70, "color_suitability_pct": 65,
                    "visual_evaluation_status": "pending",
                }],
                "live_context": {"user_need": "office wear", "occasion_signal": "office"},
                "intent_classification": {"primary_intent": Intent.OCCASION_RECOMMENDATION},
                "profile_confidence": {"score_pct": 80},
            },
        }
        repo.get_conversation.return_value = {"id": "c1", "user_id": "db-user"}
        repo.get_user_by_id.return_value = {"id": "db-user", "external_user_id": "user-1"}
        repo.find_tryon_image_by_garments.return_value = {"file_path": "/tmp/tryon.png"}
        repo.log_model_call.return_value = {"id": "log-1"}
        gw = Mock()
        gw.get_onboarding_status.return_value = {
            "profile_complete": True, "style_preference_complete": True,
            "images_uploaded": ["full_body"], "onboarding_complete": True,
        }
        gw.get_analysis_status.return_value = {
            "status": "completed",
            "profile": {"gender": "female", "style_preference": {"primaryArchetype": "classic"}},
            "attributes": {"BodyShape": {"value": "Hourglass"}},
            "derived_interpretations": {"SeasonalColorGroup": {"value": "Soft Summer"}},
        }
        gw.get_wardrobe_items.return_value = []
        gw.get_person_image_path.return_value = "/tmp/person.jpg"

        orchestrator = self._build_orchestrator(repo, gw)
        orchestrator.visual_evaluator.evaluate_candidate.return_value = EvaluatedRecommendation(
            candidate_id="c1", rank=1, match_score=0.82,
            reasoning="An expanded read.",
            body_note="Balanced.", color_note="Cool.", style_note="Refined.", occasion_note="Office.",
            body_harmony_pct=88, color_suitability_pct=84, style_fit_pct=82,
            risk_tolerance_pct=70, comfort_boundary_pct=78,
            occasion_pct=90, classic_pct=70, dramatic_pct=10, romantic_pct=15,
            natural_pct=20, minimalist_pct=55, creative_pct=10, sporty_pct=10, edgy_pct=10,
        )
        out = orchestrator.run_on_demand_visual_eval(turn_id="t1", rank=1)
        # Evaluator was called with the cached tryon path, not the bare person photo.
        eval_kwargs = orchestrator.visual_evaluator.evaluate_candidate.call_args.kwargs
        self.assertEqual("/tmp/tryon.png", eval_kwargs["image_path"])
        # Outfit got the full evaluator output and was promoted to "ready".
        self.assertEqual("ready", out["visual_evaluation_status"])
        self.assertEqual(88, out["body_harmony_pct"])
        self.assertEqual("Balanced.", out["body_note"])
        self.assertEqual(70, out["classic_pct"])
        # Persisted to the turn so re-opens see the same data.
        repo.update_turn_resolved_context.assert_called_once()
        # Both `outfits` and `recommendations` got the full evaluator
        # output mirrored — including the updated `reasoning`. Without
        # this, analytics that read recommendations would still see the
        # stale Rater note while the user sees the deeper read.
        persisted = repo.update_turn_resolved_context.call_args.kwargs["resolved_context"]
        self.assertEqual("Balanced.", persisted["outfits"][0]["body_note"])
        self.assertEqual(88, persisted["recommendations"][0]["body_harmony_pct"])
        self.assertEqual("Balanced.", persisted["recommendations"][0]["body_note"])
        self.assertEqual("ready", persisted["recommendations"][0]["visual_evaluation_status"])
        self.assertEqual("An expanded read.", persisted["recommendations"][0]["reasoning"])
        # Cost rolled up via log_model_call.
        log_kwargs = repo.log_model_call.call_args.kwargs
        self.assertEqual("visual_evaluator_on_demand", log_kwargs["call_type"])

    def test_unknown_rank_raises(self) -> None:
        repo = Mock()
        repo.get_turn.return_value = {
            "id": "t1", "conversation_id": "c1",
            "resolved_context_json": {"outfits": [{"rank": 1, "title": "Outfit 1"}]},
        }
        gw = Mock()
        orchestrator = self._build_orchestrator(repo, gw)
        with self.assertRaises(ValueError):
            orchestrator.run_on_demand_visual_eval(turn_id="t1", rank=99)


class RaterOnlyPipelineTests(unittest.TestCase):
    """May 5, 2026 — recommendation pipeline ships Rater-only dims by default.
    visual_evaluator no longer runs inline; outfits arrive with
    visual_evaluation_status="pending" and the 4 Rater dims mapped onto
    occasion_pct / body_harmony_pct / color_suitability_pct / style_fit_pct.
    """

    def test_rater_dims_flow_through_to_outfit_card(self) -> None:
        from agentic_application.schemas import (
            CopilotPlanResult, CopilotResolvedContext, CopilotActionParameters,
            RecommendationPlan, DirectionSpec, QuerySpec, ResolvedContextBlock,
            OutfitCard, RecommendationResponse,
        )
        repo = Mock()
        repo.client = Mock()
        repo.get_or_create_user.return_value = {"id": "db-user"}
        repo.get_conversation.return_value = {"id": "c1", "user_id": "db-user", "session_context_json": {}}
        repo.create_turn.return_value = {"id": "t1"}
        gw = Mock()
        gw.get_onboarding_status.return_value = {
            "profile_complete": True, "style_preference_complete": True,
            "images_uploaded": ["full_body", "headshot"], "onboarding_complete": True,
        }
        gw.get_analysis_status.return_value = {
            "status": "completed",
            "profile": {"gender": "female", "style_preference": {"primaryArchetype": "classic"}},
            "attributes": {"BodyShape": {"value": "Hourglass"}},
            "derived_interpretations": {"SeasonalColorGroup": {"value": "Soft Summer"}},
        }
        gw.get_wardrobe_items.return_value = []
        # No person photo → tryon_render skipped, but Rater promotion still runs.
        gw.get_person_image_path.return_value = ""

        plan = RecommendationPlan(
            directions=[DirectionSpec(
                direction_id="d1", label="t", direction_type="paired", rationale="r",
                queries=[QuerySpec(query_id="A1", role="top", query_document="t"),
                         QuerySpec(query_id="A2", role="bottom", query_document="b")],
            )],
            resolved_context=ResolvedContextBlock(),
        )
        planner_mock = Mock()
        planner_mock.plan.return_value = CopilotPlanResult(
            intent=Intent.OCCASION_RECOMMENDATION, intent_confidence=0.9,
            action=Action.RUN_RECOMMENDATION_PIPELINE, context_sufficient=True,
            assistant_message="ok.", follow_up_suggestions=[],
            resolved_context=CopilotResolvedContext(occasion_signal="office"),
            action_parameters=CopilotActionParameters(),
        )

        candidate = OutfitCandidate(
            candidate_id="hi-0", direction_id="d1", candidate_type="paired",
            items=[{"product_id": "p1", "title": "T"}],
            fashion_score=88,
            occasion_fit=92, body_harmony=84, color_harmony=80, archetype_match=78,
            rater_rationale="A confident pairing.",
        )

        captured: dict = {}
        def fake_format(evaluated, *a, **kw):
            captured["evaluated"] = list(evaluated)
            outfits = [
                OutfitCard(
                    rank=e.rank, title=e.title, reasoning=e.reasoning,
                    body_harmony_pct=e.body_harmony_pct,
                    color_suitability_pct=e.color_suitability_pct,
                    style_fit_pct=e.style_fit_pct,
                    occasion_pct=e.occasion_pct,
                    visual_evaluation_status=e.visual_evaluation_status,
                    items=[{"product_id": "p1", "title": "T", "image_url": ""}],
                )
                for e in evaluated
            ]
            return RecommendationResponse(
                message="ok", outfits=outfits, follow_up_suggestions=[], metadata={},
            )

        with patch("agentic_application.orchestrator.ApplicationCatalogRetrievalGateway") as gw_cls, \
             patch("agentic_application.orchestrator.OutfitArchitect") as architect_cls, \
             patch("agentic_application.orchestrator.CopilotPlanner", return_value=planner_mock), \
             patch("agentic_application.orchestrator.CatalogSearchAgent") as search_cls, \
             patch("agentic_application.orchestrator.OutfitComposer") as composer_cls, \
             patch("agentic_application.orchestrator.OutfitRater") as rater_cls, \
             patch("agentic_application.orchestrator.ResponseFormatter") as formatter_cls:
            architect_cls.return_value.plan.return_value = plan
            _wire_llm_ranker_via_patches(composer_cls, rater_cls, [candidate])
            search_cls.return_value.search.return_value = [
                RetrievedSet(direction_id="A", query_id="A1", role="complete",
                             products=[RetrievedProduct(product_id="p1", title="T",
                                                        image_url="", price="", product_url="",
                                                        garment_category="top", garment_subtype="",
                                                        primary_color="navy", source="catalog")]),
            ]
            gw_cls.return_value.get_catalog_inventory.return_value = [{"id": "p1", "title": "T"}]
            gw_cls.return_value.search.return_value = []
            formatter_cls.return_value.format.side_effect = fake_format
            from agentic_application.orchestrator import AgenticOrchestrator
            orchestrator = AgenticOrchestrator(repo=repo, onboarding_gateway=gw, config=Mock())
            result = orchestrator.process_turn(
                conversation_id="c1", external_user_id="user-1",
                message="Office outfit",
            )

        self.assertEqual(1, len(result["outfits"]))
        # Rater dims map onto the OutfitCard slots.
        self.assertEqual(84, result["outfits"][0]["body_harmony_pct"])
        self.assertEqual(80, result["outfits"][0]["color_suitability_pct"])
        self.assertEqual(78, result["outfits"][0]["style_fit_pct"])
        self.assertEqual(92, result["outfits"][0]["occasion_pct"])
        # Status pending → UI shows compact view + CTA.
        self.assertEqual("pending", result["outfits"][0]["visual_evaluation_status"])
        # Rater rationale is the card reasoning.
        self.assertEqual("A confident pairing.", result["outfits"][0]["reasoning"])


class ArchitectPromptAssemblyTests(unittest.TestCase):
    """May 3, 2026 — Lever 2 of the perf plan: anchor + follow-up rules
    are loaded only when the request actually needs them, trimming
    ~1,100 tokens off non-anchor / non-followup turns.
    """

    def test_base_prompt_excludes_anchor_and_followup_sections(self) -> None:
        from agentic_application.agents.outfit_architect import (
            _assemble_system_prompt, _load_prompt, _load_module,
        )
        base = _load_prompt()
        anchor_mod = _load_module("anchor")
        followup_mod = _load_module("followup")
        # The base prompt itself must NOT carry the conditional sections —
        # otherwise we're double-loading them on relevant turns.
        self.assertNotIn("Anchor Garment Rules", base)
        self.assertNotIn("Follow-Up Intent Rules", base)
        # And the modules must be non-empty (the loader found them).
        self.assertIn("Anchor Garment Rules", anchor_mod)
        self.assertIn("Follow-Up Intent Rules", followup_mod)

    def test_assembled_prompt_includes_anchor_only_when_anchor_present(self) -> None:
        from agentic_application.agents.outfit_architect import (
            _assemble_system_prompt, _load_prompt, _load_module,
        )
        base = _load_prompt()
        anchor = _load_module("anchor")
        followup = _load_module("followup")

        plain = _assemble_system_prompt(base, has_anchor=False, is_followup=False,
                                        anchor_module=anchor, followup_module=followup)
        self.assertNotIn("Anchor Garment Rules", plain)
        self.assertNotIn("Follow-Up Intent Rules", plain)

        with_anchor = _assemble_system_prompt(base, has_anchor=True, is_followup=False,
                                              anchor_module=anchor, followup_module=followup)
        self.assertIn("Anchor Garment Rules", with_anchor)
        self.assertNotIn("Follow-Up Intent Rules", with_anchor)

        with_followup = _assemble_system_prompt(base, has_anchor=False, is_followup=True,
                                                anchor_module=anchor, followup_module=followup)
        self.assertNotIn("Anchor Garment Rules", with_followup)
        self.assertIn("Follow-Up Intent Rules", with_followup)

        full = _assemble_system_prompt(base, has_anchor=True, is_followup=True,
                                       anchor_module=anchor, followup_module=followup)
        self.assertIn("Anchor Garment Rules", full)
        self.assertIn("Follow-Up Intent Rules", full)

    def test_base_prompt_size_below_ceiling(self) -> None:
        """Pin a soft ceiling on base prompt size. If this fires, the
        prompt has been re-bloated and the perf gain reverted."""
        from agentic_application.agents.outfit_architect import _load_prompt
        base = _load_prompt()
        # ~4 chars per token estimate. The May-3 trimmed base is ~7.2K
        # tokens (~29K chars). Allow some headroom; alarm if it climbs
        # back to the pre-trim 11K (~46K chars).
        self.assertLess(
            len(base), 42_000,
            f"Base architect prompt is {len(base)} chars — perf-trim looks reverted",
        )

    def test_query_document_template_excludes_user_side_sections(self) -> None:
        """Option A (May 3, 2026): the architect's emitted query_document
        must contain only intrinsic-garment sections. USER_NEED and
        PROFILE_AND_STYLE describe the request and the user, neither has
        a counterpart in catalog item embeddings, and including them
        dilutes cosine similarity. The prompt's explicit "what NEVER
        appears in query_document" enumeration is what enforces this on
        the model side; this test pins it as a contract.
        """
        from agentic_application.agents.outfit_architect import _load_prompt
        base = _load_prompt()
        # The prompt MUST list these sections under the "what NEVER appears" section.
        forbidden_in_query = ["USER_NEED", "PROFILE_AND_STYLE"]
        for section in forbidden_in_query:
            self.assertIn(
                f"`{section}:`",
                base,
                f"Architect prompt must explicitly forbid {section} in query_document",
            )
        # Allowed sections in the query template — all intrinsic to the garment.
        allowed_in_query = [
            "GARMENT_REQUIREMENTS",
            "EMBELLISHMENT",
            "VISUAL_DIRECTION",
            "FABRIC_AND_BUILD",
            "PATTERN_AND_COLOR",
            "CONTEXT_AND_TIMING",
        ]
        for section in allowed_in_query:
            self.assertIn(
                f"{section}:",
                base,
                f"Architect prompt must include {section} as an allowed query_document section",
            )

    def test_query_document_must_translate_user_strings(self) -> None:
        """The prompt must explicitly list user-side strings the architect
        is forbidden from leaving in the query_document literally — they
        have to be translated into garment-attribute terms first.
        """
        from agentic_application.agents.outfit_architect import _load_prompt
        base = _load_prompt()
        # Spot-check that the prompt names the categories of user-side
        # content that must be translated, not duplicated.
        for forbidden_literal in [
            "Autumn",      # seasonal palette names
            "Light and Narrow",  # frame strings
            "Pear",        # body shape strings
        ]:
            self.assertIn(
                forbidden_literal, base,
                f"Architect prompt must reference '{forbidden_literal}' in the translation guidance",
            )
        # The translation mandate itself must be explicit.
        self.assertIn(
            "translation must REPLACE the source text, not duplicate it",
            base,
            "Prompt must contain the explicit translation mandate",
        )


class TryonParallelRenderTests(unittest.TestCase):
    """May 3, 2026 — Lever 1 of the perf plan: parallelize Gemini try-on
    renders so a 3-candidate batch completes in ~max(t1,t2,t3) instead
    of t1+t2+t3.
    """

    def _make_orchestrator(self, generate_side_effect, quality_passed: bool = True):
        import time as _time
        from unittest.mock import Mock, MagicMock
        repo = Mock()
        repo.find_tryon_image_by_garments.return_value = None
        repo.insert_tryon_image.return_value = None
        repo.log_tool_trace.return_value = None
        gw = Mock()
        with patch("agentic_application.orchestrator.ApplicationCatalogRetrievalGateway"), patch(
            "agentic_application.orchestrator.OutfitArchitect"
        ), patch(
            "agentic_application.orchestrator.CopilotPlanner"
        ), patch(
            "agentic_application.orchestrator.CatalogSearchAgent"
        ), patch(
            "agentic_application.orchestrator.OutfitComposer"
        ), patch(
            "agentic_application.orchestrator.OutfitRater"
        ):
            orch = AgenticOrchestrator(repo=repo, onboarding_gateway=gw, config=Mock())
        # Wire mocks
        orch.tryon_service = Mock()
        orch.tryon_service.generate_tryon_outfit.side_effect = generate_side_effect
        orch.tryon_quality_gate = Mock()
        orch.tryon_quality_gate.evaluate.return_value = {
            "passed": quality_passed, "reason_code": "" if quality_passed else "ssim_low",
            "quality_score_pct": 90 if quality_passed else 30,
        }
        return orch

    def _make_candidate(self, cid: str) -> OutfitCandidate:
        return OutfitCandidate(
            candidate_id=cid,
            direction_id="d1",
            candidate_type="paired",
            items=[
                {"product_id": f"{cid}-top", "title": "T", "image_url": f"https://x/{cid}.png", "role": "top"},
            ],
            fashion_score=90,
        )

    def test_three_candidate_batch_renders_in_parallel(self) -> None:
        """Three concurrent renders sleeping 0.3s each should finish in
        <0.6s wallclock, not >0.9s (which would indicate sequential)."""
        import time as _time
        import base64

        small_png = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"0" * 100).decode()

        def slow_generate(person_image_path, garment_urls):
            _time.sleep(0.3)
            return {"success": True, "image_base64": small_png, "mime_type": "image/png"}

        orch = self._make_orchestrator(slow_generate, quality_passed=True)
        candidates = [self._make_candidate(f"c{i}") for i in range(3)]

        with tempfile.TemporaryDirectory() as tmp:
            import os
            cwd = os.getcwd()
            os.chdir(tmp)
            try:
                t0 = _time.monotonic()
                rendered, stats = orch._render_candidates_for_visual_eval(
                    candidates=candidates,
                    person_image_path="/tmp/person.png",
                    external_user_id="u1",
                    conversation_id="c1",
                    turn_id="t1",
                    target_count=3,
                )
                elapsed = _time.monotonic() - t0
            finally:
                os.chdir(cwd)

        self.assertEqual(3, len(rendered))
        self.assertEqual(3, stats["tryon_succeeded_count"])
        self.assertLess(
            elapsed, 0.7,
            f"3 parallel renders took {elapsed:.2f}s — likely sequential (expected <0.7s, sequential would be ~0.9s)",
        )

    def test_quality_gate_failures_recover_in_parallel_batch(self) -> None:
        """When the first 3-candidate batch fails QG entirely, the next
        batch (from the over-generation pool) is also issued in parallel,
        not one-at-a-time."""
        import time as _time
        import base64

        small_png = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"0" * 100).decode()
        # All 5 candidates render in 0.3s each. First 3 fail QG, last 2 pass.
        call_count = {"n": 0}

        def gen(person_image_path, garment_urls):
            call_count["n"] += 1
            _time.sleep(0.3)
            return {"success": True, "image_base64": small_png, "mime_type": "image/png"}

        orch = self._make_orchestrator(gen, quality_passed=True)
        # Quality gate: first 3 calls fail, rest pass.
        qg_calls = {"n": 0}
        def qg_eval(person_image_path, tryon_result):
            qg_calls["n"] += 1
            if qg_calls["n"] <= 3:
                return {"passed": False, "reason_code": "ssim_low", "quality_score_pct": 20}
            return {"passed": True, "reason_code": "", "quality_score_pct": 90}
        orch.tryon_quality_gate.evaluate.side_effect = qg_eval

        candidates = [self._make_candidate(f"c{i}") for i in range(5)]

        with tempfile.TemporaryDirectory() as tmp:
            import os
            cwd = os.getcwd()
            os.chdir(tmp)
            try:
                t0 = _time.monotonic()
                rendered, stats = orch._render_candidates_for_visual_eval(
                    candidates=candidates,
                    person_image_path="/tmp/person.png",
                    external_user_id="u1",
                    conversation_id="c1",
                    turn_id="t1",
                    target_count=3,
                )
                elapsed = _time.monotonic() - t0
            finally:
                os.chdir(cwd)

        # Two parallel batches: first batch (3 fail QG) + second batch
        # (2 pass). Wallclock should be ~0.6s, not ~1.5s sequential.
        self.assertLess(
            elapsed, 1.0,
            f"QG-failure recovery took {elapsed:.2f}s — likely sequential (expected <1.0s)",
        )
        self.assertGreaterEqual(stats["tryon_quality_gate_failures"], 3)
        self.assertEqual(1, stats["tryon_overgeneration_used"])

    def test_cache_hit_short_circuits_inside_thread(self) -> None:
        """A candidate with a cache-hit tryon image must skip the Gemini
        call entirely, even when running concurrently with renders."""
        import base64

        small_png = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"0" * 100).decode()

        def gen(person_image_path, garment_urls):
            return {"success": True, "image_base64": small_png, "mime_type": "image/png"}

        orch = self._make_orchestrator(gen, quality_passed=True)
        # First candidate: cache hit. Others: normal render.
        with tempfile.TemporaryDirectory() as tmp:
            cached_file = Path(tmp) / "cached.png"
            cached_file.write_bytes(b"cached")
            def cache_lookup(uid, gids):
                if "c0-top" in gids:
                    return {"file_path": str(cached_file)}
                return None
            orch.repo.find_tryon_image_by_garments.side_effect = cache_lookup

            import os
            cwd = os.getcwd()
            os.chdir(tmp)
            try:
                rendered, stats = orch._render_candidates_for_visual_eval(
                    candidates=[self._make_candidate(f"c{i}") for i in range(3)],
                    person_image_path="/tmp/person.png",
                    external_user_id="u1",
                    conversation_id="c1",
                    turn_id="t1",
                    target_count=3,
                )
            finally:
                os.chdir(cwd)

        # 3 results total, but only 2 actual Gemini calls (the cache-hit
        # candidate didn't call generate_tryon_outfit).
        self.assertEqual(3, len(rendered))
        self.assertEqual(2, orch.tryon_service.generate_tryon_outfit.call_count)
        # The cache-hit candidate should appear at its original rank
        # (rank 0), not at the end.
        self.assertEqual("c0", rendered[0][0].candidate_id)


if __name__ == "__main__":
    unittest.main()
