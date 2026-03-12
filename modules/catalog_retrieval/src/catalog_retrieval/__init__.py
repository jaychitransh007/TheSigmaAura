"""Catalog retrieval and embedding pipeline."""

from .config import CatalogEmbeddingConfig
from .document_builder import build_catalog_document

__all__ = [
    "CatalogEmbeddingConfig",
    "build_catalog_document",
]
