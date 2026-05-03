"""ContextVar-backed correlation IDs threaded through every request.

Item 2 of the Observability Hardening plan (May 1, 2026). Provides a
single home for the four IDs we want flowing through every layer:

- ``request_id``       — generated or echoed at the HTTP boundary
- ``turn_id``          — set inside ``orchestrator.process_turn`` once a
                         row exists in ``conversation_turns``
- ``conversation_id``  — same site as ``turn_id``
- ``external_user_id`` — same site as ``turn_id``

ContextVars are async-safe and thread-local — anywhere code reads them
sees the value the originating coroutine/task set, even after async hops.

Two usage patterns:

1. Logging filter — `RequestContextFilter` injects whatever's set into
   every `LogRecord`. The JSON formatter already serialises non-standard
   record attributes, so logs gain the IDs with zero callsite churn.

2. Persistence — repository helpers can call `get_request_id()` to
   stamp the current correlation ID onto observability rows
   (``turn_traces``, ``model_call_logs``, ``tool_traces``).
"""

from __future__ import annotations

import logging
from contextvars import ContextVar, Token
from typing import Optional

# Empty string is the canonical "unset" value so log records always have
# the field present. None would force every consumer to handle missing
# keys.
_REQUEST_ID: ContextVar[str] = ContextVar("aura_request_id", default="")
_TURN_ID: ContextVar[str] = ContextVar("aura_turn_id", default="")
_CONVERSATION_ID: ContextVar[str] = ContextVar("aura_conversation_id", default="")
_EXTERNAL_USER_ID: ContextVar[str] = ContextVar("aura_external_user_id", default="")


# ── Setters / getters ─────────────────────────────────────────────────


def set_request_id(value: str) -> Token[str]:
    return _REQUEST_ID.set(value or "")


def reset_request_id(token: Token[str]) -> None:
    _REQUEST_ID.reset(token)


def get_request_id() -> str:
    return _REQUEST_ID.get()


def set_turn_id(value: str) -> Token[str]:
    return _TURN_ID.set(value or "")


def reset_turn_id(token: Token[str]) -> None:
    _TURN_ID.reset(token)


def get_turn_id() -> str:
    return _TURN_ID.get()


def set_conversation_id(value: str) -> Token[str]:
    return _CONVERSATION_ID.set(value or "")


def reset_conversation_id(token: Token[str]) -> None:
    _CONVERSATION_ID.reset(token)


def get_conversation_id() -> str:
    return _CONVERSATION_ID.get()


def set_external_user_id(value: str) -> Token[str]:
    return _EXTERNAL_USER_ID.set(value or "")


def reset_external_user_id(token: Token[str]) -> None:
    _EXTERNAL_USER_ID.reset(token)


def get_external_user_id() -> str:
    return _EXTERNAL_USER_ID.get()


def snapshot() -> dict:
    """Return all four IDs as a dict — handy for tool_traces metadata."""
    return {
        "request_id": _REQUEST_ID.get(),
        "turn_id": _TURN_ID.get(),
        "conversation_id": _CONVERSATION_ID.get(),
        "external_user_id": _EXTERNAL_USER_ID.get(),
    }


def run_with_context(snapshot_values: dict, fn, *args, **kwargs):
    """Execute ``fn`` with correlation-ID context vars set from the
    snapshot, then reset. Designed for ThreadPoolExecutor workers —
    capture the parent thread's `snapshot()` once, pass the dict
    into each worker submission, and call this helper at the worker's
    entry to make `get_request_id()` / `get_turn_id()` / etc. inside
    the worker return the parent's values.

    Why not `contextvars.copy_context().run()`? A single Context object
    can't be entered concurrently from multiple workers; sharing one
    snapshot across a 3-worker pool raises "is already entered". This
    helper sidesteps that by setting the context vars freshly in each
    worker's thread-local context.
    """
    tokens = [
        _REQUEST_ID.set(str(snapshot_values.get("request_id") or "")),
        _TURN_ID.set(str(snapshot_values.get("turn_id") or "")),
        _CONVERSATION_ID.set(str(snapshot_values.get("conversation_id") or "")),
        _EXTERNAL_USER_ID.set(str(snapshot_values.get("external_user_id") or "")),
    ]
    try:
        return fn(*args, **kwargs)
    finally:
        # Reset in reverse order. A worker thread is a fresh Context
        # so this isn't strictly necessary, but doing it keeps thread
        # reuse (in long-lived pools) clean.
        _REQUEST_ID.reset(tokens[0])
        _TURN_ID.reset(tokens[1])
        _CONVERSATION_ID.reset(tokens[2])
        _EXTERNAL_USER_ID.reset(tokens[3])


# ── Logging filter ────────────────────────────────────────────────────


class RequestContextFilter(logging.Filter):
    """Inject correlation IDs into every LogRecord that passes through.

    Caller-supplied ``extra={"turn_id": ...}`` values win — the filter
    only fills in when the attribute isn't already present on the record,
    so explicit overrides at the log site are honoured.

    Empty values are added when nothing else is available so the JSON
    formatter has stable keys — a sink can filter on ``request_id != ""``
    to drop framework-internal log lines that aren't part of a request.
    """

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        # Only set if absent — caller's extra={} always wins.
        for key, getter in (
            ("request_id", _REQUEST_ID),
            ("turn_id", _TURN_ID),
            ("conversation_id", _CONVERSATION_ID),
            ("external_user_id", _EXTERNAL_USER_ID),
        ):
            if not hasattr(record, key):
                setattr(record, key, getter.get())
        return True
