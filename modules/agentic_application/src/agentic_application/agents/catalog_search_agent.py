from __future__ import annotations

import logging
import time
from typing import Any, Dict, Iterable, List

from platform_core.restricted_categories import detect_restricted_record
from platform_core.supabase_rest import SupabaseRestClient

from ..filters import (
    build_directional_filters,
    drop_filter_keys,
    extract_query_document_filters,
    merge_filters,
)
from ..schemas import (
    CombinedContext,
    RecommendationPlan,
    RetrievedProduct,
    RetrievedSet,
)
from ..services.catalog_retrieval_gateway import ApplicationCatalogRetrievalGateway

_log = logging.getLogger(__name__)


class CatalogSearchAgent:
    def __init__(
        self,
        *,
        retrieval_gateway: ApplicationCatalogRetrievalGateway,
        client: SupabaseRestClient,
    ) -> None:
        self._retrieval_gateway = retrieval_gateway
        self._client = client

    def search(
        self,
        plan: RecommendationPlan,
        combined_context: CombinedContext,
        *,
        relaxed_filter_keys: Iterable[str] = (),
    ) -> List[RetrievedSet]:
        """Execute retrieval for every QuerySpec across all directions."""
        results: List[RetrievedSet] = []
        relaxed_keys = {str(key or "").strip() for key in relaxed_filter_keys}
        disliked_ids: set[str] = {
            str(pid).strip()
            for pid in list(getattr(combined_context, "disliked_product_ids", []) or [])
            if str(pid or "").strip()
        }
        # Collect product IDs from previous recommendations so follow-up turns
        # surface fresh products instead of repeating the same outfits.
        prev_rec_ids: set[str] = set()
        for rec in (combined_context.previous_recommendations or []):
            for item_id in (rec.get("item_ids") or []):
                pid = str(item_id or "").strip()
                if pid:
                    prev_rec_ids.add(pid)
        exclude_ids = disliked_ids | prev_rec_ids
        _log.info(
            "CatalogSearch: starting search for %d direction(s), retrieval_count=%d, disliked_excluded=%d, prev_rec_excluded=%d",
            len(plan.directions), plan.retrieval_count, len(disliked_ids), len(prev_rec_ids),
        )
        for direction in plan.directions:
            for query in direction.queries:
                filters = merge_filters(
                    combined_context.hard_filters,
                    build_directional_filters(direction.direction_type, query.role),
                    extract_query_document_filters(query.query_document),
                    query.hard_filters,
                )
                filters = drop_filter_keys(filters, relaxed_keys)
                _log.info(
                    "CatalogSearch: dir=%s query=%s role=%s filters=%s doc_len=%d",
                    direction.direction_id, query.query_id, query.role,
                    filters, len(query.query_document),
                )

                # Embedding
                t0 = time.monotonic()
                try:
                    embedding = self._retrieval_gateway.embed_texts([query.query_document])[0]
                except Exception:
                    _log.exception("CatalogSearch: embed_texts FAILED for query %s", query.query_id)
                    embedding = None
                embed_ms = int((time.monotonic() - t0) * 1000)

                if embedding is None:
                    _log.error("CatalogSearch: embedding is None — skipping search for query %s", query.query_id)
                    results.append(
                        RetrievedSet(
                            direction_id=direction.direction_id,
                            query_id=query.query_id,
                            role=query.role,
                            products=[],
                            applied_filters={**filters, "restricted_category_policy": "excluded", "error": "embedding_failed"},
                        )
                    )
                    continue

                _log.info(
                    "CatalogSearch: embedded in %dms, dims=%d, first_5_vals=[%s]",
                    embed_ms, len(embedding),
                    ", ".join(f"{v:.4f}" for v in embedding[:5]),
                )

                # Similarity search
                t1 = time.monotonic()
                try:
                    matches = self._retrieval_gateway.similarity_search(
                        query_embedding=embedding,
                        match_count=plan.retrieval_count,
                        filters=filters,
                    ) or []
                except Exception:
                    _log.exception("CatalogSearch: similarity_search FAILED for query %s", query.query_id)
                    matches = []
                search_ms = int((time.monotonic() - t1) * 1000)

                _log.info(
                    "CatalogSearch: similarity_search returned %d matches in %dms",
                    len(matches), search_ms,
                )
                if matches:
                    top = matches[0]
                    _log.info(
                        "CatalogSearch: top match: pid=%s sim=%.4f cat=%s sub=%s",
                        str(top.get("product_id", ""))[:30],
                        float(top.get("similarity") or 0),
                        top.get("garment_category", ""),
                        top.get("garment_subtype", ""),
                    )

                # Hydrate
                t2 = time.monotonic()
                products = self._hydrate_matches(matches)
                hydrate_ms = int((time.monotonic() - t2) * 1000)
                pre_exclude = len(products)
                if exclude_ids:
                    products = [p for p in products if str(p.product_id or "") not in exclude_ids]
                excluded_count = pre_exclude - len(products)
                _log.info(
                    "CatalogSearch: hydrated %d → %d products in %dms (blocked %d by restricted policy, excluded %d disliked+prev_rec)",
                    len(matches), len(products), hydrate_ms,
                    len(matches) - pre_exclude, excluded_count,
                )

                applied_filters_meta = {
                    **filters,
                    "restricted_category_policy": "excluded",
                }
                if disliked_ids:
                    applied_filters_meta["disliked_product_policy"] = "excluded"
                if prev_rec_ids:
                    applied_filters_meta["prev_rec_product_policy"] = "excluded"
                    applied_filters_meta["prev_rec_excluded_count"] = str(len(prev_rec_ids))
                results.append(
                    RetrievedSet(
                        direction_id=direction.direction_id,
                        query_id=query.query_id,
                        role=query.role,
                        products=products,
                        applied_filters=applied_filters_meta,
                    )
                )
        _log.info(
            "CatalogSearch: completed — %d set(s), total products: %d",
            len(results), sum(len(rs.products) for rs in results),
        )
        return results

    def _hydrate_matches(self, matches: List[Dict[str, Any]]) -> List[RetrievedProduct]:
        """Convert raw vector search matches into RetrievedProduct entries."""
        products: List[RetrievedProduct] = []
        product_ids = [
            str(m.get("product_id") or (m.get("metadata_json") or {}).get("id") or "")
            for m in matches
        ]
        product_ids = [pid for pid in product_ids if pid]

        enriched_lookup: Dict[str, Dict[str, Any]] = {}
        if product_ids:
            enriched_lookup = self._batch_fetch_enriched(product_ids)
            _log.info(
                "CatalogSearch: fetched %d enriched rows for %d product IDs",
                len(enriched_lookup), len(product_ids),
            )

        for match in matches:
            metadata = dict(match.get("metadata_json") or {})
            pid = str(match.get("product_id") or metadata.get("id") or "")
            enriched = dict(enriched_lookup.get(pid, {}) or {})
            blocked_term = detect_restricted_record({**metadata, **enriched})
            if blocked_term:
                _log.info("CatalogSearch: BLOCKED pid=%s term=%s", pid[:30], blocked_term)
                continue
            products.append(
                RetrievedProduct(
                    product_id=pid,
                    similarity=float(match.get("similarity") or 0.0),
                    metadata=metadata,
                    enriched_data=enriched,
                )
            )
        return products

    def _batch_fetch_enriched(self, product_ids: List[str]) -> Dict[str, Dict[str, Any]]:
        """Fetch catalog_enriched rows for the given product IDs."""
        ids_csv = ",".join(product_ids)
        try:
            rows = self._client.select_many(
                "catalog_enriched",
                filters={"product_id": f"in.({ids_csv})"},
            )
        except Exception:
            _log.exception("CatalogSearch: _batch_fetch_enriched FAILED for %d IDs", len(product_ids))
            return {}
        return {str(row.get("product_id") or ""): row for row in (rows or [])}
