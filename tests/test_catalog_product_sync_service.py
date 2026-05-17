"""F.4 — Shopify products/* webhook applier.

Tests cover:
  - REST payload → BootstrapProductInput translation (numeric ids
    correctly turn into gid:// format, variants surface as size→gid
    map, body_html ends up in `description` for the embedder).
  - available_for_sale derivation: any in-stock variant OR continue-
    selling policy = available; all OOS = unavailable.
  - Soft-delete: products/delete sets available_for_sale=false and
    deleted_at on the row but doesn't remove it.
  - Idempotency: re-running create on an existing row uses the
    bootstrap service's cache-hit path (no embedding cost).
"""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from agentic_application.services.catalog_bootstrap_service import (
    CatalogBootstrapService,
)
from agentic_application.services.catalog_product_sync_service import (
    CatalogProductSyncService,
    _availability_from_variants,
)


def _make_clients() -> tuple[MagicMock, MagicMock]:
    """Mock SupabaseRestClient + a stub CatalogBootstrapService."""
    client = MagicMock()
    client.select_one.return_value = None
    client.insert_one.side_effect = lambda table, payload: {"id": "row-1", **payload}
    client.update_one.return_value = {"ok": True}

    bootstrap = MagicMock(spec=CatalogBootstrapService)
    bootstrap.process_products.return_value = {
        "created": 1, "updated": 0, "failed": 0, "errors": [],
    }
    return client, bootstrap


class AvailabilityHelperTests(unittest.TestCase):

    def test_no_variants_treated_as_available(self):
        # Digital products, services, default-variant items.
        self.assertTrue(_availability_from_variants(None))
        self.assertTrue(_availability_from_variants([]))

    def test_any_in_stock_variant_marks_available(self):
        variants = [
            {"inventory_quantity": 0, "inventory_policy": "deny"},
            {"inventory_quantity": 3, "inventory_policy": "deny"},
        ]
        self.assertTrue(_availability_from_variants(variants))

    def test_continue_policy_overrides_zero_stock(self):
        # Merchant has opted to oversell — product stays available.
        variants = [{"inventory_quantity": 0, "inventory_policy": "continue"}]
        self.assertTrue(_availability_from_variants(variants))

    def test_all_oos_deny_marks_unavailable(self):
        variants = [
            {"inventory_quantity": 0, "inventory_policy": "deny"},
            {"inventory_quantity": 0, "inventory_policy": "deny"},
        ]
        self.assertFalse(_availability_from_variants(variants))


class PayloadTranslationTests(unittest.TestCase):

    def test_numeric_id_becomes_gid(self):
        payload = {
            "id": 7711223344,
            "title": "Champagne Slip",
            "body_html": "<p>Soft drape</p>",
            "vendor": "Nicobar",
            "variants": [
                {"id": 11, "title": "S", "price": "4188.00", "inventory_quantity": 5},
            ],
            "image": {"src": "https://cdn.shopify.com/..."},
        }
        result = CatalogProductSyncService._payload_to_bootstrap_input(payload)
        self.assertEqual(result["shopify_product_id"], "gid://shopify/Product/7711223344")
        self.assertEqual(result["title"], "Champagne Slip")
        self.assertEqual(result["description"], "<p>Soft drape</p>")
        self.assertEqual(result["vendor"], "Nicobar")
        self.assertEqual(result["price"], 4188.0)
        self.assertEqual(result["image_url"], "https://cdn.shopify.com/...")
        self.assertTrue(result["available_for_sale"])
        self.assertEqual(
            result["shopify_variant_ids"],
            {"S": "gid://shopify/ProductVariant/11"},
        )

    def test_admin_graphql_api_id_preferred_when_present(self):
        # When Shopify includes the GID directly, use it as-is.
        payload = {
            "id": 7711,
            "admin_graphql_api_id": "gid://shopify/Product/7711",
            "title": "X",
        }
        result = CatalogProductSyncService._payload_to_bootstrap_input(payload)
        self.assertEqual(result["shopify_product_id"], "gid://shopify/Product/7711")

    def test_missing_id_returns_none(self):
        # Defensive — webhook handler should fall back to a soft no-op.
        self.assertIsNone(
            CatalogProductSyncService._payload_to_bootstrap_input({"title": "x"})
        )

    def test_images_array_fallback(self):
        # Some webhooks include `images` but no `image` key.
        payload = {
            "id": 1,
            "title": "x",
            "images": [{"src": "https://example.com/a.jpg"}],
        }
        result = CatalogProductSyncService._payload_to_bootstrap_input(payload)
        self.assertEqual(result["image_url"], "https://example.com/a.jpg")

    def test_oos_payload_marks_unavailable(self):
        payload = {
            "id": 1, "title": "x",
            "variants": [
                {"id": 11, "title": "S", "inventory_quantity": 0, "inventory_policy": "deny"},
            ],
        }
        result = CatalogProductSyncService._payload_to_bootstrap_input(payload)
        self.assertFalse(result["available_for_sale"])


