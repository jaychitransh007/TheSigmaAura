"""Top-level composition engine (Phase 4.7d).

``compose_direction(...)`` reduces the StyleGraph + planner inputs into a
single ``DirectionSpec`` plus a ``CompositionResult`` envelope carrying
confidence, peer-conflict signal, and per-attribute provenance. It is
the entry point the hot-path router (4.9) will call before falling
through to the LLM architect.

This file ties 4.7a (``yaml_loader``) and the per-attribute layers (4.7b
``reduction``, 4.7c ``relaxation``) into one orchestrated pass:

1. Look up each input against the StyleGraph and emit
   ``ClassifiedContribution``s. YAML gaps (input value not present in
   the relevant dimension) are recorded for the confidence penalty.
2. Reduce each attribute via ``reduce_with_relaxation``.
3. Pack the surviving flatters into ``DirectionSpec`` + ``QuerySpec``
   stubs. The ``query_document`` rendering layer (4.7e) fills in text.
4. Score confidence per spec §8 and detect peer conflicts per §4.2.

Pure function — no I/O, no clock, no randomness. Determinism is the
entire value proposition (it makes Phase 2's cache hit rate jump from
~0% to 50–70%+).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Sequence

from ..filters import build_global_hard_filters
from ..schemas import DirectionSpec, QuerySpec, UserContext
from .reduction import AttributeContribution
from .relaxation import (
    ClassifiedContribution,
    RelaxedReduction,
    reduce_with_relaxation,
)
from .yaml_loader import (
    AttributeMapping,
    OccasionEntry,
    QueryStructureEntry,
    StyleGraph,
)


# ─────────────────────────────────────────────────────────────────────────
# Spec-derived constants
# ─────────────────────────────────────────────────────────────────────────


# §8 confidence formula coefficients.
SOFT_DROP_PENALTY = 0.10
HARD_WIDEN_PENALTY = 0.20
ATTR_OMIT_PENALTY = 0.30
YAML_GAP_PENALTY = 0.45

# §8 acceptance threshold — strict, the asymmetric YAML-gap penalty
# (0.45 > 1 - 0.60 = 0.40) intentionally tips any genuine gap below
# the floor so it always falls through.
CONFIDENCE_THRESHOLD = 0.60


# Color attributes from weather get the soft-tier treatment (§3.3
# weather split). Fabric / structure attributes from weather are hard.
_WEATHER_COLOR_ATTRS = frozenset(
    {"ColorValue", "ColorTemperature", "ColorSaturation", "ColorCount"}
)


# §4.2 peer-pair entries marked `=` in the precedence matrix. When two
# peer kinds both contribute opinionated flatters for the same attribute
# AND their flatters disagree, the engine emits ``needs_disambiguation``.
_PEER_PAIRS: tuple[tuple[str, str], ...] = (
    ("formality_hint", "occasion_signal"),
    ("archetype", "risk_tolerance"),
    ("risk_tolerance", "time_of_day"),
)


# Source kinds whose value should be looked up in body_frame YAMLs
# under the dimension of the same name.
_BODY_DIMS = ("BodyShape", "FrameStructure")


# ─────────────────────────────────────────────────────────────────────────
# Inputs / outputs
# ─────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class CompositionInputs:
    """Mirrors spec §1: all inputs the engine needs to compose one
    direction.

    Inputs come from two sources:
    - The user's profile (gender, body_shape, frame_structure,
      seasonal_color_group, risk_tolerance).
    - Per-turn signals (archetype, occasion_signal, formality_hint,
      weather_context, time_of_day, style_goal). The planner emits
      occasion_signal + formality_hint; the rest comes from
      live_context.

    ``archetype`` may be ``None`` when the planner's style_goal didn't
    map to one of the 9 canonical archetypes — in that case the
    archetype contribution is simply absent from the reduction.
    """

    gender: str
    body_shape: str
    frame_structure: str
    seasonal_color_group: str
    archetype: str | None
    risk_tolerance: str
    occasion_signal: str
    formality_hint: str
    weather_context: str
    time_of_day: str
    style_goal: str = ""
    direction_id: str = "A"
    direction_label: str = ""
    intent: str = "occasion_recommendation"


@dataclass(frozen=True)
class ProvenanceEntry:
    """Per-attribute provenance for ops audit.

    Captures: which sources contributed, what the relaxation walk had
    to do, and the surviving flatters tuple. Avoid set is omitted to
    keep the trail compact — it can be rederived from the same
    StyleGraph + inputs when needed."""

    attribute: str
    final_flatters: tuple[str, ...]
    contributing_sources: tuple[str, ...]
    status: str
    dropped_softs: tuple[str, ...]
    widened_hards: tuple[str, ...]


@dataclass(frozen=True)
class CompositionResult:
    """The engine's output envelope. Mirrors spec §7."""

    direction: DirectionSpec | None
    confidence: float
    needs_disambiguation: bool
    provenance: tuple[ProvenanceEntry, ...]
    fallback_reason: str | None
    yaml_gaps: tuple[str, ...] = field(default_factory=tuple)


