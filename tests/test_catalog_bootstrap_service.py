"""F.2.2 — idempotent install-time catalog sync.

The hard cost-bearing invariant under test: when a product already
exists in ``catalog_enriched`` for the given tenant_id +
shopify_product_id, **the embedder is not called**. Re-installs and
daily syncs walk the same product set; missing this check would
re-charge the vision pipeline on every sync.
"""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from agentic_application.services.catalog_bootstrap_service import (
    CatalogBootstrapService,
)


def _make_embedder(num_dims: int = 1536) -> MagicMock:
    embedder = MagicMock()
    # Return one zero-vector per input text — engine only cares about
    # the count; the actual values don't matter for these tests.
    embedder.embed_texts.side_effect = lambda texts: [[0.0] * num_dims for _ in texts]
    return embedder


def _make_client(*, existing_product_ids: set[str] | None = None) -> MagicMock:
    """Mock SupabaseRestClient where `existing_product_ids` are
    pretended to already exist in catalog_enriched for the test
    tenant. Inserts return the row with a synthetic id."""
    existing = set(existing_product_ids or [])
    client = MagicMock()

    def select_one(table, filters):
        # Only catalog_enriched lookups are interesting for idempotency.
        if table != "catalog_enriched":
            return None
        tenant_filter = filters.get("tenant_id", "")
        pid_filter = filters.get("shopify_product_id", "")
        if not tenant_filter.startswith("eq.") or not pid_filter.startswith("eq."):
            return None
        pid = pid_filter[len("eq."):]
        if pid in existing:
            return {"id": f"existing-{pid}", "shopify_product_id": pid}
        return None

    def insert_one(table, payload):
        if table == "catalog_enriched":
            return {"id": f"new-{payload['shopify_product_id']}", **payload}
        return payload

    client.select_one.side_effect = select_one
    client.insert_one.side_effect = insert_one
    client.update_one.return_value = {"ok": True}
    return client


