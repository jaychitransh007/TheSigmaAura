"""Architect cache-key construction.

Pure function: takes the per-turn inputs the architect conditions on,
returns a SHA1 hex digest used as the cache lookup key.

The full key shape (see docs/phase_2_cache_design.md) is:

    hash(
      tenant_id,                       'default' today
      intent,                          planner-emitted enum
      profile_cluster,                 96 buckets — see profile_cluster.py
      occasion_signal,                 ~45 values from occasion.yaml
      calendar_season,                 spring/summer/autumn/winter
      formality_hint,                  planner-emitted
      weather_context,                 from LiveContext
      style_goal,                      from LiveContext (free text → normalised)
      time_of_day,                     from LiveContext
      architect_prompt_version,        SHA1 of base + fragments (set by outfit_architect.py)
    )

Every field is normalised (lower / strip / collapse) before hashing
so trivial casing / whitespace differences don't fragment the cache.
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime
from typing import Optional

from ..schemas import CombinedContext
from .profile_cluster import ProfileCluster, cluster_for


# Style goal is free-text from the planner. Truncate + collapse so
# "Edgy Date Night" and "edgy date night " hash to the same bucket.
_STYLE_GOAL_MAX_LEN = 80


def _normalise(value: Optional[str]) -> str:
    """Lowercase, strip, collapse whitespace. Empty / None → ''."""
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value).strip().lower())


def _normalise_style_goal(value: Optional[str]) -> str:
    """Same as `_normalise` plus a length cap.

    Free-text goals have a long tail of unique phrasings. The cap
    prevents one user's verbose 500-char paragraph from getting its
    own cache slot — anything past 80 chars is "long-tail; will miss
    anyway". Tradeoff: two long goals that share the first 80 chars
    will hash to the same key and serve the same cached direction.
    Acceptable: cluster + occasion + formality already discriminate
    most semantic differences.
    """
    return _normalise(value)[:_STYLE_GOAL_MAX_LEN]


def calendar_season_for(date: datetime) -> str:
    """Map a date to its calendar season string.

    Northern Hemisphere meteorological seasons (Mar-May spring,
    Jun-Aug summer, Sep-Nov autumn, Dec-Feb winter). Aura's user base
    is Indian-urban today; revisit if/when we serve users in the
    Southern Hemisphere.
    """
    month = date.month
    if 3 <= month <= 5:
        return "spring"
    if 6 <= month <= 8:
        return "summer"
    if 9 <= month <= 11:
        return "autumn"
    return "winter"


def build_architect_cache_key(
    *,
    tenant_id: str,
    intent: str,
    cluster: ProfileCluster,
    combined_context: CombinedContext,
    architect_prompt_version: str,
    now: Optional[datetime] = None,
) -> str:
    """Compute the SHA1 hex digest used as the architect cache key.

    Pure function: no I/O, no side effects, no clock reads (clock is
    injected via ``now=`` so tests can pin it).
    """
    live = combined_context.live
    parts = [
        _normalise(tenant_id) or "default",
        _normalise(intent),
        str(cluster),
        _normalise(live.occasion_signal),
        calendar_season_for(now or datetime.utcnow()),
        _normalise(live.formality_hint),
        _normalise(live.weather_context),
        _normalise_style_goal(getattr(live, "style_goal", "")),
        _normalise(live.time_of_day),
        _normalise(architect_prompt_version),
    ]
    # Pipe-joined and hashed. The hash is what's stored; the
    # denormalised parts get stamped on the row separately for ops
    # observability.
    payload = "|".join(parts)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def denormalised_key_fields(
    *,
    tenant_id: str,
    intent: str,
    cluster: ProfileCluster,
    combined_context: CombinedContext,
    architect_prompt_version: str,
    architect_model: str,
    now: Optional[datetime] = None,
) -> dict:
    """The key fields stamped on the cache row for ops queries.

    Mirrors the inputs to ``build_architect_cache_key`` plus
    ``architect_model`` (helpful when correlating cache hit rate with
    the model that originally generated the entry).
    """
    live = combined_context.live
    return {
        "tenant_id": tenant_id or "default",
        "intent": _normalise(intent),
        "profile_cluster": str(cluster),
        "occasion_signal": _normalise(live.occasion_signal),
        "calendar_season": calendar_season_for(now or datetime.utcnow()),
        "formality_hint": _normalise(live.formality_hint),
        "weather_context": _normalise(live.weather_context),
        "style_goal": _normalise_style_goal(getattr(live, "style_goal", "")),
        "time_of_day": _normalise(live.time_of_day),
        "architect_prompt_version": architect_prompt_version,
        "architect_model": architect_model,
    }


def cluster_for_context(combined_context: CombinedContext) -> ProfileCluster:
    """Convenience wrapper — most call sites have CombinedContext, not UserContext."""
    return cluster_for(combined_context.user)
