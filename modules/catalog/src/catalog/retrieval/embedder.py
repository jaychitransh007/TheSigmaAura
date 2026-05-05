import logging
from functools import lru_cache
from typing import Iterable, List

from openai import OpenAI

from user_profiler.config import get_api_key

from .config import CatalogEmbeddingConfig
from .schemas import CatalogDocument, CatalogEmbeddingRecord

logger = logging.getLogger(__name__)

EMBED_BATCH_SIZE = 50

# 10s per request, 2 retries (default) → fail-fast tail of ~30s
# instead of the SDK default 60s × 3 = 3min on stuck connections.
# May-5 2026: previously the retrieval gateway built a fresh
# CatalogEmbedder per orchestrator → fresh OpenAI() → cold TLS/DNS
# on the first embed of every turn, which we measured at 4.5–6.6s
# for a single short query. Sharing the client across all gateway
# instances re-uses the underlying httpx connection pool.
_EMBEDDING_TIMEOUT_SECONDS = 10.0


@lru_cache(maxsize=1)
def _shared_openai_client() -> OpenAI:
    """Process-wide OpenAI client for catalog embedding.

    Tests that need an isolated client (different config, different mock,
    or just a clean slate between cases) can call
    ``_shared_openai_client.cache_clear()`` in setUp/tearDown — the
    decorator exposes that method automatically.
    """
    return OpenAI(api_key=get_api_key(), timeout=_EMBEDDING_TIMEOUT_SECONDS)


class CatalogEmbedder:
    def __init__(self, config: CatalogEmbeddingConfig) -> None:
        # Lazy OpenAI client (May 1, 2026): retrieval gateway builds the
        # embedder eagerly from the orchestrator's __init__ even in tests
        # where it's never used; deferring the API-key load to first
        # embed call keeps the constructor env-free.
        self._config = config
        # Token usage from the most recent embed_texts call. Surfaced
        # for the orchestrator's per-turn cost rollup so the embedding
        # bill (text-embedding-3-small, ~$0.02/1M tokens) gets captured
        # alongside the LLM and try-on costs.
        self.last_usage: dict = {"prompt_tokens": 0, "total_tokens": 0}

    @property
    def _client(self) -> OpenAI:
        return _shared_openai_client()

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
