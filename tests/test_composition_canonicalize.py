"""Tests for the canonicalize layer (Phase 4.11).

Cover:
- exact-match paths (no embed call)
- embedding nearest-neighbour with mock vectors
- threshold cutoff (below floor → keep raw value)
- partial / full / empty embed batches
- failure modes (embed API raises, empty bank, missing axes)
- the seasonal_color_group dual-dimension bug fix in the engine
"""
from __future__ import annotations

import json
import math
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
for p in (
    ROOT,
    ROOT / "modules" / "agentic_application" / "src",
    ROOT / "modules" / "catalog" / "src",
    ROOT / "modules" / "platform_core" / "src",
    ROOT / "modules" / "style_engine" / "src",
    ROOT / "modules" / "user" / "src",
    ROOT / "modules" / "user_profiler" / "src",
):
    sp = str(p)
    if sp not in sys.path:
        sys.path.insert(0, sp)

from agentic_application.composition.canonicalize import (
    DEFAULT_THRESHOLD,
    CanonicalEmbeddings,
    _cosine,
    _nearest,
    canonicalize_inputs,
    clear_embeddings_cache,
    load_canonical_embeddings,
)
from agentic_application.composition.engine import (
    CompositionInputs,
    compose_direction,
)
from agentic_application.composition.yaml_loader import load_style_graph
from agentic_application.schemas import UserContext


def _baseline_inputs(**overrides) -> CompositionInputs:
    base = dict(
        gender="female",
        body_shape="Hourglass",
        frame_structure="Light and Narrow",
        seasonal_color_group="Soft Autumn",
        archetype="modern_professional",
        risk_tolerance="moderate",
        occasion_signal="daily_office_mnc",
        formality_hint="smart_casual",
        weather_context="warm_temperate",
        time_of_day="daytime",
    )
    base.update(overrides)
    return CompositionInputs(**base)


def _unit(*v: float) -> tuple[float, ...]:
    """Normalize a small vector so cosine matches are deterministic in
    tests. tuple makes the CanonicalEmbeddings hashable-friendly."""
    norm = math.sqrt(sum(x * x for x in v)) or 1.0
    return tuple(x / norm for x in v)


def _empty_embeddings() -> CanonicalEmbeddings:
    return CanonicalEmbeddings(
        occasion={}, weather={}, archetype={},
        risk_tolerance={}, seasonal={},
    )


class CosineHelperTests(unittest.TestCase):
    def test_perfect_match_is_one(self):
        self.assertAlmostEqual(_cosine([1.0, 0.0], [1.0, 0.0]), 1.0)

    def test_orthogonal_is_zero(self):
        self.assertAlmostEqual(_cosine([1.0, 0.0], [0.0, 1.0]), 0.0)

    def test_zero_vectors_return_zero(self):
        self.assertEqual(_cosine([0.0, 0.0], [1.0, 0.0]), 0.0)

    def test_mismatched_dims_return_zero(self):
        self.assertEqual(_cosine([1.0, 0.0], [1.0, 0.0, 0.0]), 0.0)

    def test_nearest_returns_top_score(self):
        bank = {
            "alpha": [1.0, 0.0, 0.0],
            "beta": [0.0, 1.0, 0.0],
            "gamma": [0.5, 0.5, 0.0],
        }
        key, score = _nearest([1.0, 0.0, 0.0], bank)
        self.assertEqual(key, "alpha")
        self.assertAlmostEqual(score, 1.0)

    def test_nearest_on_empty_bank_returns_none(self):
        key, score = _nearest([1.0], {})
        self.assertIsNone(key)
        self.assertEqual(score, 0.0)


class CanonicalizeExactMatchTests(unittest.TestCase):
    """When every input already exact-matches a YAML key, canonicalize
    must short-circuit — no embed call, no behavior change."""

    @classmethod
    def setUpClass(cls):
        cls.graph = load_style_graph()

    def test_exact_match_skips_embed_call(self):
        embed = Mock(return_value=[])
        inputs = _baseline_inputs()  # all fields are canonical
        out, result = canonicalize_inputs(
            inputs,
            graph=self.graph,
            embeddings=_empty_embeddings(),
            embed_client=embed,
        )
        embed.assert_not_called()
        self.assertEqual(result.embed_calls, 0)
        # Inputs round-trip unchanged.
        self.assertEqual(out.occasion_signal, inputs.occasion_signal)
        self.assertEqual(out.weather_context, inputs.weather_context)
        self.assertEqual(out.archetype, inputs.archetype)

    def test_exact_match_seasonal_subseason(self):
        # "Soft Autumn" exact-matches palette.SubSeason.
        embed = Mock()
        out, _ = canonicalize_inputs(
            _baseline_inputs(seasonal_color_group="Soft Autumn"),
            graph=self.graph,
            embeddings=_empty_embeddings(),
            embed_client=embed,
        )
        embed.assert_not_called()
        self.assertEqual(out.seasonal_color_group, "Soft Autumn")

    def test_exact_match_seasonal_4group(self):
        # "Autumn" exact-matches palette.SeasonalColorGroup (4-group form);
        # spec-special dual-dim lookup wins.
        embed = Mock()
        out, _ = canonicalize_inputs(
            _baseline_inputs(seasonal_color_group="Autumn"),
            graph=self.graph,
            embeddings=_empty_embeddings(),
            embed_client=embed,
        )
        embed.assert_not_called()
        self.assertEqual(out.seasonal_color_group, "Autumn")


