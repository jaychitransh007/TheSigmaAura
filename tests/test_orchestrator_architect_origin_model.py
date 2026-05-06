"""Tests for _resolve_architect_origin_model (orchestrator.py).

Stamps the architect ``model_call_logs`` row with the actual origin
of the plan so per-model cost / latency dashboards correctly attribute
work to cache hits, engine accepts, and the LLM separately."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

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
    ARCHITECT_MODEL_CACHE,
    ARCHITECT_MODEL_ENGINE,
    _resolve_architect_origin_model,
)


class ResolveArchitectOriginModelTests(unittest.TestCase):
    def test_cache_hit_returns_cache_sentinel(self):
        # Even if a router_decision was somehow constructed, cache_hit
        # short-circuits — the plan came from the architect cache,
        # neither engine nor LLM ran.
        out = _resolve_architect_origin_model(
            cache_hit=True,
            router_decision=Mock(used_engine=True),
            llm_model="gpt-5.2",
        )
        self.assertEqual(out, ARCHITECT_MODEL_CACHE)
        self.assertEqual(out, "cache")

    def test_engine_accepted_returns_engine_sentinel(self):
        out = _resolve_architect_origin_model(
            cache_hit=False,
            router_decision=Mock(used_engine=True),
            llm_model="gpt-5.2",
        )
        self.assertEqual(out, ARCHITECT_MODEL_ENGINE)
        self.assertEqual(out, "composition_engine")

    def test_llm_path_returns_llm_model(self):
        # Engine flag off OR engine fell through: the LLM produced
        # the plan and gets the attribution.
        out = _resolve_architect_origin_model(
            cache_hit=False,
            router_decision=Mock(used_engine=False),
            llm_model="gpt-5.2",
        )
        self.assertEqual(out, "gpt-5.2")

    def test_router_decision_none_falls_back_to_llm(self):
        # On the cache-miss path the orchestrator always sets
        # _router_decision; this test pins the defensive None branch
        # so a future code path that calls the helper without a
        # decision (e.g. a refactor that bypasses the router) still
        # produces a sensible row.
        out = _resolve_architect_origin_model(
            cache_hit=False,
            router_decision=None,
            llm_model="gpt-5.2",
        )
        self.assertEqual(out, "gpt-5.2")

    def test_router_decision_missing_used_engine_attr_falls_back(self):
        # getattr defensiveness: an object lacking ``used_engine`` is
        # treated as engine-not-used. Belt-and-suspenders against a
        # future refactor that changes RouterDecision shape without
        # updating this call site.
        opaque = object()
        out = _resolve_architect_origin_model(
            cache_hit=False,
            router_decision=opaque,
            llm_model="gpt-5.4",
        )
        self.assertEqual(out, "gpt-5.4")

    def test_llm_model_passes_through_verbatim(self):
        # Model id may move (gpt-5.2 → gpt-5.3 → claude-…); the helper
        # is a string passthrough on the LLM path.
        for m in ("gpt-5.2", "gpt-5.4", "claude-sonnet-4-7", "gemini-2.5-pro"):
            with self.subTest(model=m):
                out = _resolve_architect_origin_model(
                    cache_hit=False,
                    router_decision=Mock(used_engine=False),
                    llm_model=m,
                )
                self.assertEqual(out, m)


class SentinelLockdownTests(unittest.TestCase):
    """The sentinel strings end up on every row in
    model_call_logs.model — pin them so dashboard queries that filter
    on these literals don't silently break on a rename."""

    def test_cache_sentinel(self):
        self.assertEqual(ARCHITECT_MODEL_CACHE, "cache")

    def test_engine_sentinel(self):
        self.assertEqual(ARCHITECT_MODEL_ENGINE, "composition_engine")


if __name__ == "__main__":
    unittest.main()
