from __future__ import annotations

from typing import Any, Dict, List

from catalog_retrieval.config import CatalogEmbeddingConfig
from catalog_retrieval.embedder import CatalogEmbedder
from catalog_retrieval.vector_store import SupabaseVectorStore

from platform_core.supabase_rest import SupabaseRestClient


class ApplicationCatalogRetrievalGateway:
    """App-facing wrapper around catalog retrieval dependencies."""

    def __init__(self, client: SupabaseRestClient) -> None:
        self._embedder = CatalogEmbedder(CatalogEmbeddingConfig(embedding_dimensions=1536))
        self._vector_store = SupabaseVectorStore(client)

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        return self._embedder.embed_texts(texts)

    def similarity_search(
        self,
        *,
        query_embedding: List[float],
        match_count: int,
        filters: Dict[str, Any],
    ) -> Any:
        return self._vector_store.similarity_search(
            query_embedding=query_embedding,
            match_count=match_count,
            filters=filters,
        )
