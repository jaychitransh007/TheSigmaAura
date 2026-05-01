"""Reranker — Phase 12B + ranking_bias tie-break + decision logging.

Deterministic step that prunes the assembler's candidate set down to the
top-N before the expensive try-on + visual evaluator stage runs. The base
sort key is ``assembly_score``; within a small score-tie window, an
optional ``ranking_bias`` parameter breaks ties by bias-specific signal
(formality / loud / comfort).

Pulled out as an explicit pipeline step (rather than an implicit
truncation inside ``OutfitEvaluator``) so that:

- the cost of the visual evaluator stage is bounded
- over-generation can swap in the next-best candidate when a try-on
  fails the quality gate (the orchestrator pulls from the over-generated
  pool, not from a re-run of the assembler)
- staging telemetry can attribute pruning decisions to a single,
  inspectable step

Calibration story (May 1, 2026): the reranker reads
``data/reranker_weights.json`` if present; otherwise it uses the unit
defaults. The skeleton ``ops/scripts/calibrate_reranker.py`` script will
emit that file once staging accumulates ≥200 labelled turns. Until then
the loader stays a no-op and the legacy assembly-score behaviour is
preserved.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Iterable, List, Optional

from ..schemas import OutfitCandidate

_log = logging.getLogger(__name__)


# Default counts for the Phase 12B pipeline:
#   FINAL = 3 outfits actually shipped to the user
#   POOL  = 5 candidates the assembler returns so the orchestrator has
#           headroom when a try-on fails the quality gate.
DEFAULT_FINAL_TOP_N = 3
DEFAULT_POOL_TOP_N = 5

# Tie-break window: candidates whose assembly_score sits within
# ``_TIE_WINDOW`` of each other are considered tied and re-ordered using
# the bias signal. Wider window = bias has more pull; narrower = score
# stays dominant. 0.05 keeps the bias as a tiebreaker, not a primary
# signal.
_TIE_WINDOW = 0.05

# Path to the optional learned-weights file. Resolved relative to the
# repo root (the agent runs with that as the cwd).
_WEIGHTS_FILE = Path("data/reranker_weights.json")

# Bias-specific attribute signals — same vocabulary as the assembler.
_FORMAL_HIGH_SIGNALS = {"high", "very_high", "strong", "very_strong"}
_FORMAL_OK_LEVELS = {"semi_formal", "formal", "ultra_formal"}
_LOUD_PATTERNS = {"floral", "geometric", "abstract", "stripe", "stripes", "check", "checks", "plaid", "graphic", "print", "embellished"}
_LOUD_SATURATIONS = {"high", "vivid", "bold", "saturated"}
_LOUD_EMBELLISHMENT = {"moderate", "heavy", "elaborate", "ornate", "statement"}
_RELAXED_FITS = {"relaxed", "loose", "oversized"}
_SOFT_DRAPES = {"flowing", "fluid", "soft", "drapey", "draped"}

# Formality level rank (higher = more formal).
_FORMAL_RANK: dict[str, int] = {
    "casual": 0,
    "smart_casual": 1,
    "business_casual": 2,
    "semi_formal": 3,
    "formal": 4,
    "ultra_formal": 5,
}


def _load_weights() -> dict[str, float]:
    """Read learned reranker weights if the file exists, else defaults.

    Defaults preserve current behaviour: only ``assembly_score`` matters
    in the primary sort. Future calibration runs replace the values
    without code changes.
    """
    defaults = {
        "w_assembly_score": 1.0,
        "w_archetype_proximity": 0.0,
        "w_weather_time_match": 0.0,
        "w_prior_dislike": 0.0,
    }
    if not _WEIGHTS_FILE.exists():
        return defaults
    try:
        with _WEIGHTS_FILE.open("r", encoding="utf-8") as fh:
            payload = json.load(fh)
        # Calibrate scripts emit either a flat dict or {"weights": {...}, "metadata": {...}}.
        body = payload.get("weights", payload) if isinstance(payload, dict) else {}
        if isinstance(body, dict):
            for key in defaults:
                if key in body:
                    defaults[key] = float(body[key])
            _log.info("Reranker: loaded weights from %s — %s", _WEIGHTS_FILE, defaults)
    except (OSError, ValueError, TypeError) as exc:
        _log.warning("Reranker: failed to read %s (%s); using defaults", _WEIGHTS_FILE, exc)
    return defaults


def _item_attr(item: dict, key: str) -> str:
    """Look up an attribute on an OutfitCandidate item dict, lower-cased."""
    if not isinstance(item, dict):
        return ""
    val = item.get(key) or item.get(key.lower()) or ""
    return str(val).strip().lower()


def _candidate_items(c: OutfitCandidate) -> List[dict]:
    return list(getattr(c, "items", []) or [])


def _avg_formality_rank(c: OutfitCandidate) -> float:
    items = _candidate_items(c)
    ranks = [
        _FORMAL_RANK.get(_item_attr(it, "formality_level"), 0)
        for it in items
        if _item_attr(it, "formality_level")
    ]
    if not ranks:
        return 0.0
    return sum(ranks) / len(ranks)


def _loud_count(c: OutfitCandidate) -> int:
    """How many items in this candidate carry expressive signals."""
    n = 0
    for it in _candidate_items(c):
        pat = _item_attr(it, "pattern_type")
        sat = _item_attr(it, "color_saturation")
        emb = _item_attr(it, "embellishment_level")
        if pat and pat != "solid" and pat in _LOUD_PATTERNS:
            n += 1
            continue
        if sat in _LOUD_SATURATIONS:
            n += 1
            continue
        if emb in _LOUD_EMBELLISHMENT:
            n += 1
    return n


def _relaxed_count(c: OutfitCandidate) -> int:
    n = 0
    for it in _candidate_items(c):
        fit = _item_attr(it, "fit_type")
        drape = _item_attr(it, "fabric_drape")
        if fit in _RELAXED_FITS and drape in _SOFT_DRAPES:
            n += 1
        elif fit in _RELAXED_FITS:
            # half-credit for relaxed without drape evidence
            n += 1
    return n


def _bias_tiebreaker(bias: str, c: OutfitCandidate) -> float:
    """Per-bias tiebreaker score. Higher value sorts EARLIER (preferred).

    Returns 0.0 for ``balanced`` so the round-robin order is preserved.
    """
    b = (bias or "balanced").strip().lower()
    if b == "formal_first":
        return _avg_formality_rank(c)
    if b == "expressive":
        return float(_loud_count(c))
    if b == "conservative":
        return -float(_loud_count(c))
    if b == "comfort_first":
        return float(_relaxed_count(c))
    return 0.0


class Reranker:
    """Score-ordered pruning of candidates before the visual evaluator.

    The reranker does not call any LLM or service. It accepts a list of
    ``OutfitCandidate`` and returns the top-N by ``assembly_score``,
    with stable tie-breaking on ``candidate_id`` so the same input
    produces the same output across reruns of the same turn.

    A ``bias`` parameter (one of: balanced, conservative, expressive,
    formal_first, comfort_first) supplies a tie-break signal applied
    only when two candidates' ``assembly_score`` differ by less than
    ``_TIE_WINDOW``. Outside that window, score still dominates.

    Optional ``decision_log`` parameter accepts a callable that receives
    a structured log payload (``{"turn_id": ..., "kept": [...], "dropped": [...]}``)
    so the orchestrator can persist reranker decisions to ``tool_traces``
    for later calibration.
    """

    def __init__(
        self,
        *,
        final_top_n: int = DEFAULT_FINAL_TOP_N,
        pool_top_n: int = DEFAULT_POOL_TOP_N,
        weights: Optional[dict[str, float]] = None,
    ) -> None:
        if final_top_n < 1:
            raise ValueError("final_top_n must be >= 1")
        if pool_top_n < final_top_n:
            raise ValueError("pool_top_n must be >= final_top_n")
        self.final_top_n = final_top_n
        self.pool_top_n = pool_top_n
        self.weights = weights if weights is not None else _load_weights()

    def rerank(
        self,
        candidates: Iterable[OutfitCandidate],
        *,
        limit: int | None = None,
        bias: str = "balanced",
        turn_id: str = "",
        decision_log: Any | None = None,
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

        ``bias`` shifts the ordering within each ``_TIE_WINDOW`` band so
        formal_first biases toward higher-formality outfits, expressive
        toward louder ones, conservative away from them, and comfort_first
        toward relaxed/flowing fits. Outside the tie window, score wins.

        ``decision_log``, when supplied, is called once with the kept and
        dropped candidate ids so the orchestrator can persist them to
        ``tool_traces`` for offline calibration.
        """
        cap = self.pool_top_n if limit is None else max(1, int(limit))
        candidate_list = list(candidates)

        # Primary order: assembly_score desc, then bias tiebreaker desc
        # (only meaningful within the _TIE_WINDOW band — we collapse the
        # score to a quantised value so candidates within the window
        # share a primary key and the tiebreaker can re-order them).
        def _primary_key(c: OutfitCandidate) -> tuple:
            score = float(getattr(c, "assembly_score", 0.0) or 0.0)
            # quantise so candidates within _TIE_WINDOW collapse to the
            # same bucket; bias tiebreaker then orders within it.
            bucket = round(score / _TIE_WINDOW) if _TIE_WINDOW else score
            return (
                -bucket,
                -_bias_tiebreaker(bias, c),
                -score,
                str(getattr(c, "candidate_id", "")),
            )

        ordered = sorted(candidate_list, key=_primary_key)

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
            "Reranker: input=%d → kept=%d (cap=%d, directions=%d, bias=%s, final_top_n=%d, pool_top_n=%d)",
            len(ordered),
            len(result),
            cap,
            len(seen_directions),
            bias,
            self.final_top_n,
            self.pool_top_n,
        )

        if decision_log is not None:
            try:
                kept_ids = [str(getattr(c, "candidate_id", "")) for c in result]
                dropped = [
                    {
                        "candidate_id": str(getattr(c, "candidate_id", "")),
                        "direction_id": str(getattr(c, "direction_id", "")),
                        "assembly_score": float(getattr(c, "assembly_score", 0.0) or 0.0),
                    }
                    for c in candidate_list
                    if str(getattr(c, "candidate_id", "")) not in picked_ids
                ]
                decision_log({
                    "turn_id": turn_id,
                    "bias": bias,
                    "input_count": len(candidate_list),
                    "kept_count": len(result),
                    "kept": [
                        {
                            "candidate_id": str(getattr(c, "candidate_id", "")),
                            "direction_id": str(getattr(c, "direction_id", "")),
                            "assembly_score": float(getattr(c, "assembly_score", 0.0) or 0.0),
                            "rank": i,
                        }
                        for i, c in enumerate(result)
                    ],
                    "dropped": dropped,
                    "weights": self.weights,
                })
            except Exception:  # noqa: BLE001 — logging must never break pipeline
                _log.exception("Reranker: decision_log callback raised; ignoring")

        return result
