import sys
import unittest
import json
from pathlib import Path
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
for p in (
    ROOT,
    ROOT / "modules" / "user" / "src",
    ROOT / "modules" / "agentic_application" / "src",
    ROOT / "modules" / "catalog" / "src",
    ROOT / "modules" / "catalog_retrieval" / "src",
    ROOT / "modules" / "platform_core" / "src",
    ROOT / "modules" / "user_profiler" / "src",
    ROOT / "modules" / "onboarding" / "src",
):
    sp = str(p)
    if sp not in sys.path:
        sys.path.insert(0, sp)


from agentic_application.agents.catalog_search_agent import CatalogSearchAgent
from agentic_application.agents.outfit_assembler import OutfitAssembler
from agentic_application.agents.response_formatter import ResponseFormatter
from agentic_application.agents.outfit_architect import OutfitArchitect
from agentic_application.agents.outfit_evaluator import _build_eval_payload, OutfitEvaluator
from agentic_application.context.conversation_memory import (
    apply_conversation_memory,
    build_conversation_memory,
)
from agentic_application.context.occasion_resolver import resolve_occasion
from agentic_application.orchestrator import AgenticOrchestrator
from agentic_application.product_links import resolve_product_url
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
    RetrievedProduct,
    RetrievedSet,
    UserContext,
)