class UpsertWebhookTests(unittest.TestCase):

    def test_create_delegates_to_bootstrap(self):
        client, bootstrap = _make_clients()
        svc = CatalogProductSyncService(client, bootstrap_service=bootstrap)
        result = svc.apply_create_or_update(
            tenant_id="t_test",
            product_payload={
                "id": 1234,
                "title": "Black Linen",
                "body_html": "Soft.",
                "variants": [{"id": 99, "title": "M", "inventory_quantity": 1}],
            },
        )
        bootstrap.process_products.assert_called_once()
        call = bootstrap.process_products.call_args
        self.assertEqual(call.kwargs["tenant_id"], "t_test")
        self.assertEqual(len(call.kwargs["products"]), 1)
        # The forwarded product input has the gid-formatted id.
        self.assertEqual(
            call.kwargs["products"][0]["shopify_product_id"],
            "gid://shopify/Product/1234",
        )
        self.assertEqual(result["created"], 1)
        self.assertTrue(result["available_for_sale"])

    def test_update_writes_available_for_sale_on_both_tables(self):
        """Inventory state must land on both catalog_enriched (source
        of truth) AND catalog_item_embeddings (hot retrieval path)."""
        client, bootstrap = _make_clients()
        svc = CatalogProductSyncService(client, bootstrap_service=bootstrap)
        svc.apply_create_or_update(
            tenant_id="t_test",
            product_payload={
                "id": 1234,
                "title": "x",
                "variants": [{"id": 99, "title": "M", "inventory_quantity": 0, "inventory_policy": "deny"}],
            },
        )
        ce_updates = [
            c for c in client.update_one.call_args_list
            if c.args and c.args[0] == "catalog_enriched"
        ]
        cie_updates = [
            c for c in client.update_one.call_args_list
            if c.args and c.args[0] == "catalog_item_embeddings"
        ]
        self.assertEqual(len(ce_updates), 1)
        self.assertEqual(len(cie_updates), 1)
        self.assertFalse(ce_updates[0].kwargs["patch"]["available_for_sale"])
        self.assertFalse(cie_updates[0].kwargs["patch"]["available_for_sale"])

    def test_products_create_topic_revives_soft_deleted(self):
        """products/create on a previously-soft-deleted row should
        clear deleted_at so it comes back to life. Shopify lets
        merchants un-delete within 30 days."""
        client, bootstrap = _make_clients()
        svc = CatalogProductSyncService(client, bootstrap_service=bootstrap)
        svc.apply_create_or_update(
            tenant_id="t_test",
            product_payload={"id": 1234, "title": "x"},
            topic="products/create",
        )
        ce = [c for c in client.update_one.call_args_list if c.args[0] == "catalog_enriched"][0]
        self.assertIn("deleted_at", ce.kwargs["patch"])
        self.assertIsNone(ce.kwargs["patch"]["deleted_at"])

    def test_products_update_topic_preserves_soft_delete(self):
        """products/update arriving after a successful products/delete
        (out-of-order webhook retry) must NOT clear deleted_at —
        otherwise an explicitly-deleted product would silently come
        back. The patch should ONLY touch available_for_sale."""
        client, bootstrap = _make_clients()
        svc = CatalogProductSyncService(client, bootstrap_service=bootstrap)
        svc.apply_create_or_update(
            tenant_id="t_test",
            product_payload={"id": 1234, "title": "x"},
            topic="products/update",
        )
        ce = [c for c in client.update_one.call_args_list if c.args[0] == "catalog_enriched"][0]
        self.assertNotIn("deleted_at", ce.kwargs["patch"])
        # available_for_sale must still be written.
        self.assertIn("available_for_sale", ce.kwargs["patch"])

    def test_empty_topic_defaults_to_revive(self):
        """For backwards-compatibility with callers that don't thread
        the topic, an empty topic should preserve the pre-fix behavior
        (revive). Existing callers shouldn't break."""
        client, bootstrap = _make_clients()
        svc = CatalogProductSyncService(client, bootstrap_service=bootstrap)
        svc.apply_create_or_update(
            tenant_id="t_test",
            product_payload={"id": 1234, "title": "x"},
        )
        ce = [c for c in client.update_one.call_args_list if c.args[0] == "catalog_enriched"][0]
        self.assertIn("deleted_at", ce.kwargs["patch"])
        self.assertIsNone(ce.kwargs["patch"]["deleted_at"])

    def test_missing_id_payload_is_soft_no_op(self):
        client, bootstrap = _make_clients()
        svc = CatalogProductSyncService(client, bootstrap_service=bootstrap)
        result = svc.apply_create_or_update(
            tenant_id="t_test",
            product_payload={"title": "no id"},
        )
        bootstrap.process_products.assert_not_called()
        self.assertEqual(result["created"], 0)
        self.assertIn("no shopify_product_id", result["reason"])

    def test_empty_tenant_id_rejected(self):
        client, bootstrap = _make_clients()
        svc = CatalogProductSyncService(client, bootstrap_service=bootstrap)
        with self.assertRaises(ValueError):
            svc.apply_create_or_update(
                tenant_id="",
                product_payload={"id": 1, "title": "x"},
            )


