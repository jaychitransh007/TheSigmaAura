"""Unit tests for the bootstrap profile pool + grid enumeration."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
for p in (
    ROOT,
    ROOT / "modules" / "agentic_application" / "src",
    ROOT / "modules" / "catalog" / "src",
    ROOT / "modules" / "platform_core" / "src",
    ROOT / "modules" / "user" / "src",
    ROOT / "modules" / "user_profiler" / "src",
):
    sp = str(p)
    if sp not in sys.path:
        sys.path.insert(0, sp)

from agentic_application.recipes.profiles import (
    ARCHETYPES,
    BODY_FRAMES,
    GENDERS,
    PALETTES,
    SyntheticProfile,
    generate_profile_pool,
)
from agentic_application.recipes.grid import (
    OCCASIONS,
    GridCell,
    _load_occasions_from_yaml,
    enumerate_grid,
    estimate_cost,
    evaluate_coverage,
)


class ProfilePoolTests(unittest.TestCase):
    def test_default_size_is_75(self):
        pool = generate_profile_pool()
        self.assertEqual(len(pool), 75)

    def test_deterministic_across_runs_with_same_seed(self):
        a = generate_profile_pool(seed=7)
        b = generate_profile_pool(seed=7)
        self.assertEqual([p.profile_id for p in a], [p.profile_id for p in b])
        # Spot-check a downstream attribute too — id alone could match
        # even if the underlying RNG drifted.
        self.assertEqual(a[10].skin_palette, b[10].skin_palette)

    def test_different_seeds_produce_different_pools(self):
        a = generate_profile_pool(target_size=30, seed=1)
        b = generate_profile_pool(target_size=30, seed=2)
        # First-pass coverage is identical (24 guaranteed combos), but
        # the post-coverage pass should differ.
        self.assertNotEqual([p.profile_id for p in a], [p.profile_id for p in b])

    def test_first_pass_covers_all_archetype_gender_combos(self):
        pool = generate_profile_pool(target_size=30)
        seen = {(p.primary_archetype, p.gender) for p in pool}
        for archetype in ARCHETYPES:
            for gender in GENDERS:
                self.assertIn((archetype, gender), seen)

    def test_unique_profile_ids(self):
        pool = generate_profile_pool()
        ids = [p.profile_id for p in pool]
        self.assertEqual(len(ids), len(set(ids)))

    def test_blend_ratios_sum_to_100(self):
        pool = generate_profile_pool()
        for p in pool:
            self.assertEqual(p.blend_ratio_primary + p.blend_ratio_secondary, 100)

    def test_secondary_empty_when_blend_is_100(self):
        pool = generate_profile_pool()
        for p in pool:
            if p.blend_ratio_primary == 100:
                self.assertEqual(p.secondary_archetype, "")

    def test_body_frame_matches_gender(self):
        pool = generate_profile_pool()
        for p in pool:
            self.assertIn(p.body_frame, BODY_FRAMES[p.gender])

    def test_palette_is_canonical(self):
        pool = generate_profile_pool()
        for p in pool:
            self.assertIn(p.skin_palette, PALETTES)

    def test_target_size_smaller_than_24_still_returns_at_least_24(self):
        # First pass fills 24 base combos regardless of target.
        pool = generate_profile_pool(target_size=10)
        self.assertEqual(len(pool), 24)


class GridEnumerationTests(unittest.TestCase):
    def setUp(self):
        self.profiles = generate_profile_pool()

    def test_grid_size_in_target_range(self):
        cells = enumerate_grid(self.profiles)
        # OPEN_TASKS spec: ~5,000–10,000 cells. Allow a bit of slack on
        # both sides — occasion/season exclusions can drift the count.
        self.assertGreater(len(cells), 4_000)
        self.assertLess(len(cells), 12_000)

    def test_unique_cell_ids(self):
        cells = enumerate_grid(self.profiles)
        ids = [c.cell_id for c in cells]
        self.assertEqual(len(ids), len(set(ids)))

    def test_each_cell_respects_occasion_seasons(self):
        cells = enumerate_grid(self.profiles)
        occ_lookup = {o.occasion: o for o in OCCASIONS}
        for cell in cells:
            occ = occ_lookup[cell.occasion]
            self.assertIn(
                cell.season, occ.seasons,
                f"{cell.occasion} should not appear in {cell.season}",
            )

    def test_sample_profile_matches_archetype_and_gender(self):
        cells = enumerate_grid(self.profiles)
        profile_lookup = {p.profile_id: p for p in self.profiles}
        for cell in cells:
            p = profile_lookup[cell.sample_profile_id]
            self.assertEqual(p.primary_archetype, cell.archetype)
            self.assertEqual(p.gender, cell.gender)

    def test_occasion_archetype_propagates(self):
        cells = enumerate_grid(self.profiles)
        occ_lookup = {o.occasion: o for o in OCCASIONS}
        for cell in cells:
            self.assertEqual(cell.occasion_archetype, occ_lookup[cell.occasion].occasion_archetype)

    def test_intents_filter_works(self):
        cells = enumerate_grid(self.profiles, intents=["occasion_recommendation"])
        self.assertEqual({c.intent for c in cells}, {"occasion_recommendation"})

    def test_beach_day_excluded_in_winter(self):
        cells = enumerate_grid(self.profiles)
        winter_beach = [c for c in cells if c.occasion == "beach_day" and c.season == "winter"]
        self.assertEqual(winter_beach, [])

    def test_diwali_only_in_autumn(self):
        cells = enumerate_grid(self.profiles)
        diwali_seasons = {c.season for c in cells if c.occasion == "diwali"}
        self.assertEqual(diwali_seasons, {"autumn"})


class OccasionYamlLoaderTests(unittest.TestCase):
    """Regression tests for the Phase 4.4 YAML refactor.

    OCCASIONS used to be a hardcoded 31-entry list that drifted from
    knowledge/style_graph/occasion.yaml (45+ entries). Now it loads
    from the YAML at module import; these tests guard against silent
    truncation, schema drift, or an empty load.
    """

    def test_loads_at_least_30_occasions(self):
        # Floor — the YAML has 45+ entries and shouldn't shrink in
        # ordinary edits. If it does, that's a stylist deletion event
        # worth reviewing.
        self.assertGreaterEqual(len(OCCASIONS), 30)

    def test_each_occasion_has_required_fields(self):
        for o in OCCASIONS:
            with self.subTest(occasion=o.occasion):
                self.assertTrue(o.occasion, "occasion name should be non-empty")
                self.assertTrue(o.occasion_archetype, "archetype should be non-empty")
                self.assertTrue(o.formality, "formality should be non-empty")
                self.assertTrue(o.time, "time should be non-empty")
                self.assertGreater(len(o.seasons), 0, "seasons should be non-empty tuple")

    def test_formality_uses_canonical_values(self):
        # Per architect prompt: business_casual / ultra_formal don't
        # exist on rows. Stick to the 5 canonical FormalityLevel values.
        canonical = {"casual", "smart_casual", "semi_formal", "formal", "ceremonial"}
        for o in OCCASIONS:
            with self.subTest(occasion=o.occasion):
                self.assertIn(o.formality, canonical)

    def test_time_uses_canonical_values(self):
        canonical = {"daytime", "evening", "flexible"}
        for o in OCCASIONS:
            with self.subTest(occasion=o.occasion):
                self.assertIn(o.time, canonical)

    def test_seasons_use_canonical_values(self):
        canonical = {"spring", "summer", "autumn", "winter"}
        for o in OCCASIONS:
            with self.subTest(occasion=o.occasion):
                self.assertTrue(set(o.seasons).issubset(canonical),
                                f"{o.occasion}: unknown season(s) {set(o.seasons) - canonical}")

    def test_loader_function_directly(self):
        # The module-level OCCASIONS calls _load_occasions_from_yaml at
        # import time. Calling it again with the default path should
        # produce the same list — pure function, no caching.
        reloaded = _load_occasions_from_yaml()
        self.assertEqual(len(reloaded), len(OCCASIONS))
        self.assertEqual(
            [o.occasion for o in reloaded],
            [o.occasion for o in OCCASIONS],
        )

    def test_unique_occasion_names(self):
        names = [o.occasion for o in OCCASIONS]
        self.assertEqual(len(names), len(set(names)),
                         "duplicate occasion names in YAML")


class CostEstimateTests(unittest.TestCase):
    def test_estimate_within_budget(self):
        pool = generate_profile_pool()
        cells = enumerate_grid(pool)
        cost = estimate_cost(cells)
        # OPEN_TASKS budget: $10–20K. Should be well under.
        self.assertLess(cost["total_cost_usd"], 20_000)
        self.assertGreater(cost["total_cost_usd"], 100)

    def test_estimate_scales_linearly(self):
        small = estimate_cost([Mock()] * 100)
        large = estimate_cost([Mock()] * 1000)
        self.assertAlmostEqual(
            large["total_cost_usd"] / small["total_cost_usd"], 10.0, places=3,
        )


class CoverageFilterTests(unittest.TestCase):
    def test_marks_below_threshold_infeasible(self):
        cells = enumerate_grid(generate_profile_pool(target_size=24))[:10]
        catalog = Mock()
        catalog.count_skus_matching = Mock(return_value=50)
        reports = evaluate_coverage(cells, catalog, min_skus=100)
        self.assertEqual(len(reports), len(cells))
        self.assertTrue(all(not r.feasible for r in reports))

    def test_marks_above_threshold_feasible(self):
        cells = enumerate_grid(generate_profile_pool(target_size=24))[:5]
        catalog = Mock()
        catalog.count_skus_matching = Mock(return_value=500)
        reports = evaluate_coverage(cells, catalog, min_skus=100)
        self.assertTrue(all(r.feasible for r in reports))

    def test_caches_by_bucket(self):
        """Many cells share (gender, formality); catalog should be hit
        once per unique bucket, not once per cell."""
        cells = enumerate_grid(generate_profile_pool(target_size=24))
        catalog = Mock()
        catalog.count_skus_matching = Mock(return_value=500)
        evaluate_coverage(cells, catalog)

        # 2 genders × 5 formality values = at most 10 unique buckets.
        self.assertLessEqual(catalog.count_skus_matching.call_count, 10)
        # And we did process plenty of cells.
        self.assertGreater(len(cells), 100)


if __name__ == "__main__":
    unittest.main()