# ─────────────────────────────────────────────────────────────────────────
# Contribution collection
# ─────────────────────────────────────────────────────────────────────────


def _add_mapping(
    by_attr: dict[str, list[ClassifiedContribution]],
    mapping: AttributeMapping,
    source: str,
    source_kind: str,
    tier: str,
    *,
    color_attrs_split: bool = False,
) -> None:
    """Append flatters/avoid contributions from ``mapping`` to ``by_attr``.

    When ``color_attrs_split`` is True, color attributes from this
    mapping are tagged with ``weather_color`` + soft tier; fabric /
    structure attributes keep ``weather_fabric`` + hard. Caller passes
    the already-resolved ``source_kind``+``tier`` as the fabric default."""
    seen_attrs: set[str] = set()
    for attr, vals in mapping.flatters.items():
        seen_attrs.add(attr)
        if color_attrs_split and attr in _WEATHER_COLOR_ATTRS:
            kind, t = "weather_color", "soft"
        else:
            kind, t = source_kind, tier
        by_attr.setdefault(attr, []).append(
            ClassifiedContribution(
                contribution=AttributeContribution(
                    source=source,
                    flatters=tuple(vals),
                    avoid=tuple(mapping.avoid.get(attr, ())),
                ),
                source_kind=kind,
                tier=t,
            )
        )
    # avoid-only: contributors that mention an attr in avoid but not
    # flatters still influence the union.
    for attr, vals in mapping.avoid.items():
        if attr in seen_attrs:
            continue
        if color_attrs_split and attr in _WEATHER_COLOR_ATTRS:
            kind, t = "weather_color", "soft"
        else:
            kind, t = source_kind, tier
        by_attr.setdefault(attr, []).append(
            ClassifiedContribution(
                contribution=AttributeContribution(
                    source=source, flatters=(), avoid=tuple(vals),
                ),
                source_kind=kind,
                tier=t,
            )
        )


def _resolve_body_frame_yaml(
    graph: StyleGraph, gender: str
) -> Mapping[str, Mapping[str, AttributeMapping]]:
    """Pick the female or male body_frame table by user gender.

    Spec §1: gender is feminine | masculine | unisex. The body_frame
    YAMLs only exist as female / male; unisex defaults to female (the
    larger and more conservative table)."""
    g = (gender or "").strip().lower()
    if g in ("male", "masculine", "m"):
        return graph.body_frame_male
    return graph.body_frame_female


def _time_of_day_to_garment_value(time_of_day: str) -> str | None:
    """Spec §1 lists 4 values; the catalog's TimeOfDay attribute has 3
    (day, evening, flexible). Map morning/daytime → day; evening/night
    → evening. Anything else → None (skipped, no contribution)."""
    t = (time_of_day or "").strip().lower()
    if t in ("morning", "daytime", "day"):
        return "day"
    if t in ("evening", "night"):
        return "evening"
    return None


