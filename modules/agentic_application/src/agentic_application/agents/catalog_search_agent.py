from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, Iterable, List, Optional, Tuple

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
    QuerySpec,
    RecommendationPlan,
    RetrievedProduct,
    RetrievedSet,
)
from ..services.catalog_retrieval_gateway import ApplicationCatalogRetrievalGateway

_log = logging.getLogger(__name__)

_MAX_SEARCH_WORKERS = 4


class CatalogSearchAgent:
    def __init__(
        self,
        *,
        retrieval_gateway: ApplicationCatalogRetrievalGateway,
        client: SupabaseRestClient,
    ) -> None:
        self._retrieval_gateway = retrieval_gateway
        self._client = client

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def search(
        self,
        plan: RecommendationPlan,
        combined_context: CombinedContext,
        *,
        relaxed_filter_keys: Iterable[str] = (),
    ) -> List[RetrievedSet]:
        """Execute retrieval for every QuerySpec across all directions.

        Embeddings are batched into a single OpenAI API call, then
        search + hydrate cycles run in parallel via ThreadPoolExecutor.
        """
        relaxed_keys = {str(key or "").strip() for key in relaxed_filter_keys}
        disliked_ids: set[str] = {
            str(pid).strip()
            for pid in list(getattr(combined_context, "disliked_product_ids", []) or [])
            if str(pid or "").strip()
        }
        prev_rec_ids: set[str] = set()
        for rec in (combined_context.previous_recommendations or []):
            for item_id in (rec.get("item_ids") or []):
                pid = str(item_id or "").strip()
                if pid:
                    prev_rec_ids.add(pid)
        exclude_ids = disliked_ids | prev_rec_ids

        # --- Prepare tasks and collect query documents ----------------
        tasks: List[Dict[str, Any]] = []
        query_documents: List[str] = []
        for direction in plan.directions:
            for query in direction.queries:
                filters = merge_filters(
                    combined_context.hard_filters,
                    build_directional_filters(direction.direction_type, query.role),
                    extract_query_document_filters(query.query_document),
                    query.hard_filters,
                )
                filters = drop_filter_keys(filters, relaxed_keys)
                tasks.append({
                    "direction_id": direction.direction_id,
                    "query": query,
                    "filters": filters,
                })
                query_documents.append(query.query_document)

        _log.info(
            "CatalogSearch: starting search for %d direction(s), %d queries, retrieval_count=%d, disliked=%d, prev_rec=%d",
            len(plan.directions), len(tasks), plan.retrieval_count,
            len(disliked_ids), len(prev_rec_ids),
        )

        # --- Step 1: Batch embed all query documents in one call ------
        t_embed = time.monotonic()
        try:
            all_embeddings: List[Optional[List[float]]] = self._retrieval_gateway.embed_texts(query_documents)
        except Exception:
            _log.exception("CatalogSearch: batch embed_texts FAILED for %d documents", len(query_documents))
            all_embeddings = [None] * len(query_documents)
        embed_ms = int((time.monotonic() - t_embed) * 1000)
        _log.info("CatalogSearch: batch embedded %d documents in %dms", len(query_documents), embed_ms)

        # --- Step 2: Parallel search + hydrate ------------------------
        t_search = time.monotonic()
        results: List[Optional[RetrievedSet]] = [None] * len(tasks)

        def _search_one(idx: int) -> Tuple[int, RetrievedSet]:
            task = tasks[idx]
            query: QuerySpec = task["query"]
            filters: Dict[str, Any] = task["filters"]
            direction_id: str = task["direction_id"]
            embedding = all_embeddings[idx] if idx < len(all_embeddings) else None

            applied_filters_meta = {
                **filters,
                "restricted_category_policy": "excluded",
            }
            if disliked_ids:
                applied_filters_meta["disliked_product_policy"] = "excluded"
            if prev_rec_ids:
                applied_filters_meta["prev_rec_product_policy"] = "excluded"
                applied_filters_meta["prev_rec_excluded_count"] = str(len(prev_rec_ids))

            if embedding is None:
                _log.error("CatalogSearch: embedding is None — skipping query %s", query.query_id)
                return idx, RetrievedSet(
                    direction_id=direction_id,
                    query_id=query.query_id,
                    role=query.role,
                    products=[],
                    applied_filters={**applied_filters_meta, "error": "embedding_failed"},
                )

            _log.info(
                "CatalogSearch: dir=%s query=%s role=%s filters=%s",
                direction_id, query.query_id, query.role, filters,
            )

            # Similarity search
            t0 = time.monotonic()
            try:
                matches = self._retrieval_gateway.similarity_search(
                    query_embedding=embedding,
                    match_count=plan.retrieval_count,
                    filters=filters,
                ) or []
            except Exception:
                _log.exception("CatalogSearch: similarity_search FAILED for query %s", query.query_id)
                matches = []
            search_ms = int((time.monotonic() - t0) * 1000)

            _log.info(
                "CatalogSearch: [%s/%s] similarity_search returned %d matches in %dms",
                direction_id, query.query_id, len(matches), search_ms,
            )

            # Hydrate
            t1 = time.monotonic()
            products = self._hydrate_matches(matches)
            hydrate_ms = int((time.monotonic() - t1) * 1000)
            pre_exclude = len(products)
            if exclude_ids:
                products = [p for p in products if str(p.product_id or "") not in exclude_ids]
            excluded_count = pre_exclude - len(products)
            _log.info(
                "CatalogSearch: [%s/%s] hydrated %d→%d in %dms (excluded %d)",
                direction_id, query.query_id,
                len(matches), len(products), hydrate_ms, excluded_count,
            )

            return idx, RetrievedSet(
                direction_id=direction_id,
                query_id=query.query_id,
                role=query.role,
                products=products,
                applied_filters=applied_filters_meta,
            )

        workers = min(len(tasks), _MAX_SEARCH_WORKERS) if tasks else 1
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(_search_one, i): i for i in range(len(tasks))}
            for future in as_completed(futures):
                try:
                    idx, retrieved_set = future.result()
                    results[idx] = retrieved_set
                except Exception:
                    i = futures[future]
                    task = tasks[i]
                    _log.exception("CatalogSearch: worker failed for query %s", task["query"].query_id)
                    results[i] = RetrievedSet(
                        direction_id=task["direction_id"],
                        query_id=task["query"].query_id,
                        role=task["query"].role,
                        products=[],
                        applied_filters={"error": "worker_failed"},
                    )

        search_total_ms = int((time.monotonic() - t_search) * 1000)
        final = [rs for rs in results if rs is not None]
        _log.info(
            "CatalogSearch: completed — %d set(s), %d products, embed=%dms, search+hydrate=%dms (parallel, %d workers)",
            len(final), sum(len(rs.products) for rs in final),
            embed_ms, search_total_ms, workers,
        )
        return final

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
