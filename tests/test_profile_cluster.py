"""Unit tests for the Phase 2 profile clustering function.

The cluster maps a UserContext to one of 96 buckets:
gender (3) × season_group_broad (4) × body_shape (8). See
docs/phase_2_cache_design.md for the rationale.

History: the initial 36-bucket design (PR #131) used frame_class.
Replaced with body_shape per PR #131 review — BodyShape has priority
over FrameStructure in the architect prompt.

Tests focus on:
- All 12 SeasonalColorGroup sub-seasons map to the correct broad season
- All 7 canonical BodyShape values map to their bucket
- Missing / "Unable to Assess" inputs route to "unknown" buckets
- Gender variants (feminine / female / f / case-mixed) all canonicalise
- ProfileCluster is hashable (so it can serve as a dict key)
- str(cluster) is deterministic and pipe-separated
- The full Cartesian product of valid inputs really yields 96 distinct strings
- BodyShape is read from analysis_attributes (raw), not derived_interpretations
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

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

from agentic_application.cache import ProfileCluster, cluster_for
from agentic_application.cache.profile_cluster import (
    _BODY_SHAPE_BUCKETS,
    _BROAD_SEASONS,
)
from agentic_application.schemas import UserContext


def _user(
    gender: str = "feminine",
    *,
    season: str = "Soft Autumn",
    body_shape: str = "Hourglass",
) -> UserContext:
    """Build a UserContext with the cluster-relevant attributes set.

    BodyShape lives in analysis_attributes (raw); SeasonalColorGroup
    in derived_interpretations (interpreter-wrapped).
    """
    return UserContext(
        user_id="u1",
        gender=gender,
        analysis_attributes={"BodyShape": body_shape},
        derived_interpretations={
            "SeasonalColorGroup": {"value": season, "confidence": 0.8},
        },
    )


class GenderBucketingTests(unittest.TestCase):

    def test_canonical_values_passthrough(self) -> None:
        for v in ("feminine", "masculine", "unisex"):
            self.assertEqual(cluster_for(_user(gender=v)).gender, v)

    def test_alternates_canonicalise(self) -> None:
        self.assertEqual(cluster_for(_user(gender="female")).gender, "feminine")
        self.assertEqual(cluster_for(_user(gender="male")).gender, "masculine")
        self.assertEqual(cluster_for(_user(gender="F")).gender, "feminine")
        self.assertEqual(cluster_for(_user(gender="M")).gender, "masculine")
        self.assertEqual(cluster_for(_user(gender="U")).gender, "unisex")

    def test_unknown_gender_routes_to_unisex(self) -> None:
        self.assertEqual(cluster_for(_user(gender="")).gender, "unisex")
        self.assertEqual(cluster_for(_user(gender="other")).gender, "unisex")

    def test_case_insensitive(self) -> None:
        self.assertEqual(cluster_for(_user(gender="FEMININE")).gender, "feminine")
        self.assertEqual(cluster_for(_user(gender="Masculine")).gender, "masculine")


class SeasonBucketingTests(unittest.TestCase):

    SUB_SEASONS = {
        "Spring": ["Warm Spring", "Light Spring", "Clear Spring"],
        "Summer": ["Cool Summer", "Light Summer", "Soft Summer"],
        "Autumn": ["Warm Autumn", "Deep Autumn", "Soft Autumn"],
        "Winter": ["Cool Winter", "Deep Winter", "Clear Winter"],
    }

    def test_all_12_sub_seasons_map_correctly(self) -> None:
        for broad, subs in self.SUB_SEASONS.items():
            for sub in subs:
                with self.subTest(sub_season=sub):
                    self.assertEqual(
                        cluster_for(_user(season=sub)).season_group,
                        broad.lower(),
                    )

    def test_unable_to_assess_routes_to_unknown(self) -> None:
        self.assertEqual(cluster_for(_user(season="Unable to Assess")).season_group, "unknown")

    def test_empty_routes_to_unknown(self) -> None:
        self.assertEqual(cluster_for(_user(season="")).season_group, "unknown")

    def test_unrecognised_value_routes_to_unknown(self) -> None:
        self.assertEqual(cluster_for(_user(season="Mystery Season")).season_group, "unknown")

    def test_raw_string_value_supported(self) -> None:
        u = UserContext(
            user_id="u1",
            gender="feminine",
            analysis_attributes={"BodyShape": "Hourglass"},
            derived_interpretations={"SeasonalColorGroup": "Soft Autumn"},
        )
        self.assertEqual(cluster_for(u).season_group, "autumn")


class BodyShapeBucketingTests(unittest.TestCase):

    # All 7 canonical BodyShape values from prompt/outfit_architect.md:255.
    CANONICAL_SHAPES = {
        "Pear": "pear",
        "Hourglass": "hourglass",
        "Apple": "apple",
        "Inverted Triangle": "inverted_triangle",
        "Rectangle": "rectangle",
        "Diamond": "diamond",
        "Trapezoid": "trapezoid",
    }

    def test_all_7_canonical_shapes_map_correctly(self) -> None:
        for label, bucket in self.CANONICAL_SHAPES.items():
            with self.subTest(body_shape=label):
                self.assertEqual(
                    cluster_for(_user(body_shape=label)).body_shape,
                    bucket,
                )

    def test_case_insensitive(self) -> None:
        self.assertEqual(cluster_for(_user(body_shape="HOURGLASS")).body_shape, "hourglass")
        self.assertEqual(cluster_for(_user(body_shape="inverted triangle")).body_shape, "inverted_triangle")

    def test_unable_to_assess_routes_to_unknown(self) -> None:
        self.assertEqual(cluster_for(_user(body_shape="Unable to Assess")).body_shape, "unknown")

    def test_empty_routes_to_unknown(self) -> None:
        self.assertEqual(cluster_for(_user(body_shape="")).body_shape, "unknown")

    def test_unrecognised_value_routes_to_unknown(self) -> None:
        self.assertEqual(cluster_for(_user(body_shape="Banana")).body_shape, "unknown")

    def test_body_shape_read_from_analysis_attributes(self) -> None:
        # BodyShape lives in analysis_attributes (raw), not
        # derived_interpretations — the interpreter does not transform
        # it. If someone moves it later, both this test and the
        # production code need updating.
        u = UserContext(
            user_id="u1",
            gender="feminine",
            analysis_attributes={"BodyShape": "Pear"},
            derived_interpretations={"SeasonalColorGroup": {"value": "Soft Autumn"}},
        )
        self.assertEqual(cluster_for(u).body_shape, "pear")

    def test_raw_string_value_supported(self) -> None:
        # Production stores BodyShape as a raw string; legacy fixtures
        # may wrap it in {"value": ...}. Handle both.
        u = UserContext(
            user_id="u1",
            gender="feminine",
            analysis_attributes={"BodyShape": {"value": "Hourglass"}},
            derived_interpretations={"SeasonalColorGroup": {"value": "Soft Autumn"}},
        )
        self.assertEqual(cluster_for(u).body_shape, "hourglass")


class ProfileClusterValueTests(unittest.TestCase):

    def test_str_is_pipe_separated(self) -> None:
        c = ProfileCluster(gender="feminine", season_group="autumn", body_shape="hourglass")
        self.assertEqual(str(c), "feminine|autumn|hourglass")

    def test_is_hashable(self) -> None:
        c1 = ProfileCluster("feminine", "autumn", "hourglass")
        c2 = ProfileCluster("feminine", "autumn", "hourglass")
        d = {c1: 1}
        self.assertEqual(d[c2], 1)

    def test_distinct_clusters_distinct_strings(self) -> None:
        # The full Cartesian product of valid (non-unknown) buckets
        # must yield exactly 96 distinct cache-key strings:
        # 3 genders × 4 broad seasons × 8 body shapes = 96.
        # (8 = 7 canonical + "unknown"; we include "unknown" as a
        # valid bucket so unknown users still get their own slot.)
        seen: set[str] = set()
        body_buckets = set(_BODY_SHAPE_BUCKETS.values()) | {"unknown"}
        self.assertEqual(len(body_buckets), 8)
        for g in ("feminine", "masculine", "unisex"):
            for s in _BROAD_SEASONS:
                for b in body_buckets:
                    seen.add(str(ProfileCluster(g, s, b)))
        self.assertEqual(len(seen), 3 * 4 * 8)


class IntegrationTests(unittest.TestCase):

    def test_typical_alpha_user(self) -> None:
        user = _user(gender="feminine", season="Soft Autumn", body_shape="Hourglass")
        c = cluster_for(user)
        self.assertEqual(c.gender, "feminine")
        self.assertEqual(c.season_group, "autumn")
        self.assertEqual(c.body_shape, "hourglass")
        self.assertEqual(str(c), "feminine|autumn|hourglass")

    def test_minimal_profile_routes_through_unknowns(self) -> None:
        user = UserContext(user_id="u1", gender="masculine")
        c = cluster_for(user)
        self.assertEqual(c, ProfileCluster("masculine", "unknown", "unknown"))

    def test_function_is_pure(self) -> None:
        user = _user()
        self.assertEqual(cluster_for(user), cluster_for(user))


if __name__ == "__main__":
    unittest.main()
