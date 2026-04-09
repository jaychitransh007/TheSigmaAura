"""Reranker — Phase 12B.

Deterministic step that prunes the assembler's candidate set down to the
top-N before the expensive try-on + visual evaluator stage runs. Today
this is a simple ``assembly_score`` sort with a configurable cap. Phase
12E will calibrate this with prior-turn feedback signals, weather/time
match, and user style preference proximity once staging telemetry exists.

Pulled out as an explicit pipeline step (rather than an implicit
truncation inside ``OutfitEvaluator``) so that:

- the cost of the visual evaluator stage is bounded
- over-generation can swap in the next-best candidate when a try-on
  fails the quality gate (the orchestrator pulls from the over-generated
  pool, not from a re-run of the assembler)
- staging telemetry can attribute pruning decisions to a single,
  inspectable step
"""

from __future__ import annotations

import logging
from typing import Iterable, List

from ..schemas import OutfitCandidate

_log = logging.getLogger(__name__)


# Default counts for the Phase 12B pipeline:
#   FINAL = 3 outfits actually shipped to the user
#   POOL  = 5 candidates the assembler returns so the orchestrator has
#           headroom when a try-on fails the quality gate.
DEFAULT_FINAL_TOP_N = 3
DEFAULT_POOL_TOP_N = 5


class Reranker:
    """Score-ordered pruning of candidates before the visual evaluator.

    The reranker does not call any LLM or service. It accepts a list of
    ``OutfitCandidate`` and returns the top-N by ``assembly_score``,
    with stable tie-breaking on ``candidate_id`` so the same input
    produces the same output across reruns of the same turn.
    """

    def __init__(
        self,
        *,
        final_top_n: int = DEFAULT_FINAL_TOP_N,
        pool_top_n: int = DEFAULT_POOL_TOP_N,
    ) -> None:
        if final_top_n < 1:
            raise ValueError("final_top_n must be >= 1")
        if pool_top_n < final_top_n:
            raise ValueError("pool_top_n must be >= final_top_n")
        self.final_top_n = final_top_n
        self.pool_top_n = pool_top_n

    def rerank(
        self,
        candidates: Iterable[OutfitCandidate],
        *,
        limit: int | None = None,
    ) -> List[OutfitCandidate]:
        """Return candidates sorted by assembly_score (desc), capped at ``limit``.

        ``limit`` defaults to ``pool_top_n`` so the orchestrator has the
        full over-generation pool to draw from when handling try-on
        quality-gate failures. Pass ``final_top_n`` for direct top-N use.

        Direction diversity: when multiple directions produced candidates,
        we round-robin one candidate per direction (highest score from each)
        before filling remaining slots globally by score. This guarantees
        the user sees variety across the architect's different outfit
        concepts rather than N copies from whichever direction scored best.
        """
        cap = self.pool_top_n if limit is None else max(1, int(limit))
        ordered = sorted(
            list(candidates),
            key=lambda c: (
                -float(getattr(c, "assembly_score", 0.0) or 0.0),
                str(getattr(c, "candidate_id", "")),
            ),
        )

        # --- Direction-aware round-robin ---
        # 1. Pick the top candidate from each direction.
        picked_ids: set[str] = set()
        result: List[OutfitCandidate] = []
        seen_directions: set[str] = set()
        for c in ordered:
            d = getattr(c, "direction_id", "")
            if d and d not in seen_directions:
                seen_directions.add(d)
                result.append(c)
                picked_ids.add(str(getattr(c, "candidate_id", "")))
                if len(result) >= cap:
                    break

        # 2. Fill remaining slots globally by score.
        if len(result) < cap:
            for c in ordered:
                cid = str(getattr(c, "candidate_id", ""))
                if cid not in picked_ids:
                    result.append(c)
                    picked_ids.add(cid)
                    if len(result) >= cap:
                        break

        _log.info(
            "Reranker: input=%d → kept=%d (cap=%d, directions=%d, final_top_n=%d, pool_top_n=%d)",
            len(ordered),
            len(result),
            cap,
            len(seen_directions),
            self.final_top_n,
            self.pool_top_n,
        )
        return result