class IdempotencyTests(unittest.TestCase):
    """Critical-path: a product already in catalog_enriched is not
    re-embedded. Verifies the cost-bearing invariant directly."""

    def test_existing_product_skips_embedding(self):
        embedder = _make_embedder()
        client = _make_client(existing_product_ids={"shopify_pid_42"})
        service = CatalogBootstrapService(client, embedder=embedder)

        result = service.process_products(
            tenant_id="t_test",
            products=[
                {
                    "shopify_product_id": "shopify_pid_42",
                    "title": "Black linen shirt",
                    "description": "Soft drape, breathable.",
                    "price": 1999,
                },
            ],
        )

        # Embedder must NOT have been called — that's the whole point
        # of the existence check.
        embedder.embed_texts.assert_not_called()
        self.assertEqual(result["updated"], 1)
        self.assertEqual(result["created"], 0)
        self.assertEqual(result["failed"], 0)

    def test_new_product_runs_embedding_and_inserts(self):
        embedder = _make_embedder()
        client = _make_client(existing_product_ids=set())
        service = CatalogBootstrapService(client, embedder=embedder)

        result = service.process_products(
            tenant_id="t_test",
            products=[
                {
                    "shopify_product_id": "shopify_pid_new",
                    "title": "Camel wool coat",
                    "description": "Mid-weight, hits mid-thigh.",
                },
            ],
        )

        embedder.embed_texts.assert_called_once()
        # Both tables must have been inserted into.
        insert_calls = [c.args for c in client.insert_one.call_args_list]
        tables_inserted = [c[0] for c in insert_calls]
        self.assertIn("catalog_enriched", tables_inserted)
        self.assertIn("catalog_item_embeddings", tables_inserted)
        self.assertEqual(result["created"], 1)
        self.assertEqual(result["updated"], 0)

    def test_mixed_batch_only_embeds_new_products(self):
        """Re-install scenario: most products already exist, a few
        are new. Embedder gets called ONCE with only the new texts
        (batched), and the cost stays proportional to net-new
        products, not the full catalog."""
        embedder = _make_embedder()
        client = _make_client(
            existing_product_ids={"existing_1", "existing_2", "existing_3"},
        )
        service = CatalogBootstrapService(client, embedder=embedder)

        result = service.process_products(
            tenant_id="t_test",
            products=[
                {"shopify_product_id": "existing_1", "title": "A", "description": ""},
                {"shopify_product_id": "existing_2", "title": "B", "description": ""},
                {"shopify_product_id": "new_1", "title": "C", "description": ""},
                {"shopify_product_id": "existing_3", "title": "D", "description": ""},
                {"shopify_product_id": "new_2", "title": "E", "description": ""},
            ],
        )

        # Exactly one batched call with two new texts.
        embedder.embed_texts.assert_called_once()
        args = embedder.embed_texts.call_args
        embedded_texts = args.args[0] if args.args else args.kwargs.get("texts", [])
        self.assertEqual(len(embedded_texts), 2)
        self.assertEqual(result["created"], 2)
        self.assertEqual(result["updated"], 3)
        self.assertEqual(result["failed"], 0)

    def test_missing_shopify_product_id_recorded_as_error(self):
        embedder = _make_embedder()
        client = _make_client()
        service = CatalogBootstrapService(client, embedder=embedder)

        result = service.process_products(
            tenant_id="t_test",
            products=[
                {"title": "no id"},
                {"shopify_product_id": "ok", "title": "OK"},
            ],
        )

        self.assertEqual(result["failed"], 1)
        self.assertEqual(result["created"], 1)
        self.assertEqual(len(result["errors"]), 1)
        self.assertEqual(result["errors"][0]["shopify_product_id"], "")

    def test_empty_tenant_id_raises(self):
        service = CatalogBootstrapService(_make_client(), embedder=_make_embedder())
        with self.assertRaises(ValueError):
            service.process_products(tenant_id="", products=[])

    def test_empty_product_list_is_a_no_op(self):
        embedder = _make_embedder()
        service = CatalogBootstrapService(_make_client(), embedder=embedder)
        result = service.process_products(tenant_id="t_test", products=[])
        embedder.embed_texts.assert_not_called()
        self.assertEqual(result, {"created": 0, "updated": 0, "failed": 0, "errors": []})


class TenantScopedProductIdTests(unittest.TestCase):
    """`catalog_enriched.product_id` has a global UNIQUE constraint
    (verified live against staging). Two tenants legitimately importing
    the same Shopify GID must NOT collide — prevented by prefixing
    tenant_id into product_id. The bare shopify_product_id stays in
    its own column for cart wiring."""

    def test_product_id_is_tenant_prefixed_on_insert(self):
        embedder = _make_embedder()
        client = _make_client(existing_product_ids=set())
        service = CatalogBootstrapService(client, embedder=embedder)

        service.process_products(
            tenant_id="t_alpha",
            products=[{
                "shopify_product_id": "gid://shopify/Product/12345",
                "title": "Shared GID test",
                "description": "",
            }],
        )

        enriched_inserts = [
            c for c in client.insert_one.call_args_list
            if c.args[0] == "catalog_enriched"
        ]
        self.assertEqual(len(enriched_inserts), 1)
        payload = enriched_inserts[0].args[1]
        self.assertEqual(payload["product_id"], "t_alpha:gid://shopify/Product/12345")
        self.assertEqual(payload["shopify_product_id"], "gid://shopify/Product/12345")
        self.assertEqual(payload["tenant_id"], "t_alpha")

        embedding_inserts = [
            c for c in client.insert_one.call_args_list
            if c.args[0] == "catalog_item_embeddings"
        ]
        self.assertEqual(len(embedding_inserts), 1)
        emb_payload = embedding_inserts[0].args[1]
        self.assertEqual(emb_payload["product_id"], "t_alpha:gid://shopify/Product/12345")
        self.assertEqual(emb_payload["tenant_id"], "t_alpha")

    def test_two_tenants_same_shopify_gid_yield_different_product_ids(self):
        from agentic_application.services.catalog_bootstrap_service import (
            _tenant_scoped_product_id,
        )
        alpha = _tenant_scoped_product_id("t_alpha", "gid://shopify/Product/99")
        beta = _tenant_scoped_product_id("t_beta", "gid://shopify/Product/99")
        self.assertNotEqual(alpha, beta)


