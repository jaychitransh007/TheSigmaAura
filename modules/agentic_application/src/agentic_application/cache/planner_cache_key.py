"""Planner cache-key construction.

Pure function: takes the per-turn inputs the copilot_planner conditions
on, returns a SHA1 hex digest used as the cache lookup key.

The full key shape is documented at length in the
``20260517000000_planner_output_cache.sql`` migration. Quick summary:

    hash(
      tenant_id,                       'default' today
      user_message,                    normalised + length-capped
      profile_cluster,                 96 buckets (same as architect)
      previous_intent,                 follow-up classification signal
      previous_occasion,               follow-up disambiguation signal
      has_attached_image,              changes intent path
      has_person_image,                profile-readiness flag
      wardrobe_count_bucket,           '0' | '1-5' | '6-20' | '21+'
      planner_prompt_version,          SHA of prompt/copilot_planner.md
    )

Every field is normalised before hashing so trivial casing / whitespace
differences don't fragment the cache. The architect's
``cluster_for_context`` is reused — same bucketing for both caches
keeps observability consistent.
"""
from __future__ import annotations

import hashlib
import re
from typing import Optional

from .architect_cache_key import _normalise
from .profile_cluster import ProfileCluster


# Trim long messages to keep the cache key bounded. Anything past 200
# chars is "long-tail unique phrasing; will miss anyway". Two messages
# sharing the first 200 chars will hash to the same key — acceptable
# tradeoff: profile_cluster + previous_intent + previous_occasion
# already discriminate most semantic differences.
_USER_MESSAGE_MAX_LEN = 200


def _normalise_user_message(value: Optional[str]) -> str:
    """Lowercase, strip, collapse whitespace, drop trailing punctuation,
    cap length.

    Trailing punctuation removal lets "Dress me for date night",
    "Dress me for date night.", and "Dress me for date night!" all
    hash to the same key — they all classify identically downstream.
    Mid-message punctuation is preserved (it occasionally disambiguates
    intent: "Send me an outfit" vs "Send me, an outfit?")."""
    if value is None:
        return ""
    s = re.sub(r"\s+", " ", str(value).strip().lower())
    s = re.sub(r"[.!?,;:]+$", "", s)
    return s[:_USER_MESSAGE_MAX_LEN]


def _wardrobe_count_bucket(count: int) -> str:
    """Coarse-bucket wardrobe size so adding a single item doesn't bust
    the cache. The planner's `wardrobe_summary` exposes count + top 5
    items, but minor variations in top-5 stay within bucket and
    serve the same plan — acceptable since the planner only uses
    wardrobe presence as a context signal, not for itemised reasoning.
    """
    if count <= 0:
        return "0"
    if count <= 5:
        return "1-5"
    if count <= 20:
        return "6-20"
    return "21+"


def _bool_token(value: object) -> str:
    """Stable string token for booleans in the hash payload. ``True``
    → "1", everything else → "0". Avoids the Python-version
    difference where ``str(True)`` is "True" vs JSON's "true"."""
    return "1" if value else "0"


def build_planner_cache_key(
    *,
    tenant_id: str,
    user_message: str,
    cluster: ProfileCluster,
    previous_intent: Optional[str],
    previous_occasion: Optional[str],
    has_attached_image: bool,
    has_person_image: bool,
    wardrobe_count: int,
    planner_prompt_version: str,
) -> str:
    """Compute the SHA1 hex digest used as the planner cache key.

    Pure function: no I/O, no side effects.
    """
    parts = [
        _normalise(tenant_id) or "default",
        _normalise_user_message(user_message),
        str(cluster),
        _normalise(previous_intent),
        _normalise(previous_occasion),
        _bool_token(has_attached_image),
        _bool_token(has_person_image),
        _wardrobe_count_bucket(int(wardrobe_count or 0)),
        _normalise(planner_prompt_version),
    ]
    payload = "|".join(parts)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def denormalised_key_fields(
    *,
    tenant_id: str,
    user_message: str,
    cluster: ProfileCluster,
    previous_intent: Optional[str],
    previous_occasion: Optional[str],
    has_attached_image: bool,
    has_person_image: bool,
    wardrobe_count: int,
    planner_prompt_version: str,
    planner_model: str,
) -> dict:
    """The key fields stamped on the cache row for ops queries.

    Mirrors the inputs to ``build_planner_cache_key`` plus
    ``planner_model`` (helpful when correlating cache hit rate with
    the model that originally generated the entry)."""
    user_message_norm = _normalise_user_message(user_message)
    return {
        "tenant_id": tenant_id or "default",
        "user_message_preview": (user_message or "").strip()[:120],
        "user_message_norm": user_message_norm,
        "profile_cluster": str(cluster),
        "previous_intent": _normalise(previous_intent) or None,
        "previous_occasion": _normalise(previous_occasion) or None,
        "has_attached_image": bool(has_attached_image),
        "has_person_image": bool(has_person_image),
        "wardrobe_count_bucket": _wardrobe_count_bucket(int(wardrobe_count or 0)),
        "planner_prompt_version": planner_prompt_version,
        "planner_model": planner_model,
    }
