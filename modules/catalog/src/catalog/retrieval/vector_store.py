import logging
import os
from typing import Any, Dict, Iterable, List

from platform_core.supabase_rest import SupabaseRestClient

logger = logging.getLogger(__name__)

UPSERT_BATCH_SIZE = 50

from .schemas import CatalogEmbeddingRecord


def _ensure_rest_url(base: str) -> str:
    url = base.rstrip("/")
    if url.endswith("/rest/v1"):
        return url
    return f"{url}/rest/v1"


def _load_supabase_client() -> SupabaseRestClient:
    env_file = os.getenv("ENV_FILE", "").strip()
    app_env = os.getenv("APP_ENV", "").strip().lower()
    if not env_file and app_env == "staging":
        env_file = ".env.staging"
    elif not env_file and app_env == "local":
        env_file = ".env.local"
    elif not env_file and os.path.exists(".env.local"):
        env_file = ".env.local"
    if not env_file:
        raise RuntimeError("Set APP_ENV=local or APP_ENV=staging, or provide ENV_FILE explicitly.")
    if app_env in {"staging", "local"} and env_file and not os.path.exists(env_file):
        raise RuntimeError(f"APP_ENV={app_env} requires {env_file} to exist.")
    if env_file and os.path.exists(env_file):
        with open(env_file, "r", encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key:
                    os.environ[key] = value
    supabase_url = os.getenv("SUPABASE_URL", "").strip() or os.getenv("API_URL", "").strip()
    rest_url = os.getenv("SUPABASE_REST_URL", "").strip()
    if not rest_url:
        if not supabase_url:
            raise RuntimeError("Missing SUPABASE_URL or SUPABASE_REST_URL in environment.")
        rest_url = _ensure_rest_url(supabase_url)
    service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not service_role_key:
        raise RuntimeError("Missing SUPABASE_SERVICE_ROLE_KEY in environment.")
    return SupabaseRestClient(rest_url=rest_url, service_role_key=service_role_key)


def _vector_literal(values: List[float]) -> str:
    return "[" + ",".join(f"{value:.10f}" for value in values) + "]"


def _dedupe_rows_by_key(rows: Iterable[Dict[str, Any]], *, key_fields: List[str]) -> List[Dict[str, Any]]:
    deduped: Dict[tuple[Any, ...], Dict[str, Any]] = {}
    for row in rows:
        key = tuple(row.get(field) for field in key_fields)
        deduped[key] = row
    return list(deduped.values())


def _has_blank_identity(row: Dict[str, Any], *, key_fields: List[str]) -> bool:
    for field in key_fields:
        value = str(row.get(field) or "").strip()
        if not value:
            return True
    return False


class SupabaseVectorStore:
    def __init__(self, client: SupabaseRestClient | None = None) -> None:
        self._client = client or _load_supabase_client()

    @property
    def client(self) -> SupabaseRestClient:
        return self._client

    def upsert_catalog_enriched(self, rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
        payload = [
            row for row in _dedupe_rows_by_key(rows, key_fields=["product_id"])
            if not _has_blank_identity(row, key_fields=["product_id"])
        ]
        if not payload:
            return []
        saved: List[Dict[str, Any]] = []
        for i in range(0, len(payload), UPSERT_BATCH_SIZE):
            batch = payload[i : i + UPSERT_BATCH_SIZE]
            logger.info("Upserting catalog_enriched batch %d–%d of %d", i + 1, i + len(batch), len(payload))
            saved.extend(self._client.upsert_many("catalog_enriched", batch, on_conflict="product_id"))
        return saved

    def catalog_status(self) -> Dict[str, Any]:
        rows = self._client.rpc("catalog_admin_status", {})
        if isinstance(rows, list) and rows:
            return dict(rows[0])
        if isinstance(rows, dict):
            return rows
        return {
            "catalog_enriched_count": 0,
            "catalog_embeddings_count": 0,
            "embedded_product_count": 0,
        }

    def insert_embeddings(self, records: Iterable[CatalogEmbeddingRecord]) -> List[Dict[str, Any]]:
        rows = []
        for record in records:
            rows.append(
                {
                    "catalog_row_id": record.row_id,
                    "product_id": record.product_id,
                    "embedding_model": record.model,
                    "embedding_dimensions": record.dimensions,
                    "document_text": record.document_text,
                    "metadata_json": record.metadata,
                    "garment_category": record.metadata.get("GarmentCategory"),
                    "garment_subtype": record.metadata.get("GarmentSubtype"),
                    "styling_completeness": record.metadata.get("StylingCompleteness"),
                    "gender_expression": record.metadata.get("GenderExpression"),
                    "formality_level": record.metadata.get("FormalityLevel"),
                    "occasion_fit": record.metadata.get("OccasionFit"),
                    "time_of_day": record.metadata.get("TimeOfDay"),
                    "primary_color": record.metadata.get("PrimaryColor"),
                    "price": record.metadata.get("price") if str(record.metadata.get("price") or "").strip() not in {"", "Unknown"} else None,
                    "embedding": _vector_literal(record.embedding),
                }
            )
        rows = [
            row
            for row in _dedupe_rows_by_key(
                rows,
                key_fields=["product_id", "embedding_model", "embedding_dimensions"],
            )
            if not _has_blank_identity(
                row,
                key_fields=["product_id", "embedding_model", "embedding_dimensions"],
            )
        ]
        if not rows:
            return []
        saved: List[Dict[str, Any]] = []
        for i in range(0, len(rows), UPSERT_BATCH_SIZE):
            batch = rows[i : i + UPSERT_BATCH_SIZE]
            logger.info("Upserting embeddings batch %d–%d of %d", i + 1, i + len(batch), len(rows))
            saved.extend(
                self._client.upsert_many(
                    "catalog_item_embeddings",
                    batch,
                    on_conflict="product_id,embedding_model,embedding_dimensions",
                )
            )
        return saved

    def embedded_product_ids(self) -> set[str]:
        """Return the set of product_ids that already have embeddings."""
        ids: set[str] = set()
        batch_size = 1000
        cursor = ""
        while True:
            filters = {"product_id": f"gt.{cursor}"} if cursor else None
            rows = self._client.select_many(
                "catalog_item_embeddings",
                columns="product_id",
                limit=batch_size,
                order="product_id.asc",
                filters=filters,
            )
            for row in rows:
                pid = str(row.get("product_id") or "").strip()
                if pid:
                    ids.add(pid)
            if len(rows) < batch_size:
                break
            cursor = rows[-1].get("product_id", "")
        return ids

    def create_job(self, job_type: str, params: Dict[str, Any] | None = None) -> Dict[str, Any]:
        return self._client.insert_one(
            "catalog_jobs",
            {
                "job_type": job_type,
                "status": "running",
                "params_json": params or {},
            },
        )

    def complete_job(
        self,
        job_id: str,
        *,
        processed_rows: int = 0,
        saved_rows: int = 0,
        missing_url_rows: int = 0,
    ) -> None:
        self._client.update_one(
            "catalog_jobs",
            filters={"id": f"eq.{job_id}"},
            patch={
                "status": "completed",
                "processed_rows": processed_rows,
                "saved_rows": saved_rows,
                "missing_url_rows": missing_url_rows,
            },
        )

    def fail_job(self, job_id: str, error_message: str) -> None:
        self._client.update_one(
            "catalog_jobs",
            filters={"id": f"eq.{job_id}"},
            patch={
                "status": "failed",
                "error_message": error_message[:2000],
            },
        )

    def recent_jobs(self, limit: int = 20) -> List[Dict[str, Any]]:
        return self._client.select_many(
            "catalog_jobs",
            columns="id,job_type,status,params_json,processed_rows,saved_rows,missing_url_rows,error_message,started_at,completed_at,created_at",
            order="created_at.desc",
            limit=limit,
        )

    def similarity_search(self, *, query_embedding: List[float], match_count: int, filters: Dict[str, Any]) -> Any:
        return self._client.rpc(
            "match_catalog_item_embeddings",
            {
                "query_embedding": _vector_literal(query_embedding),
                "match_count": match_count,
                "filter": filters,
            },
        )
