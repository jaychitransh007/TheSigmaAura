"""Per-attribute reduction for the composition engine (Phase 4.7b).

Implements §3.1 of ``docs/composition_semantics.md``:

    flatters_set(attr) = ⋂ over sources S that have an opinion  flatters(S, attr)
    avoid_set(attr)    = ⋃ over sources S                       avoid(S, attr)
    final(attr)        = flatters_set(attr) \\ avoid_set(attr)

Three semantic notes baked in:

1. **Sources with an empty/absent ``flatters`` list don't constrain the
   intersection.** The intersect is over opinionated sources only —
   otherwise a single source with no opinion on an attribute would force
   the result empty. ``avoid`` lists from those same sources still count
   toward the union.

2. **Position 0 is strongest.** The intersect preserves the ordering of
   the FIRST opinionated source. Later sources can only filter out values,
   never reorder. This matches the spec §5 reading of YAML ``flatters:``
   lists as best-first.

3. **Avoid wins over flatters.** Final = flatters minus avoid, applied
   after the intersect/union pass.

Pure function. No I/O, no clock, no randomness. Output is structurally
deterministic for any sequence of inputs that compares equal.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class AttributeContribution:
    """One source's opinion on a single garment attribute.

    ``source`` is a label suitable for provenance logs — typically
    ``"<source_kind>:<value>"`` (e.g. ``"body_shape:Hourglass"``,
    ``"archetype:modern_professional"``). Identity is by tuple equality on
    all three fields, so two contributions from the same source with the
    same values are interchangeable."""

    source: str
    flatters: tuple[str, ...]
    avoid: tuple[str, ...]


@dataclass(frozen=True)
class AttributeReduction:
    """The reduced result for one attribute across N sources.

    ``final_flatters`` is the intersect-then-subtract-avoid result, with
    position-0-strongest ordering preserved from the first opinionated
    source. ``contributing_sources`` lists the sources whose flatters
    opinions actually shaped the intersect (sources that contributed only
    to ``avoid`` are listed separately). The pre-avoid intersect is
    surfaced in ``intersect_flatters`` so the relaxation layer (4.7c) can
    distinguish empty-via-intersect from empty-via-avoid-removal."""

    attribute: str
    final_flatters: tuple[str, ...]
    final_avoid: tuple[str, ...]
    intersect_flatters: tuple[str, ...]
    contributing_sources: tuple[str, ...]
    avoid_only_sources: tuple[str, ...]


def _ordered_union(*lists: Sequence[str]) -> tuple[str, ...]:
    """Order-preserving union: first list's order wins, later lists append
    any values not already present."""
    seen: set[str] = set()
    out: list[str] = []
    for lst in lists:
        for v in lst:
            if v not in seen:
                seen.add(v)
                out.append(v)
    return tuple(out)


def _ordered_intersect(first: Sequence[str], rest: Sequence[Sequence[str]]) -> tuple[str, ...]:
    """Intersect ``first`` with each list in ``rest``, preserving
    ``first``'s ordering. Values must appear in EVERY rest list to
    survive."""
    if not rest:
        # Dedup first while preserving order — the empty-rest case is the
        # single-opinionated-source path.
        seen: set[str] = set()
        out: list[str] = []
        for v in first:
            if v not in seen:
                seen.add(v)
                out.append(v)
        return tuple(out)
    common = set(rest[0])
    for r in rest[1:]:
        common &= set(r)
    seen2: set[str] = set()
    out2: list[str] = []
    for v in first:
        if v in common and v not in seen2:
            seen2.add(v)
            out2.append(v)
    return tuple(out2)


def reduce_attribute(
    attribute: str,
    contributions: Sequence[AttributeContribution],
) -> AttributeReduction:
    """Reduce one attribute across N source contributions.

    See module docstring for the algorithm. The function is total —
    empty contributions yields an empty reduction; a single opinionated
    source yields its dedup'd flatters minus the union of all avoids.
    """
    opinionated: list[AttributeContribution] = [
        c for c in contributions if c.flatters
    ]
    avoid_only: list[AttributeContribution] = [
        c for c in contributions if not c.flatters and c.avoid
    ]

    if not opinionated:
        intersect_flatters: tuple[str, ...] = ()
    else:
        first = opinionated[0].flatters
        rest = [c.flatters for c in opinionated[1:]]
        intersect_flatters = _ordered_intersect(first, rest)

    avoid_set = _ordered_union(*[c.avoid for c in contributions])
    avoid_lookup = set(avoid_set)
    final_flatters = tuple(v for v in intersect_flatters if v not in avoid_lookup)

    return AttributeReduction(
        attribute=attribute,
        final_flatters=final_flatters,
        final_avoid=avoid_set,
        intersect_flatters=intersect_flatters,
        contributing_sources=tuple(c.source for c in opinionated),
        avoid_only_sources=tuple(c.source for c in avoid_only),
    )
