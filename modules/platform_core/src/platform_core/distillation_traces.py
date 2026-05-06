"""Context manager for distillation-ready stage tracing.

Wraps each LLM stage call in the orchestrator and records the full input,
full output, and latency to the ``distillation_traces`` table. Coexists
with ``model_call_logs`` (which stores summaries for analytics).

Why a separate path: ``model_call_logs.request_json`` captures hand-built
summaries (e.g. the architect logs only ``{gender, occasion, message}`` —
not the 14K-token actual prompt). Distillation needs the full payloads,
so this writer captures them at the orchestrator call site where the full
context is in scope.

Trace writes are best-effort: an exception during the write is logged
and swallowed so a database hiccup never fails a user-facing turn.
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Dict, Iterator, Optional

_log = logging.getLogger(__name__)


@dataclass
class StageTraceContext:
    """Yielded inside the with-block. The caller sets ``full_output`` after
    the LLM call returns; ``status`` and ``error_message`` are managed by
    the context manager."""
    full_input: Dict[str, Any]
    full_output: Optional[Dict[str, Any]] = None
    status: str = "ok"
    error_message: str = ""


def to_jsonable(obj: Any) -> Any:
    """Convert pydantic models, dicts, and lists to a JSON-serializable shape.

    Used at orchestrator call sites so we can wrap a stage with one uniform
    pattern regardless of whether the input/output is a pydantic BaseModel,
    a plain dict, or a list of either. Falls through unchanged for
    primitives (int, str, bool, None)."""
    if obj is None:
        return None
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if isinstance(obj, dict):
        return {k: to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_jsonable(item) for item in obj]
    return obj


def hash_input(full_input: Dict[str, Any]) -> str:
    """SHA-256 of the canonicalized input, truncated to 32 hex chars.

    Sort keys + ``default=str`` so the hash is stable across dict orderings
    and tolerant of non-JSON-native types (datetime, UUID) that pydantic
    model_dump() may emit.
    """
    canonical = json.dumps(full_input, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]


@contextmanager
def record_stage_trace(
    *,
    repo: Any,
    turn_id: str,
    conversation_id: str,
    stage: str,
    model: str,
    full_input: Dict[str, Any],
    tenant_id: str = "default",
) -> Iterator[StageTraceContext]:
    """Wrap an LLM stage call to record full I/O + latency.

    Usage::

        with record_stage_trace(
            repo=self.repo,
            turn_id=turn_id,
            conversation_id=conversation_id,
            stage="outfit_architect",
            model=self.outfit_architect._model,
            full_input={"combined_context": combined_context.model_dump()},
        ) as ctx:
            plan = self.outfit_architect.plan(combined_context)
            ctx.full_output = plan.model_dump()

    On exception, ``status="error"`` is recorded and the exception is
    re-raised so the caller's existing error path runs unchanged.
    Trace-write failures are logged but never propagate.
    """
    t0 = time.monotonic()
    ctx = StageTraceContext(full_input=full_input)
    try:
        yield ctx
    except Exception as exc:
        ctx.status = "error"
        ctx.error_message = str(exc)[:2000]
        raise
    finally:
        latency_ms = int((time.monotonic() - t0) * 1000)
        try:
            repo.log_distillation_trace(
                turn_id=turn_id,
                conversation_id=conversation_id,
                stage=stage,
                model=model,
                full_input=ctx.full_input,
                full_output=ctx.full_output,
                input_hash=hash_input(ctx.full_input),
                latency_ms=latency_ms,
                status=ctx.status,
                error_message=ctx.error_message,
                tenant_id=tenant_id,
            )
        except Exception:  # noqa: BLE001 — trace writes must never fail the turn
            _log.exception("Failed to write distillation trace for stage=%s", stage)
