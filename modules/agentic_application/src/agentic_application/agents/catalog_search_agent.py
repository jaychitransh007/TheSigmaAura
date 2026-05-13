from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, Iterable, List, Optional, Tuple

from catalog.retrieval.document_builder import ROW_STATUS_DELETED_FROM_SOURCE
from platform_core.restricted_categories import detect_restricted_record
from platform_core.supabase_rest import SupabaseRestClient

from ..filters import (
    build_directional_filters,
    drop_filter_keys,
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
# (~19 attrs covering body, palette, weather, formality, occasion); the
# orchestrator additionally folds in the planner's open-axis user
# preferences (EmbellishmentLevel, ContrastLevel, ...). Phase 5x removes
# the previous 6-attr whitelist — every attr the architect emits is now
# applied at retrieval, so user-explicit preferences ("more
# embellishment", "low contrast") actually narrow the pool instead of
# being silently dropped. The original safety concern (cumulative
# penalty crushing cosine sim) is now handled by ``_HARD_ATTR_PENALTY_CAP``:
# a per-item ceiling that limits the total deduction regardless of how
# many attrs violate. With penalty=0.10/violation and cap=0.40, an item
# can lose at most 0.40 from hard_attr violations — enough to demote
# items but not so much that they fall behind unrelated items with weak
# cosine scores.
_RERANK_OVER_FETCH_FACTOR = 4
_HARD_ATTR_PENALTY = 0.10
_HARD_ATTR_PENALTY_CAP = 0.40


def _apply_hard_attr_penalty(
    products: List[Any],
    hard_attrs: Optional[Dict[str, List[str]]],
    retrieval_count: int,
) -> Tuple[List[Any], Dict[str, Dict[str, int]]]:
    """Re-rank ``products`` by penalizing each violation of ``hard_attrs``
    against each product's ``enriched_data``. Items that lack the attribute
    (no opinion) carry no penalty. Total per-item deduction is capped at
    ``_HARD_ATTR_PENALTY_CAP`` so cumulative violations across many attrs
    can't drag cosine sim into deep negatives.

    Returns ``(products, summary)`` where:

    - ``products`` is the top ``retrieval_count`` items by adjusted similarity
    - ``summary`` is a per-attribute breakdown of the rerank pool, shape
      ``{attr_name: {"items_with_attr": N, "violations": M}}``. ``N`` is
      the count of products in the pool that carried a non-empty value
      for the attribute (the eligible denominator for that axis). ``M``
      is the count among those that violated the architect's allowed
      list. Empty dict on the no-op path (``hard_attrs`` falsy) so
      callers don't need to special-case.

    Composer engine still applies its own per-tuple hard_attr penalty at
    scoring time (different stage, different role — uniform tuple-level
    scoring across paired/three_piece)."""
    if not hard_attrs:
        return products[:retrieval_count], {}
    # Pre-build allowed-value sets once; per-item membership is now O(1)
    # instead of an O(N) scan against the original list each iteration.
    allowed_sets: Dict[str, set] = {
        attr: set(values) for attr, values in hard_attrs.items() if values
    }
    if not allowed_sets:
        return products[:retrieval_count], {}

    # Per-attribute breakdown: items_with_attr (denominator), violations
    # (numerator). Initialize so attrs that ended up zero-violation
    # still appear in the summary — distinguishes "no items had this
    # attr" from "all items matched" in the dashboard panel.
    summary: Dict[str, Dict[str, int]] = {
        attr: {"items_with_attr": 0, "violations": 0} for attr in allowed_sets
    }

    for p in products:
        ed = getattr(p, "enriched_data", None) or {}
        violations = 0
        for attr_name, allowed_set in allowed_sets.items():
            val = ed.get(attr_name)
            if val is None or val == "":
                continue  # no opinion, no penalty, no counter tick
            summary[attr_name]["items_with_attr"] += 1
            if str(val) not in allowed_set:
                violations += 1
                summary[attr_name]["violations"] += 1
        if violations:
            raw_penalty = _HARD_ATTR_PENALTY * violations
            penalty = min(raw_penalty, _HARD_ATTR_PENALTY_CAP)
            if raw_penalty > _HARD_ATTR_PENALTY_CAP:
                try:
                    from platform_core.metrics import observe_hard_attr_penalty_cap_hit
                    observe_hard_attr_penalty_cap_hit("retrieval")
                except Exception:  # noqa: BLE001 — telemetry never breaks pipeline
                    pass
            try:
                p.similarity = float(getattr(p, "similarity", 0.0)) - penalty
            except (AttributeError, TypeError) as exc:
                # Pydantic immutability or odd shape — surface but don't
                # break retrieval. The item keeps its un-penalized
                # similarity and may rank higher than it should.
                _log.warning(
                    "hard_attr_penalty: could not update similarity on %s: %s",
                    getattr(p, "product_id", "<unknown>"), exc,
                )
    # Batch-emit Prometheus counter ticks once at the end (one inc()
    # per attribute, sized by the violation count) instead of per-item.
    try:
        from platform_core.metrics import observe_retrieval_attr_violation
        for attr_name, counts in summary.items():
            v = counts.get("violations") or 0
            if v:
                observe_retrieval_attr_violation(attr_name, v)
    except Exception:  # noqa: BLE001 — telemetry never breaks pipeline
        pass
    products.sort(key=lambda x: -float(getattr(x, "similarity", 0.0)))
    return products[:retrieval_count], summary


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
            # Hard-attr enforcement lives entirely in Python (see
            # ``_apply_hard_attr_penalty`` below). The May 7 SQL-level
            # penalty was dropped in the May 13 iterative-HNSW rewrite
            # (and the ``20260513020000`` migration removed the 5-arg
            # overload from the database) because the rich attributes
            # (SleeveLength, FabricWeight, ...) live in the separate
            # ``catalog_enriched`` table hydrated AFTER retrieval —
            # ``catalog_item_embeddings.metadata_json`` only carried the
            # typed-column subset, so the SQL penalty counted 0
            # violations for most keys anyway.
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

            # Hydrate + post-process. Wrap so a hydrate / rerank crash
            # preserves whatever similarity_search produced instead of
            # nuking the whole worker (the May 8 RCA pattern: a silent
            # exception in this section dropped 40 valid matches into
            # the void with no diagnostic). We still capture the
            # exception so the trace shows which post-search step broke.
            attr_summary: Dict[str, Dict[str, int]] = {}
            try:
                t1 = time.monotonic()
                products = self._hydrate_matches(matches)
                hydrate_ms = int((time.monotonic() - t1) * 1000)
                pre_exclude = len(products)
                if exclude_ids:
                    products = [p for p in products if str(p.product_id or "") not in exclude_ids]
                excluded_count = pre_exclude - len(products)
                pre_rerank = len(products)
                products, attr_summary = _apply_hard_attr_penalty(
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
            except Exception as exc:  # noqa: BLE001 — never break the turn on post-search ops
                _log.exception(
                    "CatalogSearch: post-search step failed for query %s — preserving %d raw matches",
                    query.query_id, len(matches),
                )
                # Synthesize minimal RetrievedProducts from raw matches so the
                # composer downstream still has something to work with.
                products = []
                for m in matches[:plan.retrieval_count]:
                    try:
                        meta = dict(m.get("metadata_json") or {})
                        pid = str(m.get("product_id") or meta.get("id") or "")
                        if not pid:
                            continue
                        products.append(RetrievedProduct(
                            product_id=pid,
                            similarity=float(m.get("similarity") or 0.0),
                            metadata=meta,
                            enriched_data={},
                        ))
                    except Exception:  # noqa: BLE001 — skip malformed rows individually
                        continue
                applied_filters_meta = {
                    **applied_filters_meta,
                    "post_search_error": "true",
                    "post_search_error_type": type(exc).__name__,
                    "post_search_error_message": (str(exc).splitlines()[0][:200] if str(exc) else ""),
                }

            return idx, RetrievedSet(
                direction_id=direction_id,
                query_id=query.query_id,
                role=query.role,
                products=products,
                applied_filters=applied_filters_meta,
                attr_violation_summary=attr_summary,
            )

        workers = min(len(tasks), _MAX_SEARCH_WORKERS) if tasks else 1
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(_search_one, i): i for i in range(len(tasks))}
            for future in as_completed(futures):
                try:
                    idx, retrieved_set = future.result()
                    results[idx] = retrieved_set
                except Exception as exc:  # noqa: BLE001 — never break the turn
                    i = futures[future]
                    task = tasks[i]
                    # Capture the exception type + first line of its message
                    # so tool_traces / dashboards can answer "what actually
                    # broke?" without spelunking server logs. Pre-fix this
                    # path landed in tool_traces as the bare string
                    # "worker_failed" with no further detail (May 8 RCA on
                    # turns c801683a / 3c85f046 / c688ebf7) — every retry
                    # hit the same silent exception, and the user got the
                    # generic low-confidence message with zero ops signal.
                    _err_type = type(exc).__name__
                    _err_msg = str(exc).splitlines()[0][:200] if str(exc) else ""
                    _log.exception(
                        "CatalogSearch: worker failed for query %s (%s: %s)",
                        task["query"].query_id, _err_type, _err_msg,
                    )
                    results[i] = RetrievedSet(
                        direction_id=task["direction_id"],
                        query_id=task["query"].query_id,
                        role=task["query"].role,
                        products=[],
                        applied_filters={
                            "error": "worker_failed",
                            "error_type": _err_type,
                            "error_message": _err_msg,
                        },
                    )
                    try:
                        from platform_core.metrics import observe_retrieval_worker_failure
                        observe_retrieval_worker_failure(_err_type)
                    except Exception:  # noqa: BLE001 — telemetry never breaks pipeline
                        pass

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

        _deleted_skipped = 0
        for match in matches:
            metadata = dict(match.get("metadata_json") or {})
            pid = str(match.get("product_id") or metadata.get("id") or "")
            enriched = dict(enriched_lookup.get(pid, {}) or {})
            # Drop products tagged gone-from-merchant by the title
            # recovery backfill (May 11 2026). These returned 404 /
            # Product-Not-Found at the live storefront — surfacing them
            # would mean dead Buy-Now links.
            if str(enriched.get("row_status") or "").strip().lower() == ROW_STATUS_DELETED_FROM_SOURCE:
                _log.info("CatalogSearch: SKIP %s pid=%s", ROW_STATUS_DELETED_FROM_SOURCE, pid[:30])
                _deleted_skipped += 1
                continue
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
        if _deleted_skipped:
            try:
                from platform_core.metrics import observe_catalog_deleted_skipped
                observe_catalog_deleted_skipped(
                    path="catalog_search", count=_deleted_skipped,
                )
            except Exception:  # noqa: BLE001
                pass
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
