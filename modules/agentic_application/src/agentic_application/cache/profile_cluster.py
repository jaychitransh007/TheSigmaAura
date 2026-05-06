"""Profile clustering for the Phase 2 cache.

Maps a ``UserContext`` to one of 96 buckets used as a cache-key segment
for architect + composer output caching. The cluster captures the
slow-moving parts of a user's profile that shape architect output;
per-turn variables (intent, occasion, formality, weather, style_goal,
time_of_day) live in the full cache key alongside this cluster.

Cluster shape: ``gender × season_group_broad × body_shape`` = 3 × 4 × 8 = 96.
See ``docs/phase_2_cache_design.md`` for the rationale and the
"why these three (and not others)" decisions.

History: the initial design (PR #131) used ``frame_class`` (3 buckets)
giving 36 total. PR #131 review correctly pointed out that BodyShape
is a primary driver of architect output (per outfit_architect.md
lines 368-380, "BodyShape priority" over FrameStructure when they
conflict on width signals). Replaced frame_class with body_shape
to fix the cache-pollution risk where Pear and Inverted Triangle
users would share cached outputs.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..schemas import UserContext


@dataclass(frozen=True)
class ProfileCluster:
    """A 96-bucket profile cluster for cache keying.

    Frozen + hashable so it can serve as a dict key directly. The
    string representation (``str(cluster)``) is the canonical
    cache-key segment — pipe-separated to keep collision-safe across
    bucket rename/reorder.
    """
    gender: str          # feminine | masculine | unisex
    season_group: str    # spring | summer | autumn | winter | unknown
    body_shape: str      # one of _BODY_SHAPE_BUCKETS values, or "unknown"

    def __str__(self) -> str:
        return f"{self.gender}|{self.season_group}|{self.body_shape}"


# ── Bucket definitions ─────────────────────────────────────────

# Gender canonicalisation. The schema says ``UserContext.gender`` is
# a free string; production data uses feminine/masculine/unisex but
# we accept the common alternates defensively.
_GENDER_CANONICAL = {
    "feminine": "feminine",
    "female": "feminine",
    "f": "feminine",
    "masculine": "masculine",
    "male": "masculine",
    "m": "masculine",
    "unisex": "unisex",
    "u": "unisex",
}

# All 12 SeasonalColorGroup values from interpreter._SUB_SEASON_RULES
# end in one of {Spring, Summer, Autumn, Winter} — a suffix match is
# enough to derive the broad season. The interpreter's "Unable to
# Assess" fallback maps to "unknown" rather than picking a bucket.
_BROAD_SEASONS = ("spring", "summer", "autumn", "winter")

# BodyShape — the 7 canonical values from the architect's prompt
# (prompt/outfit_architect.md:255). Stored verbatim from
# analysis_attributes.BodyShape (interpreter does not transform it).
# Lowercased + underscore-joined for cache-key cleanliness.
_BODY_SHAPE_BUCKETS = {
    "pear": "pear",
    "hourglass": "hourglass",
    "apple": "apple",
    "inverted triangle": "inverted_triangle",
    "rectangle": "rectangle",
    "diamond": "diamond",
    "trapezoid": "trapezoid",
}


def _extract_value(raw: Any) -> str:
    """Pull a canonical scalar string out of interpreter output.

    The interpreter wraps every derived value in a dict like
    ``{"value": "Spring", "confidence": 0.7, "evidence_note": "..."}``
    but legacy/test fixtures may pass the raw string. Handle both.
    """
    if isinstance(raw, dict):
        return str(raw.get("value") or "").strip()
    return str(raw or "").strip()


def _bucket_gender(gender: str) -> str:
    return _GENDER_CANONICAL.get((gender or "").strip().lower(), "unisex")


def _bucket_season(seasonal_group: str) -> str:
    """Map any of the 12 sub-seasons to the 4 broad seasons.

    Returns ``"unknown"`` for empty values or "Unable to Assess".
    """
    sg = (seasonal_group or "").strip().lower()
    if not sg or "unable" in sg:
        return "unknown"
    for season in _BROAD_SEASONS:
        if sg.endswith(season):
            return season
    return "unknown"


def _bucket_body_shape(body_shape: str) -> str:
    """Map one of the 7 canonical BodyShape values to a cache bucket.

    Returns ``"unknown"`` for empty values or anything not in the
    canonical list — defensive against future schema changes.
    """
    bs = (body_shape or "").strip().lower()
    return _BODY_SHAPE_BUCKETS.get(bs, "unknown")


def cluster_for(user: UserContext) -> ProfileCluster:
    """Compute the 96-bucket profile cluster for ``user``.

    Defensive against missing / Unable-to-Assess interpreter outputs:
    each dimension defaults to ``"unknown"``. Unknown buckets reduce
    hit rate (each unknown user runs the architect at least once to
    populate their bucket) but keep behavior correct — we don't
    misroute an unknown user into a populated bucket they wouldn't
    fit. BodyShape lives in ``analysis_attributes`` (raw) rather than
    ``derived_interpretations`` because the interpreter does not
    transform it.
    """
    derived = user.derived_interpretations or {}
    attrs = user.analysis_attributes or {}
    return ProfileCluster(
        gender=_bucket_gender(user.gender),
        season_group=_bucket_season(_extract_value(derived.get("SeasonalColorGroup"))),
        body_shape=_bucket_body_shape(_extract_value(attrs.get("BodyShape"))),
    )
