from __future__ import annotations

import logging
from typing import Any, Dict, List

from catalog.retrieval.config import CatalogEmbeddingConfig
from catalog.retrieval.embedder import CatalogEmbedder
from catalog.retrieval.vector_store import SupabaseVectorStore

from platform_core.supabase_rest import SupabaseRestClient

_log = logging.getLogger(__name__)


class ApplicationCatalogRetrievalGateway:
    """App-facing wrapper around catalog retrieval dependencies."""

    def __init__(self, client: SupabaseRestClient) -> None:
        self._client = client
        self._embedder = CatalogEmbedder(CatalogEmbeddingConfig(embedding_dimensions=1536))
        self._vector_store = SupabaseVectorStore(client)

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        _log.info("RetrievalGateway: embedding %d text(s), first %d chars: %s",
                   len(texts), min(80, len(texts[0])) if texts else 0, (texts[0][:80] if texts else ""))
        result = self._embedder.embed_texts(texts)
        if result:
            _log.info("RetrievalGateway: embedding OK, dims=%d", len(result[0]))
        else:
            _log.error("RetrievalGateway: embed_texts returned empty!")
        return result

    def similarity_search(
        self,
        *,
        query_embedding: List[float],
        match_count: int,
        filters: Dict[str, Any],
    ) -> Any:
        _log.info("RetrievalGateway: similarity_search match_count=%d filters=%s embedding_dims=%d",
                   match_count, filters, len(query_embedding))
        result = self._vector_store.similarity_search(
            query_embedding=query_embedding,
            match_count=match_count,
            filters=filters,
        )
        count = len(result) if isinstance(result, list) else 0
        _log.info("RetrievalGateway: similarity_search returned %d matches", count)
        if count == 0:
            _log.warning("RetrievalGateway: ZERO MATCHES for filters=%s", filters)
        return result

    def get_catalog_inventory(self) -> List[Dict[str, Any]]:
        """Return distinct (gender_expression, garment_category, garment_subtype,
        styling_completeness) with item counts from the embeddings table."""
        rows = self._client.select_many(
            "catalog_item_embeddings",
            columns="gender_expression,garment_category,garment_subtype,styling_completeness",
        )
        from collections import Counter
        combos: Counter[tuple[str, ...]] = Counter()
        for r in rows:
            key = (
                str(r.get("gender_expression") or ""),
                str(r.get("garment_category") or ""),
                str(r.get("garment_subtype") or ""),
                str(r.get("styling_completeness") or ""),
            )
            combos[key] += 1
        return [
            {
                "gender_expression": ge,
                "garment_category": gc,
                "garment_subtype": gs,
                "styling_completeness": sc,
                "count": count,
            }
            for (ge, gc, gs, sc), count in sorted(combos.items())
        ]
