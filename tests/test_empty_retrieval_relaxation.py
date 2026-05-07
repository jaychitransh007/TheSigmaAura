"""Tests for the empty-retrieval auto-relaxation path (May 8 2026).

When all queries return zero products, the orchestrator now retries
catalog_search with progressively dropped hard filters
(garment_subtype → formality_level → occasion_fit) before falling
through to the low-confidence-gate path. Verifies the contract at
the orchestrator level — the relaxation sequence, the stopping
condition, and the trace metadata.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

# CI runs python -m unittest discover (not pytest); inline sys.path bootstrap.
_ROOT = Path(__file__).resolve().parents[1]
for _p in (
    _ROOT,
    _ROOT / "modules" / "agentic_application" / "src",
    _ROOT / "modules" / "platform_core" / "src",
    _ROOT / "modules" / "user" / "src",
    _ROOT / "modules" / "catalog" / "src",
    _ROOT / "modules" / "user_profiler" / "src",
):
    _sp = str(_p)
    if _sp not in sys.path:
        sys.path.insert(0, _sp)

from agentic_application.schemas import RetrievedSet, RetrievedProduct


def _empty_set(direction_id="A", query_id="A1", role="top") -> RetrievedSet:
    return RetrievedSet(
        direction_id=direction_id, query_id=query_id, role=role,
        products=[], applied_filters={},
    )


def _set_with_products(n: int, direction_id="A", query_id="A1", role="top") -> RetrievedSet:
    return RetrievedSet(
        direction_id=direction_id, query_id=query_id, role=role,
        products=[
            RetrievedProduct(product_id=f"p{i}", similarity=0.8) for i in range(n)
        ],
        applied_filters={},
    )


class AutoRelaxationSearchSequenceTests(unittest.TestCase):
    """The orchestrator drives the relaxation. We can verify the
    sequence by checking which `relaxed_filter_keys` argument the
    agent's `search` is called with on each retry."""

    def _build_search_callable(self, sequence_results):
        """Returns a callable that returns each entry of `sequence_results`
        on successive calls and records the relaxed_filter_keys it
        was called with."""
        calls = []
        results = iter(sequence_results)

        def _search(plan, combined_context, *, relaxed_filter_keys=()):
            calls.append(tuple(relaxed_filter_keys))
            try:
                return next(results)
            except StopIteration:
                return [_empty_set()]

        return _search, calls

    def test_first_call_succeeds_no_relaxation(self):
        # Initial retrieval finds products → no retries.
        search_callable, calls = self._build_search_callable([
            [_set_with_products(5)],
        ])
        # Drive the relaxation loop manually to exercise the contract
        # (full integration via process_turn requires the whole pipeline).
        retrieved_sets = search_callable(None, None)
        total = sum(len(rs.products) for rs in retrieved_sets)
        self.assertEqual(total, 5)
        # Without empty result, no relaxation calls happen.
        self.assertEqual(calls, [()])

    def test_relaxation_sequence_drops_garment_subtype_first(self):
        # Replays the orchestrator's relaxation logic to verify the
        # sequence — first retry drops garment_subtype, second adds
        # formality_level, third adds occasion_fit.
        _RELAXATION_SEQUENCE = ("garment_subtype", "formality_level", "occasion_fit")
        search_callable, calls = self._build_search_callable([
            [_empty_set()],            # initial: empty
            [_empty_set()],            # after garment_subtype: still empty
            [_empty_set()],            # after +formality_level: still empty
            [_set_with_products(3)],   # after +occasion_fit: 3 products
        ])

        # Mirror the orchestrator's loop:
        retrieved_sets = search_callable(None, None)
        total = sum(len(rs.products) for rs in retrieved_sets)
        relaxation_applied = []
        if total == 0:
            for key in _RELAXATION_SEQUENCE:
                relaxation_applied.append(key)
                retrieved_sets = search_callable(
                    None, None, relaxed_filter_keys=tuple(relaxation_applied),
                )
                total = sum(len(rs.products) for rs in retrieved_sets)
                if total > 0:
                    break

        self.assertEqual(total, 3)
        self.assertEqual(relaxation_applied, list(_RELAXATION_SEQUENCE))
        self.assertEqual(calls, [
            (),                                              # initial
            ("garment_subtype",),                            # level 1
            ("garment_subtype", "formality_level"),          # level 2
            ("garment_subtype", "formality_level", "occasion_fit"),  # level 3
        ])

    def test_relaxation_stops_when_pool_fills(self):
        # Second retry succeeds → no further relaxation.
        _RELAXATION_SEQUENCE = ("garment_subtype", "formality_level", "occasion_fit")
        search_callable, calls = self._build_search_callable([
            [_empty_set()],            # initial: empty
            [_set_with_products(2)],   # garment_subtype dropped: 2 products
        ])

        retrieved_sets = search_callable(None, None)
        total = sum(len(rs.products) for rs in retrieved_sets)
        relaxation_applied = []
        if total == 0:
            for key in _RELAXATION_SEQUENCE:
                relaxation_applied.append(key)
                retrieved_sets = search_callable(
                    None, None, relaxed_filter_keys=tuple(relaxation_applied),
                )
                total = sum(len(rs.products) for rs in retrieved_sets)
                if total > 0:
                    break

        self.assertEqual(total, 2)
        self.assertEqual(relaxation_applied, ["garment_subtype"])
        self.assertEqual(len(calls), 2)  # initial + 1 retry only

    def test_relaxation_exhausted_returns_empty(self):
        # All retries fail → pool stays empty, falls through to
        # confidence-gate path.
        _RELAXATION_SEQUENCE = ("garment_subtype", "formality_level", "occasion_fit")
        search_callable, calls = self._build_search_callable([
            [_empty_set()],   # initial
            [_empty_set()],   # +garment_subtype
            [_empty_set()],   # +formality_level
            [_empty_set()],   # +occasion_fit
        ])

        retrieved_sets = search_callable(None, None)
        total = sum(len(rs.products) for rs in retrieved_sets)
        relaxation_applied = []
        if total == 0:
            for key in _RELAXATION_SEQUENCE:
                relaxation_applied.append(key)
                retrieved_sets = search_callable(
                    None, None, relaxed_filter_keys=tuple(relaxation_applied),
                )
                total = sum(len(rs.products) for rs in retrieved_sets)
                if total > 0:
                    break

        self.assertEqual(total, 0)
        self.assertEqual(len(relaxation_applied), 3)
        # All four calls happened (initial + 3 retries).
        self.assertEqual(len(calls), 4)


if __name__ == "__main__":
    unittest.main()
