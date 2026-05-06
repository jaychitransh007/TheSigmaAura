"""Query-document rendering for the composition engine (Phase 4.7e).

Translates per-attribute compositions into the structured query_document
text the catalog embedding model consumes — same format the LLM
architect emits today (``prompt/outfit_architect.md`` lines 207–248):

    PRIMARY_BRIEF:
    - GarmentCategory: ...
    - GarmentSubtype: ...
    - StylingCompleteness: ...
    - SilhouetteContour: ...
    - ...

    GARMENT_REQUIREMENTS:
    - SilhouetteType: ...
    ...

The renderer is intentionally narrow: it takes a per-attribute mapping
(``{attribute: tuple[values]}``) plus role + direction_type and emits the
section blocks. It does NOT pull from the StyleGraph or the
``CompositionResult`` directly — that decoupling lets 4.7d call it once
per query slot without duplicating provenance, and lets tests render
against minimal hand-built fixtures.

Empty values for an attribute → the line is omitted (the architect prompt
warns against emitting empty values; they only add embedding noise).
"""
from __future__ import annotations

from typing import Iterable, Mapping, Sequence


# ─────────────────────────────────────────────────────────────────────────
# Section layout (mirrors prompt/outfit_architect.md lines 211–248)
# ─────────────────────────────────────────────────────────────────────────


# Attribute order within PRIMARY_BRIEF. Order matters: it's documented
# in the prompt and downstream consumers (the embedding model) anchor
# on token position.
_PRIMARY_BRIEF: tuple[str, ...] = (
    "GarmentCategory",
    "GarmentSubtype",
    "StylingCompleteness",
    "SilhouetteContour",
    "FitType",
    "GarmentLength",
    "SleeveLength",
    "EmbellishmentLevel",
    "FabricDrape",
    "FabricWeight",
    "PatternType",
    "ColorTemperature",
    "PrimaryColor",
    "FormalityLevel",
    "TimeOfDay",
)

_GARMENT_REQUIREMENTS: tuple[str, ...] = (
    "SilhouetteType",
    "VolumeProfile",
    "FitEase",
    "ShoulderStructure",
    "WaistDefinition",
    "HipDefinition",
    "NecklineType",
    "NecklineDepth",
    "SkinExposureLevel",
)

_EMBELLISHMENT: tuple[str, ...] = (
    "EmbellishmentType",
    "EmbellishmentZone",
)

_VISUAL_DIRECTION: tuple[str, ...] = (
    "VerticalWeightBias",
    "VisualWeightPlacement",
    "StructuralFocus",
    "BodyFocusZone",
    "LineDirection",
)

_FABRIC_AND_BUILD: tuple[str, ...] = (
    "FabricTexture",
    "StretchLevel",
    "EdgeSharpness",
    "ConstructionDetail",
)

_PATTERN_AND_COLOR: tuple[str, ...] = (
    "PatternScale",
    "PatternOrientation",
    "ContrastLevel",
    "ColorSaturation",
    "ColorValue",
    "ColorCount",
    "SecondaryColor",
)


# Role-specific suppressions: SleeveLength is meaningless on a bottom
# query (per prompt line 218). The same axis isn't suppressed on
# outerwear because outerwear sleeves are a real signal.
_SUPPRESSED_BY_ROLE: dict[str, frozenset[str]] = {
    "bottom": frozenset({"SleeveLength"}),
}


# ─────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────


def _format_value(values: Sequence[str]) -> str:
    """Comma-join the value tuple into the line's right-hand side.
    Position-0-is-strongest: the order from the reduction is preserved."""
    return ", ".join(v for v in values if v)


def _emit_section(
    title: str,
    attrs: Iterable[str],
    composed: Mapping[str, Sequence[str]],
    suppressed: frozenset[str],
) -> list[str]:
    """Build the line list for one section. Returns the title line plus
    one ``- Attribute: values`` line per non-empty attribute that isn't
    suppressed for this role. Returns an empty list when no lines would
    be emitted (the section header is only included if at least one
    line follows)."""
    lines: list[str] = []
    for attr in attrs:
        if attr in suppressed:
            continue
        values = composed.get(attr) or ()
        rendered = _format_value(values)
        if not rendered:
            continue
        lines.append(f"- {attr}: {rendered}")
    if not lines:
        return []
    return [f"{title}:", *lines]


