from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class CatalogSyncRequest(BaseModel):
    input_csv_path: str = Field(default="data/catalog/enriched_catalog_upload.csv", min_length=1)
    max_rows: int = Field(default=0, ge=0)
    start_row: int = Field(default=0, ge=0)
    end_row: int = Field(default=0, ge=0)
    include_incomplete: bool = False


class CatalogSyncResponse(BaseModel):
    input_csv_path: str
    processed_rows: int
    saved_rows: int
    missing_url_rows: int = 0
    mode: str
    job_id: str = ""


class CatalogUploadResponse(BaseModel):
    input_csv_path: str
    filename: str
    bytes_written: int


class CatalogSourceInfo(BaseModel):
    input_csv_path: str
    total_rows: int
    eligible_embedding_rows: int


class CatalogUploadFileInfo(BaseModel):
    filename: str
    input_csv_path: str
    modified_at: str


class CatalogJobInfo(BaseModel):
    id: str
    job_type: str
    status: str
    params_json: Dict[str, Any] = Field(default_factory=dict)
    processed_rows: Optional[int] = None
    saved_rows: Optional[int] = None
    missing_url_rows: Optional[int] = None
    error_message: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    created_at: str = ""


class CatalogAdminStatusResponse(BaseModel):
    source: CatalogSourceInfo
    catalog_enriched_count: int
    catalog_embeddings_count: int
    embedded_product_count: int
    total_jobs: int = 0
    running_jobs: int = 0
    failed_jobs: int = 0
    recent_jobs: List[CatalogJobInfo] = Field(default_factory=list)
    latest_uploads: list[CatalogUploadFileInfo] = Field(default_factory=list)
