"""Tests for AgenticOrchestrator._build_engine_reasoning_payload.

Pins the snapshot shape passed downstream to _handle_explanation_request
and the style advisor. Specifically guards against:

- Per-direction hard_attrs collapsing to empty (the bug class that
  produced "we matched your colors and category" generic answers — turn
  edac603c)
- Missing user-profile anchors (body_shape / palette / frame)
- Router-decision metadata not flowing through (used_engine,
  fallback_reason)
"""
from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

# sys.path setup is centralised in tests/conftest.py.
from agentic_application.orchestrator import AgenticOrchestrator
from agentic_application.schemas import DirectionSpec, QuerySpec, RecommendationPlan


def _plan() -> RecommendationPlan:
    return RecommendationPlan(
        retrieval_count=5,
        directions=[
            DirectionSpec(
                direction_id="A",
                direction_type="three_piece",
                label="Layered Hill-Station",
                queries=[
                    QuerySpec(
                        query_id="A1", role="top",
                        hard_filters={"gender_expression": "feminine"},
                        query_document="navy structured top",
                        hard_attrs={
                            "SleeveLength": ["three_quarter", "full"],
                            "FabricWeight": ["light", "medium"],
                            "FormalityLevel": ["smart_casual"],
                        },
                    ),
                    QuerySpec(
                        query_id="A2", role="bottom",
                        hard_filters={"gender_expression": "feminine"},
                        query_document="cream tailored trouser",
                        hard_attrs={
                            "SleeveLength": ["three_quarter", "full"],
                            "FabricWeight": ["light", "medium"],
                            "FormalityLevel": ["smart_casual"],
                        },
                    ),
                    QuerySpec(
                        query_id="A3", role="outerwear",
                        hard_filters={"gender_expression": "feminine"},
                        query_document="structured jacket",
                        hard_attrs={
                            "SleeveLength": ["three_quarter", "full"],
                            "FabricWeight": ["light", "medium"],
                            "FormalityLevel": ["smart_casual"],
                        },
                    ),
                ],
            ),
        ],
    )


