"""Regression tests for ApplicationCatalogRetrievalGateway.

Specifically covers the kwarg surface — catalog_search_agent calls
``gateway.similarity_search(...)`` and the gateway must forward the
same kwargs to the underlying ``SupabaseVectorStore``. The May 13
RPC overload bug (PR #329) was caused by the SQL function being
defined twice; the application-side fix removed ``hard_attrs`` /
``hard_penalty`` entirely from this layer since the Python re-rank
already enforces hard_attrs against the rich catalog_enriched data
after retrieval.
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

    def test_forwards_four_args_to_vector_store(self):
        gateway = self._make()
        gateway.similarity_search(
            tenant_id="t_test_tenant",
            query_embedding=[0.0] * 1536,
            match_count=5,
            filters={"gender_expression": "feminine"},
        )
        call = gateway._vector_store.similarity_search.call_args
        self.assertEqual(call.kwargs.get("tenant_id"), "t_test_tenant")
        self.assertEqual(call.kwargs.get("query_embedding"), [0.0] * 1536)
        self.assertEqual(call.kwargs.get("match_count"), 5)
        self.assertEqual(
            call.kwargs.get("filters"),
            {"gender_expression": "feminine"},
        )
        # hard_attrs / hard_penalty were removed in PR #329 — the SQL
        # 5-arg overload was dropped from the DB and Python now owns
        # hard-attr enforcement. The kwargs must not be forwarded.
        self.assertNotIn("hard_attrs", call.kwargs)
        self.assertNotIn("hard_penalty", call.kwargs)

    def test_rejects_legacy_hard_attrs_kwarg(self):
        # Callers that still pass hard_attrs= should now fail loudly
        # rather than have it silently dropped. This guards against
        # the next overload-style regression hiding under a no-op kwarg.
        gateway = self._make()
        with self.assertRaises(TypeError):
            gateway.similarity_search(
                tenant_id="t_test_tenant",
                query_embedding=[0.0] * 1536,
                match_count=5,
                filters={"gender_expression": "feminine"},
                hard_attrs={"SleeveLength": ["three_quarter", "full"]},
            )

    def test_requires_tenant_id_kwarg(self):
        # F.2.1: tenant_id is the new required first parameter on the
        # gateway's similarity_search. Forgetting it should TypeError
        # at call time rather than silently default to a single tenant.
        gateway = self._make()
        with self.assertRaises(TypeError):
            gateway.similarity_search(
                query_embedding=[0.0] * 1536,
                match_count=5,
                filters={},
            )


if __name__ == "__main__":
    unittest.main()
