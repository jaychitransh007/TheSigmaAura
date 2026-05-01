"""Structured logging configuration shared by every entry point.

Default behaviour stays unchanged from before: a plain text formatter
goes to stdout. Set ``AURA_LOG_FORMAT=json`` (or ``LOG_FORMAT=json``)
and every record is emitted as a single JSON line — the shape every
modern log sink (Logflare, Datadog, Google Cloud Logging, OpenTelemetry
Collector, Loki, Vector) ingests without further parsing.

Set ``AURA_LOG_LEVEL`` (or ``LOG_LEVEL``) to override the root level
(default INFO). Set ``AURA_LOG_INCLUDE_PROC=1`` to include process /
thread ids in the JSON record (useful when the sink correlates by pid).

Usage:
    from platform_core.logging_config import configure_logging
    configure_logging()  # call once at process start, before logging.getLogger

This satisfies Gate 3 of `docs/RELEASE_READINESS.md` — runtime logs that
were previously stdout-only are now sink-ready. The JSON shape is stable
across releases (additive only) so dashboards and alerts can pin to
field names.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from typing import Any


_DEFAULT_TEXT_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"

# JSON keys exposed by every record. Additive over time only — never
# remove or rename without coordinated dashboard updates.
_BASE_JSON_FIELDS = (
    "ts", "level", "logger", "message", "module", "func", "line",
)


class _JsonFormatter(logging.Formatter):
    """Emit each record as a single JSON line."""

    def __init__(self, *, include_proc: bool = False) -> None:
        super().__init__()
        self._include_proc = include_proc

    def format(self, record: logging.LogRecord) -> str:  # noqa: D401
        payload: dict[str, Any] = {
            "ts": _iso_ts(record.created),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "func": record.funcName,
            "line": record.lineno,
        }
        if self._include_proc:
            payload["pid"] = record.process
            payload["thread"] = record.threadName

        # Surface exception info if present.
        if record.exc_info:
            payload["exc_type"] = (
                record.exc_info[0].__name__ if record.exc_info[0] else ""
            )
            payload["exc"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack"] = record.stack_info

        # Pull through any extra={} fields the caller passed in. We
        # ignore the standard LogRecord attributes so we don't double up.
        std_keys = set(logging.LogRecord(
            "", 0, "", 0, "", None, None,
        ).__dict__.keys()) | {"message", "asctime", "exc_text"}
        for key, val in record.__dict__.items():
            if key in std_keys or key in payload:
                continue
            try:
                json.dumps(val)
                payload[key] = val
            except (TypeError, ValueError):
                payload[key] = repr(val)

        return json.dumps(payload, ensure_ascii=False, default=str)


def _iso_ts(epoch: float) -> str:
    """ISO 8601 UTC timestamp with millisecond precision."""
    seconds = int(epoch)
    millis = int((epoch - seconds) * 1000)
    base = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(seconds))
    return f"{base}.{millis:03d}Z"


def _resolve(name: str, default: str = "") -> str:
    """First non-empty value from AURA_<name> or <name>."""
    for key in (f"AURA_{name}", name):
        v = os.getenv(key, "").strip()
        if v:
            return v
    return default


def configure_logging() -> None:
    """Configure the root logger once; safe to call multiple times.

    Re-running replaces existing handlers so reload-mode dev servers
    don't end up with duplicated output.
    """
    level_name = _resolve("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    fmt_choice = _resolve("LOG_FORMAT", "text").lower()
    include_proc = _resolve("LOG_INCLUDE_PROC", "0") in ("1", "true", "yes")

    handler = logging.StreamHandler(sys.stdout)
    if fmt_choice == "json":
        handler.setFormatter(_JsonFormatter(include_proc=include_proc))
    else:
        handler.setFormatter(logging.Formatter(_DEFAULT_TEXT_FORMAT))

    # Item 2 (May 1, 2026): inject request_id / turn_id / conversation_id
    # / external_user_id contextvars onto every record so logs auto-correlate
    # to traces with no callsite changes.
    try:
        from .request_context import RequestContextFilter
        handler.addFilter(RequestContextFilter())
    except Exception:  # noqa: BLE001 — never let logging setup fail loudly
        pass

    root = logging.getLogger()
    # Replace existing handlers — uvicorn's default config installs its
    # own which duplicates output if we don't clear them.
    for existing in list(root.handlers):
        root.removeHandler(existing)
    root.addHandler(handler)
    root.setLevel(level)

    # uvicorn / fastapi-internal loggers need their level synced too,
    # otherwise INFO records get swallowed at the child level.
    for child_name in ("uvicorn", "uvicorn.error", "uvicorn.access", "fastapi"):
        child = logging.getLogger(child_name)
        child.setLevel(level)
        child.propagate = True
