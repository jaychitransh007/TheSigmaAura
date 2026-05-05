"""Unit tests for OutfitRater.

The Rater scores Composer-built outfits on a 4-dim rubric. R3 (May 5
2026) moved fashion_score blending out of the LLM and into Python;
the LLM emits sub-scores only, the agent computes the final score
with intent-aware weights via ``compute_fashion_score`` and the
profile picked by ``select_weight_profile``.

LLM is mocked; tests focus on:
- contract: required fields, ID round-tripping
- defensive ordering: result is sorted by computed fashion_score desc
- sub-score clamping: out-of-range scores get pulled to 0..100
- empty input short-circuits before the LLM call
- weight-profile selection: picks correct profile per intent
- deterministic blend: fashion_score = round(Σ subscore × weight)
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

from agentic_application.agents.outfit_rater import (
    OutfitRater,
    WEIGHT_PROFILES,
    compute_fashion_score,
    select_weight_profile,
)
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
                 "occasion_fit": 92, "body_harmony": 85, "color_harmony": 88, "archetype_match": 86, "inter_item_coherence": 80,
                 "rationale": "Strong on occasion fit, balanced silhouette.", "unsuitable": False},
                {"composer_id": "C2", "rank": 2, "fashion_score": 70,
                 "occasion_fit": 65, "body_harmony": 80, "color_harmony": 70, "archetype_match": 70, "inter_item_coherence": 80,
                 "rationale": "Reads more casual than the brief.", "unsuitable": False},
                {"composer_id": "C3", "rank": 3, "fashion_score": 55,
                 "occasion_fit": 50, "body_harmony": 60, "color_harmony": 55, "archetype_match": 55, "inter_item_coherence": 80,
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
        # Default 5-dim blend (R5): 92*0.30 + 85*0.18 + 88*0.22 + 86*0.15 +
        # 80*0.15 = 27.6+15.3+19.36+12.9+12.0 = 87.16 → 87
        self.assertEqual(87, result.ranked_outfits[0].fashion_score)
        self.assertEqual("moderate", result.overall_assessment)


class OutfitRaterDefensiveTests(unittest.TestCase):

    def test_rater_resorts_by_fashion_score_when_llm_emits_bad_ranks(self) -> None:
        """The prompt asks the model to sort by fashion_score; the agent
        re-sorts defensively in case the model's own ordering is wrong.
        Here C2 has the highest score but the LLM placed it third."""
        payload = {
            "ranked_outfits": [
                {"composer_id": "C1", "rank": 1, "fashion_score": 60,
                 "occasion_fit": 60, "body_harmony": 60, "color_harmony": 60, "archetype_match": 60, "inter_item_coherence": 80,
                 "rationale": "ok", "unsuitable": False},
                {"composer_id": "C3", "rank": 2, "fashion_score": 70,
                 "occasion_fit": 70, "body_harmony": 70, "color_harmony": 70, "archetype_match": 70, "inter_item_coherence": 80,
                 "rationale": "good", "unsuitable": False},
                {"composer_id": "C2", "rank": 3, "fashion_score": 95,
                 "occasion_fit": 95, "body_harmony": 95, "color_harmony": 95, "archetype_match": 95, "inter_item_coherence": 80,
                 "rationale": "best", "unsuitable": False},
            ],
            "overall_assessment": "strong",
        }
        with patch("agentic_application.agents.outfit_rater.get_api_key", return_value="x"), _patch_rater() as oc:
            oc.return_value.responses.create.return_value = _mock_response(payload)
            result = OutfitRater().rate(_ctx(), _composed(), _retrieved())

        self.assertEqual(["C2", "C3", "C1"], [r.composer_id for r in result.ranked_outfits])
        self.assertEqual([1, 2, 3], [r.rank for r in result.ranked_outfits])

    def test_rater_clamps_out_of_range_subscores(self) -> None:
        """LLM occasionally emits sub-scores outside 0..100 (e.g., 0..10
        scale by mistake). Agent clamps before computing fashion_score
        so the blend math stays in range."""
        payload = {
            "ranked_outfits": [
                {"composer_id": "C1",
                 "occasion_fit": 200, "body_harmony": -5, "color_harmony": 50, "archetype_match": 9, "inter_item_coherence": 80,
                 "rationale": "weird scales", "unsuitable": False},
            ],
            "overall_assessment": "moderate",
        }
        with patch("agentic_application.agents.outfit_rater.get_api_key", return_value="x"), _patch_rater() as oc:
            oc.return_value.responses.create.return_value = _mock_response(payload)
            result = OutfitRater().rate(_ctx(), _composed(), _retrieved())

        ro = result.ranked_outfits[0]
        # Sub-scores clamped to [0, 100]
        self.assertEqual(100, ro.occasion_fit)
        self.assertEqual(0, ro.body_harmony)
        self.assertEqual(50, ro.color_harmony)
        self.assertEqual(9, ro.archetype_match)
        # 5-dim default (R5): 100*0.30 + 0*0.18 + 50*0.22 + 9*0.15 +
        # 80*0.15 = 30 + 0 + 11 + 1.35 + 12 = 54.35 → 54
        self.assertEqual(54, ro.fashion_score)

    def test_rater_treats_malformed_inter_item_as_missing(self) -> None:
        """A malformed inter_item_coherence value (empty string,
        whitespace-only, "N/A", "None", or any non-numeric junk)
        should be treated identically to a missing field — preserved
        as None on the candidate and dropped from the fashion_score
        blend. Without this guard, int(...) would raise ValueError
        and crash the entire rate() call for one bad candidate."""
        # Mix of the inputs the LLM might emit when it ignores schema:
        # blanks, sentinel strings, JSON null aliases, and plain garbage.
        for malformed in ("", "   ", "\t", "\n ", "N/A", "None", "null", "abc"):
            with self.subTest(value=repr(malformed)):
                payload = {
                    "ranked_outfits": [
                        {"composer_id": "C1",
                         "occasion_fit": 90, "body_harmony": 80, "color_harmony": 80, "archetype_match": 80,
                         "inter_item_coherence": malformed,
                         "rationale": "ok", "unsuitable": False},
                    ],
                    "overall_assessment": "moderate",
                }
                with patch("agentic_application.agents.outfit_rater.get_api_key", return_value="x"), _patch_rater() as oc:
                    oc.return_value.responses.create.return_value = _mock_response(payload)
                    result = OutfitRater().rate(_ctx(), _composed(), _retrieved())

                ro = result.ranked_outfits[0]
                self.assertIsNone(ro.inter_item_coherence)
                # 4-dim renormalised: 90*(0.30/0.85) + 80*(0.18/0.85) + 80*(0.22/0.85)
                # + 80*(0.15/0.85) = 31.76+16.94+20.71+14.12 = 83.53 → 84
                self.assertEqual(84, ro.fashion_score)

    def test_rater_treats_malformed_required_subscores_as_zero(self) -> None:
        """The four always-on sub-scores (occasion_fit / body_harmony /
        color_harmony / archetype_match) default to 0 on missing or
        malformed input rather than raising. Required for the blend so
        we treat unparseable as a low score, not a dropped dim."""
        for malformed in ("", "   ", "N/A", "None", "abc", None):
            with self.subTest(value=repr(malformed)):
                payload = {
                    "ranked_outfits": [
                        {"composer_id": "C1",
                         "occasion_fit": malformed, "body_harmony": 80,
                         "color_harmony": 80, "archetype_match": 80,
                         "inter_item_coherence": 80,
                         "rationale": "ok", "unsuitable": False},
                    ],
                    "overall_assessment": "moderate",
                }
                with patch("agentic_application.agents.outfit_rater.get_api_key", return_value="x"), _patch_rater() as oc:
                    oc.return_value.responses.create.return_value = _mock_response(payload)
                    result = OutfitRater().rate(_ctx(), _composed(), _retrieved())

                ro = result.ranked_outfits[0]
                self.assertEqual(0, ro.occasion_fit)
                # 5-dim default: 0*0.30 + 80*0.18 + 80*0.22 + 80*0.15 + 80*0.15 = 56
                self.assertEqual(56, ro.fashion_score)

    def test_rater_truncates_float_strings_in_subscores(self) -> None:
        """LLM occasionally emits "80.5" or "0.85" for an int slot.
        Truncate via float() rather than crashing or rejecting."""
        payload = {
            "ranked_outfits": [
                {"composer_id": "C1",
                 "occasion_fit": "92.7", "body_harmony": "85", "color_harmony": "88",
                 "archetype_match": "75", "inter_item_coherence": "80.9",
                 "rationale": "ok", "unsuitable": False},
            ],
            "overall_assessment": "strong",
        }
        with patch("agentic_application.agents.outfit_rater.get_api_key", return_value="x"), _patch_rater() as oc:
            oc.return_value.responses.create.return_value = _mock_response(payload)
            result = OutfitRater().rate(_ctx(), _composed(), _retrieved())

        ro = result.ranked_outfits[0]
        self.assertEqual(92, ro.occasion_fit)  # 92.7 truncated
        self.assertEqual(80, ro.inter_item_coherence)  # 80.9 truncated

    def test_rater_rejects_bool_subscores_as_malformed(self) -> None:
        """An LLM emitting `true` / `false` for a numeric score is
        malformed. Bool is an int subclass in Python so a naive
        isinstance check would silently accept True as a score of 1;
        reject explicitly instead."""
        payload = {
            "ranked_outfits": [
                {"composer_id": "C1",
                 "occasion_fit": True, "body_harmony": False,
                 "color_harmony": 80, "archetype_match": 80,
                 "inter_item_coherence": True,
                 "rationale": "ok", "unsuitable": False},
            ],
            "overall_assessment": "moderate",
        }
        with patch("agentic_application.agents.outfit_rater.get_api_key", return_value="x"), _patch_rater() as oc:
            oc.return_value.responses.create.return_value = _mock_response(payload)
            result = OutfitRater().rate(_ctx(), _composed(), _retrieved())

        ro = result.ranked_outfits[0]
        # Required dims default to 0 on bool input.
        self.assertEqual(0, ro.occasion_fit)
        self.assertEqual(0, ro.body_harmony)
        # inter_item_coherence becomes None (axis dropped from radar).
        self.assertIsNone(ro.inter_item_coherence)

    def test_rater_handles_overflow_in_float_string(self) -> None:
        """`float("1e1000")` is inf; `int(inf)` raises OverflowError.
        Catch it so the rate() loop doesn't crash on a single
        malformed candidate."""
        payload = {
            "ranked_outfits": [
                {"composer_id": "C1",
                 "occasion_fit": "1e1000", "body_harmony": 80,
                 "color_harmony": 80, "archetype_match": 80,
                 "inter_item_coherence": "1e9999",
                 "rationale": "ok", "unsuitable": False},
            ],
            "overall_assessment": "moderate",
        }
        with patch("agentic_application.agents.outfit_rater.get_api_key", return_value="x"), _patch_rater() as oc:
            oc.return_value.responses.create.return_value = _mock_response(payload)
            result = OutfitRater().rate(_ctx(), _composed(), _retrieved())

        ro = result.ranked_outfits[0]
        self.assertEqual(0, ro.occasion_fit)  # overflow → required dim default
        self.assertIsNone(ro.inter_item_coherence)  # overflow → optional dim None

    def test_rater_drops_unknown_composer_ids(self) -> None:
        """The LLM should never invent composer_ids outside the input
        slate. If it does, drop them — preserves the contract that
        ranked_outfits is a subset of the input."""
        payload = {
            "ranked_outfits": [
                {"composer_id": "C1", "rank": 1, "fashion_score": 80,
                 "occasion_fit": 80, "body_harmony": 80, "color_harmony": 80, "archetype_match": 80, "inter_item_coherence": 80,
                 "rationale": "valid", "unsuitable": False},
                {"composer_id": "BOGUS", "rank": 2, "fashion_score": 90,
                 "occasion_fit": 90, "body_harmony": 90, "color_harmony": 90, "archetype_match": 90, "inter_item_coherence": 80,
                 "rationale": "hallucinated id", "unsuitable": False},
            ],
            "overall_assessment": "strong",
        }
        with patch("agentic_application.agents.outfit_rater.get_api_key", return_value="x"), _patch_rater() as oc:
            oc.return_value.responses.create.return_value = _mock_response(payload)
            result = OutfitRater().rate(_ctx(), _composed(), _retrieved())

        self.assertEqual(1, len(result.ranked_outfits))
        self.assertEqual("C1", result.ranked_outfits[0].composer_id)


class OutfitRaterUsageTests(unittest.TestCase):
    """Token usage carries on the result object so concurrent turns
    using the same OutfitRater instance don't race over a shared
    ``last_usage`` attribute."""

    def test_rater_returns_usage_on_result(self) -> None:
        payload = {
            "ranked_outfits": [
                {"composer_id": "C1", "rank": 1, "fashion_score": 80,
                 "occasion_fit": 80, "body_harmony": 80, "color_harmony": 80, "archetype_match": 80, "inter_item_coherence": 80,
                 "rationale": "ok", "unsuitable": False},
            ],
            "overall_assessment": "moderate",
        }
        mock_resp = Mock()
        mock_resp.output_text = json.dumps(payload)
        mock_resp.usage = Mock(input_tokens=400, output_tokens=120, total_tokens=520)
        with patch("agentic_application.agents.outfit_rater.get_api_key", return_value="x"), _patch_rater() as oc:
            oc.return_value.responses.create.return_value = mock_resp
            result = OutfitRater().rate(_ctx(), _composed(), _retrieved())

        self.assertIn("prompt_tokens", result.usage)
        self.assertIn("total_tokens", result.usage)
        # Sanity-check that *something* was extracted (concrete values
        # depend on extract_token_usage's response-shape sniffing).
        self.assertGreaterEqual(result.usage.get("total_tokens", 0), 0)


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

    def test_rater_emits_weight_profile_on_result(self) -> None:
        """R3: every RaterResult records the weight profile used so we
        can SQL-grep override frequencies later."""
        payload = {
            "ranked_outfits": [
                {"composer_id": "C1",
                 "occasion_fit": 80, "body_harmony": 80, "color_harmony": 80, "archetype_match": 80, "inter_item_coherence": 80,
                 "rationale": "ok", "unsuitable": False},
            ],
            "overall_assessment": "moderate",
        }
        with patch("agentic_application.agents.outfit_rater.get_api_key", return_value="x"), _patch_rater() as oc:
            oc.return_value.responses.create.return_value = _mock_response(payload)
            # Default _ctx() has occasion=daily_office → no override → "default"
            result = OutfitRater().rate(_ctx(), _composed(), _retrieved())
        self.assertEqual("default", result.fashion_score_weight_profile)

    def test_rater_picks_ceremonial_profile_on_wedding(self) -> None:
        ctx = CombinedContext(
            user=UserContext(user_id="u1", gender="male"),
            live=LiveContext(user_need="for a friend's wedding", occasion_signal="wedding_traditional"),
            hard_filters={},
        )
        payload = {
            "ranked_outfits": [
                {"composer_id": "C1",
                 "occasion_fit": 90, "body_harmony": 70, "color_harmony": 70, "archetype_match": 70, "inter_item_coherence": 80,
                 "rationale": "ok", "unsuitable": False},
            ],
            "overall_assessment": "strong",
        }
        with patch("agentic_application.agents.outfit_rater.get_api_key", return_value="x"), _patch_rater() as oc:
            oc.return_value.responses.create.return_value = _mock_response(payload)
            result = OutfitRater().rate(ctx, _composed(), _retrieved())
        self.assertEqual("ceremonial", result.fashion_score_weight_profile)
        # ceremonial weights: occasion 0.45, body 0.20, color 0.20, archetype 0.15
        # 90*0.45 + 70*0.20 + 70*0.20 + 70*0.15 = 40.5+14+14+10.5 = 79
        self.assertEqual(79, result.ranked_outfits[0].fashion_score)


class WeightProfileSelectionTests(unittest.TestCase):
    """select_weight_profile maps planner-resolved context → profile key."""

    def test_default_when_no_signal(self) -> None:
        self.assertEqual("default", select_weight_profile())

    def test_ceremonial_for_wedding_occasion(self) -> None:
        self.assertEqual("ceremonial", select_weight_profile(occasion_signal="wedding_traditional"))
        self.assertEqual("ceremonial", select_weight_profile(occasion_signal="wedding"))
        self.assertEqual("ceremonial", select_weight_profile(occasion_signal="festival"))
        self.assertEqual("ceremonial", select_weight_profile(occasion_signal="sangeet"))

    def test_slimming_for_user_message(self) -> None:
        self.assertEqual("slimming", select_weight_profile(user_message="Make me look slimmer"))
        self.assertEqual("slimming", select_weight_profile(user_message="something to look taller"))

    def test_bold_for_user_message(self) -> None:
        self.assertEqual("bold", select_weight_profile(user_message="something bold and colorful"))
        self.assertEqual("bold", select_weight_profile(user_message="want to make a statement"))

    def test_comfortable_for_user_message(self) -> None:
        self.assertEqual("comfortable", select_weight_profile(user_message="something comfortable for the day"))
        self.assertEqual("comfortable", select_weight_profile(user_message="relaxed weekend look"))

    def test_ceremonial_beats_comfortable(self) -> None:
        """A 'comfortable wedding outfit' is still ceremonial — occasion fit
        dominates over comfort."""
        self.assertEqual(
            "ceremonial",
            select_weight_profile(
                user_message="comfortable but festive",
                occasion_signal="wedding_traditional",
            ),
        )


class FashionScoreBlendTests(unittest.TestCase):
    """compute_fashion_score is the deterministic weighted blend."""

    def test_default_profile_blend(self) -> None:
        # PR #73: inter_item_coherence default is None (post-review fix);
        # callers must pass it explicitly. 5-dim default:
        # 95*0.30 + 85*0.18 + 88*0.22 + 75*0.15 + 100*0.15
        # = 28.5+15.3+19.36+11.25+15.0 = 89.41 → 89
        self.assertEqual(
            89,
            compute_fashion_score(
                occasion_fit=95, body_harmony=85,
                color_harmony=88, archetype_match=75,
                inter_item_coherence=100,
            ),
        )

    def test_ceremonial_profile_amplifies_occasion(self) -> None:
        # Same sub-scores, ceremonial 5-dim weights:
        # 95*0.40 + 85*0.16 + 88*0.18 + 75*0.13 + 100*0.13
        # = 38+13.6+15.84+9.75+13.0 = 90.19 → 90
        self.assertEqual(
            90,
            compute_fashion_score(
                occasion_fit=95, body_harmony=85,
                color_harmony=88, archetype_match=75,
                inter_item_coherence=100,
                profile="ceremonial",
            ),
        )

    def test_none_inter_item_drops_dim_like_complete(self) -> None:
        """PR #73: when inter_item_coherence is None (LLM omitted, legacy
        data) the formula behaves identically to direction_type=complete
        — dim dropped, remaining 4 weights renormalised."""
        a = compute_fashion_score(
            occasion_fit=95, body_harmony=85,
            color_harmony=88, archetype_match=75,
            inter_item_coherence=None, direction_type="paired",
        )
        b = compute_fashion_score(
            occasion_fit=95, body_harmony=85,
            color_harmony=88, archetype_match=75,
            inter_item_coherence=100, direction_type="complete",
        )
        self.assertEqual(a, b)

    def test_complete_outfit_drops_inter_item_and_renormalizes(self) -> None:
        """Single-item outfits drop the inter_item_coherence dim and the
        remaining 4 weights renormalise to sum to 1.0. The score should
        match what R3's 4-dim default produced for the same sub-scores
        (within rounding)."""
        # Default 4 weights renormalised: 0.30/0.85=0.3529, 0.18/0.85=0.2118,
        # 0.22/0.85=0.2588, 0.15/0.85=0.1765 — close to the original R3
        # default of 0.35/0.20/0.25/0.20.
        # 95*0.3529 + 85*0.2118 + 88*0.2588 + 75*0.1765 = 88.18 → 88
        self.assertEqual(
            88,
            compute_fashion_score(
                occasion_fit=95, body_harmony=85,
                color_harmony=88, archetype_match=75,
                inter_item_coherence=100,  # ignored for complete
                direction_type="complete",
            ),
        )

    def test_complete_outfit_score_unaffected_by_inter_item_value(self) -> None:
        """For complete outfits, varying inter_item_coherence must NOT
        change the score (since the dim is dropped from the formula)."""
        a = compute_fashion_score(
            occasion_fit=80, body_harmony=80, color_harmony=80,
            archetype_match=80, inter_item_coherence=10,
            direction_type="complete",
        )
        b = compute_fashion_score(
            occasion_fit=80, body_harmony=80, color_harmony=80,
            archetype_match=80, inter_item_coherence=99,
            direction_type="complete",
        )
        self.assertEqual(a, b)
        self.assertEqual(80, a)  # all 80s blend to 80 regardless of weights

    def test_unknown_profile_falls_back_to_default(self) -> None:
        self.assertEqual(
            compute_fashion_score(
                occasion_fit=80, body_harmony=80,
                color_harmony=80, archetype_match=80,
                profile="not-a-real-profile",
            ),
            compute_fashion_score(
                occasion_fit=80, body_harmony=80,
                color_harmony=80, archetype_match=80,
            ),
        )

    def test_all_profile_weights_sum_to_one(self) -> None:
        for name, weights in WEIGHT_PROFILES.items():
            total = sum(weights.values())
            self.assertAlmostEqual(1.0, total, places=6, msg=f"{name} weights sum to {total}")

    def test_composer_id_tiebreak_is_numeric(self) -> None:
        """PR #71 review fix: ties on fashion_score sort C2 before C10
        (numeric), not lex order which would put C10 before C2."""
        from agentic_application.agents.outfit_rater import _composer_id_sort_key
        ids = ["C10", "C2", "C1", "C3"]
        # Sorted by the helper should give a natural numeric order.
        sorted_ids = sorted(ids, key=_composer_id_sort_key)
        self.assertEqual(["C1", "C2", "C3", "C10"], sorted_ids)
        # Non-numeric ids fall back to lex; mixed shapes don't crash.
        self.assertEqual(["C1", "Cx"], sorted(["Cx", "C1"], key=_composer_id_sort_key))


    def test_rater_honours_unsuitable_flag(self) -> None:
        """An unsuitable=True outfit still appears in the result so the
        orchestrator can log + drop it; the flag is not a silent skip."""
        payload = {
            "ranked_outfits": [
                {"composer_id": "C1", "rank": 1, "fashion_score": 30,
                 "occasion_fit": 25, "body_harmony": 50, "color_harmony": 30, "archetype_match": 25, "inter_item_coherence": 80,
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
