"""Empty-intersection relaxation for the composition engine (Phase 4.7c).

Implements §3.2 + §4.3 of ``docs/composition_semantics.md``: when the
naive per-attribute reduction (4.7b) returns an empty ``final_flatters``,
walk a fixed relaxation sequence to recover.

Two phases, in order:

1. **Soft drop** — drop one soft contributor at a time, in ascending
   precedence (weakest first), recomputing after each drop. The
   default order matches spec §4.3 step 2a:

       time_of_day → archetype → risk_tolerance → style_goal → weather_color

   When a soft is dropped, both its ``flatters`` and ``avoid`` go (the
   whole contributor's opinion is removed). Peers like archetype and
   risk_tolerance are dropped one at a time, never together — each drop
   gets its own recompute pass.

2. **Hard widen** — if the soft phase still leaves the result empty,
   relax a hard source's *flatters* constraint while preserving its
   ``avoid``. Walk the hards in reverse precedence (weakest first):

       weather_fabric → formality_hint → occasion_signal
       → seasonal_color_group → frame_structure → body_shape

   The avoid invariant is intentionally non-relaxed across the entire
   widening sequence: widening relaxes "must be in this set" but never
   "must NOT be in this set", because avoid carries the strongest
   stylist signal.

3. **Omit** — if both phases exhaust without producing a non-empty
   ``final_flatters``, the attribute is reported as omitted. The
   composer's downstream layer is expected to leave it out of the
   query document.

The function returns the ``AttributeReduction`` that succeeded plus a
``RelaxationOutcome`` provenance record (which softs were dropped,
which hards were widened, terminal status). Both the reduction and the
outcome are captured in a frozen ``RelaxedReduction`` wrapper.

Pure function — no I/O, no clock, no randomness.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .reduction import (
    AttributeContribution,
    AttributeReduction,
    reduce_attribute,
)


# ─────────────────────────────────────────────────────────────────────────
# Spec-derived defaults (§3.3 hard/soft table + §4.3 relaxation order)
# ─────────────────────────────────────────────────────────────────────────


# Ascending precedence — weakest soft first. weather_color is the soft
# half of weather_context (color saturation guidance); it's classified
# soft per §3.3 with the corresponding STYLIST SIGN-OFF flag.
DEFAULT_SOFT_DROP_ORDER: tuple[str, ...] = (
    "time_of_day",
    "archetype",
    "risk_tolerance",
    "style_goal",
    "weather_color",
)


# Reverse hard precedence — widen the weakest hard first. weather_fabric
# is the hard half of weather_context (fabric weight + layering guidance).
# gender intentionally absent: per §3.3 it's a catalog-filter axis, not
# a flatters/avoid contributor — widening is meaningless.
DEFAULT_HARD_WIDEN_ORDER: tuple[str, ...] = (
    "weather_fabric",
    "formality_hint",
    "occasion_signal",
    "seasonal_color_group",
    "frame_structure",
    "body_shape",
)


# ─────────────────────────────────────────────────────────────────────────
# Inputs / outputs
# ─────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ClassifiedContribution:
    """An ``AttributeContribution`` plus the per-source metadata the
    relaxation layer needs (kind = which §3.3 row, tier = hard|soft).

    Multiple contributions may share a ``source_kind`` (e.g. on rare
    occasions when more than one entry from the same YAML applies).
    Drops act on all contributions of the named kind together — the
    spec's "drop the contributor" semantics is per-source-kind, not
    per-individual-row."""

    contribution: AttributeContribution
    source_kind: str
    tier: str  # "hard" | "soft"


@dataclass(frozen=True)
class RelaxationOutcome:
    """Provenance trail for one attribute's relaxation walk."""

    status: str
    """One of:
       - "clean"          — naive reduction was already non-empty
       - "soft_relaxed"   — succeeded after dropping ≥1 soft
       - "hard_widened"   — succeeded after widening ≥1 hard
       - "omitted"        — full failure; attribute should be dropped
    """

    dropped_softs: tuple[str, ...]
    """Source-kinds whose contributions were removed during the soft
    phase, in the order they were dropped."""

    widened_hards: tuple[str, ...]
    """Source-kinds whose ``flatters`` constraint was zeroed during the
    hard-widen phase. Their ``avoid`` opinions remained in force."""