class DeleteWebhookTests(unittest.TestCase):

    def test_delete_is_soft_delete(self):
        """The row must NOT be removed — set available_for_sale=false
        + deleted_at=now() and keep the embedding cost intact."""
        client, bootstrap = _make_clients()
        client.update_one.return_value = {"id": "row-1"}
        svc = CatalogProductSyncService(client, bootstrap_service=bootstrap)
        result = svc.apply_delete(
            tenant_id="t_test",
            shopify_product_id="gid://shopify/Product/777",
        )
        # No deletes were issued on the row tables.
        client.delete_one.assert_not_called()
        # Two updates: catalog_enriched + catalog_item_embeddings.
        ce = [c for c in client.update_one.call_args_list if c.args[0] == "catalog_enriched"]
        cie = [c for c in client.update_one.call_args_list if c.args[0] == "catalog_item_embeddings"]
        self.assertEqual(len(ce), 1)
        self.assertEqual(len(cie), 1)
        self.assertFalse(ce[0].kwargs["patch"]["available_for_sale"])
        self.assertIn("deleted_at", ce[0].kwargs["patch"])
        self.assertIsNotNone(ce[0].kwargs["patch"]["deleted_at"])
        self.assertTrue(result["deleted"])

    def test_delete_missing_id_no_op(self):
        client, bootstrap = _make_clients()
        svc = CatalogProductSyncService(client, bootstrap_service=bootstrap)
        result = svc.apply_delete(tenant_id="t_test", shopify_product_id="")
        client.update_one.assert_not_called()
        self.assertFalse(result["deleted"])


if __name__ == "__main__":
    unittest.main()
