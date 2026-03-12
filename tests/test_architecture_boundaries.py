import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

from fastapi import FastAPI
from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
for p in (
    ROOT,
    ROOT / "modules" / "user" / "src",
    ROOT / "modules" / "agentic_application" / "src",
    ROOT / "modules" / "catalog" / "src",
    ROOT / "modules" / "catalog_retrieval" / "src",
    ROOT / "modules" / "conversation_platform" / "src",
    ROOT / "modules" / "user_profiler" / "src",
    ROOT / "modules" / "onboarding" / "src",
):
    sp = str(p)
    if sp not in sys.path:
        sys.path.insert(0, sp)


from agentic_application.api import create_app as create_agentic_app
from catalog.admin_api import create_catalog_admin_router
from catalog.ui import get_catalog_admin_html
from user.api import create_onboarding_router


class ArchitectureBoundaryTests(unittest.TestCase):
    def test_new_bounded_context_modules_import(self) -> None:
        self.assertTrue(callable(create_onboarding_router))
        self.assertTrue(callable(create_agentic_app))
        self.assertTrue(callable(create_catalog_admin_router))

    def test_catalog_admin_router_supports_upload_and_sync_contracts(self) -> None:
        service = Mock()
        service.get_status.return_value = {
            "source": {
                "input_csv_path": "data/catalog/uploads/test.csv",
                "total_rows": 10,
                "eligible_embedding_rows": 9,
            },
            "catalog_enriched_count": 5,
            "catalog_embeddings_count": 3,
            "embedded_product_count": 3,
            "latest_uploads": [],
        }
        service.save_uploaded_csv.return_value = "data/catalog/uploads/test.csv"
        service.sync_catalog_items.return_value = {
            "input_csv_path": "data/catalog/uploads/test.csv",
            "processed_rows": 5,
            "saved_rows": 5,
            "mode": "catalog_enriched",
        }
        service.sync_catalog_embeddings.return_value = {
            "input_csv_path": "data/catalog/uploads/test.csv",
            "processed_rows": 5,
            "saved_rows": 5,
            "mode": "catalog_embeddings",
        }

        app = FastAPI()
        app.include_router(create_catalog_admin_router(service))
        client = TestClient(app)

        status = client.get("/v1/admin/catalog/status")
        self.assertEqual(200, status.status_code)
        self.assertEqual(5, status.json()["catalog_enriched_count"])

        upload = client.post(
            "/v1/admin/catalog/upload",
            files={"file": ("catalog.csv", b"id,title\n1,Shirt\n", "text/csv")},
        )
        self.assertEqual(200, upload.status_code)
        self.assertEqual("data/catalog/uploads/test.csv", upload.json()["input_csv_path"])

        sync_items = client.post(
            "/v1/admin/catalog/items/sync",
            json={"input_csv_path": "data/catalog/uploads/test.csv", "max_rows": 5},
        )
        self.assertEqual(200, sync_items.status_code)
        self.assertEqual("catalog_enriched", sync_items.json()["mode"])

        sync_embeddings = client.post(
            "/v1/admin/catalog/embeddings/sync",
            json={"input_csv_path": "data/catalog/uploads/test.csv", "max_rows": 5},
        )
        self.assertEqual(200, sync_embeddings.status_code)
        self.assertEqual("catalog_embeddings", sync_embeddings.json()["mode"])

    def test_catalog_admin_html_renders_process_steps(self) -> None:
        html = get_catalog_admin_html()
        self.assertIn("Catalog Admin", html)
        self.assertIn("STEP 1", html)
        self.assertIn("Upload CSV", html)
        self.assertIn("Sync Catalog Enriched", html)
        self.assertIn("Generate Embeddings", html)


if __name__ == "__main__":
    unittest.main()
