"""Composition-time styling decisions.

These functions emit *styling recommendations* (dupatta drape, layering
structure) derived from body shape + gender. They are NOT garment
attributes — the catalog never carries a ``DupattaDrape`` column.
Rather, the engine emits these as part of its outfit metadata so the
front-end can surface "drape this dupatta with a single-shoulder fall"
or "wear this with an open-front longline jacket" alongside the
selected garments.

Source: ``knowledge/knowledge_v2/bodyframe_stylist_revision_patchset_v_1.md``
(stylist's body_frame review — Phase 4.2 deliverable, May 2026).

Cross-references in ``knowledge/STYLIST_NOTES.md``:
- Cross-cutting decision #2 (Dupatta drape as silhouette engineering).
- Cross-cutting decision #25 (Modern styling layers over complete anchors).

Today these functions return recommendations as ordered tuples (first
entry = strongest match). Wiring into the composer's per-outfit
metadata is a separate change — keeping the derivation library
focused makes the unit tests trivial and the engine-integration
review small.
"""
from __future__ import annotations

from typing import Mapping


# ─────────────────────────────────────────────────────────────────────────
# Dupatta drape
# ─────────────────────────────────────────────────────────────────────────


# Canonical dupatta drape values. Documented stylist intent per value:
# - vertical_fall:    lengthens frame and skims midsection
# - single_shoulder:  draws attention upward; signature Pear / Triangle
# - open_u_drape:     softer and more romantic silhouette
# - side_fall:        excellent for Diamond and Apple (softens midsection)
DUPATTA_DRAPE_VALUES: tuple[str, ...] = (
    "vertical_fall",
    "single_shoulder",
    "open_u_drape",
    "side_fall",
)


# Per-body-shape preferred drape styles. Order matters — first entry is
# the strongest recommendation; later entries are acceptable alternatives.
# Body-shape vocabulary aligns with the canonical body-shape values in
# ``knowledge/style_graph/body_frame/female.yaml`` BodyShape block.
_DRAPE_BY_SHAPE: Mapping[str, tuple[str, ...]] = {
    "Pear":              ("single_shoulder", "vertical_fall"),
    "Apple":             ("side_fall", "open_u_drape"),
    "Diamond":           ("side_fall", "vertical_fall"),
    "Hourglass":         ("open_u_drape", "vertical_fall"),
    "Rectangle":         ("single_shoulder", "open_u_drape"),
    "Inverted Triangle": ("vertical_fall", "open_u_drape"),
    "Trapezoid":         ("vertical_fall", "single_shoulder"),
}


def derive_dupatta_drape(body_shape: str | None) -> tuple[str, ...]:
    """Recommended dupatta drape styles for a given body shape.

    Returns an empty tuple when ``body_shape`` is unknown or empty —
    the caller falls back to the generic dupatta presentation (no
    specific drape recommendation surfaced).

    Order in the returned tuple is meaningful: the first entry is the
    strongest match for the body shape; subsequent entries are
    acceptable alternatives the front-end may surface as variants.
    """
    if not body_shape:
        return ()
    return _DRAPE_BY_SHAPE.get(body_shape, ())


# ─────────────────────────────────────────────────────────────────────────
# Layering structure
# ─────────────────────────────────────────────────────────────────────────


# Canonical layering structure values. Documented stylist intent per value:
# - open_front:     open-front layer creating vertical break + elongation
# - cape_overlay:   softens upper body, adds occasion drama
# - longline_jacket: vertical line + center_front focus; balances midsection
# - soft_overshirt: Gen Z / urban smart-casual layering (male.yaml addition)
LAYERING_STRUCTURE_VALUES: tuple[str, ...] = (
    "open_front",
    "cape_overlay",
    "longline_jacket",
    "soft_overshirt",
)


# Per-body-shape preferred layering. Most shapes get 1-2 structures;
# ``soft_overshirt`` is appended for masculine users (see below) since
# it's a male.yaml-specific addition in the stylist patch.
_LAYERING_BY_SHAPE: Mapping[str, tuple[str, ...]] = {
    "Pear":              ("cape_overlay",),                    # broaden upper-body
    "Apple":             ("open_front", "longline_jacket"),
    "Diamond":           ("open_front", "longline_jacket"),
    "Hourglass":         ("open_front", "cape_overlay"),       # waist still visible
    "Rectangle":         ("cape_overlay", "longline_jacket"),
    "Inverted Triangle": ("longline_jacket",),                 # vertical line away from shoulder
    "Trapezoid":         ("open_front", "longline_jacket"),
}