def _live_context(**overrides):
    base = dict(
        weather_context="high_altitude_cool",
        occasion_signal="everyday_casual",
        formality_hint="casual",
        time_of_day="daytime",
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _user_context(**overrides):
    base = dict(
        analysis_attributes={"BodyShape": {"value": "Hourglass"}},
        derived_interpretations={
            "FrameStructure": "Light and Narrow",
            "SeasonalColorGroup": "Soft Autumn",
            "PaletteAnchors": ["navy", "cream", "charcoal"],
        },
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _router_decision(used_engine: bool = True, fallback_reason: str | None = None):
    return SimpleNamespace(used_engine=used_engine, fallback_reason=fallback_reason)


class BuildEngineReasoningPayloadTests(unittest.TestCase):

    def test_per_direction_hard_attrs_captured(self):
        payload = AgenticOrchestrator._build_engine_reasoning_payload(
            plan=_plan(),
            router_decision=_router_decision(),
            composer_router_decision=_router_decision(),
            live_context=_live_context(),
            user_context=_user_context(),
        )
        self.assertIn("by_direction", payload)
        self.assertIn("A", payload["by_direction"])
        d = payload["by_direction"]["A"]
        self.assertEqual(d["direction_label"], "Layered Hill-Station")
        self.assertEqual(d["direction_type"], "three_piece")
        self.assertEqual(d["resolved_hard_attrs"]["SleeveLength"], ["three_quarter", "full"])
        self.assertEqual(d["resolved_hard_attrs"]["FabricWeight"], ["light", "medium"])

    def test_user_anchors_extracted_from_dict_value_shape(self):
        # analysis_attributes BodyShape is the {"value": "..."} dict shape.
        payload = AgenticOrchestrator._build_engine_reasoning_payload(
            plan=_plan(),
            router_decision=_router_decision(),
            composer_router_decision=_router_decision(),
            live_context=_live_context(),
            user_context=_user_context(),
        )
        self.assertEqual(payload["user_body_shape"], "Hourglass")
        self.assertEqual(payload["user_frame_structure"], "Light and Narrow")
        self.assertEqual(payload["user_seasonal_color_group"], "Soft Autumn")
        self.assertEqual(payload["user_palette_anchors"], ["navy", "cream", "charcoal"])

    def test_user_anchors_extracted_from_bare_string(self):
        # Some profiles store BodyShape as a bare string, not a dict.
        user = _user_context(analysis_attributes={"BodyShape": "Pear"})
        payload = AgenticOrchestrator._build_engine_reasoning_payload(
            plan=_plan(),
            router_decision=_router_decision(),
            composer_router_decision=_router_decision(),
            live_context=_live_context(),
            user_context=user,
        )
        self.assertEqual(payload["user_body_shape"], "Pear")

    def test_planner_signals_captured(self):
        payload = AgenticOrchestrator._build_engine_reasoning_payload(
            plan=_plan(),
            router_decision=_router_decision(),
            composer_router_decision=_router_decision(),
            live_context=_live_context(
                weather_context="high_altitude_cool",
                occasion_signal="travel_day",
            ),
            user_context=_user_context(),
        )
        self.assertEqual(payload["weather_context"], "high_altitude_cool")
        self.assertEqual(payload["occasion_signal"], "travel_day")
        self.assertEqual(payload["formality_hint"], "casual")
        self.assertEqual(payload["time_of_day"], "daytime")

    def test_router_metadata_flows_through(self):
        payload = AgenticOrchestrator._build_engine_reasoning_payload(
            plan=_plan(),
            router_decision=_router_decision(used_engine=True, fallback_reason=None),
            composer_router_decision=_router_decision(used_engine=False, fallback_reason="pool_too_sparse"),
            live_context=_live_context(),
            user_context=_user_context(),
        )
        self.assertTrue(payload["architect_used_engine"])
        self.assertIsNone(payload["architect_fallback_reason"])
        self.assertFalse(payload["composer_used_engine"])
        self.assertEqual(payload["composer_fallback_reason"], "pool_too_sparse")

    def test_handles_none_router_decisions(self):
        # Engine flag off → both router decisions are None. Helper
        # tolerates and returns sensible defaults.
        payload = AgenticOrchestrator._build_engine_reasoning_payload(
            plan=_plan(),
            router_decision=None,
            composer_router_decision=None,
            live_context=_live_context(),
            user_context=_user_context(),
        )
        self.assertFalse(payload["architect_used_engine"])
        self.assertFalse(payload["composer_used_engine"])
        self.assertIsNone(payload["architect_fallback_reason"])
        self.assertIsNone(payload["composer_fallback_reason"])

    def test_empty_hard_attrs_when_llm_path(self):
        # LLM architect doesn't populate hard_attrs (default empty).
        # Payload still returns the direction entry but with empty
        # resolved_hard_attrs.
        plan = RecommendationPlan(
            retrieval_count=5,
            directions=[
                DirectionSpec(
                    direction_id="A", direction_type="paired", label="LLM",
                    queries=[
                        QuerySpec(query_id="A1", role="top", hard_filters={}, query_document="t"),
                        QuerySpec(query_id="A2", role="bottom", hard_filters={}, query_document="b"),
                    ],
                ),
            ],
        )
        payload = AgenticOrchestrator._build_engine_reasoning_payload(
            plan=plan,
            router_decision=_router_decision(used_engine=False, fallback_reason="engine_disabled"),
            composer_router_decision=_router_decision(used_engine=False, fallback_reason="engine_disabled"),
            live_context=_live_context(),
            user_context=_user_context(),
        )
        self.assertEqual(payload["by_direction"]["A"]["resolved_hard_attrs"], {})
        # Other turn-level fields still populated.
        self.assertEqual(payload["weather_context"], "high_altitude_cool")


if __name__ == "__main__":
    unittest.main()
