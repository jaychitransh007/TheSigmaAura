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
from typing import Any, Dict, List, Optional

from catalog.retrieval.config import CatalogEmbeddingConfig
from catalog.retrieval.embedder import CatalogEmbedder

from platform_core.supabase_rest import SupabaseRestClient

_log = logging.getLogger(__name__)


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
    ) -> Dict[str, Any]:
        """Idempotent batch upsert for a single tenant.

        Each product dict must contain at least:
            shopify_product_id  — the Shopify product GID or numeric id
            title               — for the embedding text
            description         — for the embedding text (HTML allowed; passed as-is)

        Optional fields (carried through to catalog_enriched):
            price, image_url, available_for_sale, shopify_variant_ids,
            vendor, product_url, raw_row_json

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
                    patch = self._mutable_metadata_patch(product)
                    if patch:
                        self._client.update_one(
                            "catalog_enriched",
                            filters={"id": f"eq.{existing['id']}"},
                            patch=patch,
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

        Title + description is the canonical pattern; F.2.2b will
        extend this once vision attributes are also available
        (e.g. interleaving GarmentCategory / NecklineType into the
        embedding text to bias retrieval).
        """
        title = str(product.get("title") or "").strip()
        description = str(product.get("description") or "").strip()
        vendor = str(product.get("vendor") or "").strip()
        parts = [p for p in (title, vendor, description) if p]
        return "\n".join(parts) if parts else "(no description)"

    def _mutable_metadata_patch(self, product: Dict[str, Any]) -> Dict[str, Any]:
        """Subset of fields that should refresh on every sync.

        These are merchant-side data points that change over time
        (price reductions, restocks). Vision attributes are NOT here
        — they're computed once and stable.
        """
        patch: Dict[str, Any] = {}
        if "price" in product and product["price"] is not None:
            patch["price"] = product["price"]
        if "image_url" in product and product["image_url"]:
            patch["images_0_src"] = product["image_url"]
        if "shopify_variant_ids" in product and product["shopify_variant_ids"]:
            patch["shopify_variant_ids"] = product["shopify_variant_ids"]
        # available_for_sale isn't a column on catalog_enriched today —
        # F.4 (inventory webhooks) adds it. Kept out of the patch until
        # then to avoid silently dropping the data.
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
        # product_id is the legacy ingestion-source id; for new
        # Shopify-sourced products we mirror shopify_product_id into
        # it so existing joins (catalog_item_embeddings.product_id ↔
        # catalog_enriched.product_id) still work.
        payload["product_id"] = shopify_pid
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
            "product_id": shopify_pid,
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
        return self._client.insert_one("catalog_item_embeddings", payload)