class HtmlStrippingTests(unittest.TestCase):
    """Shopify's descriptionHtml is HTML — feeding it raw to the
    embedder inflates token count and worsens semantic clustering."""

    def test_html_tags_stripped_from_description(self):
        from agentic_application.services.catalog_bootstrap_service import _strip_html

        raw = "<p>Soft <strong>linen</strong> drape.</p><br/><p>Hits&nbsp;the hip.</p>"
        self.assertEqual(_strip_html(raw), "Soft linen drape. Hits the hip.")

    def test_html_entities_decoded(self):
        from agentic_application.services.catalog_bootstrap_service import _strip_html

        self.assertEqual(_strip_html("Tom&#39;s &amp; Jerry"), "Tom's & Jerry")

    def test_empty_input_returns_empty(self):
        from agentic_application.services.catalog_bootstrap_service import _strip_html

        self.assertEqual(_strip_html(""), "")
        self.assertEqual(_strip_html("   "), "")


class CronWalkRevivalTests(unittest.TestCase):
    """F.3 cron passes ``revive_soft_deleted=True`` so a daily walk
    that re-sees a previously-deleted product (e.g. when a
    products/create webhook was dropped past Shopify's 48h retry
    window) revives the row. The F.4 webhook upsert path uses the
    default False because its revival is topic-aware."""

    def test_cache_hit_writes_available_for_sale_when_provided(self):
        """The cron walk hands us available_for_sale derived from
        variants. The cache-hit patch must persist it so the engine's
        view reflects the latest inventory state."""
        embedder = _make_embedder()
        client = _make_client(existing_product_ids={"pid_1"})
        service = CatalogBootstrapService(client, embedder=embedder)
        service.process_products(
            tenant_id="t_test",
            products=[{
                "shopify_product_id": "pid_1",
                "title": "Black Linen",
                "description": "",
                "available_for_sale": False,
            }],
        )
        # The catalog_enriched PATCH must include the new value.
        ce_updates = [
            c for c in client.update_one.call_args_list
            if c.args and c.args[0] == "catalog_enriched"
        ]
        self.assertEqual(len(ce_updates), 1)
        self.assertEqual(
            ce_updates[0].kwargs["patch"]["available_for_sale"],
            False,
        )
        # And the embeddings table must be mirrored — that's where
        # the retrieval RPC filters from.
        cie_updates = [
            c for c in client.update_one.call_args_list
            if c.args and c.args[0] == "catalog_item_embeddings"
        ]
        self.assertEqual(len(cie_updates), 1)
        self.assertEqual(
            cie_updates[0].kwargs["patch"]["available_for_sale"],
            False,
        )

    def test_cache_hit_no_available_signal_doesnt_touch_embeddings(self):
        """Avoid an extra PATCH on the embeddings table for callers
        that don't carry an availability signal (legacy / minimal
        callers). Without this we'd round-trip on every cache hit."""
        embedder = _make_embedder()
        client = _make_client(existing_product_ids={"pid_1"})
        service = CatalogBootstrapService(client, embedder=embedder)
        service.process_products(
            tenant_id="t_test",
            products=[{
                "shopify_product_id": "pid_1",
                "title": "Black Linen",
                "description": "",
                # NOTE: no available_for_sale key
            }],
        )
        cie_updates = [
            c for c in client.update_one.call_args_list
            if c.args and c.args[0] == "catalog_item_embeddings"
        ]
        self.assertEqual(len(cie_updates), 0)

    def test_revive_soft_deleted_true_clears_deleted_at(self):
        """The cron-walk revival case: row was soft-deleted (e.g.
        previous products/delete webhook), but Shopify now shows it
        in the catalog walk again. Patch must clear deleted_at."""
        embedder = _make_embedder()
        client = _make_client(existing_product_ids={"pid_1"})
        service = CatalogBootstrapService(client, embedder=embedder)
        service.process_products(
            tenant_id="t_test",
            products=[{
                "shopify_product_id": "pid_1",
                "title": "Black Linen",
                "description": "",
                "available_for_sale": True,
            }],
            revive_soft_deleted=True,
        )
        ce_updates = [
            c for c in client.update_one.call_args_list
            if c.args and c.args[0] == "catalog_enriched"
        ]
        self.assertIn("deleted_at", ce_updates[0].kwargs["patch"])
        self.assertIsNone(ce_updates[0].kwargs["patch"]["deleted_at"])

    def test_revive_soft_deleted_false_preserves_deleted_at(self):
        """The webhook upsert path leaves revive_soft_deleted=False
        because products/update arriving after products/delete (out-
        of-order retry) must NOT resurrect. The patch must NOT
        touch deleted_at when the flag is False."""
        embedder = _make_embedder()
        client = _make_client(existing_product_ids={"pid_1"})
        service = CatalogBootstrapService(client, embedder=embedder)
        service.process_products(
            tenant_id="t_test",
            products=[{
                "shopify_product_id": "pid_1",
                "title": "Black Linen",
                "description": "",
                "available_for_sale": True,
            }],
            # default revive_soft_deleted=False
        )
        ce_updates = [
            c for c in client.update_one.call_args_list
            if c.args and c.args[0] == "catalog_enriched"
        ]
        self.assertNotIn("deleted_at", ce_updates[0].kwargs["patch"])

    def test_new_product_insert_carries_available_for_sale(self):
        """Cache-miss path: a freshly-installed catalog with some
        OOS products shouldn't sit at the column's TRUE default
        until the next webhook fires. The insert payload must
        include the signal."""
        embedder = _make_embedder()
        client = _make_client(existing_product_ids=set())
        service = CatalogBootstrapService(client, embedder=embedder)
        service.process_products(
            tenant_id="t_test",
            products=[{
                "shopify_product_id": "new_oos",
                "title": "OOS Product",
                "description": "",
                "available_for_sale": False,
            }],
        )
        insert_calls = [
            c.args for c in client.insert_one.call_args_list
            if c.args and c.args[0] == "catalog_enriched"
        ]
        self.assertEqual(len(insert_calls), 1)
        payload = insert_calls[0][1]
        self.assertEqual(payload["available_for_sale"], False)
        # And same for embeddings.
        emb_inserts = [
            c.args for c in client.insert_one.call_args_list
            if c.args and c.args[0] == "catalog_item_embeddings"
        ]
        self.assertEqual(emb_inserts[0][1]["available_for_sale"], False)


class CostSafetyTest(unittest.TestCase):
    """Belt-and-suspenders: under the realistic re-install case (every
    product in the input batch is already enriched), zero LLM calls
    are made regardless of batch size."""

    def test_thousand_existing_products_zero_embedder_calls(self):
        existing = {f"pid_{i}" for i in range(1000)}
        embedder = _make_embedder()
        client = _make_client(existing_product_ids=existing)
        service = CatalogBootstrapService(client, embedder=embedder)

        products = [
            {"shopify_product_id": pid, "title": f"Product {pid}", "description": ""}
            for pid in existing
        ]
        result = service.process_products(tenant_id="t_test", products=products)

        embedder.embed_texts.assert_not_called()
        self.assertEqual(result["updated"], 1000)
        self.assertEqual(result["created"], 0)


if __name__ == "__main__":
    unittest.main()
