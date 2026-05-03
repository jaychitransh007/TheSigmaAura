"""Unit tests for OutfitRater (May 3 2026).

The Rater scores Composer-built outfits on a 4-dim rubric, computes a
fashion_score, and emits a ranked list with optional unsuitable veto.
LLM is mocked; tests focus on:
- contract: required fields, ID round-tripping
- defensive ordering: result is sorted by fashion_score desc even if
  the LLM emits a bad rank order
- score clamping: out-of-range scores get pulled to 0..100
- empty input short-circuits before the LLM call
"""

from __future__ import annotations

import json
import sys
import unittest
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

from agentic_application.agents.outfit_rater import OutfitRater
from agentic_application.schemas import (
    CombinedContext,
    ComposedOutfit,
    LiveContext,
    RetrievedProduct,
    RetrievedSet,
    UserContext,
)


def _ctx() -> CombinedContext:
    return CombinedContext(
        user=UserContext(
            user_id="u1",
            gender="male",
            style_preference={"primaryArchetype": "classic", "riskTolerance": "low"},
            derived_interpretations={"BodyShape": {"value": "rectangle"}},
        ),
        live=LiveContext(
            user_need="Need an outfit for daily office.",
            occasion_signal="daily_office",
            formality_hint="smart_casual",
        ),
        hard_filters={"gender_expression": "masculine"},
    )


def _composed() -> list[ComposedOutfit]:
    return [
        ComposedOutfit(composer_id="C1", direction_id="B", direction_type="paired",
                       item_ids=["b_t1", "b_b1"], rationale="Shirt + trouser smart_casual."),
        ComposedOutfit(composer_id="C2", direction_id="B", direction_type="paired",
                       item_ids=["b_t2", "b_b2"], rationale="Polo + jeans, more relaxed."),
        ComposedOutfit(composer_id="C3", direction_id="A", direction_type="complete",
                       item_ids=["a_set1"], rationale="Complete suit_set."),
    ]


def _retrieved() -> list[RetrievedSet]:
    """Pool the Rater uses to look up item attrs by id."""
    p = lambda pid, **kw: RetrievedProduct(
        product_id=pid, similarity=0.9,
        metadata={"title": f"Product {pid}"},
        enriched_data={**kw},
    )
    return [
        RetrievedSet(direction_id="A", query_id="A1", role="complete", products=[
            p("a_set1", garment_subtype="suit_set", formality_level="formal"),
        ]),
        RetrievedSet(direction_id="B", query_id="B1", role="top", products=[
            p("b_t1", garment_subtype="shirt", formality_level="smart_casual"),
            p("b_t2", garment_subtype="polo", formality_level="casual"),
        ]),
        RetrievedSet(direction_id="B", query_id="B2", role="bottom", products=[
            p("b_b1", garment_subtype="trouser", formality_level="smart_casual"),
            p("b_b2", garment_subtype="jeans", formality_level="casual"),
        ]),
    ]


def _mock_response(payload: dict) -> Mock:
    m = Mock()
    m.output_text = json.dumps(payload)
    return m


def _patch_rater():
    return patch("agentic_application.agents.outfit_rater.OpenAI")


class OutfitRaterContractTests(unittest.TestCase):

    def test_rater_returns_scores_for_each_composed_outfit(self) -> None:
        payload = {
            "ranked_outfits": [
                {"composer_id": "C1", "rank": 1, "fashion_score": 88,
                 "occasion_fit": 92, "body_harmony": 85, "color_harmony": 88, "archetype_match": 86,
                 "rationale": "Strong on occasion fit, balanced silhouette.", "unsuitable": False},
                {"composer_id": "C2", "rank": 2, "fashion_score": 70,
                 "occasion_fit": 65, "body_harmony": 80, "color_harmony": 70, "archetype_match": 70,
                 "rationale": "Reads more casual than the brief.", "unsuitable": False},
                {"composer_id": "C3", "rank": 3, "fashion_score": 55,
                 "occasion_fit": 50, "body_harmony": 60, "color_harmony": 55, "archetype_match": 55,
                 "rationale": "Suit is too formal for daily office.", "unsuitable": False},
            ],
            "overall_assessment": "moderate",
        }
        with patch("agentic_application.agents.outfit_rater.get_api_key", return_value="x"), _patch_rater() as oc:
            oc.return_value.responses.create.return_value = _mock_response(payload)
            result = OutfitRater().rate(_ctx(), _composed(), _retrieved())

        self.assertEqual(3, len(result.ranked_outfits))
        self.assertEqual([1, 2, 3], [r.rank for r in result.ranked_outfits])
        self.assertEqual("C1", result.ranked_outfits[0].composer_id)
        self.assertEqual(88, result.ranked_outfits[0].fashion_score)
        self.assertEqual("moderate", result.overall_assessment)


