from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass(frozen=True)
class CatalogFieldValue:
    value: str
    confidence: float


@dataclass(frozen=True)
class CatalogDocument:
    row_id: str
    product_id: str
    metadata: Dict[str, Any]
    document_text: str

    def as_dict(self) -> Dict[str, Any]:
        return {
            "row_id": self.row_id,
            "product_id": self.product_id,
            "metadata": self.metadata,
            "document_text": self.document_text,
        }


@dataclass(frozen=True)
class CatalogEmbeddingRecord:
    row_id: str
    product_id: str
    model: str
    dimensions: int
    metadata: Dict[str, Any]
    document_text: str
    embedding: List[float] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "row_id": self.row_id,
            "product_id": self.product_id,
            "model": self.model,
            "dimensions": self.dimensions,
            "metadata": self.metadata,
            "document_text": self.document_text,
            "embedding": self.embedding,
        }
