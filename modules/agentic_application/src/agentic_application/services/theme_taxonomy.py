"""Theme taxonomy for the Outfits tab — Item 7 of the May 1, 2026 plan.

The Outfits tab groups historical recommendation turns by
``occasion_signal``. That signal is whatever the planner extracted from
the user message and is uncontrolled vocabulary, which means
semantically-equivalent occasions split into many small buckets:
``casual`` / ``casual outing`` / ``weekend outing`` are one outing;
``engagement`` / ``traditional engagement`` / ``wedding engagement``
are one wedding cycle. This module collapses the long tail into eight
canonical themes the user actually thinks in.

Properties:

- **Pure function.** ``map_to_theme`` is a deterministic dict lookup —
  no LLM call per turn, no clustering, fully inspectable.
- **Read-time.** The endpoint applies the mapper when it builds the
  intent-history response. No migration, no backfill, no planner
  change; rerunning the mapper after editing this file re-themes the
  full history.
- **Precedence-ordered.** Keywords are matched in declared order:
  wedding > festive > date > work > travel > evening > casual.
  So "engagement evening" lands in *Wedding & Engagement* (correct);
  "office cocktail" lands in *Work & Professional* (correct).
- **Telemetry-friendly.** Signals that don't match any keyword fall
  through to ``style_sessions`` and the caller is expected to log them
  to ``tool_traces`` so the keyword list can evolve with usage.

When in doubt about a new theme, prefer adding to an existing bucket
over creating a ninth one. The user value is in *fewer*, more
recognisable themes — not exhaustive ontology.
"""

from __future__ import annotations

import re
from typing import Dict, List, Pattern, Tuple


# Canonical theme buckets. The ``order`` field is the *fallback* sort
# key used when no theme has any active turns; live themes are sorted
# by most-recent-turn timestamp so the user's currently-active intents
# float to the top.
THEMES: Dict[str, Dict[str, object]] = {
    "wedding": {
        "key": "wedding",
        "label": "Wedding & Engagement",
        "description": "Sangeet, mehendi, engagement, ceremony, reception",
        "order": 1,
    },
    "festive": {
        "key": "festive",
        "label": "Festive & Celebration",
        "description": "Diwali, Eid, festivals, family functions, birthdays",
        "order": 2,
    },
    "date": {
        "key": "date",
        "label": "Date & Romance",
        "description": "Date nights, anniversaries, romantic dinners",
        "order": 3,
    },
    "work": {
        "key": "work",
        "label": "Work & Professional",
        "description": "Office, business meetings, interviews, work events",
        "order": 4,
    },
    "casual": {
        "key": "casual",
        "label": "Casual & Everyday",
        "description": "Brunches, weekends, errands, daily wear",
        "order": 5,
    },
    "travel": {
        "key": "travel",
        "label": "Travel & Vacation",
        "description": "Beach, vacations, trips, holidays, airports",
        "order": 6,
    },
    "evening": {
        "key": "evening",
        "label": "Evening & Party",
        "description": "Cocktails, parties, night-outs, dinner parties",
        "order": 7,
    },
    "style_sessions": {
        "key": "style_sessions",
        "label": "Style Sessions",
        "description": "Pairing requests, advice, and looks without a specific occasion",
        "order": 99,
    },
}


# Keyword → theme mapping. Order matters — the FIRST keyword whose
# substring is found in the lowercased signal wins. This lets specific
# event types (sangeet, baraat) outrank generic energy (evening) and
# lets work-codes (interview, business) outrank "casual".
#
# Adding a new keyword: pick the most-specific theme it should map to,
# place the entry above any broader keyword that would otherwise win.
KEYWORDS: List[Tuple[str, str]] = [
    # ── Wedding & Engagement (most specific first) ─────────────────────
    ("sangeet", "wedding"),
    ("mehendi", "wedding"),
    ("haldi", "wedding"),
    ("baraat", "wedding"),
    ("reception", "wedding"),
    ("engagement", "wedding"),
    ("wedding ceremony", "wedding"),
    ("wedding", "wedding"),
    ("nikkah", "wedding"),
    ("nikah", "wedding"),
    ("bridal", "wedding"),
    ("groom", "wedding"),

    # ── Festive & Celebration ──────────────────────────────────────────
    ("diwali", "festive"),
    ("holi", "festive"),
    ("eid", "festive"),
    ("navratri", "festive"),
    ("durga", "festive"),
    ("ganesh", "festive"),
    ("raksha", "festive"),
    ("festival", "festive"),
    ("family function", "festive"),
    ("family event", "festive"),
    ("birthday", "festive"),
    ("anniversary celebration", "festive"),
    ("housewarming", "festive"),
    ("naming ceremony", "festive"),
    ("baby shower", "festive"),

    # ── Date & Romance ─────────────────────────────────────────────────
    ("date night", "date"),
    ("date_night", "date"),
    ("first date", "date"),
    ("anniversary", "date"),
    ("valentine", "date"),
    ("romantic dinner", "date"),
    ("romantic", "date"),

    # ── Work & Professional ────────────────────────────────────────────
    ("interview", "work"),
    ("business meeting", "work"),
    ("client meeting", "work"),
    ("work event", "work"),
    ("conference", "work"),
    ("presentation", "work"),
    ("daily office", "work"),
    ("office", "work"),
    ("business", "work"),
    ("corporate", "work"),
    ("workplace", "work"),

    # ── Travel & Vacation ──────────────────────────────────────────────
    ("vacation", "travel"),
    ("holiday", "travel"),
    ("beach", "travel"),
    ("airport", "travel"),
    ("road trip", "travel"),
    ("weekend trip", "travel"),
    ("travel", "travel"),
    ("trip", "travel"),
    ("resort", "travel"),

    # ── Evening & Party (after wedding/date so cross-overs go correctly)
    ("cocktail", "evening"),
    ("dinner party", "evening"),
    ("night out", "evening"),
    ("nightclub", "evening"),
    ("club night", "evening"),
    ("pub", "evening"),
    ("party", "evening"),
    ("evening", "evening"),

    # ── Casual & Everyday (last specific, before fallthrough) ──────────
    ("brunch", "casual"),
    ("coffee", "casual"),
    ("lunch", "casual"),
    ("weekend outing", "casual"),
    ("weekend", "casual"),
    ("errands", "casual"),
    ("everyday", "casual"),
    ("daily wear", "casual"),
    ("daily", "casual"),
    ("casual outing", "casual"),
    ("casual", "casual"),
    ("smart casual", "casual"),
    ("smart_casual", "casual"),
]


