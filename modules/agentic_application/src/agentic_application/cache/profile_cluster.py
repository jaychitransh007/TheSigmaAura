"""Profile clustering for the Phase 2 cache.

Maps a ``UserContext`` to one of 36 buckets used as a cache-key segment
for architect + composer output caching. The cluster captures the
slow-moving parts of a user's profile that shape architect output;
per-turn variables (intent, occasion, formality) live in the full
cache key alongside this cluster.

Cluster shape: ``gender × season_group_broad × frame_class`` = 3 × 4 × 3 = 36.
See ``docs/phase_2_cache_design.md`` for the rationale and the
"why these three (and not others)" decisions.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..schemas import UserContext


@dataclass(frozen=True)
class ProfileCluster:
    """A 36-bucket profile cluster for cache keying.

    Frozen + hashable so it can serve as a dict key directly. The
    string representation (``str(cluster)``) is the canonical
    cache-key segment — pipe-separated to keep collision-safe across
    bucket rename/reorder.
    """
    gender: str          # feminine | masculine | unisex
    season_group: str    # spring | summer | autumn | winter | unknown
    frame_class: str     # slim | medium | sturdy | unknown

    def __str__(self) -> str:
        return f"{self.gender}|{self.season_group}|{self.frame_class}"


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

# FrameStructure has 6 labels (interpreter._derive_frame_structure).
# Collapsed to 3 buckets per design: Light* → slim, Medium* → medium,
# Solid* → sturdy. Unable-to-Assess → "unknown".
_FRAME_BUCKETS = {
    "Light and Narrow": "slim",
    "Light and Broad": "slim",
    "Medium and Balanced": "medium",
    "Solid and Narrow": "sturdy",
    "Solid and Balanced": "sturdy",
    "Solid and Broad": "sturdy",
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


def _bucket_frame(frame_structure: str) -> str:
    return _FRAME_BUCKETS.get((frame_structure or "").strip(), "unknown")


def cluster_for(user: UserContext) -> ProfileCluster:
    """Compute the 36-bucket profile cluster for ``user``.

    Defensive against missing / Unable-to-Assess interpreter outputs:
    each dimension defaults to ``"unknown"``. Unknown buckets reduce
    hit rate (each unknown user runs the architect at least once to
    populate their bucket) but keep behavior correct — we don't
    misroute an unknown user into a populated bucket they wouldn't
    fit.
    """
    derived = user.derived_interpretations or {}
    return ProfileCluster(
        gender=_bucket_gender(user.gender),
        season_group=_bucket_season(_extract_value(derived.get("SeasonalColorGroup"))),
        frame_class=_bucket_frame(_extract_value(derived.get("FrameStructure"))),
    )
