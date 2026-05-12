"""Theme taxonomy for the Outfits tab.

The Outfits tab groups historical recommendation turns by
``occasion_signal``. That signal is whatever the planner extracted from
the user message and is uncontrolled vocabulary, which means
semantically-equivalent occasions split into many small buckets:
``beach`` / ``pool party`` / ``vacation`` are one beach outing;
``engagement`` / ``traditional engagement`` / ``wedding engagement``
are one wedding cycle. This module collapses synonyms into a
fine-grained set of occasion buckets the user actually thinks in
(Beach & Vacation, Date Night, Office & Professional, ...).

For sessions where the planner could not extract any occasion (e.g.
pure pairing requests), ``map_formality_to_bucket`` falls back to
labeling the group by the *style* of the outfits themselves (Smart
Looks / Easy Everyday Looks / Off-Duty Pieces), driven by the
rater's ``formality_pct`` averaged across the session's outfits.

Properties:

- **Pure function.** ``map_to_theme`` and ``map_formality_to_bucket``
  are deterministic lookups — no LLM call per turn, fully inspectable.
- **Read-time.** The endpoint applies the mapper when it builds the
  intent-history response. No migration, no backfill, no planner
  change; rerunning the mapper after editing this file re-themes the
  full history.
- **Precedence-ordered.** Keywords are matched in declared order:
  wedding > festive > date > office > beach > travel > party >
  casual. So "engagement evening" lands in *Wedding & Engagement*
  (correct); "office cocktail" lands in *Office & Professional*.
- **Telemetry-friendly.** Signals that don't match any keyword fall
  through to ``style_sessions`` and the caller is expected to log them
  to ``tool_traces`` so the keyword list can evolve with usage.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Pattern, Tuple


# Canonical occasion buckets. ``order`` is the fallback sort key used
# when no theme has any active turns; live themes are sorted by
# most-recent-turn timestamp so the user's currently-active intents
# float to the top.
THEMES: Dict[str, Dict[str, object]] = {
    # ── Occasion buckets (driven by planner-extracted occasion) ──
    "wedding": {
        "key": "wedding",
        "label": "Wedding & Engagement",
        "description": "Sangeet, mehendi, engagement, ceremony, reception",
        "order": 1,
    },
    "festive": {
        "key": "festive",
        "label": "Festival & Celebration",
        "description": "Diwali, Eid, festivals, family functions, birthdays",
        "order": 2,
    },
    "date": {
        "key": "date",
        "label": "Date Night",
        "description": "Date nights, anniversaries, romantic dinners",
        "order": 3,
    },
    "office": {
        "key": "office",
        "label": "Office & Professional",
        "description": "Office, business meetings, interviews, work events",
        "order": 4,
    },
    "beach": {
        "key": "beach",
        "label": "Beach & Vacation",
        "description": "Beach trips, pool days, resorts, holidays",
        "order": 5,
    },
    "travel": {
        "key": "travel",
        "label": "Travel & Trips",
        "description": "Airports, road trips, weekend getaways",
        "order": 6,
    },
    "party": {
        "key": "party",
        "label": "Party & Night Out",
        "description": "Cocktails, dinner parties, nights out, clubs",
        "order": 7,
    },
    "casual": {
        "key": "casual",
        "label": "Weekend & Everyday",
        "description": "Brunches, weekends, errands, daily wear",
        "order": 8,
    },
    # ── Formality fallback buckets (used when occasion is empty) ──
    "smart_looks": {
        "key": "smart_looks",
        "label": "Smart Looks",
        "description": "Polished, elevated outfits without a specific occasion",
        "order": 20,
    },
    "easy_everyday": {
        "key": "easy_everyday",
        "label": "Easy Everyday Looks",
        "description": "Balanced, wearable outfits without a specific occasion",
        "order": 21,
    },
    "off_duty": {
        "key": "off_duty",
        "label": "Off-Duty Pieces",
        "description": "Relaxed, low-formality outfits without a specific occasion",
        "order": 22,
    },
    # ── Ultimate fallback (rarely surfaced; api.py overrides via formality) ──
    "style_sessions": {
        "key": "style_sessions",
        "label": "Style Sessions",
        "description": "Pairing requests and looks without a specific occasion",
        "order": 99,
    },
}


# Keyword → theme mapping. Order matters — the FIRST keyword whose
# substring is found in the lowercased signal wins. Specific event
# types (sangeet, baraat) outrank generic energy (evening); work
# codes (interview, business) outrank ambient ones; pool/beach beat
# generic "vacation".
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

    # ── Festival & Celebration ─────────────────────────────────────────
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

    # ── Date Night ─────────────────────────────────────────────────────
    ("date night", "date"),
    ("date_night", "date"),
    ("first date", "date"),
    ("anniversary", "date"),
    ("valentine", "date"),
    ("romantic dinner", "date"),
    ("romantic", "date"),

    # ── Office & Professional ──────────────────────────────────────────
    ("interview", "office"),
    ("business meeting", "office"),
    ("client meeting", "office"),
    ("work event", "office"),
    ("conference", "office"),
    ("presentation", "office"),
    ("daily office", "office"),
    ("office", "office"),
    ("business", "office"),
    ("corporate", "office"),
    ("workplace", "office"),

    # ── Beach & Vacation (before travel so "beach holiday" → beach) ────
    ("beach", "beach"),
    ("pool party", "beach"),
    ("pool", "beach"),
    ("resort", "beach"),

    # ── Travel & Trips ─────────────────────────────────────────────────
    ("vacation", "travel"),
    ("holiday", "travel"),
    ("airport", "travel"),
    ("road trip", "travel"),
    ("weekend trip", "travel"),
    ("getaway", "travel"),
    ("travel", "travel"),
    ("trip", "travel"),

    # ── Party & Night Out (after wedding/date so cross-overs go right) ─
    ("cocktail", "party"),
    ("dinner party", "party"),
    ("night out", "party"),
    ("nightclub", "party"),
    ("club night", "party"),
    ("pub", "party"),
    ("party", "party"),
    ("evening", "party"),

    # ── Weekend & Everyday (last specific, before fallthrough) ─────────
    ("brunch", "casual"),
    ("coffee", "casual"),
    ("lunch", "casual"),
    ("breakfast", "casual"),
    ("weekend outing", "casual"),
    ("weekend", "casual"),
    ("errands", "casual"),
    ("everyday", "casual"),
    ("daily wear", "casual"),
    ("daily", "casual"),
    ("casual outing", "casual"),
    ("smart casual", "casual"),
    ("smart_casual", "casual"),
    ("casual", "casual"),
]


# Intent fallbacks — when occasion_signal is empty, certain intents
# still have no occasion meaning of their own; map them to the sentinel
# ``style_sessions`` so the api layer can swap in a formality bucket.
INTENT_FALLBACK: Dict[str, str] = {
    "pairing_request": "style_sessions",
    "occasion_recommendation": "style_sessions",
    "outfit_check": "style_sessions",
    "garment_evaluation": "style_sessions",
    "style_discovery": "style_sessions",
    "explanation_request": "style_sessions",
}


def _normalize(text: str) -> str:
    text = (text or "").lower().replace("_", " ")
    return " ".join(text.split())


_COMPILED: List[Tuple[Pattern[str], str]] = []


def _compile_patterns() -> List[Tuple[Pattern[str], str]]:
    if not _COMPILED:
        for kw, theme_key in KEYWORDS:
            pattern = re.compile(r"\b" + re.escape(kw) + r"\b", re.IGNORECASE)
            _COMPILED.append((pattern, theme_key))
    return _COMPILED


def map_to_theme(occasion_signal: str, intent: str = "") -> str:
    """Map a raw occasion signal + intent to an occasion bucket key.

    Returns one of the occasion keys in ``THEMES`` when the signal
    matches a keyword. Returns the sentinel ``style_sessions`` when
    nothing matches — callers with access to outfit-level formality
    data should swap that for a formality bucket via
    ``map_formality_to_bucket``.
    """
    sig = _normalize(occasion_signal)
    if sig:
        for pattern, theme_key in _compile_patterns():
            if pattern.search(sig):
                return theme_key
        return "style_sessions"
    intent_key = (intent or "").strip().lower()
    return INTENT_FALLBACK.get(intent_key, "style_sessions")


def map_formality_to_bucket(avg_formality_pct: Optional[float]) -> str:
    """Map an average ``formality_pct`` (0..100) to a formality bucket.

    Used as the fallback grouping when a session has no occasion
    signal — the outfits' own formality determines whether the user
    sees them under "Smart Looks", "Easy Everyday Looks", or
    "Off-Duty Pieces". Returns ``easy_everyday`` when input is None so
    sessions without rater data still have a sensible bucket.
    """
    if avg_formality_pct is None:
        return "easy_everyday"
    if avg_formality_pct >= 65:
        return "smart_looks"
    if avg_formality_pct >= 35:
        return "easy_everyday"
    return "off_duty"


def is_unmapped(occasion_signal: str) -> bool:
    """True when a non-empty occasion_signal failed to match any keyword."""
    sig = _normalize(occasion_signal)
    if not sig:
        return False
    return all(not pattern.search(sig) for pattern, _ in _compile_patterns())


def theme_label(theme_key: str) -> str:
    return str(THEMES.get(theme_key, THEMES["style_sessions"])["label"])


def theme_description(theme_key: str) -> str:
    return str(THEMES.get(theme_key, THEMES["style_sessions"])["description"])


def theme_order(theme_key: str) -> int:
    return int(THEMES.get(theme_key, THEMES["style_sessions"])["order"])


def all_theme_keys() -> List[str]:
    """Return all theme keys in canonical sort order."""
    return sorted(THEMES.keys(), key=theme_order)
