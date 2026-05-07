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

# Reduced from 4 → 2 to limit concurrent vector similarity RPCs against
# the database.  With 7 queries (3 directions × 2-3 roles), 4 workers
# caused intermittent statement timeouts on Supabase (error 57014).
_MAX_SEARCH_WORKERS = 2

# Retry config for similarity_search timeouts.
_SEARCH_MAX_RETRIES = 1
_SEARCH_RETRY_DELAY_S = 0.5

# Hard-attr re-rank. The architect engine emits a wide hard_attrs set
# (~19 attrs covering body, palette, weather, formality, occasion).
# Applying the full set as a retrieval penalty was too aggressive —
# items partial-matching across many soft preferences accumulated 5+
# violations × 0.30 = -1.5+ penalty, dragging cosine sim from ~0.75
# into deep negatives (turn 5e2180aa). Two-stage fix:
#
# 1. Filter to ``_RETRIEVAL_HARD_ATTR_KEYS`` — the genuinely categorical
#    contextual attributes where a mismatch reads as wrong (cool weather +
#    short sleeves; ceremonial occasion + casual fabric). Body-shape,
#    palette, and silhouette preferences stay in query_document text
#    only (handled by cosine fuzziness) and apply later as a tuple-level
#    penalty in the composer engine via TupleContext.hard_attrs.
# 2. Lower per-violation penalty to 0.10 (was 0.30). With ~6 keys max
#    in the retrieval set, total penalty bounded at 0.6 — meaningful
#    but not crushing.
#
# Composer engine still uses the FULL hard_attrs at tuple scoring;
# this filter only narrows the retrieval-stage penalty.
_RERANK_OVER_FETCH_FACTOR = 4
_HARD_ATTR_PENALTY = 0.10
_RETRIEVAL_HARD_ATTR_KEYS = frozenset({
    "FormalityLevel",
    "OccasionFit",
    "SleeveLength",
    "FabricWeight",
    "FabricDrape",
    "SkinExposureLevel",
})


def _apply_hard_attr_penalty(
    products: List[Any],
    hard_attrs: Optional[Dict[str, List[str]]],
    retrieval_count: int,
) -> List[Any]:
    """Re-rank ``products`` by adding ``_HARD_ATTR_PENALTY`` per violation
    of the retrieval-narrow ``hard_attrs`` subset against each product's
    ``enriched_data``. Items that lack the attribute (no opinion) carry
    no penalty. Returns the top ``retrieval_count`` items by adjusted
    similarity.

    Filters ``hard_attrs`` to ``_RETRIEVAL_HARD_ATTR_KEYS`` before
    applying — the wider engine-resolved set still flows to the
    composer engine for tuple-level scoring (different stage, different
    role). No-op (just truncates to retrieval_count) when ``hard_attrs``
    is falsy — preserves backward compatibility with the LLM-architect
    path which doesn't populate hard_attrs."""
    if not hard_attrs:
        return products[:retrieval_count]
    narrow = {
        k: v for k, v in hard_attrs.items() if k in _RETRIEVAL_HARD_ATTR_KEYS
    }
    if not narrow:
        return products[:retrieval_count]
    for p in products:
        ed = getattr(p, "enriched_data", None) or {}
        violations = 0
        for attr_name, allowed in narrow.items():
            val = ed.get(attr_name)
            if val is None or val == "":
                continue  # no opinion, no penalty
            if str(val) not in allowed:
                violations += 1
        if violations:
            try:
                p.similarity = float(getattr(p, "similarity", 0.0)) - _HARD_ATTR_PENALTY * violations
            except Exception:  # noqa: BLE001 — Pydantic immutability or odd shape
                pass
    products.sort(key=lambda x: -float(getattr(x, "similarity", 0.0)))
    return products[:retrieval_count]


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

            # Similarity search with retry on timeout. When the architect
            # engine resolved hard_attrs, over-fetch from cosine so the
            # post-hydrate Python re-rank has room to push violators
            # below clean items. Without over-fetch, if every cosine
            # top-K item violates, re-ranking can't recover.
            #
            # Why not enforce hard_attrs in SQL: catalog_item_embeddings.
            # metadata_json only carries the typed-column subset
            # (FormalityLevel, GarmentSubtype, etc.) — the rich
            # attributes (SleeveLength, FabricWeight, ...) live in the
            # separate catalog_enriched table that we hydrate AFTER
            # retrieval. The SQL function's hard_attrs param sees keys
            # that don't exist in metadata_json and counts 0
            # violations. Re-rank in Python where we already have the
            # rich enriched_data attached.
            t0 = time.monotonic()
            matches: list = []
            search_count = (
                plan.retrieval_count * _RERANK_OVER_FETCH_FACTOR
                if query.hard_attrs
                else plan.retrieval_count
            )
            for attempt in range(_SEARCH_MAX_RETRIES + 1):
                try:
                    matches = self._retrieval_gateway.similarity_search(
                        query_embedding=embedding,
                        match_count=search_count,
                        filters=filters,
                        hard_attrs=query.hard_attrs or None,
                    ) or []
                    break
                except Exception as exc:
                    exc_msg = str(exc)
                    is_timeout = "57014" in exc_msg or "timeout" in exc_msg.lower()
                    if is_timeout and attempt < _SEARCH_MAX_RETRIES:
                        _log.warning(
                            "CatalogSearch: similarity_search TIMEOUT for query %s (attempt %d/%d), retrying in %.1fs",
                            query.query_id, attempt + 1, _SEARCH_MAX_RETRIES + 1, _SEARCH_RETRY_DELAY_S,
                        )
                        time.sleep(_SEARCH_RETRY_DELAY_S)
                        continue
                    _log.exception(
                        "CatalogSearch: similarity_search FAILED for query %s (attempt %d/%d, timeout=%s)",
                        query.query_id, attempt + 1, _SEARCH_MAX_RETRIES + 1, is_timeout,
                    )
                    matches = []
                    break
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

            # Engine-resolved hard-attr re-rank: penalize products whose
            # enriched_data violates the architect's resolved per-attr
            # allowed lists. Truncates to retrieval_count.
            pre_rerank = len(products)
            products = _apply_hard_attr_penalty(
                products, query.hard_attrs or None, plan.retrieval_count,
            )
            _log.info(
                "CatalogSearch: [%s/%s] hydrated %d→%d in %dms "
                "(excluded %d, rerank %d→%d, hard_attrs=%d)",
                direction_id, query.query_id,
                len(matches), pre_rerank, hydrate_ms, excluded_count,
                pre_rerank, len(products),
                len(query.hard_attrs or {}),
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
