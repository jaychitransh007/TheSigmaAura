"""Unit tests for the Phase 2 profile clustering function.

The cluster maps a UserContext to one of 36 buckets:
gender (3) × season_group_broad (4) × frame_class (3). See
docs/phase_2_cache_design.md for the rationale.

Tests focus on:
- All 12 SeasonalColorGroup sub-seasons map to the correct broad season
- All 6 FrameStructure labels map to the correct frame_class
- Missing / "Unable to Assess" inputs route to "unknown" buckets
- Gender variants (feminine / female / f / case-mixed) all canonicalise
- ProfileCluster is hashable (so it can serve as a dict key)
- str(cluster) is deterministic and pipe-separated
- The full Cartesian product of valid inputs really yields 36 distinct strings
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
    _BROAD_SEASONS,
    _FRAME_BUCKETS,
)
from agentic_application.schemas import UserContext


# Helper: build a UserContext with the relevant derived_interpretations
def _user(gender: str = "feminine", *, season: str = "Soft Autumn", frame: str = "Medium and Balanced") -> UserContext:
    return UserContext(
        user_id="u1",
        gender=gender,
        derived_interpretations={
            "SeasonalColorGroup": {"value": season, "confidence": 0.8},
            "FrameStructure": {"value": frame, "confidence": 0.7},
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
        # Defensive: if a user record has an empty/strange gender string,
        # bucket as unisex rather than crashing or routing unpredictably.
        self.assertEqual(cluster_for(_user(gender="")).gender, "unisex")
        self.assertEqual(cluster_for(_user(gender="other")).gender, "unisex")

    def test_case_insensitive(self) -> None:
        self.assertEqual(cluster_for(_user(gender="FEMININE")).gender, "feminine")
        self.assertEqual(cluster_for(_user(gender="Masculine")).gender, "masculine")


class SeasonBucketingTests(unittest.TestCase):

    # All 12 sub-seasons from interpreter.SUB_SEASON_PALETTE_MAP must
    # map to the broad season suffix. If interpreter adds new
    # sub-seasons, both this list and the production code need
    # updating — keep them in lockstep.
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
        # Defensive: if interpreter ever emits an unexpected value,
        # don't silently bucket it under one of the known seasons.
        self.assertEqual(cluster_for(_user(season="Mystery Season")).season_group, "unknown")

    def test_raw_string_value_supported(self) -> None:
        # Legacy/test-fixture path: derived_interpretations may carry
        # a raw string rather than the standard {"value": ...} dict.
        u = UserContext(
            user_id="u1",
            gender="feminine",
            derived_interpretations={"SeasonalColorGroup": "Soft Autumn"},
        )
        self.assertEqual(cluster_for(u).season_group, "autumn")


class FrameBucketingTests(unittest.TestCase):

    def test_all_6_frame_labels_map_correctly(self) -> None:
        # Source of truth: interpreter._derive_frame_structure label dict
        expected = {
            "Light and Narrow": "slim",
            "Light and Broad": "slim",
            "Medium and Balanced": "medium",
            "Solid and Narrow": "sturdy",
            "Solid and Balanced": "sturdy",
            "Solid and Broad": "sturdy",
        }
        for label, bucket in expected.items():
            with self.subTest(frame_label=label):
                self.assertEqual(cluster_for(_user(frame=label)).frame_class, bucket)

    def test_unable_to_assess_routes_to_unknown(self) -> None:
        self.assertEqual(cluster_for(_user(frame="Unable to Assess")).frame_class, "unknown")

    def test_empty_routes_to_unknown(self) -> None:
        self.assertEqual(cluster_for(_user(frame="")).frame_class, "unknown")


class ProfileClusterValueTests(unittest.TestCase):

    def test_str_is_pipe_separated(self) -> None:
        c = ProfileCluster(gender="feminine", season_group="autumn", frame_class="medium")
        self.assertEqual(str(c), "feminine|autumn|medium")

    def test_is_hashable(self) -> None:
        # Must be usable as a dict key for the metrics dashboard.
        c1 = ProfileCluster("feminine", "autumn", "medium")
        c2 = ProfileCluster("feminine", "autumn", "medium")
        d = {c1: 1}
        self.assertEqual(d[c2], 1)

    def test_distinct_clusters_distinct_strings(self) -> None:
        # The full Cartesian product of valid (non-unknown) buckets
        # must yield exactly 36 distinct cache-key strings.
        seen: set[str] = set()
        for g in ("feminine", "masculine", "unisex"):
            for s in _BROAD_SEASONS:
                for f in set(_FRAME_BUCKETS.values()):
                    seen.add(str(ProfileCluster(g, s, f)))
        self.assertEqual(len(seen), 3 * 4 * 3)


class IntegrationTests(unittest.TestCase):

    def test_typical_alpha_user(self) -> None:
        user = _user(gender="feminine", season="Soft Autumn", frame="Medium and Balanced")
        c = cluster_for(user)
        self.assertEqual(c.gender, "feminine")
        self.assertEqual(c.season_group, "autumn")
        self.assertEqual(c.frame_class, "medium")
        self.assertEqual(str(c), "feminine|autumn|medium")

    def test_minimal_profile_routes_through_unknowns(self) -> None:
        # A user mid-onboarding may not have SeasonalColorGroup or
        # FrameStructure derived yet. The cluster falls through to
        # unknown buckets — they still get cached, just under
        # gender|unknown|unknown which serves anyone with the same
        # gender and a not-yet-derived profile.
        user = UserContext(user_id="u1", gender="masculine")
        c = cluster_for(user)
        self.assertEqual(c, ProfileCluster("masculine", "unknown", "unknown"))

    def test_function_is_pure(self) -> None:
        # Running cluster_for twice on the same user gives the same
        # result. No side effects, no state.
        user = _user()
        self.assertEqual(cluster_for(user), cluster_for(user))


if __name__ == "__main__":
    unittest.main()
