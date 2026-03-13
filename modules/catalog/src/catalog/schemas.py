from pydantic import BaseModel, Field


class CatalogSyncRequest(BaseModel):
    input_csv_path: str = Field(default="data/catalog/enriched_catalog.csv", min_length=1)
    max_rows: int = Field(default=0, ge=0)
    include_incomplete: bool = False


class CatalogSyncResponse(BaseModel):
    input_csv_path: str
    processed_rows: int
    saved_rows: int
    missing_url_rows: int = 0
    mode: str


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


class CatalogAdminStatusResponse(BaseModel):
    source: CatalogSourceInfo
    catalog_enriched_count: int
    catalog_embeddings_count: int
    embedded_product_count: int
    latest_uploads: list[CatalogUploadFileInfo] = Field(default_factory=list)