class CanonicalizeEmbeddingTests(unittest.TestCase):
    """Drive canonicalize with stub vectors so behavior is deterministic
    and doesn't depend on the real embedding bank."""

    @classmethod
    def setUpClass(cls):
        cls.graph = load_style_graph()

    def test_above_threshold_replaces_raw_with_canonical_key(self):
        # Build a tiny bank where "everyday_casual" is a strong match
        # for the query. Mock the embed client to return aligned vectors.
        embeddings = CanonicalEmbeddings(
            occasion={
                "everyday_casual": _unit(1.0, 0.0, 0.0),
                "diwali": _unit(0.0, 1.0, 0.0),
            },
            weather={}, archetype={}, risk_tolerance={}, seasonal={},
        )

        def stub_embed(texts):
            assert len(texts) == 1, texts
            assert texts[0] == "casual"
            # Aligned with everyday_casual → cosine 1.0
            return [list(_unit(1.0, 0.0, 0.0))]

        out, result = canonicalize_inputs(
            _baseline_inputs(occasion_signal="casual"),
            graph=self.graph,
            embeddings=embeddings,
            embed_client=stub_embed,
        )
        self.assertEqual(out.occasion_signal, "everyday_casual")
        self.assertEqual(result.matches["occasion"][0], "everyday_casual")
        self.assertGreater(result.matches["occasion"][1], 0.99)

    def test_below_threshold_keeps_raw_value(self):
        embeddings = CanonicalEmbeddings(
            occasion={
                "everyday_casual": _unit(1.0, 0.0, 0.0),
            },
            weather={}, archetype={}, risk_tolerance={}, seasonal={},
        )

        def stub_embed(texts):
            # Orthogonal to the bank's only entry → cosine 0.0,
            # well below the 0.5 default threshold.
            return [list(_unit(0.0, 1.0, 0.0))]

        out, result = canonicalize_inputs(
            _baseline_inputs(occasion_signal="hangout"),
            graph=self.graph,
            embeddings=embeddings,
            embed_client=stub_embed,
        )
        # Original value preserved → engine will flag this as a YAML gap.
        self.assertEqual(out.occasion_signal, "hangout")
        # Match record carries the score so telemetry can see it.
        self.assertIsNone(result.matches["occasion"][0])

    def test_batched_embed_call_for_multiple_axes(self):
        # Two non-canonical axes should produce ONE embed call with
        # both texts in input order.
        embeddings = CanonicalEmbeddings(
            occasion={"everyday_casual": _unit(1.0, 0.0)},
            weather={"warm_temperate": _unit(0.0, 1.0)},
            archetype={}, risk_tolerance={}, seasonal={},
        )

        embed = Mock(return_value=[
            list(_unit(1.0, 0.0)),  # for "casual"
            list(_unit(0.0, 1.0)),  # for "balmy"
        ])

        out, result = canonicalize_inputs(
            _baseline_inputs(occasion_signal="casual", weather_context="balmy"),
            graph=self.graph,
            embeddings=embeddings,
            embed_client=embed,
        )
        embed.assert_called_once_with(["casual", "balmy"])
        self.assertEqual(result.embed_calls, 1)
        self.assertEqual(out.occasion_signal, "everyday_casual")
        self.assertEqual(out.weather_context, "warm_temperate")

    def test_embed_failure_keeps_raw_values(self):
        embeddings = CanonicalEmbeddings(
            occasion={"everyday_casual": _unit(1.0, 0.0)},
            weather={}, archetype={}, risk_tolerance={}, seasonal={},
        )

        def stub_embed(texts):
            raise RuntimeError("OpenAI 502")

        out, result = canonicalize_inputs(
            _baseline_inputs(occasion_signal="casual"),
            graph=self.graph,
            embeddings=embeddings,
            embed_client=stub_embed,
        )
        # Raw value survives; engine flags as gap.
        self.assertEqual(out.occasion_signal, "casual")
        # Embed call was attempted but didn't yield matches.
        self.assertEqual(result.embed_calls, 1)
        self.assertNotIn("occasion", result.matches)

    def test_no_embed_client_runs_exact_match_only(self):
        # When canonicalize is wired without an embed client (e.g.
        # tests that disable the network), any non-exact value stays
        # raw. Engine still runs and flags gaps as it would.
        out, result = canonicalize_inputs(
            _baseline_inputs(occasion_signal="hangout"),
            graph=self.graph,
            embeddings=_empty_embeddings(),
            embed_client=None,
        )
        self.assertEqual(out.occasion_signal, "hangout")
        self.assertEqual(result.embed_calls, 0)