def _collect_contributions(
    inputs: CompositionInputs,
    graph: StyleGraph,
) -> tuple[dict[str, list[ClassifiedContribution]], list[str]]:
    """Walk every input, look it up in the StyleGraph, and gather
    ClassifiedContributions per attribute. Return (contributions, gaps)
    where ``gaps`` is a list of source-kind labels whose value wasn't
    found in the relevant YAML."""
    by_attr: dict[str, list[ClassifiedContribution]] = {}
    gaps: list[str] = []

    body_yaml = _resolve_body_frame_yaml(graph, inputs.gender)

    # --- HARD sources -----------------------------------------------------
    bs = body_yaml.get("BodyShape", {}).get(inputs.body_shape)
    if bs is not None:
        _add_mapping(
            by_attr, bs, f"body_shape:{inputs.body_shape}", "body_shape", "hard"
        )
    elif inputs.body_shape:
        gaps.append(f"body_shape:{inputs.body_shape}")

    fs = body_yaml.get("FrameStructure", {}).get(inputs.frame_structure)
    if fs is not None:
        _add_mapping(
            by_attr,
            fs,
            f"frame_structure:{inputs.frame_structure}",
            "frame_structure",
            "hard",
        )
    elif inputs.frame_structure:
        gaps.append(f"frame_structure:{inputs.frame_structure}")

    sub = graph.palette.get("SubSeason", {}).get(inputs.seasonal_color_group)
    if sub is not None:
        _add_mapping(
            by_attr,
            sub,
            f"seasonal:{inputs.seasonal_color_group}",
            "seasonal_color_group",
            "hard",
        )
    elif inputs.seasonal_color_group:
        gaps.append(f"seasonal_color_group:{inputs.seasonal_color_group}")

    occ: OccasionEntry | None = graph.occasion.get(inputs.occasion_signal)
    if occ is not None:
        _add_mapping(
            by_attr,
            occ.mapping,
            f"occasion:{inputs.occasion_signal}",
            "occasion_signal",
            "hard",
        )
    elif inputs.occasion_signal:
        gaps.append(f"occasion_signal:{inputs.occasion_signal}")

    if inputs.formality_hint:
        # formality_hint is a single-value contribution to FormalityLevel.
        # It conflicts with occasion_signal as a peer (§4.2), so the
        # peer-detection pass sees both kinds when both are present.
        by_attr.setdefault("FormalityLevel", []).append(
            ClassifiedContribution(
                contribution=AttributeContribution(
                    source=f"formality_hint:{inputs.formality_hint}",
                    flatters=(inputs.formality_hint,),
                    avoid=(),
                ),
                source_kind="formality_hint",
                tier="hard",
            )
        )

    weather = graph.weather.get(inputs.weather_context)
    if weather is not None:
        _add_mapping(
            by_attr,
            weather.mapping,
            f"weather:{inputs.weather_context}",
            "weather_fabric",
            "hard",
            color_attrs_split=True,
        )
    elif inputs.weather_context:
        gaps.append(f"weather_context:{inputs.weather_context}")

    # --- SOFT sources -----------------------------------------------------
    if inputs.archetype:
        a_map = graph.archetype.get("primary_archetype", {}).get(inputs.archetype)
        if a_map is not None:
            _add_mapping(
                by_attr,
                a_map,
                f"archetype:{inputs.archetype}",
                "archetype",
                "soft",
            )
        else:
            gaps.append(f"archetype:{inputs.archetype}")

    rt_map = graph.archetype.get("risk_tolerance", {}).get(inputs.risk_tolerance)
    if rt_map is not None:
        _add_mapping(
            by_attr,
            rt_map,
            f"risk_tolerance:{inputs.risk_tolerance}",
            "risk_tolerance",
            "soft",
        )
    elif inputs.risk_tolerance:
        gaps.append(f"risk_tolerance:{inputs.risk_tolerance}")

    tod_value = _time_of_day_to_garment_value(inputs.time_of_day)
    if tod_value is not None:
        by_attr.setdefault("TimeOfDay", []).append(
            ClassifiedContribution(
                contribution=AttributeContribution(
                    source=f"time_of_day:{inputs.time_of_day}",
                    flatters=(tod_value,),
                    avoid=(),
                ),
                source_kind="time_of_day",
                tier="soft",
            )
        )

    return by_attr, gaps


# ─────────────────────────────────────────────────────────────────────────
# Peer-conflict detection
# ─────────────────────────────────────────────────────────────────────────


def _detect_peer_conflict(
    contribs: Sequence[ClassifiedContribution],
) -> bool:
    """Return True if any §4.2 peer pair has BOTH kinds opinionated for
    this attribute AND their flatters lists are disjoint."""
    by_kind: dict[str, set[str]] = {}
    for c in contribs:
        if c.contribution.flatters:
            by_kind.setdefault(c.source_kind, set()).update(
                c.contribution.flatters
            )
    for a, b in _PEER_PAIRS:
        sa, sb = by_kind.get(a), by_kind.get(b)
        if sa and sb and not (sa & sb):
            return True
    return False


# ─────────────────────────────────────────────────────────────────────────
# Direction-type resolution
# ─────────────────────────────────────────────────────────────────────────


def _resolve_query_structure(
    graph: StyleGraph,
    intent: str,
    occasion_signal: str,
) -> QueryStructureEntry | None:
    intent_map = graph.query_structure.get(intent) or {}
    entry = intent_map.get(occasion_signal)
    if entry is not None:
        return entry
    fallback_map = graph.query_structure.get("fallback") or {}
    return fallback_map.get("default")


