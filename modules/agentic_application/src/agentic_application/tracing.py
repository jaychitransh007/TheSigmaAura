"""TurnTraceBuilder — lightweight per-turn trace accumulator.

Instantiated at the top of ``process_turn`` and populated incrementally
as the orchestrator walks through the pipeline stages. At the end of
every handler path the orchestrator calls ``build()`` which returns the
full trace dict ready for ``repo.insert_turn_trace(**trace)``.

The builder is a plain Python object with no I/O — it only accumulates
dicts in memory. The single DB write happens at persist time, so the
latency overhead is effectively zero during the turn itself.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Dict, List, Optional


class TurnTraceBuilder:
    """Accumulates the per-turn trace during ``process_turn``."""

    def __init__(
        self,
        *,
        turn_id: str,
        conversation_id: str,
        user_id: str,
        user_message: str = "",
        has_image: bool = False,
    ) -> None:
        self._turn_id = turn_id
        self._conversation_id = conversation_id
        self._user_id = user_id
        self._user_message = user_message
        self._has_image = has_image
        self._start_time = time.monotonic()

        # Populated incrementally as the orchestrator progresses.
        self._image_classification: Dict[str, Any] = {}
        self._primary_intent: str = ""
        self._intent_confidence: float = 0.0
        self._action: str = ""
        self._reason_codes: List[str] = []
        self._profile_snapshot: Dict[str, Any] = {}
        self._query_entities: Dict[str, Any] = {}
        self._steps: List[Dict[str, Any]] = []
        self._evaluation: Dict[str, Any] = {}
        # Aggregate cost across all LLM / image-gen / embedding calls
        # in this turn. Surfaced as `total_cost_usd` on build() so a
        # consumer can see the per-turn dollar figure without summing
        # `model_call_logs` themselves. May 3 2026 PR — addresses the
        # observability gap surfaced when the user asked "what's this
        # turn costing me end to end".
        self._total_cost_usd: float = 0.0
        # PR #71 (May 5 2026): tryon_render and visual_eval batches call
        # add_model_cost_from_row from a ThreadPoolExecutor. Without this
        # lock, two non-zero cost increments can interleave and lose an
        # update (Python's `+=` on a float is not atomic — bytecode is
        # LOAD/LOAD/ADD/STORE). Cost is currently 0 for cache hits so
        # the bug is latent, but the cold-render path has been writing
        # non-zero costs from worker threads since R3. Lock is held
        # only across the integer add — negligible contention.
        self._cost_lock = threading.Lock()

    # ── Step accumulation ────────────────────────────────────────────

    def add_step(
        self,
        step: str,
        *,
        model: Optional[str] = None,
        input_summary: str = "",
        output_summary: str = "",
        latency_ms: Optional[int] = None,
        status: str = "ok",
        error: Optional[str] = None,
    ) -> None:
        """Append one pipeline step to the trace."""
        entry: Dict[str, Any] = {
            "step": step,
            "model": model,
            "input_summary": input_summary,
            "output_summary": output_summary,
            "latency_ms": latency_ms,
            "status": status,
        }
        if error:
            entry["error"] = error
        self._steps.append(entry)

    # ── Field setters ────────────────────────────────────────────────

    def set_image_classification(
        self,
        *,
        is_garment_photo: Optional[bool] = None,
        garment_present_confidence: Optional[float] = None,
    ) -> None:
        self._image_classification = {
            "is_garment_photo": is_garment_photo,
            "garment_present_confidence": garment_present_confidence,
        }

    def set_intent(
        self,
        *,
        primary_intent: str,
        intent_confidence: float = 0.0,
        action: str = "",
        reason_codes: Optional[List[str]] = None,
    ) -> None:
        self._primary_intent = primary_intent
        self._intent_confidence = intent_confidence
        self._action = action
        self._reason_codes = list(reason_codes or [])

    def set_context(
        self,
        *,
        profile_snapshot: Optional[Dict[str, Any]] = None,
        query_entities: Optional[Dict[str, Any]] = None,
    ) -> None:
        if profile_snapshot is not None:
            self._profile_snapshot = profile_snapshot
        if query_entities is not None:
            self._query_entities = query_entities

    def set_evaluation(self, evaluation: Dict[str, Any]) -> None:
        self._evaluation = evaluation

    def add_cost(self, amount: Optional[float]) -> None:
        """Accumulate a single LLM / image / embedding call's cost into
        the per-turn total. Tolerates None / 0 / strings — anything
        non-numeric is treated as zero. Thread-safe: held under
        ``self._cost_lock`` because callers run inside the orchestrator's
        ThreadPoolExecutor (try-on render, parallel visual evals)."""
        if amount is None:
            return
        try:
            value = float(amount)
        except (TypeError, ValueError):
            return
        with self._cost_lock:
            self._total_cost_usd += value

    def add_model_cost_from_row(self, row: Optional[Dict[str, Any]]) -> None:
        """Convenience: extract ``estimated_cost_usd`` from a
        model_call_logs row and accumulate it. Used at every
        ``repo.log_model_call(...)`` callsite so the per-turn cost
        rollup mirrors the sum of all model_call_logs rows for the
        turn."""
        if not isinstance(row, dict):
            return
        self.add_cost(row.get("estimated_cost_usd"))

    # ── Build ────────────────────────────────────────────────────────

    def build(self) -> Dict[str, Any]:
        """Return the full trace dict ready for ``repo.insert_turn_trace(**trace)``."""
        total_ms = int((time.monotonic() - self._start_time) * 1000)
        return {
            "turn_id": self._turn_id,
            "conversation_id": self._conversation_id,
            "user_id": self._user_id,
            "user_message": self._user_message,
            "has_image": self._has_image,
            "image_classification": self._image_classification,
            "primary_intent": self._primary_intent,
            "intent_confidence": self._intent_confidence,
            "action": self._action,
            "reason_codes": self._reason_codes,
            "profile_snapshot": self._profile_snapshot,
            "query_entities": self._query_entities,
            "steps": self._steps,
            # Fold total_cost_usd into the existing evaluation JSONB so
            # no schema migration is needed. Rounded to 6 decimals —
            # sub-millicent precision is enough. Skipped entirely when
            # zero so consumers can distinguish "no cost" from "$0.00".
            "evaluation": (
                {**self._evaluation, "total_cost_usd": round(self._total_cost_usd, 6)}
                if self._total_cost_usd > 0
                else self._evaluation
            ),
            "total_latency_ms": total_ms,
        }
