"""Tests for _coerce_tryon_trace_db_status (orchestrator.py).

Per-candidate try-on path status carries values like ``cache_hit`` and
``tryon_failed`` that are richer than the ``tool_traces.status`` CHECK
constraint allows. The helper coerces to ``'ok'`` / ``'error'`` so the
trace insert succeeds; the original path label still flows through
``output_json.status``."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for p in (
    ROOT,
    ROOT / "modules" / "agentic_application" / "src",
    ROOT / "modules" / "catalog" / "src",
    ROOT / "modules" / "platform_core" / "src",
    ROOT / "modules" / "style_engine" / "src",
    ROOT / "modules" / "user" / "src",
    ROOT / "modules" / "user_profiler" / "src",
):
    sp = str(p)
    if sp not in sys.path:
        sys.path.insert(0, sp)

from agentic_application.orchestrator import (
    _TRYON_TRACE_DB_OK_STATUSES,
    _coerce_tryon_trace_db_status,
)


class CoerceTryonTraceDbStatusTests(unittest.TestCase):
    """Every path-status value used in the tryon batch closure must
    map cleanly to {'ok', 'error'} — that's the full set the DB
    constraint accepts."""

    def test_ok_passes_through(self):
        self.assertEqual(_coerce_tryon_trace_db_status("ok"), "ok")

    def test_cache_hit_maps_to_ok(self):
        # The bug from the staging log: cache_hit was being passed
        # straight to the DB and rejected. Most-common path on a
        # warm cache.
        self.assertEqual(_coerce_tryon_trace_db_status("cache_hit"), "ok")

    def test_skipped_no_urls_maps_to_ok(self):
        # Candidate had no garment URLs to render — not an error,
        # just a no-op.
        self.assertEqual(
            _coerce_tryon_trace_db_status("skipped_no_urls"), "ok"
        )

    def test_failure_paths_all_map_to_error(self):
        # Every path the orchestrator marks as a real try-on failure.
        for path_status in (
            "tryon_failed",
            "quality_gate_failed",
            "tryon_no_image",
            "decode_failed",
            "decode_empty",
            "error",
        ):
            with self.subTest(path_status=path_status):
                self.assertEqual(
                    _coerce_tryon_trace_db_status(path_status), "error"
                )

    def test_unknown_value_defaults_to_error(self):
        # Fail-safe: unrecognised path-status reads as 'error' so an
        # accidentally-introduced new path doesn't silently flip to
        # 'ok' and hide a real failure.
        self.assertEqual(
            _coerce_tryon_trace_db_status("brand_new_path"), "error"
        )

    def test_empty_string_maps_to_error(self):
        self.assertEqual(_coerce_tryon_trace_db_status(""), "error")

    def test_ok_set_lockdown(self):
        # Lock the OK whitelist so a future refactor that adds a value
        # has to update both the constant and this test deliberately.
        self.assertEqual(
            _TRYON_TRACE_DB_OK_STATUSES,
            frozenset({"ok", "cache_hit", "skipped_no_urls"}),
        )


if __name__ == "__main__":
    unittest.main()
