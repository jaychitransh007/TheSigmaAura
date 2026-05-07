"""Quality-validator primitives for the composition engine (Phase 4.8).

Pure-function comparators that score how closely an engine-emitted
``RecommendationPlan`` matches an LLM-emitted one. Used by
``ops/scripts/composition_quality_eval.py`` to produce a per-cell
divergence report against the Phase 4.6 eval set.

This module is intentionally small — the heavy lifting (running the
LLM architect against an eval JSONL) lives in the ops script. Keeping
the comparison primitives here makes them unit-testable without an
OpenAI dependency.

Comparison axes (per ``RecommendationPlan``):

- ``direction_type`` — binary match across paired directions
- ``hard_filters``  — Jaccard on the (key, value) item set per query
- ``query_document`` — Jaccard on whitespace-split tokens

Plans are paired by ``direction_id`` (A/B/C). Within a paired
``DirectionSpec`` the queries are matched by ``role`` (top/bottom/
outerwear/complete) — query_id is engine-derived and shouldn't
penalize the comparison.
"""
from __future__ import annotations

import re
import statistics
from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

from ..schemas import (
    ComposedOutfit,
    ComposerResult,
    DirectionSpec,
    QuerySpec,
    RecommendationPlan,
)


# ─────────────────────────────────────────────────────────────────────────
# Tokenization
# ─────────────────────────────────────────────────────────────────────────


_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")


def _tokens(text: str) -> set[str]:
    """Lowercase tokenise. The query_document is structured but not
    JSON; whitespace + punctuation split is enough for Jaccard."""
    return set(t.lower() for t in _TOKEN_RE.findall(text or ""))


def _filter_items(filters: Mapping[str, object] | None) -> set[tuple[str, str]]:
    """Flatten a hard_filters dict to a set of (key, value) pairs.
    Multi-value filter values (list) expand to one pair per element."""
    items: set[tuple[str, str]] = set()
    if not filters:
        return items
    for key, value in filters.items():
        if isinstance(value, (list, tuple)):
            for v in value:
                items.add((str(key), str(v)))
        else:
            items.add((str(key), str(value)))
    return items


def _jaccard(a: set, b: set) -> float:
    """Standard Jaccard index. Empty/empty → 1.0 (perfectly matching
    absence). Empty/non-empty → 0.0 (handled via the union check)."""
    union = a | b
    if not union:
        return 1.0
    return len(a & b) / len(union)


# ─────────────────────────────────────────────────────────────────────────
# Comparison shapes
# ─────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class QueryComparison:
    """Per-role match between engine + LLM queries."""

    role: str
    query_document_jaccard: float
    hard_filters_jaccard: float


@dataclass(frozen=True)
class DirectionComparison:
    """Per-direction match between engine + LLM DirectionSpecs."""

    direction_id: str
    direction_type_match: bool
    label_jaccard: float
    queries: tuple[QueryComparison, ...]


@dataclass(frozen=True)
class PlanComparison:
    """Per-plan match. ``coverage`` reports the fraction of LLM
    directions that the engine also emitted (paired by direction_id).
    ``aggregate_query_document_jaccard`` is the macro-mean across all
    paired queries — the most useful single number for ops dashboards."""

    coverage: float
    direction_type_match_rate: float
    aggregate_query_document_jaccard: float
    aggregate_hard_filters_jaccard: float
    directions: tuple[DirectionComparison, ...]
    unmatched_direction_ids: tuple[str, ...]


# ─────────────────────────────────────────────────────────────────────────
# Comparators
# ─────────────────────────────────────────────────────────────────────────


def compare_queries(engine: QuerySpec, llm: QuerySpec) -> QueryComparison:
    return QueryComparison(
        role=engine.role,
        query_document_jaccard=_jaccard(
            _tokens(engine.query_document), _tokens(llm.query_document)
        ),
        hard_filters_jaccard=_jaccard(
            _filter_items(engine.hard_filters),
            _filter_items(llm.hard_filters),
        ),
    )


def _index_by_role(queries: Iterable[QuerySpec]) -> dict[str, QuerySpec]:
    out: dict[str, QuerySpec] = {}
    for q in queries:
        out[q.role] = q
    return out


def compare_directions(engine: DirectionSpec, llm: DirectionSpec) -> DirectionComparison:
    engine_by_role = _index_by_role(engine.queries)
    llm_by_role = _index_by_role(llm.queries)
    common_roles = sorted(set(engine_by_role) & set(llm_by_role))
    queries: list[QueryComparison] = []
    for role in common_roles:
        queries.append(
            compare_queries(engine_by_role[role], llm_by_role[role])
        )
    return DirectionComparison(
        direction_id=engine.direction_id,
        direction_type_match=engine.direction_type == llm.direction_type,
        label_jaccard=_jaccard(_tokens(engine.label), _tokens(llm.label)),
        queries=tuple(queries),
    )


