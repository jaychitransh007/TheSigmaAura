"""Real-time per-product sync from Shopify webhooks (F.4).

Bootstrap (F.2.2) and the daily cron (F.3) walk the merchant's
catalog in passes — authoritative for product existence but lag
inventory by up to a day. Shopify's `products/*` webhooks land
on vibe-app in near-real-time and forward here so we can:

  - products/create  → insert a fresh catalog_enriched row (same
                       idempotent path as bootstrap-batch). Vision
                       enrichment picks it up via the daily cron.
  - products/update  → refresh mutable metadata (price, image,
                       variants) AND availability. The hot path
                       for inventory accuracy.
  - products/delete  → soft-delete: available_for_sale=false +
                       deleted_at=now(). Row stays so an accidental
                       delete in Shopify can be revived without
                       re-running vision enrichment.

The webhook payload from Shopify's REST product topics carries the
full product including variants — same shape we already accept at
``BootstrapBatchRequest.products[]``. This service translates that
shape internally and delegates the insert path to
``CatalogBootstrapService`` so the embedding logic stays in one
place.

Idempotency: every webhook call is safe to receive more than once.
Shopify retries failed webhooks for up to 48h, and we may also
catch a self-fired duplicate from `products/update` if the merchant
saves twice in quick succession. Re-running this code on the same
payload is a no-op for unchanged fields and a single UPDATE for
changed ones.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from platform_core.supabase_rest import SupabaseRestClient

from .catalog_bootstrap_service import CatalogBootstrapService

_log = logging.getLogger(__name__)


def _availability_from_variants(variants: Optional[List[Dict[str, Any]]]) -> bool:
    """A product is "available" if ANY variant is in stock OR if the
    payload has no variant inventory data at all.

    Shopify's products/* webhook payload includes ``variants[]`` with
    ``inventory_quantity`` per variant. A variant is in stock iff
    ``inventory_quantity > 0`` OR ``inventory_policy='continue'``
    (the merchant explicitly oversells). Missing variants array means
    the product is variant-less (digital, services) — we treat it as
    available.
    """
    if not variants:
        return True
    for v in variants:
        # Continue selling when sold out → always available.
        policy = str(v.get("inventory_policy") or "").strip().lower()
        if policy == "continue":
            return True
        qty = v.get("inventory_quantity")
        if isinstance(qty, (int, float)) and qty > 0:
            return True
    return False


class CatalogProductSyncService:
    """Per-product webhook applier. Lives next to (and delegates into)
    CatalogBootstrapService."""

    def __init__(
        self,
        client: SupabaseRestClient,
        *,
        bootstrap_service: CatalogBootstrapService,
    ) -> None:
        self._client = client
        self._bootstrap = bootstrap_service

    def apply_create_or_update(
        self,
        *,
        tenant_id: str,
        product_payload: Dict[str, Any],
        topic: str = "",
    ) -> Dict[str, Any]:
        """Handle a products/create or products/update webhook.

        The two topics share most logic — Shopify's payload format is
        identical, and our upsert is idempotent. Going through
        ``CatalogBootstrapService.process_products`` handles both
        cache-hit refresh (existing row → metadata patch) and
        cache-miss insert (new row → embedding + insert).

        ``topic`` should be the verbatim Shopify topic ("products/
        create" or "products/update"); it gates whether to clear a
        prior soft-deletion. A genuine products/create revives a
        soft-deleted row (Shopify lets merchants un-delete within
        30 days); products/update arriving after a products/delete
        — a retry-order edge case — must NOT revive, otherwise an
        explicitly-deleted product would silently come back.

        Returns the bootstrap_service result dict ({created, updated,
        failed, errors}) plus the resolved availability flag.
        """
        if not tenant_id or not tenant_id.strip():
            raise ValueError("apply_create_or_update: tenant_id is required")

        # Normalise topic to the metric-label form (drops "products/"
        # prefix). Empty / unrecognised → "upsert" so metrics don't
        # explode on a future topic addition.
        topic_label = topic.strip().lower().replace("products/", "")
        if topic_label not in ("create", "update"):
            topic_label = "upsert"

        bootstrap_input = self._payload_to_bootstrap_input(product_payload)
        if not bootstrap_input:
            _log.warning(
                "CatalogProductSync: webhook no-op tenant=%s topic=%s reason=no_shopify_product_id",
                tenant_id, topic or "(unset)",
            )
            try:
                from platform_core.metrics import observe_product_webhook
                observe_product_webhook(topic=topic_label, status="no_op")
            except Exception:  # noqa: BLE001
                pass
            return {
                "created": 0,
                "updated": 0,
                "failed": 0,
                "errors": [],
                "available_for_sale": True,
                "reason": "no shopify_product_id in payload",
            }

        # Run the bootstrap path. Cache-hit = metadata refresh, no
        # LLM cost. Cache-miss = thin row insert + text embedding.
        bootstrap_result = self._bootstrap.process_products(
            tenant_id=tenant_id,
            products=[bootstrap_input],
        )

        # Now explicitly write available_for_sale on BOTH tables. The
        # bootstrap service intentionally avoids this column (it
        # didn't exist pre-F.4); we own it here.
        available = bool(bootstrap_input.get("available_for_sale", True))
        shopify_pid = str(bootstrap_input["shopify_product_id"])

        # catalog_enriched: source of truth. Conditionally clear
        # deleted_at — only on products/create or when topic is
        # unknown (defensive default for callers that don't thread
        # the topic). On products/update, leave deleted_at as-is so
        # an out-of-order retry can't resurrect an intentionally-
        # deleted product.
        ce_patch: Dict[str, Any] = {"available_for_sale": available}
        normalized_topic = topic.strip().lower()
        will_revive = normalized_topic != "products/update"
        if will_revive:
            # products/create → revive. Empty topic → defensive
            # revive (preserves pre-fix behaviour).
            ce_patch["deleted_at"] = None
        # Pre-check if the row was actually soft-deleted, so the
        # catalog-status-change counter only ticks "revived" on a
        # genuine state transition (not on every products/create
        # for a never-deleted row).
        was_deleted = False
        if will_revive:
            try:
                existing = self._client.select_one(
                    "catalog_enriched",
                    filters={
                        "tenant_id": f"eq.{tenant_id}",
                        "shopify_product_id": f"eq.{shopify_pid}",
                    },
                )
                was_deleted = bool(existing and existing.get("deleted_at"))
            except Exception:  # noqa: BLE001
                # SELECT failure shouldn't block the UPDATE; counter
                # just won't tick this time.
                was_deleted = False
        self._client.update_one(
            "catalog_enriched",
            filters={
                "tenant_id": f"eq.{tenant_id}",
                "shopify_product_id": f"eq.{shopify_pid}",
            },
            patch=ce_patch,
        )
        if was_deleted:
            try:
                from platform_core.metrics import observe_catalog_status_change
                observe_catalog_status_change(action="revived")
            except Exception:  # noqa: BLE001
                pass
        # catalog_item_embeddings: the hot retrieval path uses this.
        self._client.update_one(
            "catalog_item_embeddings",
            filters={
                "tenant_id": f"eq.{tenant_id}",
                "product_id": f"eq.{tenant_id}:{shopify_pid}",
            },
            patch={"available_for_sale": available},
        )

        _log.info(
            "CatalogProductSync: webhook upsert tenant=%s topic=%s shopify_product_id=%s "
            "created=%d updated=%d failed=%d available=%s",
            tenant_id, topic or "(unset)", shopify_pid,
            int(bootstrap_result.get("created", 0) or 0),
            int(bootstrap_result.get("updated", 0) or 0),
            int(bootstrap_result.get("failed", 0) or 0),
            available,
        )
        try:
            from platform_core.metrics import observe_product_webhook
            observe_product_webhook(topic=topic_label, status="ok")
        except Exception:  # noqa: BLE001
            pass

        return {
            **bootstrap_result,
            "available_for_sale": available,
            "shopify_product_id": shopify_pid,
        }

    def apply_delete(
        self,
        *,
        tenant_id: str,
        shopify_product_id: str,
    ) -> Dict[str, Any]:
        """Handle a products/delete webhook. Soft-delete only.

        Shopify's products/delete payload is just ``{id}`` — no
        variants, no metadata. We mark the row as unavailable +
        soft-deleted; the row itself stays so:

          - the vision-enrichment cost we already paid isn't wasted
          - an accidental delete (Shopify lets merchants un-delete
            within 30 days) can be rolled back via the next
            products/create webhook without any LLM cost.
        """
        if not tenant_id or not tenant_id.strip():
            raise ValueError("apply_delete: tenant_id is required")
        shopify_pid = str(shopify_product_id or "").strip()
        if not shopify_pid:
            _log.warning(
                "CatalogProductSync: webhook delete no-op tenant=%s reason=missing_shopify_product_id",
                tenant_id,
            )
            try:
                from platform_core.metrics import observe_product_webhook
                observe_product_webhook(topic="delete", status="no_op")
            except Exception:  # noqa: BLE001
                pass
            return {"deleted": False, "reason": "missing shopify_product_id"}

        now_iso = datetime.now(timezone.utc).isoformat()
        cat_row = self._client.update_one(
            "catalog_enriched",
            filters={
                "tenant_id": f"eq.{tenant_id}",
                "shopify_product_id": f"eq.{shopify_pid}",
            },
            patch={
                "available_for_sale": False,
                "deleted_at": now_iso,
            },
        )
        # Mirror to the embeddings table so the retrieval RPC stops
        # surfacing this row immediately.
        self._client.update_one(
            "catalog_item_embeddings",
            filters={
                "tenant_id": f"eq.{tenant_id}",
                "product_id": f"eq.{tenant_id}:{shopify_pid}",
            },
            patch={"available_for_sale": False},
        )
        _log.info(
            "CatalogProductSync: webhook delete tenant=%s shopify_product_id=%s deleted=%s",
            tenant_id, shopify_pid, bool(cat_row),
        )
        try:
            from platform_core.metrics import (
                observe_catalog_status_change,
                observe_product_webhook,
            )
            observe_product_webhook(topic="delete", status="ok")
            if cat_row:
                # Only tick if the row actually existed and was
                # transitioned; webhook-for-unknown-shopify-id won't
                # update any row and shouldn't count as a delete event.
                observe_catalog_status_change(action="soft_deleted")
        except Exception:  # noqa: BLE001
            pass
        return {
            "deleted": bool(cat_row),
            "shopify_product_id": shopify_pid,
        }

    # ─── helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _payload_to_bootstrap_input(
        payload: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Translate a Shopify products/* webhook payload to the
        BootstrapProductInput shape.

        Webhook payload (REST style) uses numeric ids and a different
        shape than the Admin GraphQL response that bootstrap-batch
        sees from the vibe-app chunk processor. Normalise to the
        shared input format so the bootstrap service doesn't need to
        know about webhook-specific quirks.
        """
        # Shopify's REST product id is numeric; the engine stores
        # `gid://shopify/Product/<n>`. Use the GID format for
        # cross-API consistency with the Admin-GraphQL path.
        product_id_raw = payload.get("id") or payload.get("admin_graphql_api_id")
        if not product_id_raw:
            return None
        if isinstance(product_id_raw, (int, float)):
            shopify_pid = f"gid://shopify/Product/{int(product_id_raw)}"
        else:
            shopify_pid = str(product_id_raw).strip()
            if not shopify_pid:
                return None

        variants = payload.get("variants") or []
        # Variant gid format: gid://shopify/ProductVariant/<n>.
        # Title is the size label for apparel; for default-variant
        # products it's literally "Default Title".
        variant_map: Dict[str, str] = {}
        first_price: Optional[float] = None
        for v in variants:
            vid_raw = v.get("admin_graphql_api_id") or v.get("id")
            if isinstance(vid_raw, (int, float)):
                vid = f"gid://shopify/ProductVariant/{int(vid_raw)}"
            else:
                vid = str(vid_raw or "").strip()
            size = str(v.get("title") or "").strip()
            if size and vid:
                variant_map[size] = vid
            if first_price is None:
                price_raw = v.get("price")
                if price_raw is not None:
                    try:
                        first_price = float(price_raw)
                    except (TypeError, ValueError):
                        pass

        image_url = ""
        image = payload.get("image") or {}
        if isinstance(image, dict):
            image_url = str(image.get("src") or "")
        if not image_url:
            images = payload.get("images") or []
            if images and isinstance(images, list):
                first_img = images[0]
                if isinstance(first_img, dict):
                    image_url = str(first_img.get("src") or "")

        handle = str(payload.get("handle") or "").strip()

        return {
            "shopify_product_id": shopify_pid,
            "title": str(payload.get("title") or ""),
            # body_html is the REST product description field — the
            # bootstrap service strips HTML before embedding.
            "description": str(payload.get("body_html") or ""),
            "vendor": str(payload.get("vendor") or ""),
            "price": first_price,
            "image_url": image_url,
            "product_url": handle,  # relative; engine doesn't compose absolute URLs
            "available_for_sale": _availability_from_variants(variants),
            "shopify_variant_ids": variant_map,
        }