def _build_query_specs(
    direction_type: str,
    direction_id: str,
    user: UserContext,
) -> list[QuerySpec]:
    """Emit QuerySpec stubs (one per role) for the resolved direction
    type. ``query_document`` is left empty here; 4.7e renders it from
    the composed attributes."""
    base_filters = build_global_hard_filters(user)
    if direction_type == "complete":
        roles = ("complete",)
    elif direction_type == "three_piece":
        roles = ("top", "bottom", "outerwear")
    else:  # default to paired
        roles = ("top", "bottom")
    return [
        QuerySpec(
            query_id=f"{direction_id}{i + 1}",
            role=role,
            hard_filters=dict(base_filters),
            query_document="",
        )
        for i, role in enumerate(roles)
    ]


# ─────────────────────────────────────────────────────────────────────────
# Confidence
# ─────────────────────────────────────────────────────────────────────────


def _compute_confidence(
    provenance: Sequence[ProvenanceEntry],
    yaml_gap: bool,
) -> float:
    softs = sum(len(p.dropped_softs) for p in provenance)
    hards = sum(len(p.widened_hards) for p in provenance)
    omitted = sum(1 for p in provenance if p.status == "omitted")
    score = (
        1.0
        - SOFT_DROP_PENALTY * softs
        - HARD_WIDEN_PENALTY * hards
        - ATTR_OMIT_PENALTY * omitted
        - (YAML_GAP_PENALTY if yaml_gap else 0.0)
    )
    return max(0.0, min(1.0, score))


# ─────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────


def compose_direction(
    *,
    inputs: CompositionInputs,
    graph: StyleGraph,
    user: UserContext,
) -> CompositionResult:
    """Reduce inputs + StyleGraph to a single ``DirectionSpec``.

    See spec §7 for the API contract. Returns a ``CompositionResult``
    whose ``confidence`` field the hot-path router (4.9) compares against
    the §9 fall-through criteria.

    The function is total — even on a YAML gap or full-failure cascade
    it returns a ``CompositionResult`` (with ``direction=None`` and a
    ``fallback_reason``) rather than raising. The router's job is to
    decide whether to honour the engine's result or fall through to the
    LLM architect.
    """
    contributions, gaps = _collect_contributions(inputs, graph)

    # Reduce every attribute that has any contribution.
    relaxed_by_attr: dict[str, RelaxedReduction] = {}
    needs_disambiguation = False
    for attr, contribs in contributions.items():
        if _detect_peer_conflict(contribs):
            needs_disambiguation = True
        relaxed_by_attr[attr] = reduce_with_relaxation(attr, contribs)

    # Provenance — sorted by attribute so output is stable.
    provenance: list[ProvenanceEntry] = []
    for attr in sorted(relaxed_by_attr):
        rr = relaxed_by_attr[attr]
        provenance.append(
            ProvenanceEntry(
                attribute=attr,
                final_flatters=rr.reduction.final_flatters,
                contributing_sources=rr.reduction.contributing_sources,
                status=rr.outcome.status,
                dropped_softs=rr.outcome.dropped_softs,
                widened_hards=rr.outcome.widened_hards,
            )
        )

    # Direction type from query_structure; YAML gap if neither the
    # intent-specific entry nor the fallback default exists.
    qs_entry = _resolve_query_structure(graph, inputs.intent, inputs.occasion_signal)
    if qs_entry is None:
        gaps.append(f"query_structure:{inputs.intent}.{inputs.occasion_signal}")
        direction_type = "paired"
    else:
        direction_type = qs_entry.default_structure or "paired"

    has_yaml_gap = bool(gaps)
    confidence = _compute_confidence(provenance, has_yaml_gap)

    queries = _build_query_specs(direction_type, inputs.direction_id, user)
    label = inputs.direction_label or _default_label(inputs)

    direction = DirectionSpec(
        direction_id=inputs.direction_id,
        direction_type=direction_type,
        label=label,
        queries=queries,
    )

    fallback_reason: str | None = None
    if has_yaml_gap:
        fallback_reason = "yaml_gap"
    elif confidence < CONFIDENCE_THRESHOLD:
        fallback_reason = "low_confidence"

    return CompositionResult(
        direction=direction,
        confidence=confidence,
        needs_disambiguation=needs_disambiguation,
        provenance=tuple(provenance),
        fallback_reason=fallback_reason,
        yaml_gaps=tuple(gaps),
    )


def _default_label(inputs: CompositionInputs) -> str:
    parts = [inputs.occasion_signal or "outfit"]
    if inputs.archetype:
        parts.append(inputs.archetype)
    if inputs.formality_hint:
        parts.append(inputs.formality_hint)
    return " — ".join(parts)
