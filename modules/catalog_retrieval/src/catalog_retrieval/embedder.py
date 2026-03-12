from typing import Iterable, List

from openai import OpenAI

from user_profiler.config import get_api_key

from .config import CatalogEmbeddingConfig
from .schemas import CatalogDocument, CatalogEmbeddingRecord


class CatalogEmbedder:
    def __init__(self, config: CatalogEmbeddingConfig) -> None:
        self._config = config
        self._client = OpenAI(api_key=get_api_key())

    def embed_documents(self, documents: Iterable[CatalogDocument]) -> List[CatalogEmbeddingRecord]:
        docs = list(documents)
        if not docs:
            return []
        response = self._embedding_response([doc.document_text for doc in docs])
        records: List[CatalogEmbeddingRecord] = []
        for doc, item in zip(docs, response.data):
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
        response = self._embedding_response(texts)
        return [list(item.embedding) for item in response.data]

    def _embedding_response(self, texts: List[str]):
        return self._client.embeddings.create(
            model=self._config.embedding_model,
            input=texts,
            dimensions=self._config.embedding_dimensions,
        )
