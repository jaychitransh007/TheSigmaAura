"""Per-tuple scoring and rule evaluation for the composer engine (Phase 5b).

Implements §3-4 of ``docs/composer_semantics.md``. The scoring model:

- Each tuple starts with ``base_score = 1.0``.
- Hard rule violation → tuple is **dropped**. Score becomes 0, ``dropped=True``.
- Soft rule violation → ``-0.10`` per violation, accumulating.
- ``score_tuple()`` is the entry point; per-category evaluators dispatch
  via ``evaluate_constraint()``.

The 9 categories from ``pairing_rules.yaml``:

| Category | Type | On violation |
|---|---|---|
| formality_alignment | hard | drop |
| color_story | hard | drop |
| pattern_mixing | hard | drop |
| scale_balance | hard | drop (with bridal exception suspending) |
| bridal_specific | hard | v1 no-op (formality_alignment covers the practical case) |
| silhouette_balance | soft | -0.10 per violation |
| fabric_compatibility | soft | -0.10 per violation |
| cultural_coherence | soft | -0.10 per violation |
| anchor_constraints | (gate) | router declines anchor turns pre-engine; engine never invoked |

Pure functions. No I/O, no clock, no randomness. Same inputs → same output.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from itertools import combinations
from types import MappingProxyType
from typing import Callable, Mapping, Sequence

from .yaml_loader import StyleGraph


# ─────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────

HARD_CATEGORIES: tuple[str, ...] = (
    "formality_alignment",
    "color_story",
    "pattern_mixing",
    "scale_balance",
    "bridal_specific",
)
SOFT_CATEGORIES: tuple[str, ...] = (
    "silhouette_balance",
    "fabric_compatibility",
    "cultural_coherence",
)
ALL_CATEGORIES: tuple[str, ...] = HARD_CATEGORIES + SOFT_CATEGORIES

SOFT_PENALTY: float = 0.10
BASE_SCORE: float = 1.0


# ─────────────────────────────────────────────────────────────────────────
# Dataclasses
# ─────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Item:
    """Engine-internal view of a garment for tuple scoring.

    Projected from ``RetrievedProduct`` by the router (Phase 5d) — the
    engine itself never sees catalog enrichment naming. Empty strings
    indicate "no opinion / not enriched"; evaluators skip rules whose
    inputs are empty rather than treating absent data as a violation.
    """

    item_id: str
    slot: str  # "top" | "bottom" | "outerwear" | "complete"
    formality: str = ""
    dominant_color: str = ""
    contrast_level: str = ""
    pattern_type: str = ""
    pattern_scale: str = ""
    embellishment_level: str = ""
    color_saturation: str = ""
    color_temperature: str = ""
    color_value: str = ""
    fit_type: str = ""
    fit_ease: str = ""
    silhouette_contour: str = ""
    fabric_drape: str = ""
    fabric_texture: str = ""
    fabric_weight: str = ""
    sleeve_length: str = ""
    neckline_type: str = ""
    neckline_depth: str = ""
    garment_length: str = ""
    cultural_register: str = ""  # "indian_traditional" | "indo_western" | "western"
    subtype: str = ""  # e.g. "bandhgala", "lehenga", "saree" — for bridal_specific


# Maps architect hard_attrs key (PascalCase, catalog-side) → Item field
# (lowercase snake_case, engine-side). Attributes that aren't on Item
# (VolumeProfile, ShoulderStructure, etc.) get skipped at tuple-level
# scoring — they're body-shape preferences that stay in query_document
# text rather than as a hard penalty.
HARD_ATTR_TO_ITEM_FIELD: dict[str, str] = {
    "FormalityLevel": "formality",
    "FabricDrape": "fabric_drape",
    "FabricWeight": "fabric_weight",
    "FabricTexture": "fabric_texture",
    "SleeveLength": "sleeve_length",
    "FitType": "fit_type",
    "FitEase": "fit_ease",
    "SilhouetteContour": "silhouette_contour",
    "PatternType": "pattern_type",
    "PatternScale": "pattern_scale",
    "EmbellishmentLevel": "embellishment_level",
    "ColorSaturation": "color_saturation",
    "ColorTemperature": "color_temperature",
    "ColorValue": "color_value",
    "PrimaryColor": "dominant_color",
    "ContrastLevel": "contrast_level",
    "NecklineType": "neckline_type",
    "NecklineDepth": "neckline_depth",
    "GarmentLength": "garment_length",
}


# Per-violation penalty applied at tuple scoring (composer engine)
# when an item's enriched attribute value isn't in the architect's
# resolved allowed list. Same magnitude as a soft pairing-rule
# violation so neither dominates. Uniform across paired (2 items) and
# three_piece (3 items) tuples — the loop just iterates items.
HARD_ATTR_TUPLE_PENALTY: float = 0.10

# Phase 5x: per-tuple ceiling on cumulative hard-attr penalty. With
# the wider mapping (~19 attrs) and the orchestrator folding in
# user-explicit preferences, an item violating many axes could
# accumulate >1.0 penalty and dominate scoring. Cap at 0.40 per tuple
# so violations demote-but-don't-kill, and pairing-rule violations
# (formality, color_story, scale_balance) stay the dominant signal.
HARD_ATTR_TUPLE_PENALTY_CAP: float = 0.40


@dataclass(frozen=True)
class TupleContext:
    """Per-tuple context the evaluators need: planner output + select
    user-profile signals. Decoupled from CombinedContext so tests can
    construct minimal cases without touching the full request shape.

    ``hard_attrs`` carries the architect-engine-resolved per-attribute
    allowed-value lists (see engine.py:_build_hard_attrs). When set,
    score_tuple applies a per-item-per-violation penalty across the
    full tuple. Default empty preserves the spec §3 scoring (pairing
    rules only) for tests / direct callers that don't want this.
    """

    formality_hint: str = ""
    occasion_signal: str = ""
    palette_anchors: tuple[str, ...] = ()
    body_shape: str = ""
    intent: str = "recommendation_request"
    hard_attrs: Mapping[str, tuple[str, ...]] = field(default_factory=dict)


@dataclass(frozen=True)
class Violation:
    """One rule violation. Carries enough context to render a rationale
    and to surface in dashboards (Phase 5f panels 26 + 27)."""

    category: str
    rule: str
    detail: str
    is_hard: bool


@dataclass(frozen=True)
class TupleScore:
    """Result of scoring one tuple.

    ``dropped=True`` short-circuits — engine never picks dropped tuples.
    ``violations`` carries everything observed (hard violation that
    triggered the drop *plus* any earlier soft violations from
    short-circuited categories — none, in current implementation, since
    hard categories are checked first). ``drop_reason`` is the category
    name of the first hard violation observed, ``None`` if not dropped.
    """

    base_score: float
    violations: tuple[Violation, ...]
    dropped: bool
    drop_reason: str | None

    @property
    def is_kept(self) -> bool:
        return not self.dropped


# ─────────────────────────────────────────────────────────────────────────
# Public helpers
# ─────────────────────────────────────────────────────────────────────────


def is_statement(item: Item, _rules_unused: object | None = None) -> bool:
    """Statement-piece detection per ``scale_balance.statement_definition``.

    Source of truth: ``knowledge/style_graph/pairing_rules.yaml``,
    block ``scale_balance.statement_definition``. When that block changes,
    update this function in the same PR (composer_semantics.md §5 calls
    out the dual-edit requirement).

    The ``_rules_unused`` parameter exists for forward compatibility with
    a future YAML-DSL definition; v1 uses hardcoded thresholds.

    Returns True iff ANY of:
    - embellishment_level ∈ {moderate, heavy, statement}
    - pattern_scale ∈ {large, oversized}
    - color_saturation == very_high
    - pattern_type ∈ {animal, ethnic, abstract} AND pattern_scale ∈ {medium, large, oversized}
    """
    if item.embellishment_level in {"moderate", "heavy", "statement"}:
        return True
    if item.pattern_scale in {"large", "oversized"}:
        return True
    if item.color_saturation == "very_high":
        return True
    # Fourth clause adds the borderline `medium` scale for the three
    # high-impact pattern types — `large`/`oversized` are already
    # caught by the second clause regardless of pattern_type.
    if (
        item.pattern_type in {"animal", "ethnic", "abstract"}
        and item.pattern_scale == "medium"
    ):
        return True
    return False


def bridal_exception_active(ctx: TupleContext, graph: StyleGraph) -> bool:
    """Return True when the bridal exception applies to this tuple.

    Per composer_semantics.md §6: the exception suspends
    ``scale_balance.one_statement_per_outfit`` and activates
    ``bridal_specific`` subtype rules. Triggered by
    ``formality_hint == "ceremonial"`` AND
    ``occasion_signal in pairing_rules.bridal_specific.triggers_on``.

    The triggers_on list is YAML-driven so stylists can add bridal
    occasions without code changes.
    """
    if ctx.formality_hint != "ceremonial":
        return False
    bridal = graph.pairing_rules.get("bridal_specific")
    if bridal is None:
        return False
    return ctx.occasion_signal in bridal.triggers_on


def evaluate_constraint(
    category: str,
    items: tuple[Item, ...],
    ctx: TupleContext,
    graph: StyleGraph,
) -> tuple[Violation, ...]:
    """Dispatch to the per-category evaluator. Returns the (possibly
    empty) tuple of violations for that category."""
    fn = _DISPATCH.get(category)
    if fn is None:
        raise ValueError(f"Unknown pairing category: {category!r}")
    return fn(items, ctx, graph)


def _count_tuple_hard_attr_violations(
    items: Sequence[Item], hard_attrs: Mapping[str, Sequence[str]]
) -> int:
    """Sum hard_attrs violations across the tuple. Each item's enriched
    field (mapped via HARD_ATTR_TO_ITEM_FIELD) is checked against the
    architect's resolved allowed-value list; values not in the list
    count as a violation. Empty fields (``""``) and unmapped attribute
    names count as no opinion → no violation. Same loop shape applies
    to paired (2 items) and three_piece (3 items) tuples; complete
    direction iterates the single item."""
    if not hard_attrs:
        return 0
    count = 0
    for attr_name, allowed in hard_attrs.items():
        field_name = HARD_ATTR_TO_ITEM_FIELD.get(attr_name)
        if field_name is None:
            continue  # attr not on Item; skip (e.g., SilhouetteType)
        allowed_set = set(allowed) if allowed else set()
        if not allowed_set:
            continue
        for item in items:
            val = getattr(item, field_name, "") or ""
            if val and val not in allowed_set:
                count += 1
    return count


def score_tuple(
    items: Sequence[Item],
    ctx: TupleContext,
    graph: StyleGraph,
) -> TupleScore:
    """Score a candidate tuple.

    Hard categories are checked first; the first hard violation
    short-circuits and produces a dropped TupleScore (no soft checks
    run, so dropped tuples carry only the hard violation that caused
    the drop). Surviving tuples accumulate soft penalties at -0.10
    each.

    Tuple-level hard_attrs penalty (added May 7 2026): when
    ``ctx.hard_attrs`` is populated, the score is further reduced by
    ``HARD_ATTR_TUPLE_PENALTY (0.10)`` per-item-per-violation across
    the tuple. A 3-item tuple where 2 items violate `SleeveLength` and
    1 violates `FabricWeight` accumulates 3 violations → -0.30. This
    runs in addition to the per-item retrieval penalty (catalog_search_
    agent's _apply_hard_attr_penalty) — they're at different stages and
    serve different roles: retrieval ranks within a role pool;
    composer-tuple ranks across the full outfit.

    Empty tuple → dropped with reason "empty_tuple".
    """
    items_t = tuple(items)
    if not items_t:
        return TupleScore(
            base_score=0.0,
            violations=(),
            dropped=True,
            drop_reason="empty_tuple",
        )

    for cat in HARD_CATEGORIES:
        violations = evaluate_constraint(cat, items_t, ctx, graph)
        if violations:
            return TupleScore(
                base_score=0.0,
                violations=violations,
                dropped=True,
                drop_reason=cat,
            )

    soft_violations: list[Violation] = []
    for cat in SOFT_CATEGORIES:
        soft_violations.extend(evaluate_constraint(cat, items_t, ctx, graph))

    hard_attr_violations = _count_tuple_hard_attr_violations(items_t, ctx.hard_attrs)
    hard_attr_penalty = min(
        HARD_ATTR_TUPLE_PENALTY * hard_attr_violations,
        HARD_ATTR_TUPLE_PENALTY_CAP,
    )

    score = (
        BASE_SCORE
        - SOFT_PENALTY * len(soft_violations)
        - hard_attr_penalty
    )
    return TupleScore(
        base_score=score,
        violations=tuple(soft_violations),
        dropped=False,
        drop_reason=None,
    )


# ─────────────────────────────────────────────────────────────────────────
# Per-category evaluators
# ─────────────────────────────────────────────────────────────────────────


def _evaluate_formality_alignment(
    items: tuple[Item, ...], ctx: TupleContext, graph: StyleGraph
) -> tuple[Violation, ...]:
    group = graph.pairing_rules.get("formality_alignment")
    if group is None:
        return ()
    rule = group.rules.get("formality_within_one_step")
    if rule is None or not rule.compatibility_matrix:
        return ()
    matrix = rule.compatibility_matrix
    violations: list[Violation] = []
    for a, b in combinations(items, 2):
        if not a.formality or not b.formality:
            continue
        allowed = matrix.get(a.formality, ())
        if b.formality not in allowed:
            violations.append(
                Violation(
                    category="formality_alignment",
                    rule="formality_within_one_step",
                    detail=(
                        f"{a.slot}({a.formality}) + {b.slot}({b.formality}) "
                        "outside ±1 step on formality scale"
                    ),
                    is_hard=True,
                )
            )
    return tuple(violations)


def _evaluate_color_story(
    items: tuple[Item, ...], ctx: TupleContext, graph: StyleGraph
) -> tuple[Violation, ...]:
    group = graph.pairing_rules.get("color_story")
    if group is None:
        return ()
    violations: list[Violation] = []

    # max_dominant_colors: distinct dominant colors across slots ≤ 3.
    max_rule = group.rules.get("max_dominant_colors")
    max_count = (
        max_rule.value
        if max_rule is not None and max_rule.value is not None
        else 3
    )
    distinct = {it.dominant_color for it in items if it.dominant_color}
    if len(distinct) > max_count:
        violations.append(
            Violation(
                category="color_story",
                rule="max_dominant_colors",
                detail=f"{len(distinct)} dominant colors > {max_count} limit",
                is_hard=True,
            )
        )

    # palette_anchor_required: at least one slot in user's palette anchors.
    # Skip when caller didn't provide anchors (test setups, profile gaps).
    # Also skip when ANY item is missing dominant_color — under the
    # "skip if empty" policy we can't confirm the rule is violated when
    # an unknown-color item might itself be an anchor color. Only
    # report a violation when every item has color data and none of
    # them match an anchor.
    if ctx.palette_anchors:
        colors = [it.dominant_color for it in items if it.dominant_color]
        if len(colors) == len(items):  # every item has a color
            if not any(c in ctx.palette_anchors for c in colors):
                violations.append(
                    Violation(
                        category="color_story",
                        rule="palette_anchor_required",
                        detail="no slot uses a color from user's SubSeason palette anchors",
                        is_hard=True,
                    )
                )

    # contrast_alignment: ordered-pair compatibility.
    contrast_rule = group.rules.get("contrast_alignment")
    if contrast_rule is not None and contrast_rule.compatibility_matrix:
        matrix = contrast_rule.compatibility_matrix
        for a, b in combinations(items, 2):
            if not a.contrast_level or not b.contrast_level:
                continue
            allowed = matrix.get(a.contrast_level, ())
            if b.contrast_level not in allowed:
                violations.append(
                    Violation(
                        category="color_story",
                        rule="contrast_alignment",
                        detail=(
                            f"{a.contrast_level} + {b.contrast_level} contrast "
                            "outside compatibility matrix"
                        ),
                        is_hard=True,
                    )
                )

    return tuple(violations)


def _evaluate_pattern_mixing(
    items: tuple[Item, ...], ctx: TupleContext, graph: StyleGraph
) -> tuple[Violation, ...]:
    group = graph.pairing_rules.get("pattern_mixing")
    if group is None:
        return ()

    patterned = [it for it in items if it.pattern_type and it.pattern_type != "solid"]
    n = len(patterned)

    if n <= 1:
        return ()  # solid_plus_pattern always passes

    if n >= 3:
        return (
            Violation(
                category="pattern_mixing",
                rule="three_patterns",
                detail=f"{n} patterned slots; max 2 (3+ reads chaotic)",
                is_hard=True,
            ),
        )

    # n == 2: scale-pair must be in matrix AND same-color-family OR same-contrast.
    two_rule = group.rules.get("two_patterns")
    if two_rule is None:
        return ()
    a, b = patterned[0], patterned[1]

    if two_rule.compatibility_matrix and a.pattern_scale and b.pattern_scale:
        allowed = two_rule.compatibility_matrix.get(a.pattern_scale, ())
        if b.pattern_scale not in allowed:
            return (
                Violation(
                    category="pattern_mixing",
                    rule="two_patterns_scale",
                    detail=(
                        f"pattern scales {a.pattern_scale} + {b.pattern_scale} "
                        "not allowed together"
                    ),
                    is_hard=True,
                ),
            )

    # two_patterns_color_family: skip-if-empty — only fire when BOTH
    # color and contrast are evaluable on both items. With a missing
    # field we can't confirm there's no link, so abstain rather than
    # report a violation against possibly-compatible inputs.
    color_evaluable = bool(a.dominant_color and b.dominant_color)
    contrast_evaluable = bool(a.contrast_level and b.contrast_level)
    if not (color_evaluable and contrast_evaluable):
        return ()
    same_color = a.dominant_color == b.dominant_color
    same_contrast = a.contrast_level == b.contrast_level
    if not (same_color or same_contrast):
        return (
            Violation(
                category="pattern_mixing",
                rule="two_patterns_color_family",
                detail=(
                    "two patterned slots require same dominant_color "
                    "or same contrast_level"
                ),
                is_hard=True,
            ),
        )

    return ()


def _evaluate_scale_balance(
    items: tuple[Item, ...], ctx: TupleContext, graph: StyleGraph
) -> tuple[Violation, ...]:
    if bridal_exception_active(ctx, graph):
        return ()  # statement cap suspended in bridal contexts
    statement_count = sum(1 for it in items if is_statement(it))
    if statement_count > 1:
        return (
            Violation(
                category="scale_balance",
                rule="one_statement_per_outfit",
                detail=(
                    f"{statement_count} statement slots; max 1 outside bridal context"
                ),
                is_hard=True,
            ),
        )
    return ()


def _evaluate_bridal_specific(
    items: tuple[Item, ...], ctx: TupleContext, graph: StyleGraph
) -> tuple[Violation, ...]:
    """v1 no-op. Subtype-specific rules (bridal_lehenga_pairing,
    heavy_banarasi_pairing, sherwani_pairing, bandhgala_versatility)
    enforce per-subtype companion constraints whose practical effect
    on the tuple-scoring path is already covered by formality_alignment
    (ceremonial-only pairings) and scale_balance's bridal exception.

    Subtype-specific enforcement (e.g., dupatta-must-be-lighter-weight-
    than-lehenga) ships in a Phase 5 follow-up after the core engine
    is validated. Empty implementation here documents the deferral
    rather than silently leaving the category un-dispatched.
    """
    return ()


def _evaluate_silhouette_balance(
    items: tuple[Item, ...], ctx: TupleContext, graph: StyleGraph
) -> tuple[Violation, ...]:
    violations: list[Violation] = []

    fits = [it.fit_type for it in items if it.fit_type]
    if fits and len(fits) == len(items):
        if all(f in {"slim", "tailored"} for f in fits) and ctx.body_shape != "Hourglass":
            violations.append(
                Violation(
                    category="silhouette_balance",
                    rule="no_all_fitted",
                    detail="every slot fitted; reads bodycon outside Hourglass exception",
                    is_hard=False,
                )
            )
        if (
            all(f in {"boxy", "loose", "relaxed"} for f in fits)
            and ctx.body_shape not in {"Apple", "Diamond"}
        ):
            violations.append(
                Violation(
                    category="silhouette_balance",
                    rule="no_all_relaxed",
                    detail="every slot relaxed; silhouette disappears outside Apple/Diamond exception",
                    is_hard=False,
                )
            )

    for it in items:
        if it.slot == "outerwear" and it.fabric_drape == "fluid":
            violations.append(
                Violation(
                    category="silhouette_balance",
                    rule="structured_outerwear_anchor",
                    detail="outerwear with fluid drape inverts structural hierarchy",
                    is_hard=False,
                )
            )

    return tuple(violations)


def _evaluate_fabric_compatibility(
    items: tuple[Item, ...], ctx: TupleContext, graph: StyleGraph
) -> tuple[Violation, ...]:
    group = graph.pairing_rules.get("fabric_compatibility")
    if group is None:
        return ()
    violations: list[Violation] = []

    tex_rule = group.rules.get("texture_mixing")
    if tex_rule is not None and tex_rule.compatibility_matrix:
        matrix = tex_rule.compatibility_matrix
        for a, b in combinations(items, 2):
            if not a.fabric_texture or not b.fabric_texture:
                continue
            allowed = matrix.get(a.fabric_texture, ())
            if b.fabric_texture not in allowed:
                violations.append(
                    Violation(
                        category="fabric_compatibility",
                        rule="texture_mixing",
                        detail=(
                            f"texture {a.fabric_texture} + {b.fabric_texture} clashes"
                        ),
                        is_hard=False,
                    )
                )

    weight_rule = group.rules.get("weight_pairing")
    if weight_rule is not None and weight_rule.compatibility_matrix:
        matrix = weight_rule.compatibility_matrix
        for a, b in combinations(items, 2):
            if not a.fabric_weight or not b.fabric_weight:
                continue
            allowed = matrix.get(a.fabric_weight, ())
            if b.fabric_weight not in allowed:
                violations.append(
                    Violation(
                        category="fabric_compatibility",
                        rule="weight_pairing",
                        detail=(
                            f"weight {a.fabric_weight} + {b.fabric_weight} register mismatch"
                        ),
                        is_hard=False,
                    )
                )

    # drape_compatibility — documentation-only in YAML, no engine check.
    return tuple(violations)


def _evaluate_cultural_coherence(
    items: tuple[Item, ...], ctx: TupleContext, graph: StyleGraph
) -> tuple[Violation, ...]:
    registers = [it.cultural_register for it in items if it.cultural_register]
    if not registers:
        return ()

    has_traditional = "indian_traditional" in registers
    has_western = "western" in registers
    has_fusion = "indo_western" in registers
    violations: list[Violation] = []

    # indo_western_fusion: skip-if-empty — only report when every item's
    # cultural_register is known. An unknown-register item could itself
    # be the indo_western bridge that satisfies the rule, so we can't
    # confirm a violation without complete data.
    if (
        has_traditional and has_western and not has_fusion
        and len(registers) == len(items)
    ):
        violations.append(
            Violation(
                category="cultural_coherence",
                rule="indo_western_fusion",
                detail="indian_traditional + western without indo_western bridge slot",
                is_hard=False,
            )
        )

    heavy_traditional = any(
        it.cultural_register == "indian_traditional"
        and it.embellishment_level in {"heavy", "statement"}
        for it in items
    )
    if heavy_traditional and has_western:
        violations.append(
            Violation(
                category="cultural_coherence",
                rule="heavy_traditional_no_western_fusion",
                detail="heavy/statement traditional item paired with western item",
                is_hard=False,
            )
        )

    return tuple(violations)


# ─────────────────────────────────────────────────────────────────────────
# Dispatch table — defined after the evaluators so they're in scope.
# ─────────────────────────────────────────────────────────────────────────


_EvaluatorFn = Callable[
    [tuple[Item, ...], TupleContext, StyleGraph], tuple[Violation, ...]
]
_DISPATCH: dict[str, _EvaluatorFn] = {
    "formality_alignment": _evaluate_formality_alignment,
    "color_story": _evaluate_color_story,
    "pattern_mixing": _evaluate_pattern_mixing,
    "scale_balance": _evaluate_scale_balance,
    "bridal_specific": _evaluate_bridal_specific,
    "silhouette_balance": _evaluate_silhouette_balance,
    "fabric_compatibility": _evaluate_fabric_compatibility,
    "cultural_coherence": _evaluate_cultural_coherence,
}


__all__ = [
    "Item",
    "TupleContext",
    "Violation",
    "TupleScore",
    "HARD_CATEGORIES",
    "SOFT_CATEGORIES",
    "ALL_CATEGORIES",
    "SOFT_PENALTY",
    "BASE_SCORE",
    "is_statement",
    "bridal_exception_active",
    "evaluate_constraint",
    "score_tuple",
]
