import logging
from functools import cached_property
from typing import Iterable, List

from openai import OpenAI

from user_profiler.config import get_api_key

from .config import CatalogEmbeddingConfig
from .schemas import CatalogDocument, CatalogEmbeddingRecord

logger = logging.getLogger(__name__)

EMBED_BATCH_SIZE = 50


class CatalogEmbedder:
    def __init__(self, config: CatalogEmbeddingConfig) -> None:
        # May 1, 2026 (CI fix): lazy OpenAI client. The retrieval gateway
        # constructs CatalogEmbedder eagerly from the orchestrator's
        # __init__ even in tests where the embedder is never used; deferring
        # the API-key load until first embed_documents call keeps the
        # constructor env-free.
        self._config = config

    @cached_property
    def _client(self) -> OpenAI:
        return OpenAI(api_key=get_api_key())

    def embed_documents(self, documents: Iterable[CatalogDocument]) -> List[CatalogEmbeddingRecord]:
        docs = list(documents)
        if not docs:
            return []
        records: List[CatalogEmbeddingRecord] = []
        for i in range(0, len(docs), EMBED_BATCH_SIZE):
            batch = docs[i : i + EMBED_BATCH_SIZE]
            logger.info("Embedding batch %d–%d of %d", i + 1, i + len(batch), len(docs))
            response = self._embedding_response([doc.document_text for doc in batch])
            for doc, item in zip(batch, response.data):
                records.append(
                    CatalogEmbeddingRecord(
                        row_id=doc.row_id,
                        product_id=doc.product_id,
                        model=self._config.embedding_model,
                        dimensions=self._config.embedding_dimensions,
                        metadata=doc.metadata,
                        document_text=doc.document_text,
                        embedding=list(item.embedding),
                    )
                )
        return records

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        all_embeddings: List[List[float]] = []
        for i in range(0, len(texts), EMBED_BATCH_SIZE):
            batch = texts[i : i + EMBED_BATCH_SIZE]
            response = self._embedding_response(batch)
            all_embeddings.extend(list(item.embedding) for item in response.data)
        return all_embeddings

    def _embedding_response(self, texts: List[str]):
        return self._client.embeddings.create(
            model=self._config.embedding_model,
            input=texts,
            dimensions=self._config.embedding_dimensions,
        )
