from fastapi import APIRouter, File, HTTPException, UploadFile

from platform_core.supabase_rest import SupabaseError
from .admin_service import CatalogAdminService
from .schemas import (
    CatalogAdminStatusResponse,
    CatalogResyncRequest,
    CatalogSyncRequest,
    CatalogSyncResponse,
    CatalogUploadResponse,
)


def create_catalog_admin_router(service: CatalogAdminService | None = None) -> APIRouter:
    router = APIRouter(prefix="/v1/admin/catalog", tags=["catalog-admin"])

    def get_service() -> CatalogAdminService:
        return service or CatalogAdminService()

    @router.post("/upload", response_model=CatalogUploadResponse)
    async def upload_catalog_csv(file: UploadFile = File(...)) -> CatalogUploadResponse:
        content = await file.read()
        path = get_service().save_uploaded_csv(file.filename or "catalog.csv", content)
        return CatalogUploadResponse(
            input_csv_path=path,
            filename=file.filename or "catalog.csv",
            bytes_written=len(content),
        )

    @router.get("/status", response_model=CatalogAdminStatusResponse)
    def get_catalog_status(input_csv_path: str = "data/catalog/enriched_catalog_upload.csv") -> CatalogAdminStatusResponse:
        try:
            result = get_service().get_status(input_csv_path=input_csv_path)
            return CatalogAdminStatusResponse(**result)
        except SupabaseError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @router.post("/items/sync", response_model=CatalogSyncResponse)
    def sync_catalog_items(payload: CatalogSyncRequest) -> CatalogSyncResponse:
        try:
            result = get_service().sync_catalog_items(
                input_csv_path=payload.input_csv_path,
                max_rows=payload.max_rows,
                start_row=payload.start_row,
                end_row=payload.end_row,
            )
            return CatalogSyncResponse(**result)
        except SupabaseError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Catalog sync failed: {exc}") from exc

    @router.post("/items/backfill-urls", response_model=CatalogSyncResponse)
    def backfill_catalog_urls(payload: CatalogSyncRequest) -> CatalogSyncResponse:
        try:
            result = get_service().backfill_catalog_urls(max_rows=payload.max_rows)
            return CatalogSyncResponse(**result)
        except SupabaseError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @router.post("/embeddings/sync", response_model=CatalogSyncResponse)
    def sync_catalog_embeddings(payload: CatalogSyncRequest) -> CatalogSyncResponse:
        try:
            result = get_service().sync_catalog_embeddings(
                input_csv_path=payload.input_csv_path,
                max_rows=payload.max_rows,
                start_row=payload.start_row,
                end_row=payload.end_row,
                include_incomplete=payload.include_incomplete,
            )
            return CatalogSyncResponse(**result)
        except SupabaseError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Embedding sync failed: {exc}") from exc

    @router.post("/embeddings/resync", response_model=CatalogSyncResponse)
    def resync_catalog_embeddings(payload: CatalogResyncRequest) -> CatalogSyncResponse:
        """Re-generate embeddings from catalog_enriched database.

        Reads the current enriched state from the DB (not CSV) and upserts
        embeddings — including items that already have embeddings. Use after
        a re-enrichment batch to refresh vectors and filter columns.
        """
        try:
            result = get_service().resync_catalog_embeddings(
                product_id_prefix=payload.product_id_prefix,
                max_rows=payload.max_rows,
                include_incomplete=payload.include_incomplete,
            )
            return CatalogSyncResponse(**result)
        except SupabaseError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Embedding resync failed: {exc}") from exc

    return router
