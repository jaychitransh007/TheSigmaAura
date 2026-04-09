from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from .retrieval.config import CatalogEmbeddingConfig
from .retrieval.document_builder import iter_catalog_documents
from .retrieval.embedder import CatalogEmbedder
from .retrieval.repository import (
    build_catalog_enriched_rows,
    canonical_product_url,
    read_catalog_rows,
    write_jsonl,
)
from .retrieval.vector_store import SupabaseVectorStore

logger = logging.getLogger(__name__)


def _format_exc() -> str:
    import traceback
    return traceback.format_exc()[:2000]


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

    def get_status(self, *, input_csv_path: str = "data/catalog/enriched_catalog_upload.csv") -> Dict[str, Any]:
        try:
            rows = read_catalog_rows(input_csv_path)
        except FileNotFoundError:
            rows = []
        eligible_embedding_rows = sum(
            1 for row in rows if str(row.get("row_status") or "").strip().lower() in {"ok", "complete"}
        )
        status = self.vector_store.catalog_status()
        recent_jobs = self.vector_store.recent_jobs(limit=20)
        return {
            "source": {
                "input_csv_path": input_csv_path,
                "total_rows": len(rows),
                "eligible_embedding_rows": eligible_embedding_rows,
            },
            "catalog_enriched_count": int(status.get("catalog_enriched_count") or 0),
            "catalog_embeddings_count": int(status.get("catalog_embeddings_count") or 0),
            "embedded_product_count": int(status.get("embedded_product_count") or 0),
            "total_jobs": int(status.get("total_jobs") or 0),
            "running_jobs": int(status.get("running_jobs") or 0),
            "failed_jobs": int(status.get("failed_jobs") or 0),
            "recent_jobs": recent_jobs,
            "latest_uploads": self._latest_uploads(),
        }

    def sync_catalog_items(
        self,
        *,
        input_csv_path: str,
        max_rows: int = 0,
        start_row: int = 0,
        end_row: int = 0,
    ) -> Dict[str, int | str]:
        job = self.vector_store.create_job(
            "items_sync",
            {"input_csv_path": input_csv_path, "max_rows": max_rows, "start_row": start_row, "end_row": end_row},
        )
        job_id = str(job.get("id") or "")
        try:
            rows = read_catalog_rows(input_csv_path)
            rows = rows[start_row : end_row or None]
            if max_rows > 0:
                rows = rows[:max_rows]
            item_rows = build_catalog_enriched_rows(rows)
            saved = self.vector_store.upsert_catalog_enriched(item_rows)
            missing_url_rows = sum(1 for row in item_rows if not str(row.get("url") or "").strip())
            self.vector_store.complete_job(
                job_id, processed_rows=len(rows), saved_rows=len(saved), missing_url_rows=missing_url_rows,
            )
            return {
                "input_csv_path": input_csv_path,
                "processed_rows": len(rows),
                "saved_rows": len(saved),
                "missing_url_rows": missing_url_rows,
                "mode": "catalog_enriched",
                "job_id": job_id,
            }
        except Exception:
            self.vector_store.fail_job(job_id, _format_exc())
            raise

    def backfill_catalog_urls(self, *, max_rows: int = 0) -> Dict[str, int | str]:
        job = self.vector_store.create_job("url_backfill", {"max_rows": max_rows})
        job_id = str(job.get("id") or "")
        try:
            limit = max_rows if max_rows > 0 else None
            rows = self.vector_store.client.select_many(
                "catalog_enriched",
                filters={"or": "(url.is.null,url.eq.)"},
                columns="product_id,url,raw_row_json",
                limit=limit,
            )
            patches: List[Dict[str, Any]] = []
            still_missing = 0
            for row in rows:
                raw_row = row.get("raw_row_json") or {}
                if not isinstance(raw_row, dict):
                    raw_row = {}
                canonical_url = canonical_product_url(
                    raw_url=str(row.get("url") or raw_row.get("url") or ""),
                    store=str(raw_row.get("store") or ""),
                    handle=str(raw_row.get("handle") or ""),
                )
                if not canonical_url:
                    still_missing += 1
                    continue
                patches.append(
                    {
                        "product_id": str(row.get("product_id") or ""),
                        "url": canonical_url,
                    }
                )

            saved = self.vector_store.upsert_catalog_enriched(patches)
            self.vector_store.complete_job(
                job_id, processed_rows=len(rows), saved_rows=len(saved), missing_url_rows=still_missing,
            )
            return {
                "input_csv_path": "catalog_enriched",
                "processed_rows": len(rows),
                "saved_rows": len(saved),
                "missing_url_rows": still_missing,
                "mode": "catalog_enriched_url_backfill",
                "job_id": job_id,
            }
        except Exception:
            self.vector_store.fail_job(job_id, _format_exc())
            raise

    def sync_catalog_embeddings(
        self,
        *,
        input_csv_path: str,
        max_rows: int = 0,
        start_row: int = 0,
        end_row: int = 0,
        include_incomplete: bool = False,
    ) -> Dict[str, int | str]:
        job = self.vector_store.create_job(
            "embeddings_sync",
            {"input_csv_path": input_csv_path, "max_rows": max_rows, "start_row": start_row, "end_row": end_row},
        )
        job_id = str(job.get("id") or "")
        try:
            rows = read_catalog_rows(input_csv_path)
            rows = rows[start_row : end_row or None]
            if max_rows > 0:
                rows = rows[:max_rows]
            existing_ids = self.vector_store.embedded_product_ids()
            pre_filter_count = len(rows)
            rows = [
                row for row in rows
                if str(row.get("product_id") or row.get("id") or "").strip() not in existing_ids
            ]
            skipped_count = pre_filter_count - len(rows)
            logger.info("Skipped %d already-embedded products (of %d), %d remaining", skipped_count, pre_filter_count, len(rows))
            config = CatalogEmbeddingConfig(
                input_csv_path=input_csv_path,
                max_rows=max_rows,
                require_complete_rows_only=not include_incomplete,
            )
            documents = list(iter_catalog_documents(rows, config))
            write_jsonl("data/catalog/embeddings/catalog_documents.jsonl", [doc.as_dict() for doc in documents])
            embeddings = CatalogEmbedder(config).embed_documents(documents)
            saved = self.vector_store.insert_embeddings(embeddings)
            self.vector_store.complete_job(
                job_id, processed_rows=len(documents), saved_rows=len(saved),
            )
            return {
                "input_csv_path": input_csv_path,
                "processed_rows": len(documents),
                "saved_rows": len(saved),
                "mode": "catalog_embeddings",
                "job_id": job_id,
            }
        except Exception:
            self.vector_store.fail_job(job_id, _format_exc())
            raise

    _RESYNC_PAGE_SIZE = 500

    def _fetch_enriched_rows(
        self,
        filters: Dict[str, str] | None,
        max_rows: int,
    ) -> List[Dict[str, Any]]:
        """Paginated fetch from catalog_enriched."""
        all_rows: List[Dict[str, Any]] = []
        page = self._RESYNC_PAGE_SIZE
        offset = 0
        while True:
            batch = self.vector_store.client.select_many(
                "catalog_enriched",
                filters=filters or None,
                order="product_id.asc",
                limit=page,
                offset=offset,
            )
            all_rows.extend(batch)
            if len(batch) < page:
                break
            offset += page
            if max_rows > 0 and len(all_rows) >= max_rows:
                all_rows = all_rows[:max_rows]
                break
        return all_rows

    def resync_catalog_embeddings(
        self,
        *,
        product_id_prefix: str = "",
        max_rows: int = 0,
        include_incomplete: bool = False,
    ) -> Dict[str, int | str]:
        """Re-generate embeddings from catalog_enriched (database).

        Unlike ``sync_catalog_embeddings`` which reads from a CSV and skips
        already-embedded products, this method reads the current enriched
        state from the database and **upserts** embeddings for items that
        already exist.  Use this after running a re-enrichment batch to
        refresh vectors and filter columns.
        """
        params: Dict[str, Any] = {
            "product_id_prefix": product_id_prefix,
            "max_rows": max_rows,
            "include_incomplete": include_incomplete,
        }
        job = self.vector_store.create_job("embeddings_resync", params)
        job_id = str(job.get("id") or "")
        try:
            filters: Dict[str, str] = {}
            if product_id_prefix:
                filters["product_id"] = f"like.{product_id_prefix}*"
            rows = self._fetch_enriched_rows(filters or None, max_rows)
            logger.info(
                "resync_catalog_embeddings: fetched %d rows from catalog_enriched (prefix=%r)",
                len(rows), product_id_prefix or "(all)",
            )
            config = CatalogEmbeddingConfig(
                require_complete_rows_only=not include_incomplete,
            )
            documents = list(iter_catalog_documents(rows, config))
            logger.info(
                "resync_catalog_embeddings: %d documents after row_status filter (from %d rows)",
                len(documents), len(rows),
            )
            if not documents:
                self.vector_store.complete_job(job_id, processed_rows=0, saved_rows=0)
                return {
                    "input_csv_path": "catalog_enriched",
                    "processed_rows": 0,
                    "saved_rows": 0,
                    "mode": "embeddings_resync",
                    "job_id": job_id,
                }
            embeddings = CatalogEmbedder(config).embed_documents(documents)
            saved = self.vector_store.insert_embeddings(embeddings)
            self.vector_store.complete_job(
                job_id, processed_rows=len(documents), saved_rows=len(saved),
            )
            return {
                "input_csv_path": "catalog_enriched",
                "processed_rows": len(documents),
                "saved_rows": len(saved),
                "mode": "embeddings_resync",
                "job_id": job_id,
            }
        except Exception:
            self.vector_store.fail_job(job_id, _format_exc())
            raise

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
