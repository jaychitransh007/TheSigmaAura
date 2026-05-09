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


__all__ = [
    "DUPATTA_DRAPE_VALUES",
    "LAYERING_STRUCTURE_VALUES",
    "derive_dupatta_drape",
    "recommend_layering_structures",
]