class OutfitRaterDefensiveTests(unittest.TestCase):

    def test_rater_resorts_by_fashion_score_when_llm_emits_bad_ranks(self) -> None:
        """The prompt asks the model to sort by fashion_score; the agent
        re-sorts defensively in case the model's own ordering is wrong.
        Here C2 has the highest score but the LLM placed it third."""
        payload = {
            "ranked_outfits": [
                {"composer_id": "C1", "rank": 1, "fashion_score": 60,
                 "occasion_fit": 60, "body_harmony": 60, "color_harmony": 60, "archetype_match": 60,
                 "rationale": "ok", "unsuitable": False},
                {"composer_id": "C3", "rank": 2, "fashion_score": 70,
                 "occasion_fit": 70, "body_harmony": 70, "color_harmony": 70, "archetype_match": 70,
                 "rationale": "good", "unsuitable": False},
                {"composer_id": "C2", "rank": 3, "fashion_score": 95,
                 "occasion_fit": 95, "body_harmony": 95, "color_harmony": 95, "archetype_match": 95,
                 "rationale": "best", "unsuitable": False},
            ],
            "overall_assessment": "strong",
        }
        with patch("agentic_application.agents.outfit_rater.get_api_key", return_value="x"), _patch_rater() as oc:
            oc.return_value.responses.create.return_value = _mock_response(payload)
            result = OutfitRater().rate(_ctx(), _composed(), _retrieved())

        self.assertEqual(["C2", "C3", "C1"], [r.composer_id for r in result.ranked_outfits])
        self.assertEqual([1, 2, 3], [r.rank for r in result.ranked_outfits])

    def test_rater_clamps_out_of_range_scores(self) -> None:
        """LLM occasionally emits scores outside 0..100 (e.g., 0..10
        scale by mistake). Agent clamps before downstream uses them."""
        payload = {
            "ranked_outfits": [
                {"composer_id": "C1", "rank": 1, "fashion_score": 150,
                 "occasion_fit": 200, "body_harmony": -5, "color_harmony": 50, "archetype_match": 9,
                 "rationale": "weird scales", "unsuitable": False},
            ],
            "overall_assessment": "moderate",
        }
        with patch("agentic_application.agents.outfit_rater.get_api_key", return_value="x"), _patch_rater() as oc:
            oc.return_value.responses.create.return_value = _mock_response(payload)
            result = OutfitRater().rate(_ctx(), _composed(), _retrieved())

        ro = result.ranked_outfits[0]
        self.assertEqual(100, ro.fashion_score)
        self.assertEqual(100, ro.occasion_fit)
        self.assertEqual(0, ro.body_harmony)
        self.assertEqual(50, ro.color_harmony)
        self.assertEqual(9, ro.archetype_match)

    def test_rater_drops_unknown_composer_ids(self) -> None:
        """The LLM should never invent composer_ids outside the input
        slate. If it does, drop them — preserves the contract that
        ranked_outfits is a subset of the input."""
        payload = {
            "ranked_outfits": [
                {"composer_id": "C1", "rank": 1, "fashion_score": 80,
                 "occasion_fit": 80, "body_harmony": 80, "color_harmony": 80, "archetype_match": 80,
                 "rationale": "valid", "unsuitable": False},
                {"composer_id": "BOGUS", "rank": 2, "fashion_score": 90,
                 "occasion_fit": 90, "body_harmony": 90, "color_harmony": 90, "archetype_match": 90,
                 "rationale": "hallucinated id", "unsuitable": False},
            ],
            "overall_assessment": "strong",
        }
        with patch("agentic_application.agents.outfit_rater.get_api_key", return_value="x"), _patch_rater() as oc:
            oc.return_value.responses.create.return_value = _mock_response(payload)
            result = OutfitRater().rate(_ctx(), _composed(), _retrieved())

        self.assertEqual(1, len(result.ranked_outfits))
        self.assertEqual("C1", result.ranked_outfits[0].composer_id)


class OutfitRaterEdgeCaseTests(unittest.TestCase):

    def test_rater_short_circuits_on_empty_input(self) -> None:
        with patch("agentic_application.agents.outfit_rater.get_api_key", return_value="x"), _patch_rater() as oc:
            result = OutfitRater().rate(_ctx(), [], _retrieved())

        oc.return_value.responses.create.assert_not_called()
        self.assertEqual(0, len(result.ranked_outfits))

    def test_rater_handles_malformed_json(self) -> None:
        bad = Mock()
        bad.output_text = "not json{"
        with patch("agentic_application.agents.outfit_rater.get_api_key", return_value="x"), _patch_rater() as oc:
            oc.return_value.responses.create.return_value = bad
            result = OutfitRater().rate(_ctx(), _composed(), _retrieved())

        self.assertEqual(0, len(result.ranked_outfits))
        self.assertEqual("weak", result.overall_assessment)

    def test_rater_honours_unsuitable_flag(self) -> None:
        """An unsuitable=True outfit still appears in the result so the
        orchestrator can log + drop it; the flag is not a silent skip."""
        payload = {
            "ranked_outfits": [
                {"composer_id": "C1", "rank": 1, "fashion_score": 30,
                 "occasion_fit": 25, "body_harmony": 50, "color_harmony": 30, "archetype_match": 25,
                 "rationale": "Dealbreaker — wrong occasion entirely.", "unsuitable": True},
            ],
            "overall_assessment": "weak",
        }
        with patch("agentic_application.agents.outfit_rater.get_api_key", return_value="x"), _patch_rater() as oc:
            oc.return_value.responses.create.return_value = _mock_response(payload)
            result = OutfitRater().rate(_ctx(), _composed(), _retrieved())

        self.assertEqual(1, len(result.ranked_outfits))
        self.assertTrue(result.ranked_outfits[0].unsuitable)


if __name__ == "__main__":
    unittest.main()
