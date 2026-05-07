"""Composer engine — Phase 5c.

Reduces ``RecommendationPlan + retrieved pools + CombinedContext`` to a
``ComposerResult`` via tuple scoring (5b's pairing rules) + greedy top-K
with diversity penalty. Pure function: no I/O, no clock, no randomness.

Algorithm (composer_semantics.md §3-§7):

1. Project each ``RetrievedProduct`` into the engine's ``Item`` shape.
2. Per direction, check sparse-pool eligibility (§3.4).
3. Enumerate candidate tuples per direction up to ``MAX_POOL_PER_ROLE``
   per role.
4. Score each tuple via ``score_tuple`` (5b). Drop hard-violators.
5. Greedy top-K with multiplicative diversity penalty (same direction
   ×0.6, same dominant color ×0.7, same statement slot ×0.8).
6. Compute confidence per §7.1; surface yaml_gaps; assemble
   ``ComposerEngineResult``.

Engine returns ``ComposerEngineResult.composer_result == None`` whenever
fall-through is required (low confidence, fewer than ``MIN_PICKS``
outfits, sparse pool, or YAML gap). The router (5d) honors that signal
and triggers the LLM ``OutfitComposer`` fallback.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

from ..schemas import (
    ComposedOutfit,
    ComposerResult,
    RecommendationPlan,
    RetrievedProduct,
    RetrievedSet,
)
from .pairing import (
    Item,
    TupleContext,
    TupleScore,
    Violation,
    is_statement,
    score_tuple,
)
from .yaml_loader import StyleGraph


# ─────────────────────────────────────────────────────────────────────────
# Spec-derived constants
# ─────────────────────────────────────────────────────────────────────────

MAX_POOL_PER_ROLE = 5
MIN_OUTFIT_SCORE = 0.50
MIN_PICKS = 3
MAX_OUTFITS = 6

# Confidence formula (§7.1)
CONFIDENCE_THRESHOLD = 0.50
PENALTY_DIRECTION_SKIPPED = 0.20
PENALTY_DIRECTION_NO_PICKS = 0.30
PENALTY_PICK_SHORTFALL = 0.10
PENALTY_YAML_GAP = 0.45

# Diversity multipliers (§3.3)
DIV_SAME_DIRECTION = 0.6
DIV_SAME_COLOR = 0.7
DIV_SAME_STATEMENT_SLOT = 0.8


# Subtype → cultural_register heuristic (composer_semantics.md §4.7).
# Empty register → engine abstains from cultural_coherence rule.
_INDIAN_TRADITIONAL_SUBTYPES = frozenset(
    {
        "kurta", "kurti", "saree", "lehenga", "lehenga_set", "sherwani",
        "dupatta", "anarkali", "choli", "banarasi", "kanjeevaram",
        "salwar", "churidar", "dhoti", "dhoti_pant", "palazzo", "patiala",
        "jodhpuri", "achkan", "ghagra", "patola", "phulkari",
    }
)
_INDO_WESTERN_SUBTYPES = frozenset(
    {"bandhgala", "nehru_jacket", "fusion_kurta", "kurta_jacket", "indo_western_jacket"}
)
_WESTERN_SUBTYPES = frozenset(
    {
        "shirt", "t_shirt", "blouse", "blazer", "jacket", "coat", "trouser",
        "jeans", "skirt", "dress", "gown", "suit", "pant", "chinos",
    }
)


# ─────────────────────────────────────────────────────────────────────────
# Output dataclasses
# ─────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class TupleProvenance:
    """One tuple's audit trail. Surfaces in PR 5f's panel-25 plan-source
    distribution, panel-26 rule-violation distribution, and panel-28
    single-turn diagnostic.
    """

    direction_id: str
    direction_type: str
    item_ids: tuple[str, ...]
    base_score: float
    violations: tuple[Violation, ...]
    dropped: bool
    drop_reason: str | None
    picked: bool
    diversity_multiplier: float


@dataclass(frozen=True)
class ComposerEngineResult:
    """Engine envelope per composer_semantics.md §7."""

    composer_result: ComposerResult | None
    confidence: float
    fallback_reason: str | None
    yaml_gaps: tuple[str, ...]
    provenance: tuple[TupleProvenance, ...]


# ─────────────────────────────────────────────────────────────────────────
# Item projection (PascalCase enriched_data → engine Item)
# ─────────────────────────────────────────────────────────────────────────


def _infer_cultural_register(subtype: str) -> str:
    """Subtype-driven heuristic. Empty when ambiguous; engine treats
    empty as 'no opinion' and abstains from cultural_coherence."""
    s = (subtype or "").strip().lower().replace("-", "_")
    if s in _INDIAN_TRADITIONAL_SUBTYPES:
        return "indian_traditional"
    if s in _INDO_WESTERN_SUBTYPES:
        return "indo_western"
    if s in _WESTERN_SUBTYPES:
        return "western"
    return ""


def _project_item(product: RetrievedProduct, slot: str) -> Item:
    """Convert a ``RetrievedProduct`` into the engine's ``Item`` shape.

    Reads enrichment columns from ``product.enriched_data`` (PascalCase
    per catalog convention). Empty strings indicate missing enrichment;
    pairing evaluators skip rules whose inputs are empty rather than
    treating absent data as a violation."""
    enriched = product.enriched_data or {}

    def get_str(key: str) -> str:
        v = enriched.get(key)
        return str(v) if v is not None and v != "" else ""

    subtype = get_str("GarmentSubtype")
    return Item(
        item_id=product.product_id,
        slot=slot,
        formality=get_str("FormalityLevel"),
        dominant_color=get_str("PrimaryColor"),
        contrast_level=get_str("ContrastLevel"),
        pattern_type=get_str("PatternType"),
        pattern_scale=get_str("PatternScale"),
        embellishment_level=get_str("EmbellishmentLevel"),
        color_saturation=get_str("ColorSaturation"),
        fit_type=get_str("FitType"),
        fabric_drape=get_str("FabricDrape"),
        fabric_texture=get_str("FabricTexture"),
        fabric_weight=get_str("FabricWeight"),
        sleeve_length=get_str("SleeveLength"),
        cultural_register=_infer_cultural_register(subtype),
        subtype=subtype,
    )


# ─────────────────────────────────────────────────────────────────────────
# Pool eligibility + tuple enumeration
# ─────────────────────────────────────────────────────────────────────────


def _direction_is_eligible(
    direction_type: str, pools_by_role: Mapping[str, Sequence[Item]]
) -> bool:
    """Spec §3.4: each role pool needs ≥2 items for the direction to
    be enumerable. Unknown direction_type is treated as ineligible
    (engine falls through cleanly)."""
    if direction_type == "complete":
        return len(pools_by_role.get("complete", [])) >= 2
    if direction_type == "paired":
        return (
            len(pools_by_role.get("top", [])) >= 2
            and len(pools_by_role.get("bottom", [])) >= 2
        )
    if direction_type == "three_piece":
        return (
            len(pools_by_role.get("top", [])) >= 2
            and len(pools_by_role.get("bottom", [])) >= 2
            and len(pools_by_role.get("outerwear", [])) >= 2
        )
    return False


def _dedupe_by_item_id(items: Sequence[Item]) -> list[Item]:
    """Drop duplicate item_ids within a single role pool, keeping the
    first occurrence (which is the highest-similarity item per the
    cosine ranking from retrieval). The catalog has products that
    appear as multiple embedding rows under the same product_id (size
    / color variants); without this dedup the retrieved pool is
    effectively narrower than its row count suggests."""
    seen: set[str] = set()
    out: list[Item] = []
    for it in items:
        if it.item_id and it.item_id not in seen:
            seen.add(it.item_id)
            out.append(it)
    return out


def _enumerate_direction_tuples(
    direction_id: str,
    direction_type: str,
    pools_by_role: Mapping[str, Sequence[Item]],
) -> list[tuple[Item, ...]]:
    """Cartesian product across roles, capped at MAX_POOL_PER_ROLE.

    Per-role pools are deduped by ``item_id`` first (catalog has
    duplicate product_ids across embedding rows). Then for paired and
    three_piece, the cartesian is filtered so all items in a tuple
    have distinct item_ids — otherwise the same product showing up in
    top + bottom + outerwear pools (catalog data corruption — same
    product_id with different subtypes per row) yields outfits like
    (X, X, X). Same uniqueness rule for paired (2 items) and
    three_piece (3 items)."""
    cap = MAX_POOL_PER_ROLE
    if direction_type == "complete":
        complete = _dedupe_by_item_id(list(pools_by_role.get("complete", [])))[:cap]
        return [(it,) for it in complete]
    if direction_type == "paired":
        tops = _dedupe_by_item_id(list(pools_by_role.get("top", [])))[:cap]
        bottoms = _dedupe_by_item_id(list(pools_by_role.get("bottom", [])))[:cap]
        return [
            (t, b)
            for t in tops for b in bottoms
            if t.item_id != b.item_id
        ]
    if direction_type == "three_piece":
        tops = _dedupe_by_item_id(list(pools_by_role.get("top", [])))[:cap]
        bottoms = _dedupe_by_item_id(list(pools_by_role.get("bottom", [])))[:cap]
        outers = _dedupe_by_item_id(list(pools_by_role.get("outerwear", [])))[:cap]
        return [
            (t, b, o)
            for t in tops for b in bottoms for o in outers
            if t.item_id != b.item_id and t.item_id != o.item_id and b.item_id != o.item_id
        ]
    return []


# ─────────────────────────────────────────────────────────────────────────
# Diversity penalty
# ─────────────────────────────────────────────────────────────────────────


def _dominant_color(items: tuple[Item, ...]) -> str:
    counts: dict[str, int] = {}
    for it in items:
        if it.dominant_color:
            counts[it.dominant_color] = counts.get(it.dominant_color, 0) + 1
    if not counts:
        return ""
    # Tie-break by lexical color for determinism.
    return max(counts.items(), key=lambda kv: (kv[1], kv[0]))[0]


def _statement_slot(items: tuple[Item, ...]) -> str:
    for it in items:
        if is_statement(it):
            return it.slot
    return ""


def _diversity_multiplier(
    candidate_dir: str,
    candidate_items: tuple[Item, ...],
    picks: Sequence[tuple[str, str, tuple[Item, ...], TupleScore, float]],
) -> float:
    """Spec §3.3 — multiplicative penalty against already-picked outfits.
    For each pick, compute a per-pick multiplier then take the minimum
    across picks. (Severity-weighted: a candidate maximally similar to
    *any* already-picked outfit is the constraint.)"""
    if not picks:
        return 1.0

    cand_color = _dominant_color(candidate_items)
    cand_statement = _statement_slot(candidate_items)
    worst = 1.0
    for picked in picks:
        m = 1.0
        if picked[0] == candidate_dir:
            m *= DIV_SAME_DIRECTION
        if cand_color and _dominant_color(picked[2]) == cand_color:
            m *= DIV_SAME_COLOR
        if cand_statement and _statement_slot(picked[2]) == cand_statement:
            m *= DIV_SAME_STATEMENT_SLOT
        worst = min(worst, m)
    return worst


# ─────────────────────────────────────────────────────────────────────────
# Greedy selection
# ─────────────────────────────────────────────────────────────────────────


def _greedy_top_k(
    scored: Sequence[tuple[str, str, tuple[Item, ...], TupleScore]],
) -> list[tuple[str, str, tuple[Item, ...], TupleScore, float]]:
    """Greedy top-K with diversity penalty. Pick highest effective_score,
    recompute multipliers against the new pick set, repeat. Stop at
    ``MAX_OUTFITS`` picks or when no candidate has effective_score ≥
    ``MIN_OUTFIT_SCORE``.

    Returns picks with their final diversity_multiplier attached.
    """
    remaining = list(scored)
    picks: list[tuple[str, str, tuple[Item, ...], TupleScore, float]] = []
    while remaining and len(picks) < MAX_OUTFITS:
        best_idx = -1
        best_eff = -1.0
        best_mult = 1.0
        for i, cand in enumerate(remaining):
            mult = _diversity_multiplier(cand[0], cand[2], picks)
            eff = cand[3].base_score * mult
            if eff < MIN_OUTFIT_SCORE:
                continue
            if eff > best_eff:
                best_eff = eff
                best_idx = i
                best_mult = mult
        if best_idx < 0:
            break
        chosen = remaining.pop(best_idx)
        picks.append((chosen[0], chosen[1], chosen[2], chosen[3], best_mult))
    return picks


# ─────────────────────────────────────────────────────────────────────────
# Confidence + assessment
# ─────────────────────────────────────────────────────────────────────────


def _compute_confidence(
    *,
    total_directions: int,
    directions_skipped: int,
    directions_with_picks: int,
    pick_count: int,
    has_yaml_gap: bool,
) -> float:
    if total_directions == 0:
        return 0.0
    skipped_frac = directions_skipped / total_directions
    no_picks_frac = 1.0 - (directions_with_picks / total_directions)
    pick_shortfall = max(0, MAX_OUTFITS - pick_count) / MAX_OUTFITS
    score = (
        1.0
        - PENALTY_DIRECTION_SKIPPED * skipped_frac
        - PENALTY_DIRECTION_NO_PICKS * no_picks_frac
        - PENALTY_PICK_SHORTFALL * pick_shortfall
        - (PENALTY_YAML_GAP if has_yaml_gap else 0.0)
    )
    return max(0.0, min(1.0, score))


def _assess_overall(
    pick_count: int, soft_violation_count: int, total_directions_with_picks: int
) -> str:
    """Map pick stats to ``ComposerResult.overall_assessment``.

    Heuristic — not user-visible nuance, just a rater-input hint.
    Values: strong | moderate | weak | unsuitable.
    """
    if pick_count == 0:
        return "unsuitable"
    if pick_count >= 5 and soft_violation_count <= 2 and total_directions_with_picks >= 2:
        return "strong"
    if pick_count >= 3:
        return "moderate"
    return "weak"


# ─────────────────────────────────────────────────────────────────────────
# Outfit naming + rationale
# ─────────────────────────────────────────────────────────────────────────


_CONTRAST_WORD = {
    "very_high": "Bold",
    "high": "Sharp",
    "medium": "Balanced",
    "low": "Soft",
}


def _outfit_name(
    items: tuple[Item, ...], direction_type: str, direction_label: str
) -> str:
    """Spec §7.5 deterministic name template. Stylist polish deferred
    to a follow-up; v1 names are functional-but-bland."""
    color = _dominant_color(items) or "neutral"
    color_word = color.replace("_", " ").title()

    if direction_type == "complete":
        label_short = (direction_label or "Look").strip().split(" ")[0].title() or "Look"
        return f"{color_word} {label_short}"

    if direction_type == "three_piece":
        outer_subtype = next(
            (it.subtype for it in items if it.slot == "outerwear" and it.subtype),
            "",
        )
        ow_word = (outer_subtype or "Layered").replace("_", " ").title()
        return f"{ow_word} {color_word} Layered"

    # paired (default)
    contrast = next((it.contrast_level for it in items if it.contrast_level), "")
    contrast_word = _CONTRAST_WORD.get(contrast, "Classic")
    return f"{contrast_word} {color_word} Pair"


def _rationale(items: tuple[Item, ...], score: TupleScore) -> str:
    parts: list[str] = []
    formality = next((it.formality for it in items if it.formality), "")
    if formality:
        parts.append(f"formality {formality}")
    color = _dominant_color(items)
    if color:
        parts.append(f"color {color}")
    if any(is_statement(it) for it in items):
        parts.append("one statement piece")
    elif items:
        parts.append("balanced silhouette")
    if score.violations:
        n = len(score.violations)
        parts.append(f"({n} soft note{'s' if n != 1 else ''})")
    return ", ".join(parts) or "clean composition"


# ─────────────────────────────────────────────────────────────────────────
# Audit JSON for ComposerResult.raw_response
# ─────────────────────────────────────────────────────────────────────────


def _render_audit_json(
    *,
    plan: RecommendationPlan,
    picks: Sequence[tuple[str, str, tuple[Item, ...], TupleScore, float]],
    confidence: float,
    directions_skipped: int,
    yaml_gaps: tuple[str, ...],
) -> str:
    """Pretty-printed JSON for ``ComposerResult.raw_response``. Engine
    state for ops debugging + 5e quality validator + 5f single-turn
    diagnostic dashboard."""
    return json.dumps(
        {
            "engine": "composer",
            "version": "5c",
            "directions_total": len(plan.directions),
            "directions_skipped_for_sparse_pool": directions_skipped,
            "yaml_gaps": list(yaml_gaps),
            "picks": [
                {
                    "composer_id": f"E{i + 1}",
                    "direction_id": p[0],
                    "direction_type": p[1],
                    "item_ids": [it.item_id for it in p[2]],
                    "base_score": round(p[3].base_score, 4),
                    "diversity_multiplier": round(p[4], 4),
                    "soft_violations": [v.rule for v in p[3].violations],
                }
                for i, p in enumerate(picks)
            ],
            "confidence": round(confidence, 4),
        },
        indent=2,
        sort_keys=False,
    )


# ─────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────


def compose_outfits(
    *,
    plan: RecommendationPlan,
    retrieved_sets: Iterable[RetrievedSet],
    ctx: TupleContext,
    graph: StyleGraph,
) -> ComposerEngineResult:
    """Reduce architect plan + retrieved pools to a ComposerResult.

    Pure function — no I/O, no clock, no randomness. Pre-engine
    eligibility gates (anchor turns, follow-ups, ``previous_recommendations``,
    ``architect_plan_from_cache``) are checked by the router (5d) before
    this is called. The engine itself handles only the sparse-pool gate
    per §3.4.

    Returns a ``ComposerEngineResult`` whose ``composer_result is None``
    signals fall-through to the LLM. ``provenance`` is populated for
    every scored tuple regardless of fall-through, so ops can audit
    misses.
    """
    sets_list = list(retrieved_sets)
    yaml_gaps: list[str] = []  # reserved for future YAML-gap surfaces

    # Group retrieved sets by (direction_id, role) and project items.
    by_dir: dict[str, dict[str, list[Item]]] = {}
    for rs in sets_list:
        items = [_project_item(p, rs.role) for p in rs.products]
        by_dir.setdefault(rs.direction_id, {}).setdefault(rs.role, []).extend(items)

    # Eligibility check per direction.
    total_directions = len(plan.directions)
    directions_skipped = 0
    eligible_directions: list[tuple[str, str, str, dict[str, list[Item]]]] = []
    for d in plan.directions:
        pools = by_dir.get(d.direction_id, {})
        if _direction_is_eligible(d.direction_type, pools):
            eligible_directions.append(
                (d.direction_id, d.direction_type, d.label, pools)
            )
        else:
            directions_skipped += 1

    direction_label_map = {d.direction_id: d.label for d in plan.directions}

    # Per-direction hard_attrs: the architect engine emits identical
    # hard_attrs across every QuerySpec in a direction, so any query's
    # value works as the direction-level constraint set used for tuple
    # scoring. Empty dict for LLM-architect-path plans (they don't
    # populate hard_attrs); score_tuple's tuple-level penalty no-ops.
    direction_hard_attrs: dict[str, Mapping[str, tuple[str, ...]]] = {}
    for d in plan.directions:
        if d.queries:
            ha = d.queries[0].hard_attrs or {}
            direction_hard_attrs[d.direction_id] = {
                k: tuple(v) for k, v in ha.items()
            }

    # Enumerate + score across eligible directions. Each direction's
    # hard_attrs flow into the per-tuple TupleContext so score_tuple
    # can apply its tuple-level penalty (-0.10 per item-per-violation
    # across the tuple).
    all_scored: list[tuple[str, str, tuple[Item, ...], TupleScore]] = []
    for direction_id, direction_type, _label, pools in eligible_directions:
        ha = direction_hard_attrs.get(direction_id) or {}
        # Replace ctx.hard_attrs with this direction's resolved set;
        # other ctx fields (formality_hint, body_shape, etc.) carry
        # over unchanged for the non-hard-attr pairing rules.
        scoped_ctx = TupleContext(
            formality_hint=ctx.formality_hint,
            occasion_signal=ctx.occasion_signal,
            palette_anchors=ctx.palette_anchors,
            body_shape=ctx.body_shape,
            intent=ctx.intent,
            hard_attrs=ha,
        )
        for items in _enumerate_direction_tuples(direction_id, direction_type, pools):
            score = score_tuple(items, scoped_ctx, graph)
            all_scored.append((direction_id, direction_type, items, score))

    kept = [s for s in all_scored if not s[3].dropped]
    # Stable sort: highest base_score first, ties broken by item_ids for determinism.
    kept.sort(key=lambda s: (-s[3].base_score, tuple(it.item_id for it in s[2])))

    picks = _greedy_top_k(kept)

    # Build ComposedOutfits.
    outfits = [
        ComposedOutfit(
            composer_id=f"E{i + 1}",
            direction_id=p[0],
            direction_type=p[1],
            item_ids=[it.item_id for it in p[2]],
            rationale=_rationale(p[2], p[3]),
            name=_outfit_name(p[2], p[1], direction_label_map.get(p[0], "")),
        )
        for i, p in enumerate(picks)
    ]

    # Provenance for every scored tuple.
    picked_keys = {(p[0], tuple(it.item_id for it in p[2])): p[4] for p in picks}
    provenance = tuple(
        TupleProvenance(
            direction_id=did,
            direction_type=dtype,
            item_ids=tuple(it.item_id for it in items),
            base_score=score.base_score,
            violations=score.violations,
            dropped=score.dropped,
            drop_reason=score.drop_reason,
            picked=(did, tuple(it.item_id for it in items)) in picked_keys,
            diversity_multiplier=picked_keys.get(
                (did, tuple(it.item_id for it in items)), 1.0
            ),
        )
        for did, dtype, items, score in all_scored
    )

    directions_with_picks = len({p[0] for p in picks})
    has_yaml_gap = bool(yaml_gaps)
    confidence = _compute_confidence(
        total_directions=total_directions,
        directions_skipped=directions_skipped,
        directions_with_picks=directions_with_picks,
        pick_count=len(picks),
        has_yaml_gap=has_yaml_gap,
    )

    soft_violations_total = sum(len(p[3].violations) for p in picks)
    overall_assessment = _assess_overall(
        len(picks), soft_violations_total, directions_with_picks
    )

    composer_result = ComposerResult(
        outfits=outfits,
        overall_assessment=overall_assessment,
        pool_unsuitable=(len(picks) == 0),
        raw_response=_render_audit_json(
            plan=plan,
            picks=picks,
            confidence=confidence,
            directions_skipped=directions_skipped,
            yaml_gaps=tuple(yaml_gaps),
        ),
        usage={"input_tokens": 0, "output_tokens": 0},
        attempt_count=1,
    )

    fallback_reason: str | None = None
    if has_yaml_gap:
        fallback_reason = "yaml_gap"
    elif len(picks) < MIN_PICKS:
        fallback_reason = "pool_too_sparse" if directions_skipped > 0 else "low_picks"
    elif confidence < CONFIDENCE_THRESHOLD:
        fallback_reason = "low_confidence"

    if fallback_reason is not None:
        return ComposerEngineResult(
            composer_result=None,
            confidence=confidence,
            fallback_reason=fallback_reason,
            yaml_gaps=tuple(yaml_gaps),
            provenance=provenance,
        )

    return ComposerEngineResult(
        composer_result=composer_result,
        confidence=confidence,
        fallback_reason=None,
        yaml_gaps=tuple(yaml_gaps),
        provenance=provenance,
    )


__all__ = [
    "ComposerEngineResult",
    "TupleProvenance",
    "MAX_POOL_PER_ROLE",
    "MAX_OUTFITS",
    "MIN_OUTFIT_SCORE",
    "MIN_PICKS",
    "CONFIDENCE_THRESHOLD",
    "compose_outfits",
]