class AgenticApplicationTests(unittest.TestCase):
    def test_occasion_resolver_prefers_specific_phrases(self) -> None:
        smart_casual = resolve_occasion("Need a smart casual look")
        work_meeting = resolve_occasion("Need an outfit for a work meeting")

        self.assertEqual("smart_casual", smart_casual.occasion_signal)
        self.assertEqual("work_meeting", work_meeting.occasion_signal)

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

        live_context = resolve_occasion(
            "Show me something bolder",
            has_previous_recommendations=True,
        )
        memory = build_conversation_memory(previous_context, live_context)
        effective = apply_conversation_memory(live_context, memory)

        self.assertTrue(effective.is_followup)
        self.assertEqual("wedding", effective.occasion_signal)
        self.assertEqual("formal", effective.formality_hint)
        self.assertIn("elongation", effective.specific_needs)
        self.assertEqual(2, memory.followup_count)

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
                                "- StylingCompleteness: needs_pairing\n"
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

        agent.search(plan, context, relaxed_filter_keys=["occasion_fit"])

        filters = retrieval_gateway.similarity_search.call_args.kwargs["filters"]
        self.assertEqual("feminine", filters["gender_expression"])
        self.assertEqual("needs_pairing", filters["styling_completeness"])
        self.assertEqual("top", filters["garment_category"])
        self.assertEqual("blouse", filters["garment_subtype"])
        self.assertEqual("smart_casual", filters["formality_level"])
        self.assertEqual("evening", filters["time_of_day"])
        self.assertNotIn("occasion_fit", filters)

    def test_outfit_architect_falls_back_to_deterministic_plan(self) -> None:
        context = CombinedContext(
            user=UserContext(
                user_id="u1",
                gender="female",
                derived_interpretations={
                    "SeasonalColorGroup": {"value": "Soft Summer"},
                    "ContrastLevel": {"value": "Medium"},
                    "FrameStructure": {"value": "Balanced"},
                    "HeightCategory": {"value": "Tall"},
                    "WaistSizeBand": {"value": "Medium"},
                },
                style_preference={
                    "primaryArchetype": "classic",
                    "patternType": "solid",
                },
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
            plan = architect.plan(context)

        self.assertEqual("fallback", plan.plan_source)
        self.assertEqual("paired_only", plan.plan_type)
        self.assertEqual("needs_pairing", plan.directions[0].queries[0].hard_filters["styling_completeness"])
        self.assertIn("PrimaryColor: blue", plan.directions[0].queries[0].query_document)

    def test_outfit_architect_similar_to_previous_uses_prior_recommendation_color(self) -> None:
        context = CombinedContext(
            user=UserContext(
                user_id="u1",
                gender="female",
                derived_interpretations={"SeasonalColorGroup": {"value": "Soft Summer"}},
                style_preference={"primaryArchetype": "classic", "patternType": "solid"},
                profile_richness="full",
            ),
            live=LiveContext(
                user_need="Show me something similar",
                is_followup=True,
                followup_intent="similar_to_previous",
            ),
            hard_filters={"gender_expression": "feminine"},
            previous_recommendations=[{"primary_colors": ["burgundy"]}],
        )

        with patch("agentic_application.agents.outfit_architect.get_api_key", return_value="x"), patch(
            "agentic_application.agents.outfit_architect.OpenAI"
        ) as openai_cls:
            openai_cls.return_value.responses.create.side_effect = RuntimeError("boom")
            architect = OutfitArchitect()
            plan = architect.plan(context)

        self.assertIn("PrimaryColor: burgundy", plan.directions[0].queries[0].query_document)

    def test_outfit_architect_similar_to_previous_preserves_prior_plan_shape(self) -> None:
        context = CombinedContext(
            user=UserContext(
                user_id="u1",
                gender="female",
                derived_interpretations={"SeasonalColorGroup": {"value": "Soft Summer"}},
                style_preference={"primaryArchetype": "classic", "patternType": "solid"},
                profile_richness="full",
            ),
            live=LiveContext(
                user_need="Show me something similar",
                is_followup=True,
                followup_intent="similar_to_previous",
            ),
            hard_filters={"gender_expression": "feminine"},
            previous_recommendations=[
                {
                    "candidate_type": "paired",
                    "primary_colors": ["navy"],
                    "occasion_fits": ["date_night"],
                }
            ],
        )

        with patch("agentic_application.agents.outfit_architect.get_api_key", return_value="x"), patch(
            "agentic_application.agents.outfit_architect.OpenAI"
        ) as openai_cls:
            openai_cls.return_value.responses.create.side_effect = RuntimeError("boom")
            architect = OutfitArchitect()
            plan = architect.plan(context)

        self.assertEqual("paired_only", plan.plan_type)
        self.assertIn("OccasionFit: date_night", plan.directions[0].queries[0].query_document)
        self.assertIn("PrimaryColor: navy", plan.directions[0].queries[0].query_document)

    def test_outfit_architect_similar_to_previous_preserves_prior_silhouette_signals(self) -> None:
        context = CombinedContext(
            user=UserContext(
                user_id="u1",
                gender="female",
                derived_interpretations={"SeasonalColorGroup": {"value": "Soft Summer"}},
                style_preference={"primaryArchetype": "classic", "patternType": "solid"},
                profile_richness="full",
            ),
            live=LiveContext(
                user_need="Show me something similar",
                is_followup=True,
                followup_intent="similar_to_previous",
            ),
            hard_filters={"gender_expression": "feminine"},
            previous_recommendations=[
                {
                    "candidate_type": "paired",
                    "volume_profiles": ["oversized"],
                    "fit_types": ["relaxed"],
                    "silhouette_types": ["draped"],
                    "pattern_types": ["striped"],
                }
            ],
        )

        with patch("agentic_application.agents.outfit_architect.get_api_key", return_value="x"), patch(
            "agentic_application.agents.outfit_architect.OpenAI"
        ) as openai_cls:
            openai_cls.return_value.responses.create.side_effect = RuntimeError("boom")
            architect = OutfitArchitect()
            plan = architect.plan(context)

        query_document = plan.directions[0].queries[0].query_document
        self.assertIn("VolumeProfile: oversized", query_document)
        self.assertIn("FitType: relaxed", query_document)
        self.assertIn("SilhouetteType: draped", query_document)
        self.assertIn("PatternType: striped", query_document)

    def test_outfit_architect_change_color_mentions_prior_color_shift(self) -> None:
        context = CombinedContext(
            user=UserContext(
                user_id="u1",
                gender="female",
                derived_interpretations={"SeasonalColorGroup": {"value": "Soft Summer"}},
                style_preference={"primaryArchetype": "classic", "patternType": "solid"},
                profile_richness="full",
            ),
            live=LiveContext(
                user_need="Show me a different color",
                is_followup=True,
                followup_intent="change_color",
            ),
            hard_filters={"gender_expression": "feminine"},
            previous_recommendations=[{"primary_colors": ["navy"]}],
        )

        with patch("agentic_application.agents.outfit_architect.get_api_key", return_value="x"), patch(
            "agentic_application.agents.outfit_architect.OpenAI"
        ) as openai_cls:
            openai_cls.return_value.responses.create.side_effect = RuntimeError("boom")
            architect = OutfitArchitect()
            plan = architect.plan(context)

        self.assertIn(
            "styling_goal: change color direction away from navy",
            plan.directions[0].queries[0].query_document,
        )

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
            metadata={"plan_type": "mixed", "plan_source": "fallback"},
        )
        plan = RecommendationPlan(
            plan_type="mixed",
            retrieval_count=8,
            plan_source="fallback",
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

        self.assertEqual("fallback", resolved_context["plan"]["plan_source"])
        self.assertEqual("wedding", resolved_context["conversation_memory"]["occasion_signal"])
        self.assertEqual("complete", resolved_context["retrieval"][0]["applied_filters"]["styling_completeness"])
        self.assertEqual(2, session_context["memory"]["followup_count"])
        self.assertEqual("feminine", result["filters_applied"]["gender_expression"])
        self.assertEqual(["blue"], session_context["last_recommendations"][0]["primary_colors"])
        self.assertEqual("complete", session_context["last_recommendations"][0]["candidate_type"])
        self.assertEqual(["wedding"], session_context["last_recommendations"][0]["occasion_fits"])
        self.assertEqual(["formal"], session_context["last_recommendations"][0]["formality_levels"])

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

        self.assertEqual(5, len(response.outfits))
        self.assertEqual(5, response.metadata["outfit_count"])
        self.assertEqual([1, 2, 3, 4, 5], [outfit.rank for outfit in response.outfits])

    def test_resolve_product_url_returns_empty_when_no_canonical_url_exists(self) -> None:
        result = resolve_product_url(
            raw_url="",
            store="andamen",
            handle="palm-green-cotton-resort-shirt",
        )

        self.assertEqual("", result)


if __name__ == "__main__":
    unittest.main()