@dataclass(frozen=True)
class RelaxedReduction:
    """The final reduction plus provenance. Always carries a non-None
    ``reduction``; on ``omitted`` status, the reduction's
    ``final_flatters`` will be empty and downstream code should skip
    the attribute."""

    reduction: AttributeReduction
    outcome: RelaxationOutcome


# ─────────────────────────────────────────────────────────────────────────
# Implementation
# ─────────────────────────────────────────────────────────────────────────


def _reduce_unwrapped(
    attribute: str, classified: Sequence[ClassifiedContribution]
) -> AttributeReduction:
    return reduce_attribute(
        attribute, [c.contribution for c in classified]
    )


def _drop_kind(
    classified: Sequence[ClassifiedContribution], kind: str
) -> list[ClassifiedContribution]:
    """Return ``classified`` minus every contribution whose source_kind
    matches ``kind``. Used by the soft-drop phase."""
    return [c for c in classified if c.source_kind != kind]


def _widen_kind(
    classified: Sequence[ClassifiedContribution], kind: str
) -> list[ClassifiedContribution]:
    """Return ``classified`` with every matching contribution's
    ``flatters`` zeroed but ``avoid`` preserved. Used by the
    hard-widen phase."""
    out: list[ClassifiedContribution] = []
    for c in classified:
        if c.source_kind == kind:
            zeroed = AttributeContribution(
                source=c.contribution.source,
                flatters=(),
                avoid=c.contribution.avoid,
            )
            out.append(
                ClassifiedContribution(
                    contribution=zeroed,
                    source_kind=c.source_kind,
                    tier=c.tier,
                )
            )
        else:
            out.append(c)
    return out


def reduce_with_relaxation(
    attribute: str,
    contributions: Sequence[ClassifiedContribution],
    *,
    soft_drop_order: Sequence[str] = DEFAULT_SOFT_DROP_ORDER,
    hard_widen_order: Sequence[str] = DEFAULT_HARD_WIDEN_ORDER,
) -> RelaxedReduction:
    """Reduce ``attribute`` across ``contributions`` with empty-intersection
    relaxation per spec §3.2.

    Returns a ``RelaxedReduction`` whose ``outcome.status`` reports which
    phase produced the result. The relaxation is total: it always
    returns a result, with ``omitted`` status when every relaxation step
    failed to produce a non-empty ``final_flatters``.
    """
    base = _reduce_unwrapped(attribute, contributions)
    if base.final_flatters:
        return RelaxedReduction(
            reduction=base,
            outcome=RelaxationOutcome(
                status="clean",
                dropped_softs=(),
                widened_hards=(),
            ),
        )

    # Phase 1 — soft drops, accumulating across the walk.
    current = list(contributions)
    dropped: list[str] = []
    for kind in soft_drop_order:
        next_state = _drop_kind(current, kind)
        if len(next_state) == len(current):
            # Nothing of this kind to drop — skip without recording it.
            continue
        current = next_state
        dropped.append(kind)
        attempt = _reduce_unwrapped(attribute, current)
        if attempt.final_flatters:
            return RelaxedReduction(
                reduction=attempt,
                outcome=RelaxationOutcome(
                    status="soft_relaxed",
                    dropped_softs=tuple(dropped),
                    widened_hards=(),
                ),
            )

    # Phase 2 — hard widens, accumulating on top of the post-soft state.
    widened: list[str] = []
    for kind in hard_widen_order:
        next_state = _widen_kind(current, kind)
        # Skip kinds with no contributions — _widen_kind is a no-op then.
        if next_state == current:
            continue
        current = next_state
        widened.append(kind)
        attempt = _reduce_unwrapped(attribute, current)
        if attempt.final_flatters:
            return RelaxedReduction(
                reduction=attempt,
                outcome=RelaxationOutcome(
                    status="hard_widened",
                    dropped_softs=tuple(dropped),
                    widened_hards=tuple(widened),
                ),
            )

    # Both phases failed — attribute is omitted.
    final = _reduce_unwrapped(attribute, current)
    return RelaxedReduction(
        reduction=final,
        outcome=RelaxationOutcome(
            status="omitted",
            dropped_softs=tuple(dropped),
            widened_hards=tuple(widened),
        ),
    )