def _index_by_direction_id(plan: RecommendationPlan) -> dict[str, DirectionSpec]:
    return {d.direction_id: d for d in plan.directions}


def compare_plans(
    engine: RecommendationPlan, llm: RecommendationPlan
) -> PlanComparison:
    """Pair directions by direction_id and aggregate the per-direction
    metrics into one envelope per plan.

    Coverage is the count of LLM direction_ids the engine also emitted,
    over the LLM's total. Engine-only ids (rare — the engine usually
    emits a subset) don't penalize coverage but show up in
    unmatched_direction_ids for the ops report."""
    engine_by_id = _index_by_direction_id(engine)
    llm_by_id = _index_by_direction_id(llm)
    common_ids = sorted(set(engine_by_id) & set(llm_by_id))

    direction_comparisons: list[DirectionComparison] = []
    qd_scores: list[float] = []
    hf_scores: list[float] = []
    type_matches = 0
    for did in common_ids:
        cmp = compare_directions(engine_by_id[did], llm_by_id[did])
        direction_comparisons.append(cmp)
        if cmp.direction_type_match:
            type_matches += 1
        for q in cmp.queries:
            qd_scores.append(q.query_document_jaccard)
            hf_scores.append(q.hard_filters_jaccard)

    coverage = (
        len(common_ids) / len(llm_by_id) if llm_by_id else 0.0
    )
    type_match_rate = (
        type_matches / len(common_ids) if common_ids else 0.0
    )
    qd_mean = sum(qd_scores) / len(qd_scores) if qd_scores else 0.0
    hf_mean = sum(hf_scores) / len(hf_scores) if hf_scores else 0.0

    unmatched = tuple(sorted(set(llm_by_id) - set(engine_by_id)))

    return PlanComparison(
        coverage=coverage,
        direction_type_match_rate=type_match_rate,
        aggregate_query_document_jaccard=qd_mean,
        aggregate_hard_filters_jaccard=hf_mean,
        directions=tuple(direction_comparisons),
        unmatched_direction_ids=unmatched,
    )


# ─────────────────────────────────────────────────────────────────────────
# Aggregation across an eval set
# ─────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class EvalSummary:
    """Aggregate comparison stats across N eval cells.

    ``cell_count`` is the number of PlanComparison rows reduced. The
    fallback / engine-used breakdown lives in the ops driver — it has
    the cell metadata (status, reject_reason) ``aggregate_eval`` does
    not see. This dataclass only reduces the comparison numbers."""

    cell_count: int
    median_query_document_jaccard: float
    median_hard_filters_jaccard: float
    direction_type_match_rate: float


def aggregate_eval(comparisons: Sequence[PlanComparison]) -> EvalSummary:
    """Reduce a sequence of per-cell comparisons to one summary row.

    Median (not mean) on the Jaccard metrics: a few catastrophic cells
    shouldn't dominate the headline number. Mean on the binary match
    rate (the natural definition: pct of cells where the engine
    matched)."""
    if not comparisons:
        return EvalSummary(
            cell_count=0,
            median_query_document_jaccard=0.0,
            median_hard_filters_jaccard=0.0,
            direction_type_match_rate=0.0,
        )
    type_match = sum(c.direction_type_match_rate for c in comparisons) / len(
        comparisons
    )
    return EvalSummary(
        cell_count=len(comparisons),
        median_query_document_jaccard=statistics.median(
            c.aggregate_query_document_jaccard for c in comparisons
        ),
        median_hard_filters_jaccard=statistics.median(
            c.aggregate_hard_filters_jaccard for c in comparisons
        ),
        direction_type_match_rate=type_match,
    )


# ─────────────────────────────────────────────────────────────────────────
# Composer comparators (Phase 5e)
# ─────────────────────────────────────────────────────────────────────────
#
# Engine output is ``ComposerResult`` (List[ComposedOutfit] + assessment +
# pool_unsuitable). The comparison axes:
#
# - ``item_ids`` Jaccard per direction — set intersection over union of
#   item_ids picked. Higher = engine + LLM picked overlapping items.
# - ``direction_type`` match per direction — binary.
# - ``overall_assessment`` match — binary.
# - ``outfit_count`` per direction — match rate.
#
# Outfits are paired by ``direction_id`` first (A/B/C); within a
# direction, item_ids are compared as flat sets across all outfits in
# that direction (the LLM might emit 2 outfits for direction A and the
# engine 3 — meaningful overlap is at the item-ID set level, not at the
# composer_id level which is engine/LLM-derived and unstable).


@dataclass(frozen=True)
class ComposerDirectionComparison:
    """Per-direction match between engine + LLM outfits."""

    direction_id: str
    direction_type_match: bool
    item_ids_jaccard: float
    engine_outfit_count: int
    llm_outfit_count: int


