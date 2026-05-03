"""Recent signals — deterministic stylist-voice copy for the profile dossier.

Phase 14 Step 5 left a "Recent signals" timeline as the only deferred item
on the profile redesign. The data exists already (``user_comfort_learning``
+ ``feedback_events`` + ``catalog_interaction_history``); this module
shapes it into a small list of human-readable lines like:

    "Leaning Autumn from your saved looks"   [comfort_learning]
    "Asked for warmer tones explicitly"      [comfort_learning]
    "Liked 4 outfits in the last 14 days"    [feedback]
    "Skipped 2 wishlist items"               [catalog]

Strict rules:

- No LLM call. The copy strings are derived deterministically from raw
  rows so the timeline is fast to render and predictable per-user.
- Items are ordered most-recent-first; the caller decides how many to
  show (default 5).
- The fan-in is bounded — we read the most recent 50 rows from each of
  the three sources, never more, so this stays cheap on the profile
  page render.
- Empty states return an empty list — the caller renders the editorial
  "Aura is still learning your preferences" copy.

This satisfies the deferred Phase 14 Step 5 item — see
``docs/WORKFLOW_REFERENCE.md`` § Phase History (Phase 14).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional


_FRESH_WINDOW_DAYS = 30


@dataclass(frozen=True)
class ProfileSignal:
    """A single line shown on the Recent Signals timeline."""

    label: str          # primary line, stylist voice
    detail: str         # one short qualifier (e.g. "from 4 saved looks")
    source: str         # comfort_learning | feedback | catalog
    when: str           # ISO timestamp of the most recent contributing row

    def as_dict(self) -> Dict[str, str]:
        return {
            "label": self.label,
            "detail": self.detail,
            "source": self.source,
            "when": self.when,
        }


def _parse_iso(s: str) -> Optional[datetime]:
    if not s:
        return None
    try:
        # accept both `Z` and `+00:00` suffixes
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def _is_fresh(ts: Optional[datetime], window_days: int = _FRESH_WINDOW_DAYS) -> bool:
    if ts is None:
        return False
    cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)
    return ts >= cutoff


def _comfort_signals(rows: Iterable[Dict[str, Any]]) -> List[ProfileSignal]:
    """Bucket comfort-learning rows by signal_source + direction; emit one line per bucket."""
    fresh_rows = [r for r in rows if _is_fresh(_parse_iso(str(r.get("created_at") or "")))]
    if not fresh_rows:
        return []

    # Bucket by (signal_source, detected_seasonal_direction). Each bucket
    # becomes one line so the timeline doesn't repeat the same fact.
    buckets: Dict[tuple[str, str], List[Dict[str, Any]]] = {}
    for r in fresh_rows:
        key = (
            str(r.get("signal_source") or "").strip(),
            str(r.get("detected_seasonal_direction") or "").strip(),
        )
        buckets.setdefault(key, []).append(r)

    out: List[ProfileSignal] = []
    for (source, direction), bucket in buckets.items():
        if not direction:
            continue
        latest = max(bucket, key=lambda r: str(r.get("created_at") or ""))
        when = str(latest.get("created_at") or "")
        n = len(bucket)
        if source == "outfit_like":
            label = f"Leaning {direction} from your saved looks"
            detail = f"{n} like{'s' if n != 1 else ''} in the last 30 days"
        elif source == "color_request":
            label = f"Asked for {direction.lower()} tones explicitly"
            detail = f"{n} request{'s' if n != 1 else ''} in the last 30 days"
        else:
            label = f"Trending toward {direction}"
            detail = f"{n} signal{'s' if n != 1 else ''} via {source or 'feedback'}"
        out.append(ProfileSignal(
            label=label, detail=detail, source="comfort_learning", when=when,
        ))
    return out


def _feedback_signals(rows: Iterable[Dict[str, Any]]) -> List[ProfileSignal]:
    """Aggregate likes / dislikes from feedback_events into one line each."""
    fresh = [r for r in rows if _is_fresh(_parse_iso(str(r.get("created_at") or "")))]
    if not fresh:
        return []

    counts = Counter(str(r.get("event_type") or "").lower() for r in fresh)
    out: List[ProfileSignal] = []
    if counts.get("like"):
        latest = max((r for r in fresh if r.get("event_type") == "like"),
                     key=lambda r: str(r.get("created_at") or ""))
        n = counts["like"]
        out.append(ProfileSignal(
            label=f"Liked {n} outfit{'s' if n != 1 else ''} recently",
            detail="last 30 days",
            source="feedback",
            when=str(latest.get("created_at") or ""),
        ))
    if counts.get("dislike"):
        latest = max((r for r in fresh if r.get("event_type") == "dislike"),
                     key=lambda r: str(r.get("created_at") or ""))
        n = counts["dislike"]
        out.append(ProfileSignal(
            label=f"Pushed back on {n} outfit{'s' if n != 1 else ''}",
            detail="last 30 days",
            source="feedback",
            when=str(latest.get("created_at") or ""),
        ))
    return out


def _catalog_signals(rows: Iterable[Dict[str, Any]]) -> List[ProfileSignal]:
    """Aggregate shopping interactions (skip / save) from catalog_interaction_history."""
    fresh = [r for r in rows if _is_fresh(_parse_iso(str(r.get("created_at") or "")))]
    if not fresh:
        return []

    counts = Counter(str(r.get("interaction_type") or "").lower() for r in fresh)
    out: List[ProfileSignal] = []
    if counts.get("save"):
        latest = max((r for r in fresh if r.get("interaction_type") == "save"),
                     key=lambda r: str(r.get("created_at") or ""))
        n = counts["save"]
        out.append(ProfileSignal(
            label=f"Saved {n} piece{'s' if n != 1 else ''} for later",
            detail="last 30 days",
            source="catalog",
            when=str(latest.get("created_at") or ""),
        ))
    if counts.get("skip"):
        latest = max((r for r in fresh if r.get("interaction_type") == "skip"),
                     key=lambda r: str(r.get("created_at") or ""))
        n = counts["skip"]
        out.append(ProfileSignal(
            label=f"Skipped {n} item{'s' if n != 1 else ''} from the catalog",
            detail="last 30 days",
            source="catalog",
            when=str(latest.get("created_at") or ""),
        ))
    return out


def build_recent_signals(
    *,
    comfort_rows: Iterable[Dict[str, Any]],
    feedback_rows: Iterable[Dict[str, Any]],
    catalog_rows: Iterable[Dict[str, Any]],
    limit: int = 5,
) -> List[Dict[str, str]]:
    """Public entry point — returns up to ``limit`` signals, newest first.

    Each input is expected to be already filtered to a single user_id and
    capped at a reasonable size by the caller (≤50 rows from each source
    is plenty — older rows fall outside the 30-day fresh window anyway).
    """
    all_signals: List[ProfileSignal] = []
    all_signals.extend(_comfort_signals(comfort_rows))
    all_signals.extend(_feedback_signals(feedback_rows))
    all_signals.extend(_catalog_signals(catalog_rows))
    all_signals.sort(key=lambda s: s.when or "", reverse=True)
    return [s.as_dict() for s in all_signals[: max(0, int(limit))]]