# ``soft_overshirt`` was introduced in the male.yaml LayeringStructure
# block as an urban Gen Z / millennial styling option. It pairs across
# body shapes when intentionally styled, so we append it for masculine
# users on top of the body-shape defaults rather than replacing them.
_SOFT_OVERSHIRT_GENDERS: frozenset[str] = frozenset({"masculine", "male"})


def recommend_layering_structures(
    body_shape: str | None,
    *,
    gender: str | None = None,
) -> tuple[str, ...]:
    """Recommended layering structures for a given body shape.

    For masculine / male users, ``soft_overshirt`` is appended to the
    body-shape defaults — the stylist's male.yaml block adds it as a
    Gen Z / urban casual layering option that works across body
    shapes when intentionally styled.

    Returns an empty tuple when ``body_shape`` is unknown or empty.
    """
    if not body_shape:
        return ()
    base = _LAYERING_BY_SHAPE.get(body_shape, ())
    if not base:
        # Unknown body shape (truthy but not in the table) — don't
        # surface ``soft_overshirt`` without a body-shape anchor; the
        # caller has no styling signal to anchor against.
        return ()
    gender_norm = (gender or "").strip().lower()
    if gender_norm in _SOFT_OVERSHIRT_GENDERS:
        return base + ("soft_overshirt",)
    return base


# ─────────────────────────────────────────────────────────────────────────
# Movement security
# ─────────────────────────────────────────────────────────────────────────


# Canonical movement-security values from the bodyframe stylist patch.
# - secure:    suitable for dancing and long-duration events
# - moderate:  some adjustment may be needed during movement
# - delicate:  editorial / low-movement styling only
MOVEMENT_SECURITY_VALUES: tuple[str, ...] = ("secure", "moderate", "delicate")


# Occasions where a dance-heavy / movement-heavy outfit is the user
# need. Stylist's occasion review explicitly flagged sangeet + navratri
# as movement-centric ("rotational movement, heat tolerance, comfort —
# not just visual glamour").
_DANCE_HEAVY_OCCASIONS: frozenset[str] = frozenset({
    "sangeet",
    "navratri",
    "mehndi",          # mehndi often runs into impromptu dancing
    "garba",
    "dance_event",
})


# Occasions where low-movement / editorial styling is acceptable —
# the outfit doesn't need to support sustained physical activity.
_LOW_MOVEMENT_OCCASIONS: frozenset[str] = frozenset({
    "gala_dinner",
    "fine_dining",
    "business_dinner",
    "anniversary_dinner",
    "in_laws_first_meeting",
    "interview",
    "business_meeting",
    "kitty_party",
})


def derive_movement_security(occasion_signal: str | None) -> str:
    """Return the movement-security level the outfit needs to support.

    - ``secure`` for dance-heavy occasions (sangeet, navratri, mehndi).
    - ``delicate`` for editorial / sit-down formal contexts.
    - ``moderate`` everywhere else (the safe default).

    The engine should drop / penalise candidates whose construction
    can't deliver the required level (e.g., strapless cocktail gown
    for sangeet → support + movement risk).
    """
    if not occasion_signal:
        return "moderate"
    occ = occasion_signal.strip().lower()
    if occ in _DANCE_HEAVY_OCCASIONS:
        return "secure"
    if occ in _LOW_MOVEMENT_OCCASIONS:
        return "delicate"
    return "moderate"


# ─────────────────────────────────────────────────────────────────────────
# Support requirement
# ─────────────────────────────────────────────────────────────────────────


# Canonical support-requirement values from the bodyframe stylist patch.
# - low:    minimal internal support needed
# - medium: requires stable tailoring or blouse engineering
# - high:   requires corsetry, boning, secure blouse structure
SUPPORT_REQUIREMENT_VALUES: tuple[str, ...] = ("low", "medium", "high")


# Garment subtypes that inherently need high internal support to be
# wearable. Stylist's bodyframe patch was explicit that strapless +
# similar exposure-heavy cuts have a non-negotiable support floor.
_HIGH_SUPPORT_GARMENTS: frozenset[str] = frozenset({
    "strapless_dress",
    "strapless_blouse",
    "off_shoulder_blouse",
    "off_shoulder_dress",
    "tube_top",
    "bustier",
    "halter_top",
    "halter_dress",
    "corset",
    "corset_blouse",
})