def _resolve_garment_category(role: str, direction_type: str) -> str:
    """Map (role, direction_type) → catalog GarmentCategory value.

    The catalog uses 6 categories (garment_attributes.json):
    top | bottom | outerwear | one_piece | set | accessory. The engine
    emits one_piece for ``role=complete``; the LLM ranker can refine
    to ``set`` (sherwani-as-set, lehenga_set) at composer stage."""
    if role in ("top", "bottom", "outerwear"):
        return role
    if role == "complete":
        # set vs one_piece is a per-occasion stylist call. one_piece is
        # the safer default — most "complete" garments in the catalog
        # are dresses / gowns / jumpsuits / sarees, all flagged
        # one_piece. The Indian-traditional sets (lehenga_set, kurta_set,
        # sherwani-as-set) are tagged "set" and will surface via
        # GarmentSubtype rather than GarmentCategory.
        return "one_piece"
    return ""


def _resolve_styling_completeness(role: str, direction_type: str) -> str:
    """Map (role, direction_type) → StylingCompleteness value, mirroring
    ``build_directional_filters`` in agentic_application.filters."""
    if direction_type == "complete" or role == "complete":
        return "complete"
    if role == "outerwear":
        return "needs_innerwear"
    if role == "top":
        return "needs_bottomwear"
    if role == "bottom":
        return "needs_topwear"
    return ""


# ─────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────


def render_query_document(
    *,
    composed_attributes: Mapping[str, Sequence[str]],
    role: str,
    direction_type: str,
) -> str:
    """Render the structured query_document for one query slot.

    Inputs:

    - ``composed_attributes``: the engine's per-attribute final values.
      Empty / missing attributes produce no line. Tuple ordering is
      preserved (position-0-is-strongest from the reduction).
    - ``role``: top | bottom | outerwear | complete. Drives
      GarmentCategory + StylingCompleteness derivation; suppresses
      SleeveLength on ``bottom``.
    - ``direction_type``: complete | paired | three_piece. Combined
      with role to derive StylingCompleteness.

    Output: a multi-section string ready to be assigned to
    ``QuerySpec.query_document``. Sections with no surviving attributes
    are omitted entirely (no empty headers).
    """
    composed: dict[str, tuple[str, ...]] = {
        k: tuple(v) for k, v in composed_attributes.items()
    }

    # Inject derived attributes that the engine doesn't carry in the
    # contributions map (they're not in YAML flatters/avoid blocks).
    derived_category = _resolve_garment_category(role, direction_type)
    if derived_category and "GarmentCategory" not in composed:
        composed["GarmentCategory"] = (derived_category,)

    derived_completeness = _resolve_styling_completeness(role, direction_type)
    if derived_completeness and "StylingCompleteness" not in composed:
        composed["StylingCompleteness"] = (derived_completeness,)

    suppressed = _SUPPRESSED_BY_ROLE.get(role, frozenset())

    blocks: list[list[str]] = [
        _emit_section("PRIMARY_BRIEF", _PRIMARY_BRIEF, composed, suppressed),
        _emit_section(
            "GARMENT_REQUIREMENTS", _GARMENT_REQUIREMENTS, composed, suppressed
        ),
        _emit_section("EMBELLISHMENT", _EMBELLISHMENT, composed, suppressed),
        _emit_section(
            "VISUAL_DIRECTION", _VISUAL_DIRECTION, composed, suppressed
        ),
        _emit_section(
            "FABRIC_AND_BUILD", _FABRIC_AND_BUILD, composed, suppressed
        ),
        _emit_section(
            "PATTERN_AND_COLOR", _PATTERN_AND_COLOR, composed, suppressed
        ),
    ]
    rendered_blocks = [block for block in blocks if block]
    return "\n\n".join("\n".join(block) for block in rendered_blocks)