# Intent fallbacks — when occasion_signal is empty, certain intents
# imply a theme. Keeps "what should I wear today?" out of the
# undifferentiated bucket when the planner couldn't extract an
# occasion.
INTENT_FALLBACK: Dict[str, str] = {
    # No reliable mapping — pairing requests without occasion really
    # are style-advice sessions, not themed events.
    "pairing_request": "style_sessions",
    "occasion_recommendation": "style_sessions",
    "outfit_check": "style_sessions",
    "garment_evaluation": "style_sessions",
    "style_discovery": "style_sessions",
    "explanation_request": "style_sessions",
}


def _normalize(text: str) -> str:
    """Trim, lowercase, collapse internal whitespace, replace underscores with spaces.

    Underscore handling matters because the planner sometimes emits
    enum-shaped values (`date_night`, `daily_office`) that should match
    the same keywords as their spoken form.
    """
    text = (text or "").lower().replace("_", " ")
    return " ".join(text.split())


# Compile each keyword to a word-boundary regex. Word-boundary
# matching prevents short keywords (`holi` for Holi festival, `eid`
# for Eid) from accidentally matching unrelated longer strings (`holiday`,
# `weight_id`). The first pattern that matches wins, preserving the
# explicit precedence ordering in ``KEYWORDS``.
_COMPILED: List[Tuple[Pattern[str], str]] = []


def _compile_patterns() -> List[Tuple[Pattern[str], str]]:
    if not _COMPILED:
        for kw, theme_key in KEYWORDS:
            # `re.escape` so multi-word keywords like "date night" stay
            # literal; \b at both ends so "holi" doesn't match "holiday".
            pattern = re.compile(r"\b" + re.escape(kw) + r"\b", re.IGNORECASE)
            _COMPILED.append((pattern, theme_key))
    return _COMPILED


def map_to_theme(occasion_signal: str, intent: str = "") -> str:
    """Map a raw occasion signal + intent to a canonical theme key.

    Returns one of the keys in ``THEMES``. Falls through to
    ``style_sessions`` when nothing matches — that's the safe default
    for "no occasion provided" (pairing requests, generic style asks).

    Args:
        occasion_signal: the planner-extracted occasion string. May be
            free-form ("traditional engagement"), an enum value
            ("date_night"), or empty.
        intent: the primary_intent for the turn. Used as a secondary
            signal when occasion_signal is empty — a `pairing_request`
            with no occasion is a style session, not an event.
    """
    sig = _normalize(occasion_signal)
    if sig:
        for pattern, theme_key in _compile_patterns():
            if pattern.search(sig):
                return theme_key
        # Non-empty signal that didn't match — caller should log this
        # so the keyword list can grow.
        return "style_sessions"
    # Empty signal — use intent as the secondary cue.
    intent_key = (intent or "").strip().lower()
    return INTENT_FALLBACK.get(intent_key, "style_sessions")


def is_unmapped(occasion_signal: str) -> bool:
    """True when a non-empty occasion_signal failed to match any keyword.

    Used by the read endpoint to drive an ops-dashboard counter via a
    ``tool_traces`` row — operators query the trailing 7d for the most
    common unmapped signals and add them to ``KEYWORDS`` above. Empty
    signals are NOT unmapped (they're expected, e.g. for pairing
    requests with no occasion).
    """
    sig = _normalize(occasion_signal)
    if not sig:
        return False
    return all(not pattern.search(sig) for pattern, _ in _compile_patterns())


def theme_label(theme_key: str) -> str:
    """Return the display label for a theme key, with a safe fallback."""
    return str(THEMES.get(theme_key, THEMES["style_sessions"])["label"])


def theme_description(theme_key: str) -> str:
    return str(THEMES.get(theme_key, THEMES["style_sessions"])["description"])


def theme_order(theme_key: str) -> int:
    return int(THEMES.get(theme_key, THEMES["style_sessions"])["order"])


def all_theme_keys() -> List[str]:
    """Return all theme keys in canonical sort order. Useful for tests + UI placeholders."""
    return sorted(THEMES.keys(), key=theme_order)
