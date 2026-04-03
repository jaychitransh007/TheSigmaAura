from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CatalogEmbeddingConfig:
    input_csv_path: str = "data/catalog/enriched_catalog_upload.csv"
    documents_output_path: str = "data/catalog/embeddings/catalog_documents.jsonl"
    embeddings_output_path: str = "data/catalog/embeddings/catalog_embeddings.jsonl"
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536
    max_rows: int = 0
    min_confidence_keep_value: float = 0.6
    min_confidence_mark_uncertain: float = 0.2
    max_description_chars: int = 700
    require_complete_rows_only: bool = True

    @property
    def documents_output_file(self) -> Path:
        return Path(self.documents_output_path)

    @property
    def embeddings_output_file(self) -> Path:
        return Path(self.embeddings_output_path)
