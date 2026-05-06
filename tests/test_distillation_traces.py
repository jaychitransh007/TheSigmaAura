"""Unit tests for the distillation_traces context manager + helpers."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT, ROOT / "modules" / "platform_core" / "src"):
    sp = str(p)
    if sp not in sys.path:
        sys.path.insert(0, sp)

from platform_core.distillation_traces import (
    StageTraceContext,
    hash_input,
    record_stage_trace,
    to_jsonable,
)


class _FakeModel:
    """Stand-in for a pydantic model with .model_dump()."""

    def __init__(self, payload):
        self._payload = payload

    def model_dump(self):
        return dict(self._payload)


class HashInputTests(unittest.TestCase):
    def test_deterministic_across_key_order(self):
        h1 = hash_input({"a": 1, "b": 2})
        h2 = hash_input({"b": 2, "a": 1})
        self.assertEqual(h1, h2)

    def test_truncated_to_32_chars(self):
        self.assertEqual(len(hash_input({"foo": "bar"})), 32)

    def test_different_inputs_different_hashes(self):
        self.assertNotEqual(hash_input({"a": 1}), hash_input({"a": 2}))

    def test_handles_non_json_native_via_default_str(self):
        from datetime import datetime
        h = hash_input({"ts": datetime(2026, 1, 1)})
        self.assertEqual(len(h), 32)


class ToJsonableTests(unittest.TestCase):
    def test_passes_through_primitives(self):
        self.assertEqual(to_jsonable(42), 42)
        self.assertEqual(to_jsonable("hello"), "hello")
        self.assertIsNone(to_jsonable(None))

    def test_unwraps_pydantic_like_model(self):
        model = _FakeModel({"foo": "bar", "n": 7})
        self.assertEqual(to_jsonable(model), {"foo": "bar", "n": 7})

    def test_recurses_into_dict(self):
        nested = {"outer": _FakeModel({"inner": 1})}
        self.assertEqual(to_jsonable(nested), {"outer": {"inner": 1}})

    def test_recurses_into_list(self):
        items = [_FakeModel({"i": 1}), _FakeModel({"i": 2})]
        self.assertEqual(to_jsonable(items), [{"i": 1}, {"i": 2}])


class RecordStageTraceTests(unittest.TestCase):
    def setUp(self):
        self.repo = Mock()
        self.repo.log_distillation_trace = Mock(return_value={"id": "trace-id"})

    def test_writes_trace_on_success(self):
        with record_stage_trace(
            repo=self.repo,
            turn_id="t1",
            conversation_id="c1",
            stage="outfit_architect",
            model="gpt-5.4",
            full_input={"foo": "bar"},
        ) as ctx:
            ctx.full_output = {"directions": []}

        self.repo.log_distillation_trace.assert_called_once()
        kwargs = self.repo.log_distillation_trace.call_args.kwargs
        self.assertEqual(kwargs["stage"], "outfit_architect")
        self.assertEqual(kwargs["model"], "gpt-5.4")
        self.assertEqual(kwargs["full_input"], {"foo": "bar"})
        self.assertEqual(kwargs["full_output"], {"directions": []})
        self.assertEqual(kwargs["status"], "ok")
        self.assertEqual(kwargs["error_message"], "")
        self.assertGreaterEqual(kwargs["latency_ms"], 0)
        self.assertEqual(kwargs["input_hash"], hash_input({"foo": "bar"}))
        self.assertEqual(kwargs["tenant_id"], "default")

    def test_records_error_status_on_exception_and_reraises(self):
        with self.assertRaises(ValueError):
            with record_stage_trace(
                repo=self.repo,
                turn_id="t1",
                conversation_id="c1",
                stage="copilot_planner",
                model="gpt-5-mini",
                full_input={"msg": "hi"},
            ):
                raise ValueError("boom")

        self.repo.log_distillation_trace.assert_called_once()
        kwargs = self.repo.log_distillation_trace.call_args.kwargs
        self.assertEqual(kwargs["status"], "error")
        self.assertIn("boom", kwargs["error_message"])
        self.assertIsNone(kwargs["full_output"])

    def test_swallows_writer_failure(self):
        """A trace-write failure must never break the user-facing turn."""
        self.repo.log_distillation_trace = Mock(side_effect=RuntimeError("supabase down"))

        # No exception should escape — the writer error is swallowed.
        with record_stage_trace(
            repo=self.repo,
            turn_id="t1",
            conversation_id="c1",
            stage="outfit_rater",
            model="gpt-5-mini",
            full_input={"x": 1},
        ) as ctx:
            ctx.full_output = {"y": 2}

    def test_propagates_tenant_id(self):
        with record_stage_trace(
            repo=self.repo,
            turn_id="t1",
            conversation_id="c1",
            stage="outfit_composer",
            model="gpt-5.4",
            full_input={},
            tenant_id="shop-123",
        ) as ctx:
            ctx.full_output = {}

        self.assertEqual(
            self.repo.log_distillation_trace.call_args.kwargs["tenant_id"],
            "shop-123",
        )


class StageTraceContextTests(unittest.TestCase):
    def test_default_state(self):
        ctx = StageTraceContext(full_input={"a": 1})
        self.assertEqual(ctx.full_input, {"a": 1})
        self.assertIsNone(ctx.full_output)
        self.assertEqual(ctx.status, "ok")
        self.assertEqual(ctx.error_message, "")


if __name__ == "__main__":
    unittest.main()