# Occasions where medium support is expected (long ceremonies, dancing,
# or otherwise extended-wear contexts).
_MEDIUM_SUPPORT_OCCASIONS: frozenset[str] = frozenset({
    "sangeet",
    "navratri",
    "mehndi",
    "wedding_ceremony",
    "reception",
    "wedding_reception",
    "gala_dinner",
    "engagement",
})


def derive_support_requirement(
    *,
    occasion_signal: str | None = None,
    garment_subtype: str | None = None,
) -> str:
    """Return the support-engineering level the outfit requires.

    Garment subtype dominates: a strapless dress is ``high`` regardless
    of occasion. Below that, occasion drives — extended-wear ceremonial
    contexts default to ``medium``; everything else is ``low``.
    """
    sub = (garment_subtype or "").strip().lower()
    if sub in _HIGH_SUPPORT_GARMENTS:
        return "high"
    occ = (occasion_signal or "").strip().lower()
    if occ in _MEDIUM_SUPPORT_OCCASIONS:
        return "medium"
    return "low"


# ─────────────────────────────────────────────────────────────────────────
# Bridal priority — role-aware dressing schema
# ─────────────────────────────────────────────────────────────────────────


# Canonical bridal-role values. ``attendee`` is the default for
# unspecified non-special attendees; it falls through to ``guest``
# rules in any occasion's ``bridal_priority`` block.
BRIDAL_ROLE_VALUES: tuple[str, ...] = ("bride", "groom", "guest", "attendee")


# Occasions where bride / groom / guest distinction matters
# (per stylist's occasion review — guests should never visually compete
# with bridal participants, even attending the same wedding).
_BRIDAL_ROLE_OCCASIONS: frozenset[str] = frozenset({
    "wedding_ceremony",
    "wedding_reception",
    "reception",
    "sangeet",
    "mehndi",
    "haldi",
    "engagement",
    "sagai_engagement",
})


def is_bridal_role_occasion(occasion_signal: str | None) -> bool:
    """Whether the occasion has a bride / groom / guest hierarchy.

    The engine should look up the user's role-in-occasion ONLY for
    occasions where the distinction is meaningful — for everything
    else the role is irrelevant and should be ignored.
    """
    if not occasion_signal:
        return False
    return occasion_signal.strip().lower() in _BRIDAL_ROLE_OCCASIONS


def lookup_bridal_priority_rules(
    role: str | None,
    occasion_priority_block: dict | None,
) -> dict | None:
    """Return role-specific rules from an occasion's ``bridal_priority``
    block, if present and applicable.

    The occasion.yaml ``bridal_priority`` shape proposed by the
    stylist (filed in OPEN_TASKS as engine extension):

        bridal_priority:
          bride:
            hard_flatters: { ... }
          groom:
            hard_flatters: { ... }
          guest:
            hard_avoid: { ... }

    ``attendee`` is treated as a synonym for ``guest`` — the role
    every non-bridal-party attendee falls into by default.

    Returns ``None`` when the role is unknown / unmapped or the
    occasion has no ``bridal_priority`` block. The caller should
    interpret that as "no role-specific override; apply the standard
    occasion rules".
    """
    if not role or not occasion_priority_block:
        return None
    role_norm = role.strip().lower()
    if role_norm in occasion_priority_block:
        return dict(occasion_priority_block[role_norm])
    # ``attendee`` → ``guest`` fallback. The stylist's schema only
    # defines bride / groom / guest; attendee is the human-friendly
    # default we expose to users.
    if role_norm == "attendee" and "guest" in occasion_priority_block:
        return dict(occasion_priority_block["guest"])
    return None


__all__ = [
    "DUPATTA_DRAPE_VALUES",
    "LAYERING_STRUCTURE_VALUES",
    "MOVEMENT_SECURITY_VALUES",
    "SUPPORT_REQUIREMENT_VALUES",
    "BRIDAL_ROLE_VALUES",
    "derive_dupatta_drape",
    "recommend_layering_structures",
    "derive_movement_security",
    "derive_support_requirement",
    "is_bridal_role_occasion",
    "lookup_bridal_priority_rules",
]
