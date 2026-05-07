"""Regression tests for ApplicationCatalogRetrievalGateway.

Specifically covers the kwarg surface — catalog_search_agent passes
``hard_attrs=...`` to the gateway, so the gateway must accept and
forward it. A previous deploy missed updating this layer (PR #171
review escape) and engine-served turns errored at retrieval. These
tests pin the contract.
"""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock

# sys.path setup is centralised in tests/conftest.py.
from agentic_application.services.catalog_retrieval_gateway import (
    ApplicationCatalogRetrievalGateway,
)


class SimilaritySearchKwargsTests(unittest.TestCase):
    """Lock the gateway's similarity_search kwarg surface so future
    refactors don't drop the parameter forwarding silently."""

    def _make(self) -> ApplicationCatalogRetrievalGateway:
        # Build a gateway with a mock client; we only exercise the
        # similarity_search path so embedder/store internals can be
        # replaced post-construction.
        gateway = ApplicationCatalogRetrievalGateway(client=MagicMock())
        gateway._vector_store = MagicMock()
        gateway._vector_store.similarity_search.return_value = []
        return gateway

    def test_forwards_hard_attrs_to_vector_store(self):
        gateway = self._make()
        gateway.similarity_search(
            query_embedding=[0.0] * 1536,
            match_count=5,
            filters={"gender_expression": "feminine"},
            hard_attrs={"SleeveLength": ["three_quarter", "full"]},
        )
        call = gateway._vector_store.similarity_search.call_args
        self.assertEqual(
            call.kwargs.get("hard_attrs"),
            {"SleeveLength": ["three_quarter", "full"]},
        )

    def test_omitted_hard_attrs_passes_none(self):
        # Backward-compat path: callers that don't supply hard_attrs
        # (LLM-architect path, legacy tests) should still work and the
        # vector_store sees hard_attrs=None.
        gateway = self._make()
        gateway.similarity_search(
            query_embedding=[0.0] * 1536,
            match_count=5,
            filters={"gender_expression": "feminine"},
        )
        call = gateway._vector_store.similarity_search.call_args
        self.assertIsNone(call.kwargs.get("hard_attrs"))


if __name__ == "__main__":
    unittest.main()
