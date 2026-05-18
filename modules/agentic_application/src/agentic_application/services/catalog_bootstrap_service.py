"""Install-time catalog sync (F.2.2).

Owns the idempotent ingestion of a merchant's Shopify catalog into
``catalog_enriched`` + ``catalog_item_embeddings``, tenant-scoped via
F.2.0's ``tenants`` table and F.2.1's ``tenant_id`` columns.

The hard cost-bearing invariant (user-stated, 2026-05-18): **never
re-run the vision pipeline on a product that already has enrichment +
embeddings**. Re-installs and daily syncs walk the same product set
and must skip products that already exist. This service enforces
that with an existence check per product before any LLM call.

Current MVP (F.2.2): generates text embeddings only — vision
attribute enrichment (the expensive ~$0.003/product gpt-5-mini call)
is **deferred to F.2.2b**. Products inserted here have NULL on every
vision-derived attribute column (GarmentCategory, FabricDrape, etc.);
retrieval still works via cosine similarity on the text embedding,
just without hard-attribute filtering. F.2.2b backfills the rich
attributes lazily.

Threading: the public methods are safe to call from a FastAPI request
handler (they don't spawn background tasks). For a large catalog the
caller (Vibe-app or daily-sync cron) batches into chunks of 25-50
products per HTTP call.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from catalog.retrieval.config import CatalogEmbeddingConfig
from catalog.retrieval.embedder import CatalogEmbedder

from platform_core.supabase_rest import SupabaseRestClient

_log = logging.getLogger(__name__)


# Tag stripper for Shopify descriptionHtml. The embedder
# (text-embedding-3-small) treats `<p>` / `<br>` / etc. as input
# tokens — passing HTML directly inflates token count and worsens
# semantic clustering. Crude but sufficient: drop tags, collapse
# whitespace, decode the handful of HTML entities Shopify emits.
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_HTML_ENTITIES = {"&amp;": "&", "&lt;": "<", "&gt;": ">", "&quot;": '"', "&#39;": "'", "&nbsp;": " "}


def _strip_html(s: str) -> str:
    if not s:
        return ""
    cleaned = _HTML_TAG_RE.sub(" ", s)
    for k, v in _HTML_ENTITIES.items():
        cleaned = cleaned.replace(k, v)
    return re.sub(r"\s+", " ", cleaned).strip()


def _tenant_scoped_product_id(tenant_id: str, shopify_product_id: str) -> str:
    """Compose the global-unique product_id under the schema's
    UNIQUE constraint on `catalog_enriched.product_id`.

    The legacy single-tenant world stored product_id as the source
    retailer's bare id (e.g. "POWERLOOK_47880414134522"). Those have
    been globally unique by accident — only one tenant ingested them.

    Now that Vibe Test (and future tenants) will share the same table,
    we MUST prefix product_id by tenant_id so two tenants legitimately
    importing the same Shopify GID don't collide on insert. The bare
    shopify_product_id stays in its own column for cart wiring.
    """
    return f"{tenant_id}:{shopify_product_id}"


class CatalogBootstrapService:
    """Idempotent per-product upsert into the tenant's catalog.

    On a cache hit (tenant_id + shopify_product_id already in
    catalog_enriched) the row's mutable metadata is refreshed (price,
    inventory, image_url, shopify_variant_ids) and the embedding is
    left untouched — no LLM cost. On a cache miss a thin row is
    inserted and a text embedding is generated. Vision attributes
    stay NULL until F.2.2b lights them up.
    """

    def __init__(
        self,
        client: SupabaseRestClient,
        *,
        embedder: Optional[CatalogEmbedder] = None,
    ) -> None:
        self._client = client
        # Reuse the configured embedder if the caller threads one in
        # (the engine already constructs one for retrieval — sharing
        # avoids a duplicate OpenAI client). Otherwise build a default
        # 1536-dim text-embedding-3-small embedder.
        self._embedder = embedder or CatalogEmbedder(
            CatalogEmbeddingConfig(embedding_dimensions=1536),
        )

    def process_products(
        self,
        *,
        tenant_id: str,
        products: List[Dict[str, Any]],
        revive_soft_deleted: bool = False,
    ) -> Dict[str, Any]:
        """Idempotent batch upsert for a single tenant.

        Each product dict must contain at least:
            shopify_product_id  — the Shopify product GID or numeric id
            title               — for the embedding text
            description         — for the embedding text (HTML allowed; passed as-is)

        Optional fields (carried through to catalog_enriched):
            price, image_url, available_for_sale, shopify_variant_ids,
            vendor, product_url, raw_row_json

        ``revive_soft_deleted`` (default False): when True, a cache-hit
        on a row that has ``deleted_at`` set will clear it (resurrect
        the row). The F.3 daily cron passes True so a walk that
        re-sees a previously-deleted product (e.g. products/create
        webhook was dropped) corrects the engine state. The webhook
        path (F.4) passes False because products/update arriving
        out-of-order after products/delete must NOT revive.

        Returns:
            {
              "created":      <int>,   # new rows inserted
              "updated":      <int>,   # existing rows refreshed
              "failed":       <int>,   # processing errors per product
              "errors":       [{shopify_product_id, error}, ...],
            }
        """
        if not tenant_id or not str(tenant_id).strip():
            raise ValueError("process_products: tenant_id is required")

        created = 0
        updated = 0
        errors: List[Dict[str, str]] = []

        # Embedding generation is the most expensive step. Batch
        # the new-product subset into a single OpenAI call rather
        # than per-product round-trips.
        new_product_inputs: List[Dict[str, Any]] = []

        for product in products:
            shopify_pid = str(
                product.get("shopify_product_id")
                or product.get("id")
                or ""
            ).strip()
            if not shopify_pid:
                errors.append({"shopify_product_id": "", "error": "missing shopify_product_id"})
                continue

            try:
                existing = self._client.select_one(
                    "catalog_enriched",
                    filters={
                        "tenant_id": f"eq.{tenant_id}",
                        "shopify_product_id": f"eq.{shopify_pid}",
                    },
                )

                if existing:
                    # Cache hit — refresh metadata, skip embedding. No
                    # LLM cost. The mutable fields are the merchant-
                    # facing data that changes day-to-day (price,
                    # stock); the vision attributes stay frozen.
                    patch = self._mutable_metadata_patch(
                        product,
                        revive_soft_deleted=revive_soft_deleted,
                    )
                    if patch:
                        self._client.update_one(
                            "catalog_enriched",
                            filters={"id": f"eq.{existing['id']}"},
                            patch=patch,
                        )
                    # F.3 daily-cron revival event — if the cache-hit
                    # row was previously soft-deleted and this call
                    # opted into revival (cron path passes True), tick
                    # the catalog-status-change counter so dashboards
                    # can distinguish webhook-driven revives (real-
                    # time) from cron-walk recovery (drift catch-up).
                    if revive_soft_deleted and existing.get("deleted_at"):
                        try:
                            from platform_core.metrics import (
                                observe_catalog_status_change,
                            )
                            observe_catalog_status_change(action="revived")
                        except Exception:  # noqa: BLE001
                            pass
                    # Mirror availability to the embeddings table —
                    # the retrieval RPC filters on
                    # catalog_item_embeddings.available_for_sale so
                    # the source of truth on catalog_enriched alone
                    # isn't enough for customer-facing recs. Only
                    # mirror when the product carried an explicit
                    # availability signal (the cron walk and F.4
                    # webhooks both do), otherwise skip to avoid an
                    # unnecessary PATCH round-trip.
                    if "available_for_sale" in product:
                        cie_patch: Dict[str, Any] = {
                            "available_for_sale": bool(
                                product.get("available_for_sale", True)
                            ),
                        }
                        self._client.update_one(
                            "catalog_item_embeddings",
                            filters={
                                "tenant_id": f"eq.{tenant_id}",
                                "product_id": (
                                    "eq."
                                    + _tenant_scoped_product_id(tenant_id, shopify_pid)
                                ),
                            },
                            patch=cie_patch,
                        )
                    updated += 1
                    continue

                # Cache miss — queue for embedding generation. Defer
                # the actual insert until we've batched the embedding
                # call.
                new_product_inputs.append({
                    "product": product,
                    "shopify_pid": shopify_pid,
                    "embedding_text": self._build_embedding_text(product),
                })
            except Exception as exc:  # noqa: BLE001
                errors.append({
                    "shopify_product_id": shopify_pid,
                    "error": f"{type(exc).__name__}: {exc}",
                })

        # Batch-embed the new products (single OpenAI call) then
        # insert one row each into catalog_enriched + catalog_item_
        # embeddings.
        if new_product_inputs:
            try:
                texts = [item["embedding_text"] for item in new_product_inputs]
                embeddings = self._embedder.embed_texts(texts)
            except Exception as exc:  # noqa: BLE001
                # Whole batch failed — every product in the batch
                # gets an error entry. Caller can retry the batch.
                msg = f"embed_texts: {type(exc).__name__}: {exc}"
                for item in new_product_inputs:
                    errors.append({"shopify_product_id": item["shopify_pid"], "error": msg})
                _log.exception("CatalogBootstrap: embedding batch failed for tenant=%s", tenant_id)
                return {
                    "created": created,
                    "updated": updated,
                    "failed": len(errors),
                    "errors": errors,
                }

            for item, embedding in zip(new_product_inputs, embeddings, strict=True):
                shopify_pid = item["shopify_pid"]
                product = item["product"]
                try:
                    enriched_row = self._insert_catalog_enriched(
                        tenant_id=tenant_id,
                        shopify_pid=shopify_pid,
                        product=product,
                    )
                    self._insert_catalog_item_embedding(
                        tenant_id=tenant_id,
                        catalog_row_id=str(enriched_row.get("id") or ""),
                        shopify_pid=shopify_pid,
                        embedding=embedding,
                        document_text=item["embedding_text"],
                        product=product,
                    )
                    created += 1
                except Exception as exc:  # noqa: BLE001
                    errors.append({
                        "shopify_product_id": shopify_pid,
                        "error": f"insert: {type(exc).__name__}: {exc}",
                    })

        return {
            "created": created,
            "updated": updated,
            "failed": len(errors),
            "errors": errors,
        }

    # ── private helpers ────────────────────────────────────────────────

    def _build_embedding_text(self, product: Dict[str, Any]) -> str:
        """Build the text fed to the embedder for a new product.

        Description arrives as Shopify `descriptionHtml` — strip HTML
        tags so the embedder isn't tokenising `<p>` / `<br>` /
        entities. Title + vendor + description joined by newlines.

        F.2.2b will extend this once vision attributes are also
        available (interleaving GarmentCategory / NecklineType into
        the embedding text to bias retrieval).
        """
        title = str(product.get("title") or "").strip()
        description = _strip_html(str(product.get("description") or ""))
        vendor = str(product.get("vendor") or "").strip()
        parts = [p for p in (title, vendor, description) if p]
        return "\n".join(parts) if parts else "(no description)"

    def _mutable_metadata_patch(
        self,
        product: Dict[str, Any],
        *,
        revive_soft_deleted: bool = False,
    ) -> Dict[str, Any]:
        """Subset of fields that should refresh on every sync.

        These are merchant-side data points that change over time
        (price reductions, restocks). Vision attributes are NOT here
        — they're computed once and stable.

        When ``revive_soft_deleted`` is True, the patch also clears
        ``deleted_at`` so a row that was previously marked deleted
        (via the F.4 products/delete webhook) but is now visible in
        the F.3 cron walk gets resurrected. The F.4 webhook upsert
        path passes False here so that an out-of-order products/update
        retry after a products/delete doesn't undo the delete; its
        topic-aware revival lives in CatalogProductSyncService.
        """
        patch: Dict[str, Any] = {}
        if "price" in product and product["price"] is not None:
            patch["price"] = product["price"]
        if "image_url" in product and product["image_url"]:
            patch["images_0_src"] = product["image_url"]
        if "shopify_variant_ids" in product and product["shopify_variant_ids"]:
            patch["shopify_variant_ids"] = product["shopify_variant_ids"]
        # F.4 column. Only write when the caller actually provided a
        # signal (the cron walk and F.4 webhooks both do); skipping
        # the write when the column is absent preserves the existing
        # value rather than overwriting with a guessed default.
        if "available_for_sale" in product:
            patch["available_for_sale"] = bool(
                product.get("available_for_sale", True)
            )
        if revive_soft_deleted:
            # Don't gate on whether the row was actually deleted —
            # PostgREST is happy to update a NULL column to NULL, and
            # checking deleted_at first would cost an extra SELECT
            # per cache-hit row.
            patch["deleted_at"] = None
        return patch

    def _insert_catalog_enriched(
        self,
        *,
        tenant_id: str,
        shopify_pid: str,
        product: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Thin insert into catalog_enriched. Vision attributes stay NULL.

        F.2.2b's vision pipeline will UPDATE the row to populate
        GarmentCategory, FabricDrape, and the dozens of other
        attribute columns. Until then, retrieval works on text
        embedding only.
        """
        payload: Dict[str, Any] = {
            "tenant_id": tenant_id,
            "shopify_product_id": shopify_pid,
            "title": str(product.get("title") or ""),
            "description": str(product.get("description") or ""),
            "url": str(product.get("product_url") or product.get("url") or ""),
            "images_0_src": str(product.get("image_url") or ""),
            "row_status": "pending_enrichment",
        }
        if product.get("price") is not None:
            payload["price"] = product["price"]
        if product.get("shopify_variant_ids"):
            payload["shopify_variant_ids"] = product["shopify_variant_ids"]
        if product.get("raw_row_json"):
            payload["raw_row_json"] = product["raw_row_json"]
        # F.4 availability — write on insert so a freshly-bootstrapped
        # row that's actually out-of-stock doesn't sit at the table's
        # default TRUE until the next webhook fires. Only write when
        # the caller actually provided a signal.
        if "available_for_sale" in product:
            payload["available_for_sale"] = bool(
                product.get("available_for_sale", True)
            )
        # product_id is globally UNIQUE under the catalog_enriched
        # schema constraint. Prefix with tenant_id so two tenants
        # legitimately importing the same Shopify GID can't collide
        # on insert (PG error 23505 otherwise). bare shopify_product_id
        # stays in its own column for cart wiring.
        payload["product_id"] = _tenant_scoped_product_id(tenant_id, shopify_pid)
        return self._client.insert_one("catalog_enriched", payload)

    def _insert_catalog_item_embedding(
        self,
        *,
        tenant_id: str,
        catalog_row_id: str,
        shopify_pid: str,
        embedding: List[float],
        document_text: str,
        product: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Insert the embedding row paired with the catalog_enriched row.

        Vision-derived filter columns (garment_category, FabricDrape,
        etc.) stay NULL — F.2.2b populates them. The retrieval RPC
        treats missing filter columns as "no filter on this axis", so
        cosine similarity is the only ranking signal until then.
        """
        from catalog.retrieval.vector_store import _vector_literal

        payload: Dict[str, Any] = {
            "tenant_id": tenant_id,
            # Same tenant-scoped product_id as catalog_enriched so the
            # hydration join (cie.product_id ↔ ce.product_id) lines up.
            "product_id": _tenant_scoped_product_id(tenant_id, shopify_pid),
            "catalog_row_id": catalog_row_id,
            "embedding_model": "text-embedding-3-small",
            "embedding_dimensions": 1536,
            "document_text": document_text,
            "embedding": _vector_literal(embedding),
            # metadata_json holds raw JSON snapshot — minimal until
            # F.2.2b backfills the attribute columns.
            "metadata_json": {
                "source": "shopify_bootstrap",
                "bootstrap_version": "F.2.2",
                "title": str(product.get("title") or ""),
                "vendor": str(product.get("vendor") or ""),
            },
        }
        if product.get("price") is not None:
            payload["price"] = product["price"]
        # F.4 availability mirror — kept on this table because the
        # retrieval RPC filters on it. Default to True if the caller
        # didn't pass a signal (matches the column's NOT NULL DEFAULT).
        if "available_for_sale" in product:
            payload["available_for_sale"] = bool(
                product.get("available_for_sale", True)
            )
        return self._client.insert_one("catalog_item_embeddings", payload)
