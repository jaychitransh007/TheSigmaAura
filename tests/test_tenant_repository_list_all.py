"""F.3 — TenantRepository.list_all for the daily-sync cron.

The cron iterates over installed shops without holding per-shop
sessions. list_all is the enumeration primitive.

Tests cover:
  - Returns all tenant rows when no filter.
  - bootstrap_status='ready' filter excludes pending/syncing/failed.
  - Result is ordered by last_sync_at ASC NULLS FIRST so the
    stalest tenants get worked on first (important when the cron
    runs out of time budget).
"""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from platform_core.tenants import TenantRepository


class ListAllTests(unittest.TestCase):

    def test_no_filter_returns_all(self):
        client = MagicMock()
        client.select_many.return_value = [
            {"tenant_id": "t_a", "shopify_shop_domain": "a.myshopify.com"},
            {"tenant_id": "t_b", "shopify_shop_domain": "b.myshopify.com"},
        ]
        repo = TenantRepository(client)
        rows = repo.list_all()
        self.assertEqual(len(rows), 2)
        # No filters keyword in the select_many call.
        call = client.select_many.call_args
        self.assertIsNone(call.kwargs.get("filters"))

    def test_bootstrap_status_filter_passed_through(self):
        client = MagicMock()
        client.select_many.return_value = []
        repo = TenantRepository(client)
        repo.list_all(bootstrap_status="ready")
        call = client.select_many.call_args
        self.assertEqual(
            call.kwargs.get("filters"),
            {"bootstrap_status": "eq.ready"},
        )

    def test_ordered_stalest_first(self):
        """The cron processes tenants oldest-last_sync_at-first so a
        partial run still makes forward progress on stale shops."""
        client = MagicMock()
        client.select_many.return_value = []
        repo = TenantRepository(client)
        repo.list_all()
        call = client.select_many.call_args
        self.assertEqual(call.kwargs.get("order"), "last_sync_at.asc.nullsfirst")


if __name__ == "__main__":
    unittest.main()
