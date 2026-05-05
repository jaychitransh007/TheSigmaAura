"""Unit tests for OutfitRater.

R7 (May 5 2026): the rater scores Composer-built outfits on a six-dim
rubric using a 1/2/3 scale (1=clear miss, 2=works, 3=clear win). LLMs
cluster ~70-90 on a 0-100 scale with no real discrimination, so the
discrete 3-point scale forces honest choices. The orchestrator blends
the sub-scores into a 0-100 fashion_score via compute_fashion_score:

    raw   = Σ subscore × weight        (1.0 .. 3.0)
    score = ((raw − 1) / 2) × 100      (0 .. 100)

LLM is mocked; tests focus on:
- contract: required fields, ID round-tripping, six dims surfaced
- defensive ordering: result is sorted by computed fashion_score desc
- sub-score clamping: out-of-range scores get pulled to {1, 2, 3}
- empty input short-circuits before the LLM call
- weight-profile selection: picks correct profile per intent
- deterministic blend: rescaled fashion_score lands on the expected band
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


def _row(cid: str, occ=2, body=2, col=2, pair=2, form=2, stmt=2,
         rationale="ok", unsuitable=False) -> dict:
    """Helper to build a single rater output row in the new R7 shape.
    Defaults to all-2s (neutral)."""
    return {
        "composer_id": cid,
        "occasion_fit": occ,
        "body_harmony": body,
        "color_harmony": col,
        "pairing": pair,
        "formality": form,
        "statement": stmt,
        "rationale": rationale,
        "unsuitable": unsuitable,
    }


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
                _row("C1", occ=3, body=3, col=3, pair=3, form=3, stmt=3,
                     rationale="Strong all around."),
                _row("C2", occ=2, body=3, col=2, pair=3, form=2, stmt=2,
                     rationale="Solid, slightly casual read."),
                _row("C3", occ=1, body=2, col=2, pair=3, form=1, stmt=2,
                     rationale="Suit is too formal for daily office."),
            ],
            "overall_assessment": "moderate",
        }
        with patch("agentic_application.agents.outfit_rater.get_api_key", return_value="x"), _patch_rater() as oc:
            oc.return_value.responses.create.return_value = _mock_response(payload)
            result = OutfitRater().rate(_ctx(), _composed(), _retrieved())

        self.assertEqual(3, len(result.ranked_outfits))
        # Sorted by computed fashion_score desc — C1 (all 3s = 100) wins.
        self.assertEqual([1, 2, 3], [r.rank for r in result.ranked_outfits])
        self.assertEqual("C1", result.ranked_outfits[0].composer_id)
        self.assertEqual(100, result.ranked_outfits[0].fashion_score)
        # Six sub-scores all surfaced on the result row.
        ro = result.ranked_outfits[0]
        self.assertEqual(3, ro.occasion_fit)
        self.assertEqual(3, ro.body_harmony)
        self.assertEqual(3, ro.color_harmony)
        self.assertEqual(3, ro.pairing)
        self.assertEqual(3, ro.formality)
        self.assertEqual(3, ro.statement)
        self.assertEqual("moderate", result.overall_assessment)


class OutfitRaterDefensiveTests(unittest.TestCase):

    def test_rater_resorts_by_fashion_score_when_llm_emits_bad_ranks(self) -> None:
        """The agent re-sorts by computed fashion_score in case the
        model's own ordering is wrong. C2 here has the highest scores
        but the LLM emits it third."""
        payload = {
            "ranked_outfits": [
                _row("C1", occ=2, body=2, col=2, pair=2, form=2, stmt=2),  # all 2s → 50
                _row("C3", occ=2, body=2, col=2, pair=2, form=2, stmt=2),  # tie at 50
                _row("C2", occ=3, body=3, col=3, pair=3, form=3, stmt=3),  # all 3s → 100
            ],
            "overall_assessment": "strong",
        }
        with patch("agentic_application.agents.outfit_rater.get_api_key", return_value="x"), _patch_rater() as oc:
            oc.return_value.responses.create.return_value = _mock_response(payload)
            result = OutfitRater().rate(_ctx(), _composed(), _retrieved())

        # C2 lands first (highest score); C1 / C3 tie on score and the
        # natural-numeric tiebreak puts C1 before C3.
        self.assertEqual(["C2", "C1", "C3"], [r.composer_id for r in result.ranked_outfits])
        self.assertEqual([1, 2, 3], [r.rank for r in result.ranked_outfits])

    def test_rater_clamps_out_of_range_subscores(self) -> None:
        """The strict-output schema enforces enum [1,2,3], but if a
        legacy / mocked response leaks an out-of-range int the parser
        clamps to {1, 2, 3}."""
        payload = {
            "ranked_outfits": [
                _row("C1", occ=99, body=-5, col=2, pair=2, form=2, stmt=2),
            ],
            "overall_assessment": "moderate",
        }
        with patch("agentic_application.agents.outfit_rater.get_api_key", return_value="x"), _patch_rater() as oc:
            oc.return_value.responses.create.return_value = _mock_response(payload)
            result = OutfitRater().rate(_ctx(), _composed(), _retrieved())

        ro = result.ranked_outfits[0]
        self.assertEqual(3, ro.occasion_fit)   # 99 clamped to 3
        self.assertEqual(1, ro.body_harmony)   # -5 clamped to 1
        self.assertEqual(2, ro.color_harmony)  # in range, untouched

    def test_rater_treats_malformed_pairing_as_missing(self) -> None:
        """A malformed `pairing` value (empty string, "N/A", etc.) is
        treated identically to a missing field — preserved as None on
        the candidate and dropped from the fashion_score blend."""
        for malformed in ("", "   ", "\t", "\n ", "N/A", "None", "null", "abc"):
            with self.subTest(value=repr(malformed)):
                payload = {
                    "ranked_outfits": [
                        {**_row("C1"), "pairing": malformed},
                    ],
                    "overall_assessment": "moderate",
                }
                with patch("agentic_application.agents.outfit_rater.get_api_key", return_value="x"), _patch_rater() as oc:
                    oc.return_value.responses.create.return_value = _mock_response(payload)
                    result = OutfitRater().rate(_ctx(), _composed(), _retrieved())

                ro = result.ranked_outfits[0]
                self.assertIsNone(ro.pairing)
                # All other dims are 2 → blended score lands at 50
                # (uniform sub-scores yield identical % across profiles).
                self.assertEqual(50, ro.fashion_score)

    def test_rater_treats_malformed_required_subscores_as_neutral(self) -> None:
        """The five always-on sub-scores default to 2 (neutral midpoint)
        on missing or malformed input. Required for the blend, so we
        treat unparseable as 'works' rather than dropping the dim or
        defaulting to 1 (which would be a false-negative miss)."""
        for malformed in ("", "   ", "N/A", "None", "abc", None):
            with self.subTest(value=repr(malformed)):
                payload = {
                    "ranked_outfits": [
                        {**_row("C1"), "occasion_fit": malformed},
                    ],
                    "overall_assessment": "moderate",
                }
                with patch("agentic_application.agents.outfit_rater.get_api_key", return_value="x"), _patch_rater() as oc:
                    oc.return_value.responses.create.return_value = _mock_response(payload)
                    result = OutfitRater().rate(_ctx(), _composed(), _retrieved())

                ro = result.ranked_outfits[0]
                self.assertEqual(2, ro.occasion_fit)
                # All 2s → 50.
                self.assertEqual(50, ro.fashion_score)

    def test_rater_truncates_float_strings_in_subscores(self) -> None:
        """LLM occasionally emits "2.7" or "2.0" for an int slot.
        Truncate via float() rather than crashing or rejecting."""
        payload = {
            "ranked_outfits": [
                {**_row("C1"), "occasion_fit": "2.7", "pairing": "1.9"},
            ],
            "overall_assessment": "strong",
        }
        with patch("agentic_application.agents.outfit_rater.get_api_key", return_value="x"), _patch_rater() as oc:
            oc.return_value.responses.create.return_value = _mock_response(payload)
            result = OutfitRater().rate(_ctx(), _composed(), _retrieved())

        ro = result.ranked_outfits[0]
        self.assertEqual(2, ro.occasion_fit)  # 2.7 truncated to 2
        self.assertEqual(1, ro.pairing)       # 1.9 truncated to 1

    def test_rater_rejects_bool_subscores_as_malformed(self) -> None:
        """An LLM emitting `true` / `false` for a numeric score is
        malformed. Bool is an int subclass in Python so a naive
        isinstance check would silently accept True as 1 / False as 0;
        reject explicitly instead."""
        payload = {
            "ranked_outfits": [
                {**_row("C1"), "occasion_fit": True, "body_harmony": False, "pairing": True},
            ],
            "overall_assessment": "moderate",
        }
        with patch("agentic_application.agents.outfit_rater.get_api_key", return_value="x"), _patch_rater() as oc:
            oc.return_value.responses.create.return_value = _mock_response(payload)
            result = OutfitRater().rate(_ctx(), _composed(), _retrieved())

        ro = result.ranked_outfits[0]
        # Required dims default to 2 on bool input (parser rejects → neutral).
        self.assertEqual(2, ro.occasion_fit)
        self.assertEqual(2, ro.body_harmony)
        # Pairing becomes None (axis dropped from radar).
        self.assertIsNone(ro.pairing)

    def test_rater_handles_overflow_in_float_string(self) -> None:
        """`float("1e1000")` is inf; `int(inf)` raises OverflowError.
        Catch it so the rate() loop doesn't crash on a malformed
        candidate."""
        payload = {
            "ranked_outfits": [
                {**_row("C1"), "occasion_fit": "1e1000", "pairing": "1e9999"},
            ],
            "overall_assessment": "moderate",
        }
        with patch("agentic_application.agents.outfit_rater.get_api_key", return_value="x"), _patch_rater() as oc:
            oc.return_value.responses.create.return_value = _mock_response(payload)
            result = OutfitRater().rate(_ctx(), _composed(), _retrieved())

        ro = result.ranked_outfits[0]
        self.assertEqual(2, ro.occasion_fit)  # overflow → neutral default
        self.assertIsNone(ro.pairing)         # overflow → optional dim None

    def test_rater_drops_unknown_composer_ids(self) -> None:
        """The LLM should never invent composer_ids outside the input
        slate. If it does, drop them — preserves the contract that
        ranked_outfits is a subset of the input."""
        payload = {
            "ranked_outfits": [
                _row("C1"),
                _row("BOGUS"),
            ],
            "overall_assessment": "moderate",
        }
        with patch("agentic_application.agents.outfit_rater.get_api_key", return_value="x"), _patch_rater() as oc:
            oc.return_value.responses.create.return_value = _mock_response(payload)
            result = OutfitRater().rate(_ctx(), _composed(), _retrieved())

        self.assertEqual(1, len(result.ranked_outfits))
        self.assertEqual("C1", result.ranked_outfits[0].composer_id)


class OutfitRaterUsageTests(unittest.TestCase):

    def test_rater_returns_usage_on_result(self) -> None:
        payload = {
            "ranked_outfits": [_row("C1")],
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
        """Every RaterResult records the weight profile used so we can
        SQL-grep override frequencies later."""
        payload = {
            "ranked_outfits": [_row("C1")],
            "overall_assessment": "moderate",
        }
        with patch("agentic_application.agents.outfit_rater.get_api_key", return_value="x"), _patch_rater() as oc:
            oc.return_value.responses.create.return_value = _mock_response(payload)
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
                _row("C1", occ=3, body=2, col=2, pair=2, form=3, stmt=2),
            ],
            "overall_assessment": "strong",
        }
        with patch("agentic_application.agents.outfit_rater.get_api_key", return_value="x"), _patch_rater() as oc:
            oc.return_value.responses.create.return_value = _mock_response(payload)
            result = OutfitRater().rate(ctx, _composed(), _retrieved())
        self.assertEqual("ceremonial", result.fashion_score_weight_profile)
        # Ceremonial weights (R7): occasion 0.32, formality 0.22, color
        # 0.16, body 0.12, pairing 0.10, statement 0.08
        # raw = 3*.32 + 2*.12 + 2*.16 + 2*.10 + 3*.22 + 2*.08
        #     = 0.96 + 0.24 + 0.32 + 0.20 + 0.66 + 0.16 = 2.54
        # score = (2.54 - 1) / 2 * 100 = 77
        self.assertEqual(77, result.ranked_outfits[0].fashion_score)


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
    """compute_fashion_score is the deterministic weighted blend.

    The math: raw = Σ subscore × weight (1.0..3.0); score = ((raw-1)/2)×100.
    All-1s → 0, all-2s → 50, all-3s → 100. Uniform sub-scores yield
    identical percentages across all profiles since weights sum to 1.0.
    """

    def test_all_threes_yield_100(self) -> None:
        self.assertEqual(
            100,
            compute_fashion_score(
                occasion_fit=3, body_harmony=3, color_harmony=3,
                pairing=3, formality=3, statement=3,
            ),
        )

    def test_all_twos_yield_50(self) -> None:
        self.assertEqual(
            50,
            compute_fashion_score(
                occasion_fit=2, body_harmony=2, color_harmony=2,
                pairing=2, formality=2, statement=2,
            ),
        )

    def test_all_ones_yield_0(self) -> None:
        self.assertEqual(
            0,
            compute_fashion_score(
                occasion_fit=1, body_harmony=1, color_harmony=1,
                pairing=1, formality=1, statement=1,
            ),
        )

    def test_default_profile_blend_mixed(self) -> None:
        # Default (R7): occ 0.25, body 0.15, color 0.20, pair 0.15,
        # form 0.13, stmt 0.12.
        # raw = 3*.25 + 2*.15 + 3*.20 + 2*.15 + 2*.13 + 3*.12
        #     = 0.75 + 0.30 + 0.60 + 0.30 + 0.26 + 0.36 = 2.57
        # score = (2.57 - 1) / 2 * 100 = 78.5 → 78 (banker's round)
        self.assertEqual(
            78,
            compute_fashion_score(
                occasion_fit=3, body_harmony=2, color_harmony=3,
                pairing=2, formality=2, statement=3,
            ),
        )

    def test_ceremonial_profile_amplifies_occasion_and_formality(self) -> None:
        # Ceremonial: occ 0.32, form 0.22 dominate.
        # Same sub-scores as above, different profile → different score.
        # raw = 3*.32 + 2*.12 + 3*.16 + 2*.10 + 2*.22 + 3*.08
        #     = 0.96 + 0.24 + 0.48 + 0.20 + 0.44 + 0.24 = 2.56
        # score = (2.56 - 1) / 2 * 100 = 78
        self.assertEqual(
            78,
            compute_fashion_score(
                occasion_fit=3, body_harmony=2, color_harmony=3,
                pairing=2, formality=2, statement=3,
                profile="ceremonial",
            ),
        )

    def test_none_pairing_drops_dim_like_complete(self) -> None:
        """When pairing is None (LLM omitted), the formula behaves
        identically to direction_type=complete — dim dropped, remaining
        five weights renormalised."""
        a = compute_fashion_score(
            occasion_fit=3, body_harmony=2, color_harmony=3,
            pairing=None, formality=2, statement=3,
            direction_type="paired",
        )
        b = compute_fashion_score(
            occasion_fit=3, body_harmony=2, color_harmony=3,
            pairing=3, formality=2, statement=3,  # ignored for complete
            direction_type="complete",
        )
        self.assertEqual(a, b)

    def test_complete_outfit_drops_pairing(self) -> None:
        """Single-item outfits drop pairing and renormalise the
        remaining five weights to sum to 1.0."""
        # All non-pairing dims at 2 → raw = 2.0 across the 5 kept dims
        # (regardless of how the renorm distributes weight) → score = 50.
        self.assertEqual(
            50,
            compute_fashion_score(
                occasion_fit=2, body_harmony=2, color_harmony=2,
                pairing=3,  # ignored for complete outfits
                formality=2, statement=2,
                direction_type="complete",
            ),
        )

    def test_complete_outfit_score_unaffected_by_pairing_value(self) -> None:
        """For complete outfits, varying pairing must NOT change the
        score (since the dim is dropped)."""
        a = compute_fashion_score(
            occasion_fit=2, body_harmony=2, color_harmony=2,
            pairing=1, formality=2, statement=2, direction_type="complete",
        )
        b = compute_fashion_score(
            occasion_fit=2, body_harmony=2, color_harmony=2,
            pairing=3, formality=2, statement=2, direction_type="complete",
        )
        self.assertEqual(a, b)
        self.assertEqual(50, a)  # all 2s on the kept dims → 50.

    def test_unknown_profile_falls_back_to_default(self) -> None:
        self.assertEqual(
            compute_fashion_score(
                occasion_fit=2, body_harmony=2, color_harmony=2,
                pairing=2, formality=2, statement=2,
                profile="not-a-real-profile",
            ),
            compute_fashion_score(
                occasion_fit=2, body_harmony=2, color_harmony=2,
                pairing=2, formality=2, statement=2,
            ),
        )

    def test_all_profile_weights_sum_to_one(self) -> None:
        for name, weights in WEIGHT_PROFILES.items():
            total = sum(weights.values())
            self.assertAlmostEqual(1.0, total, places=6, msg=f"{name} weights sum to {total}")

    def test_all_profiles_have_six_dims(self) -> None:
        """R7: every profile must define weights for the six rater dims
        — missing one would make compute_fashion_score raise KeyError."""
        expected = {"occasion_fit", "body_harmony", "color_harmony", "pairing", "formality", "statement"}
        for name, weights in WEIGHT_PROFILES.items():
            self.assertEqual(expected, set(weights.keys()), msg=f"profile {name}")

    def test_composer_id_tiebreak_is_numeric(self) -> None:
        """Ties on fashion_score sort C2 before C10 (numeric), not lex
        order which would put C10 before C2."""
        from agentic_application.agents.outfit_rater import _composer_id_sort_key
        ids = ["C10", "C2", "C1", "C3"]
        sorted_ids = sorted(ids, key=_composer_id_sort_key)
        self.assertEqual(["C1", "C2", "C3", "C10"], sorted_ids)
        self.assertEqual(["C1", "Cx"], sorted(["Cx", "C1"], key=_composer_id_sort_key))


class OutfitRaterUnsuitableTests(unittest.TestCase):

    def test_rater_honours_unsuitable_flag(self) -> None:
        """An unsuitable=True outfit still appears in the result so the
        orchestrator can log + drop it; the flag is not a silent skip."""
        payload = {
            "ranked_outfits": [
                _row("C1", occ=1, body=2, col=1, pair=2, form=1, stmt=2,
                     rationale="Dealbreaker — wrong occasion entirely.",
                     unsuitable=True),
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