class LoadCanonicalEmbeddingsTests(unittest.TestCase):
    def setUp(self):
        clear_embeddings_cache()

    def tearDown(self):
        clear_embeddings_cache()

    def test_missing_file_returns_empty_bank_without_raising(self):
        out = load_canonical_embeddings(Path("/tmp/this_does_not_exist.json"))
        self.assertEqual(out.occasion, {})
        self.assertEqual(out.weather, {})

    def test_loads_real_artifact_if_present(self):
        # The build script should have produced this on first install.
        # If absent (fresh checkout pre-build), the missing-file test
        # above covers the degraded path.
        artifact = (
            ROOT / "modules" / "agentic_application" / "src"
            / "agentic_application" / "composition" / "canonical_embeddings.json"
        )
        if not artifact.exists():
            self.skipTest("canonical_embeddings.json not yet built")
        out = load_canonical_embeddings(artifact)
        # Real artifact has all 5 axes populated.
        self.assertGreater(len(out.occasion), 30)  # 44 in current YAML
        self.assertEqual(len(out.weather), 10)
        self.assertGreater(len(out.archetype), 5)
        self.assertEqual(len(out.risk_tolerance), 3)
        self.assertGreater(len(out.seasonal), 10)  # 12 SubSeason + 4 SCG = 16 unique

    def test_load_is_module_cached(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump({"occasion": {"x": [1.0, 0.0]}}, f)
            tmp_path = Path(f.name)
        try:
            a = load_canonical_embeddings(tmp_path)
            b = load_canonical_embeddings(tmp_path)
            self.assertIs(a, b)
        finally:
            tmp_path.unlink()


class SeasonalColorGroupBugFixTests(unittest.TestCase):
    """Engine bug: profile data sometimes stores the 4-entry
    SeasonalColorGroup form ("Autumn") instead of the 12-entry SubSeason
    form ("Soft Autumn"). Engine now tries both palette dimensions
    before flagging a gap."""

    @classmethod
    def setUpClass(cls):
        cls.graph = load_style_graph()
        cls.user = UserContext(user_id="t", gender="female")

    def test_4group_seasonal_no_longer_yaml_gaps(self):
        result = compose_direction(
            inputs=_baseline_inputs(seasonal_color_group="Autumn"),
            graph=self.graph,
            user=self.user,
        )
        # No yaml_gap on seasonal_color_group anymore.
        for gap in result.yaml_gaps:
            self.assertFalse(
                gap.startswith("seasonal_color_group"),
                f"unexpected gap: {gap}",
            )

    def test_subseason_still_works(self):
        # The pre-bug-fix path: SubSeason exact match.
        result = compose_direction(
            inputs=_baseline_inputs(seasonal_color_group="Soft Autumn"),
            graph=self.graph,
            user=self.user,
        )
        for gap in result.yaml_gaps:
            self.assertFalse(gap.startswith("seasonal_color_group"))

    def test_unknown_seasonal_still_gaps(self):
        # Genuine garbage still falls through; canonicalize at runtime
        # would catch this via embedding fallback, but the engine
        # bug-fix is exact-match only.
        result = compose_direction(
            inputs=_baseline_inputs(seasonal_color_group="not_a_season"),
            graph=self.graph,
            user=self.user,
        )
        self.assertTrue(
            any(g.startswith("seasonal_color_group:") for g in result.yaml_gaps),
            f"expected seasonal gap; got {result.yaml_gaps}",
        )


class DefaultThresholdTests(unittest.TestCase):
    def test_default_is_05(self):
        self.assertEqual(DEFAULT_THRESHOLD, 0.50)


if __name__ == "__main__":
    unittest.main()
