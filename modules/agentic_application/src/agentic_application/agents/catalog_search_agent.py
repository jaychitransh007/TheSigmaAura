from __future__ import annotations

from typing import Any, Dict, Iterable, List

from catalog_retrieval.embedder import CatalogEmbedder
from catalog_retrieval.vector_store import SupabaseVectorStore
from conversation_platform.supabase_rest import SupabaseRestClient

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


class CatalogSearchAgent:
    def __init__(
        self,
        *,
        embedder: CatalogEmbedder,
        vector_store: SupabaseVectorStore,
        client: SupabaseRestClient,
    ) -> None:
        self._embedder = embedder
        self._vector_store = vector_store
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
        for direction in plan.directions:
            for query in direction.queries:
                filters = merge_filters(
                    combined_context.hard_filters,
                    build_directional_filters(direction.direction_type, query.role),
                    extract_query_document_filters(query.query_document),
                    query.hard_filters,
                )
                filters = drop_filter_keys(filters, relaxed_keys)
                embedding = self._embedder.embed_texts([query.query_document])[0]
                matches = self._vector_store.similarity_search(
                    query_embedding=embedding,
                    match_count=plan.retrieval_count,
                    filters=filters,
                ) or []

                products = self._hydrate_matches(matches)
                results.append(
                    RetrievedSet(
                        direction_id=direction.direction_id,
                        query_id=query.query_id,
                        role=query.role,
                        products=products,
                        applied_filters=filters,
                    )
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

        for match in matches:
            metadata = dict(match.get("metadata_json") or {})
            pid = str(match.get("product_id") or metadata.get("id") or "")
            products.append(
                RetrievedProduct(
                    product_id=pid,
                    similarity=float(match.get("similarity") or 0.0),
                    metadata=metadata,
                    enriched_data=enriched_lookup.get(pid, {}),
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
            return {}
        return {str(row.get("product_id") or ""): row for row in (rows or [])}
