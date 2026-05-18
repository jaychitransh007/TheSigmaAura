"""Tenant identity for the multi-tenant Vibe deployment (F.2.0).

Every Shopify shop that installs Vibe gets an opaque ``tenant_id`` of
the form ``t_<base64url-22-chars>``. The id is stable across reinstalls
(derived deterministically from the shop's domain) but unguessable from
the outside — useful for logs and identifiers without revealing the
shop name.

Layered on top of:

* ``tenants`` table — see migration ``20260518000000_f20_f21_tenants_and_retrieval.sql``.
  One row per installed shop, tracks bootstrap status and product
  counts.
* ``catalog_item_embeddings.tenant_id`` — every retrieval query filters
  by this. See ``match_catalog_item_embeddings_v2`` in the same
  migration.

This module is intentionally thin. The engine doesn't store any
auth-bearing material here; the tenant_id is just a partition key.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import secrets
import struct
import time
from typing import Any, Dict, Optional

from platform_core.supabase_rest import SupabaseRestClient

_log = logging.getLogger(__name__)


# TheSigmaVibe's tenant_id, locked when the catalog was first imported
# (A.1 + A.2 backfill, 2026-05-15). Engine code that falls back to a
# "default tenant" during the F.2 rollout uses this — kept here as a
# named constant so the fallback is greppable and removable once every
# entry point passes tenant_id explicitly.
THESIGMAVIBE_TENANT_ID = "t_Oq0BSHnewiEAAAAAagWWlmnV-0sJmcGk"


def derive_tenant_id(shop_domain: str) -> str:
    """Derive a stable opaque tenant_id from a Shopify shop domain.

    The scheme (from ``docs/OPEN_TASKS.md``):

        tenant_id = "t_" + base64url(
            sha256(shop_domain)[:8]      # 8 bytes: shop fingerprint
          + uint64_be(unix_timestamp)    # 8 bytes: creation time
          + random_bytes(8)              # 8 bytes: entropy
        )

    Two notes that make this less obviously deterministic than the
    scheme suggests:

    * The original scheme included a creation timestamp + random bytes,
      so the id is unique per derivation call — not stable across
      installs. That's by design: a merchant uninstalling and
      reinstalling gets a *new* tenant_id and a clean slate. This
      function is the **assignment** primitive; once written to the
      tenants table, that id is the canonical one for the shop.
    * Callers should NEVER re-derive a tenant_id for an existing shop.
      Use ``get_or_create_tenant`` instead, which looks up the existing
      row first and only derives a new id on first install.

    Args:
        shop_domain: The merchant's ``*.myshopify.com`` domain. Case-
            normalised internally.

    Returns:
        A 34-character ``t_``-prefixed opaque id.
    """
    if not shop_domain or not shop_domain.strip():
        raise ValueError("derive_tenant_id: shop_domain is required")
    normalized = shop_domain.strip().lower()
    fingerprint = hashlib.sha256(normalized.encode("utf-8")).digest()[:8]
    timestamp_bytes = struct.pack(">Q", int(time.time()))
    entropy = secrets.token_bytes(8)
    raw = fingerprint + timestamp_bytes + entropy
    return "t_" + base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


class TenantRepository:
    """CRUD helpers for the ``tenants`` table.

    All callers should go through this rather than hitting the table
    directly so the tenant_id <-> shop_domain mapping stays consistent.
    """

    def __init__(self, client: SupabaseRestClient) -> None:
        self._client = client

    def get_by_shop_domain(self, shop_domain: str) -> Optional[Dict[str, Any]]:
        """Look up the tenants row for a Shopify shop domain.

        Returns ``None`` if the shop has never installed Vibe.
        """
        normalized = shop_domain.strip().lower()
        return self._client.select_one(
            "tenants",
            filters={"shopify_shop_domain": f"eq.{normalized}"},
        )

    def get_by_tenant_id(self, tenant_id: str) -> Optional[Dict[str, Any]]:
        return self._client.select_one(
            "tenants",
            filters={"tenant_id": f"eq.{tenant_id}"},
        )

    def get_or_create(
        self,
        shop_domain: str,
        *,
        shopify_shop_gid: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Idempotent lookup-or-create. Returns the tenants row.

        On first install (no existing row), derives a fresh tenant_id
        via ``derive_tenant_id`` and inserts a ``pending`` row. The
        catalog-sync orchestrator (F.2.2) transitions ``bootstrap_status``
        through ``syncing`` and finally ``ready``.

        Idempotent: calling repeatedly with the same shop_domain
        returns the same row.
        """
        existing = self.get_by_shop_domain(shop_domain)
        if existing:
            # Backfill shop_gid if we now know it and didn't before —
            # an install flow may know the gid on second contact but
            # not the first.
            if shopify_shop_gid and not existing.get("shopify_shop_gid"):
                updated = self._client.update_one(
                    "tenants",
                    filters={"tenant_id": f"eq.{existing['tenant_id']}"},
                    patch={"shopify_shop_gid": shopify_shop_gid},
                )
                if updated:
                    return updated
            return existing

        new_tenant_id = derive_tenant_id(shop_domain)
        normalized = shop_domain.strip().lower()
        payload: Dict[str, Any] = {
            "tenant_id": new_tenant_id,
            "shopify_shop_domain": normalized,
            "bootstrap_status": "pending",
            "product_count": 0,
        }
        if shopify_shop_gid:
            payload["shopify_shop_gid"] = shopify_shop_gid
        row = self._client.insert_one("tenants", payload)
        _log.info(
            "tenants.get_or_create: created tenant_id=%s for shop_domain=%s",
            new_tenant_id, normalized,
        )
        return row

    def set_bootstrap_status(
        self,
        tenant_id: str,
        status: str,
        *,
        product_count: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        """Update a tenant's bootstrap_status (and optionally product_count).

        Status values are constrained by the CHECK in the migration:
        'pending', 'syncing', 'ready', 'failed'.
        """
        if status not in ("pending", "syncing", "ready", "failed"):
            raise ValueError(f"set_bootstrap_status: invalid status {status!r}")
        patch: Dict[str, Any] = {"bootstrap_status": status}
        if status == "ready":
            patch["bootstrap_completed_at"] = _now_iso()
            patch["last_sync_at"] = _now_iso()
        if product_count is not None:
            patch["product_count"] = int(product_count)
        return self._client.update_one(
            "tenants",
            filters={"tenant_id": f"eq.{tenant_id}"},
            patch=patch,
        )

    def set_theme_overrides(
        self,
        tenant_id: str,
        overrides: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Replace the tenant's theme_overrides JSONB blob.

        Called from vibe-app on install + on `themes/update` webhooks.
        Pass an empty dict to clear (Vibe will fall back to Confident
        Luxe defaults). Empty-string fields are stripped before write
        so a partial probe doesn't store {"font_body": ""} keys that
        downstream consumers would mistake for "explicitly set to
        empty" instead of "not provided".
        """
        from datetime import datetime, timezone

        cleaned: Dict[str, Any] = {}
        for k, v in (overrides or {}).items():
            if v is None:
                continue
            if isinstance(v, str) and not v.strip():
                continue
            cleaned[k] = v
        if cleaned:
            cleaned["updated_at_iso"] = datetime.now(timezone.utc).isoformat()
        return self._client.update_one(
            "tenants",
            filters={"tenant_id": f"eq.{tenant_id}"},
            patch={"theme_overrides": cleaned or None},
        )

    def touch_last_sync(
        self,
        tenant_id: str,
        *,
        product_count: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        """Bump ``last_sync_at`` after a successful daily sync run."""
        patch: Dict[str, Any] = {"last_sync_at": _now_iso()}
        if product_count is not None:
            patch["product_count"] = int(product_count)
        return self._client.update_one(
            "tenants",
            filters={"tenant_id": f"eq.{tenant_id}"},
            patch=patch,
        )

    def list_all(
        self,
        *,
        bootstrap_status: Optional[str] = None,
    ) -> list[Dict[str, Any]]:
        """Enumerate every tenant row.

        Used by the F.3 daily-sync cron to iterate over installed
        shops without holding per-shop sessions. Optionally filtered
        by bootstrap_status (typically 'ready' — there's nothing for
        the daily sync to do on a tenant that hasn't finished
        bootstrap yet).
        """
        filters: Dict[str, str] = {}
        if bootstrap_status:
            filters["bootstrap_status"] = f"eq.{bootstrap_status}"
        return self._client.select_many(
            "tenants",
            filters=filters or None,
            columns="tenant_id,shopify_shop_domain,bootstrap_status,product_count,last_sync_at",
            order="last_sync_at.asc.nullsfirst",
        )


def _now_iso() -> str:
    """ISO-8601 UTC string suitable for Postgres timestamptz columns."""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def resolve_tenant_id_or_default(
    repo: TenantRepository,
    *,
    shop_domain: Optional[str],
    channel: str,
) -> str:
    """Resolve the tenant_id for an incoming request, with a backward-
    compat fallback for the legacy ``web`` channel.

    Branch behaviour:

    * ``shop_domain`` provided → look up via tenants table; if found,
      return the row's tenant_id. If the shop hasn't installed Vibe
      yet, raise ``ValueError`` — engine callers should never reach
      retrieval before the install flow has run.
    * ``shop_domain`` missing AND channel is ``"web"`` (legacy direct-
      engine UI / agentic-application admin) → fall back to TheSigmaVibe.
      Logged as a DeprecationWarning so the fallback usage is visible
      in dashboards.
    * ``shop_domain`` missing AND channel is anything else (especially
      ``"vibe_storefront"``) → raise. Vibe customers MUST be tenant-
      scoped; serving them from the default tenant would leak the wrong
      catalog into the wrong store.
    """
    if shop_domain and shop_domain.strip():
        tenant = repo.get_by_shop_domain(shop_domain)
        if tenant:
            return str(tenant["tenant_id"])
        raise ValueError(
            f"resolve_tenant_id: shop {shop_domain!r} has no tenant row; "
            "install flow must run before retrieval."
        )

    if channel == "web":
        _log.warning(
            "resolve_tenant_id: shop_domain missing on channel=web; "
            "falling back to TheSigmaVibe tenant. Pass shop_domain to "
            "remove this warning.",
        )
        return THESIGMAVIBE_TENANT_ID

    raise ValueError(
        f"resolve_tenant_id: channel={channel!r} requires shop_domain; "
        "refusing to default to a single tenant."
    )
