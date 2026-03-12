from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from catalog_retrieval.config import CatalogEmbeddingConfig
from catalog_retrieval.document_builder import iter_catalog_documents
from catalog_retrieval.embedder import CatalogEmbedder
from catalog_retrieval.repository import build_catalog_enriched_rows, read_catalog_rows, write_jsonl
from catalog_retrieval.vector_store import SupabaseVectorStore


def _now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")


class CatalogAdminService:
    def __init__(self, vector_store: SupabaseVectorStore | None = None) -> None:
        self.vector_store = vector_store or SupabaseVectorStore()

    def save_uploaded_csv(self, filename: str, content: bytes) -> str:
        safe_name = Path(filename or "catalog.csv").name
        destination = Path("data/catalog/uploads") / f"{_now_stamp()}_{safe_name}"
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
        return str(destination)

    def get_status(self, *, input_csv_path: str = "data/catalog/enriched_catalog.csv") -> Dict[str, Any]:
        rows = read_catalog_rows(input_csv_path)
        eligible_embedding_rows = sum(
            1 for row in rows if str(row.get("row_status") or "").strip().lower() in {"ok", "complete"}
        )
        status = self.vector_store.catalog_status()
        return {
            "source": {
                "input_csv_path": input_csv_path,
                "total_rows": len(rows),
                "eligible_embedding_rows": eligible_embedding_rows,
            },
            "catalog_enriched_count": int(status.get("catalog_enriched_count") or 0),
            "catalog_embeddings_count": int(status.get("catalog_embeddings_count") or 0),
            "embedded_product_count": int(status.get("embedded_product_count") or 0),
            "latest_uploads": self._latest_uploads(),
        }

    def sync_catalog_items(self, *, input_csv_path: str, max_rows: int = 0) -> Dict[str, int | str]:
        rows = read_catalog_rows(input_csv_path)
        selected_rows = rows[:max_rows] if max_rows > 0 else rows
        item_rows = build_catalog_enriched_rows(selected_rows)
        saved = self.vector_store.upsert_catalog_enriched(item_rows)
        return {
            "input_csv_path": input_csv_path,
            "processed_rows": len(selected_rows),
            "saved_rows": len(saved),
            "mode": "catalog_enriched",
        }

    def sync_catalog_embeddings(
        self,
        *,
        input_csv_path: str,
        max_rows: int = 0,
        include_incomplete: bool = False,
    ) -> Dict[str, int | str]:
        rows = read_catalog_rows(input_csv_path)
        if max_rows > 0:
            rows = rows[:max_rows]
        config = CatalogEmbeddingConfig(
            input_csv_path=input_csv_path,
            max_rows=max_rows,
            require_complete_rows_only=not include_incomplete,
        )
        documents = list(iter_catalog_documents(rows, config))
        write_jsonl("data/catalog/embeddings/catalog_documents.jsonl", [doc.as_dict() for doc in documents])
        embeddings = CatalogEmbedder(config).embed_documents(documents)
        saved = self.vector_store.insert_embeddings(embeddings)
        return {
            "input_csv_path": input_csv_path,
            "processed_rows": len(documents),
            "saved_rows": len(saved),
            "mode": "catalog_embeddings",
        }

    def _latest_uploads(self, limit: int = 10) -> List[Dict[str, str]]:
        uploads_dir = Path("data/catalog/uploads")
        if not uploads_dir.exists():
            return []
        files = sorted(
            [path for path in uploads_dir.iterdir() if path.is_file() and path.suffix.lower() == ".csv"],
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        output: List[Dict[str, str]] = []
        for path in files[:limit]:
            output.append(
                {
                    "filename": path.name,
                    "input_csv_path": str(path),
                    "modified_at": datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat(),
                }
            )
        return output
