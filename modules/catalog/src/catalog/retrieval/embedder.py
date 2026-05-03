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
        # Token usage from the most recent embed_texts call. Surfaced
        # for the orchestrator's per-turn cost rollup so the embedding
        # bill (text-embedding-3-small, ~$0.02/1M tokens) gets captured
        # alongside the LLM and try-on costs.
        self.last_usage: dict = {"prompt_tokens": 0, "total_tokens": 0}

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
            self.last_usage = {"prompt_tokens": 0, "total_tokens": 0}
            return []
        all_embeddings: List[List[float]] = []
        # Sum usage across batches so callers see one number per call,
        # not per-batch. text-embedding-3-small reports `prompt_tokens`
        # and `total_tokens`; both are equal for embedding endpoints
        # (no completion). Stored on `self.last_usage` so the
        # orchestrator can pull it after the call without changing the
        # public return type.
        prompt_tokens = 0
        total_tokens = 0
        for i in range(0, len(texts), EMBED_BATCH_SIZE):
            batch = texts[i : i + EMBED_BATCH_SIZE]
            response = self._embedding_response(batch)
            all_embeddings.extend(list(item.embedding) for item in response.data)
            usage = getattr(response, "usage", None)
            if usage is not None:
                prompt_tokens += int(getattr(usage, "prompt_tokens", 0) or 0)
                total_tokens += int(getattr(usage, "total_tokens", 0) or 0)
        self.last_usage = {
            "prompt_tokens": prompt_tokens,
            "total_tokens": total_tokens or prompt_tokens,
        }
        return all_embeddings

    def _embedding_response(self, texts: List[str]):
        return self._client.embeddings.create(
            model=self._config.embedding_model,
            input=texts,
            dimensions=self._config.embedding_dimensions,
        )