@dataclass(frozen=True)
class ComposerComparison:
    """Per-turn match between engine + LLM ComposerResults."""

    coverage: float                                   # fraction of LLM direction_ids the engine also covered
    direction_type_match_rate: float                  # mean across paired directions
    aggregate_item_ids_jaccard: float                 # macro-mean across paired directions
    overall_assessment_match: bool
    pool_unsuitable_match: bool
    engine_outfit_count_total: int
    llm_outfit_count_total: int
    directions: tuple[ComposerDirectionComparison, ...]
    unmatched_direction_ids: tuple[str, ...]          # in LLM but not engine


def _outfits_by_direction(outfits: Iterable[ComposedOutfit]) -> dict[str, list[ComposedOutfit]]:
    by_dir: dict[str, list[ComposedOutfit]] = {}
    for o in outfits:
        by_dir.setdefault(o.direction_id, []).append(o)
    return by_dir


def _flatten_item_ids(outfits: Iterable[ComposedOutfit]) -> set[str]:
    out: set[str] = set()
    for o in outfits:
        for item_id in (o.item_ids or ()):
            if item_id:
                out.add(str(item_id))
    return out


def _direction_type_of(outfits: Sequence[ComposedOutfit]) -> str:
    """Direction_type is per-direction-not-per-outfit. Use the first
    outfit in the direction; engine + LLM both populate this consistently
    so any outfit in the bucket reports the same value."""
    if not outfits:
        return ""
    return outfits[0].direction_type or ""


def compare_composer_outputs(
    engine: ComposerResult, llm: ComposerResult
) -> ComposerComparison:
    """Pair outfits by direction_id, aggregate per-direction metrics
    into one envelope per turn.

    ``coverage`` is the count of LLM direction_ids the engine also
    emitted, over the LLM's total. Engine-only direction_ids (rare —
    the engine never invents directions; it only picks within them)
    don't penalize coverage and aren't surfaced separately.
    """
    engine_by_dir = _outfits_by_direction(engine.outfits or [])
    llm_by_dir = _outfits_by_direction(llm.outfits or [])
    common_ids = sorted(set(engine_by_dir) & set(llm_by_dir))

    direction_comparisons: list[ComposerDirectionComparison] = []
    item_jaccards: list[float] = []
    type_matches = 0
    for did in common_ids:
        engine_outfits = engine_by_dir[did]
        llm_outfits = llm_by_dir[did]
        ej = _jaccard(_flatten_item_ids(engine_outfits), _flatten_item_ids(llm_outfits))
        type_match = _direction_type_of(engine_outfits) == _direction_type_of(llm_outfits)
        if type_match:
            type_matches += 1
        item_jaccards.append(ej)
        direction_comparisons.append(
            ComposerDirectionComparison(
                direction_id=did,
                direction_type_match=type_match,
                item_ids_jaccard=ej,
                engine_outfit_count=len(engine_outfits),
                llm_outfit_count=len(llm_outfits),
            )
        )

    coverage = (
        len(common_ids) / len(llm_by_dir) if llm_by_dir else 0.0
    )
    type_match_rate = (
        type_matches / len(common_ids) if common_ids else 0.0
    )
    item_jaccard_mean = (
        sum(item_jaccards) / len(item_jaccards) if item_jaccards else 0.0
    )
    unmatched = tuple(sorted(set(llm_by_dir) - set(engine_by_dir)))

    return ComposerComparison(
        coverage=coverage,
        direction_type_match_rate=type_match_rate,
        aggregate_item_ids_jaccard=item_jaccard_mean,
        overall_assessment_match=engine.overall_assessment == llm.overall_assessment,
        pool_unsuitable_match=engine.pool_unsuitable == llm.pool_unsuitable,
        engine_outfit_count_total=len(engine.outfits or []),
        llm_outfit_count_total=len(llm.outfits or []),
        directions=tuple(direction_comparisons),
        unmatched_direction_ids=unmatched,
    )


@dataclass(frozen=True)
class ComposerEvalSummary:
    """Aggregate composer comparison stats across N eval cells."""

    cell_count: int
    median_item_ids_jaccard: float
    direction_type_match_rate: float
    overall_assessment_match_rate: float


def aggregate_composer_eval(
    comparisons: Sequence[ComposerComparison],
) -> ComposerEvalSummary:
    """Reduce N composer comparisons to one summary row. Same median +
    binary-rate model as ``aggregate_eval`` for the architect."""
    if not comparisons:
        return ComposerEvalSummary(
            cell_count=0,
            median_item_ids_jaccard=0.0,
            direction_type_match_rate=0.0,
            overall_assessment_match_rate=0.0,
        )
    return ComposerEvalSummary(
        cell_count=len(comparisons),
        median_item_ids_jaccard=statistics.median(
            c.aggregate_item_ids_jaccard for c in comparisons
        ),
        direction_type_match_rate=sum(
            c.direction_type_match_rate for c in comparisons
        ) / len(comparisons),
        overall_assessment_match_rate=sum(
            1 for c in comparisons if c.overall_assessment_match
        ) / len(comparisons),
    )
