import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
for p in (
    ROOT,
    ROOT / "modules" / "catalog" / "src",
    ROOT / "modules" / "catalog_retrieval" / "src",
    ROOT / "modules" / "platform_core" / "src",
    ROOT / "modules" / "user_profiler" / "src",
):
    sp = str(p)
    if sp not in sys.path:
        sys.path.insert(0, sp)

from catalog_retrieval.config import CatalogEmbeddingConfig
from catalog_retrieval.document_builder import build_catalog_document, iter_catalog_documents
from catalog_retrieval.repository import build_catalog_enriched_rows, build_catalog_item_rows
from catalog_retrieval.schemas import CatalogEmbeddingRecord
from catalog_retrieval.vector_store import SupabaseVectorStore
from catalog.admin_service import CatalogAdminService


class CatalogRetrievalTests(unittest.TestCase):
    def test_build_catalog_document_keeps_all_sections_and_marks_low_confidence(self) -> None:
        row = {
            "": "1",
            "id": "sku_1",
            "title": "Linen Wrap Blouse",
            "description": "<p>Soft linen blouse.</p>",
            "price": "89",
            "url": "https://example.com/p/1",
            "images__0__src": "https://example.com/1.jpg",
            "images__1__src": "",
            "row_status": "complete",
            "error_reason": "",
            "GarmentCategory": "Top",
            "GarmentCategory_confidence": "0.93",
            "GarmentSubtype": "Blouse",
            "GarmentSubtype_confidence": "0.88",
            "GarmentLength": "Hip Length",
            "GarmentLength_confidence": "0.91",
            "StylingCompleteness": "Needs Pairing",
            "StylingCompleteness_confidence": "0.9",
            "GenderExpression": "Feminine",
            "GenderExpression_confidence": "0.95",
            "SilhouetteContour": "Soft",
            "SilhouetteContour_confidence": "0.54",
            "SilhouetteType": "",
            "SilhouetteType_confidence": "0.0",
            "VolumeProfile": "Moderate",
            "VolumeProfile_confidence": "0.84",
            "FitEase": "Relaxed",
            "FitEase_confidence": "0.82",
            "FitType": "Relaxed",
            "FitType_confidence": "0.8",
            "ShoulderStructure": "Natural",
            "ShoulderStructure_confidence": "0.75",
            "WaistDefinition": "Defined",
            "WaistDefinition_confidence": "0.9",
            "HipDefinition": "Skimming",
            "HipDefinition_confidence": "0.83",
            "NecklineType": "V-Neck",
            "NecklineType_confidence": "0.92",
            "NecklineDepth": "Medium",
            "NecklineDepth_confidence": "0.81",
            "SleeveLength": "Three-Quarter",
            "SleeveLength_confidence": "0.88",
            "SkinExposureLevel": "Moderate",
            "SkinExposureLevel_confidence": "0.77",
            "FabricDrape": "Soft",
            "FabricDrape_confidence": "0.9",
            "FabricWeight": "Lightweight",
            "FabricWeight_confidence": "0.94",
            "FabricTexture": "Smooth",
            "FabricTexture_confidence": "0.9",
            "StretchLevel": "Low Stretch",
            "StretchLevel_confidence": "0.73",
            "EdgeSharpness": "Soft",
            "EdgeSharpness_confidence": "0.7",
            "ConstructionDetail": "Minimal",
            "ConstructionDetail_confidence": "0.69",
            "EmbellishmentLevel": "Minimal",
            "EmbellishmentLevel_confidence": "0.9",
            "EmbellishmentType": "None",
            "EmbellishmentType_confidence": "0.2",
            "EmbellishmentZone": "",
            "EmbellishmentZone_confidence": "0.0",
            "VerticalWeightBias": "Balanced",
            "VerticalWeightBias_confidence": "0.71",
            "VisualWeightPlacement": "Even",
            "VisualWeightPlacement_confidence": "0.7",
            "StructuralFocus": "Waist",
            "StructuralFocus_confidence": "0.7",
            "BodyFocusZone": "Upper Body",
            "BodyFocusZone_confidence": "0.7",
            "LineDirection": "Vertical",
            "LineDirection_confidence": "0.7",
            "PatternType": "Solid",
            "PatternType_confidence": "0.95",
            "PatternScale": "None",
            "PatternScale_confidence": "0.1",
            "PatternOrientation": "None",
            "PatternOrientation_confidence": "0.1",
            "ContrastLevel": "Low",
            "ContrastLevel_confidence": "0.9",
            "ColorTemperature": "Warm",
            "ColorTemperature_confidence": "0.85",
            "ColorSaturation": "Muted",
            "ColorSaturation_confidence": "0.88",
            "ColorValue": "Medium",
            "ColorValue_confidence": "0.81",
            "ColorCount": "Two Color",
            "ColorCount_confidence": "0.73",
            "PrimaryColor": "Sage Green",
            "PrimaryColor_confidence": "0.97",
            "SecondaryColor": "Cream",
            "SecondaryColor_confidence": "0.79",
            "FormalitySignalStrength": "Moderate",
            "FormalitySignalStrength_confidence": "0.7",
            "FormalityLevel": "Smart Casual",
            "FormalityLevel_confidence": "0.84",
            "OccasionFit": "Celebration",
            "OccasionFit_confidence": "0.82",
            "OccasionSignal": "Day Event",
            "OccasionSignal_confidence": "0.8",
            "TimeOfDay": "Daytime",
            "TimeOfDay_confidence": "0.88",
        }
        config = CatalogEmbeddingConfig()
        doc = build_catalog_document(row, 0, config)
        self.assertEqual("1", doc.row_id)
        self.assertEqual("sku_1", doc.product_id)
        self.assertIn("GARMENT_IDENTITY:", doc.document_text)
        self.assertIn("PATTERN_AND_COLOR:", doc.document_text)
        self.assertIn("- SilhouetteContour: Uncertain(Soft) [confidence=0.54]", doc.document_text)
        self.assertIn("- PatternScale: Unknown [confidence=0.10]", doc.document_text)
        self.assertIn("- description: Soft linen blouse.", doc.document_text)

    def test_iter_catalog_documents_respects_max_rows(self) -> None:
        config = CatalogEmbeddingConfig(max_rows=2)
        rows = [
            {"": "1", "id": "a", "row_status": "complete"},
            {"": "2", "id": "b", "row_status": "complete"},
            {"": "3", "id": "c", "row_status": "complete"},
        ]
        docs = list(iter_catalog_documents(rows, config))
        self.assertEqual(2, len(docs))
        self.assertEqual(["a", "b"], [doc.product_id for doc in docs])

    def test_build_catalog_item_rows_maps_catalog_for_upsert(self) -> None:
        rows = [
            {
                "": "7",
                "id": "sku_7",
                "title": "Oxford Shirt",
                "description": "desc",
                "price": "1999.0",
                "images__0__src": "https://img/1.jpg",
                "images__1__src": "https://img/2.jpg",
                "url": "https://example.com/sku_7",
                "row_status": "ok",
                "error_reason": "",
                "GarmentCategory": "top",
            }
        ]
        built = build_catalog_item_rows(rows)
        self.assertEqual(1, len(built))
        self.assertEqual("sku_7", built[0]["product_id"])
        self.assertEqual("Oxford Shirt", built[0]["title"])
        self.assertEqual(1999.0, built[0]["price"])
        self.assertEqual("ok", built[0]["row_status"])
        self.assertEqual("top", built[0]["metadata_json"]["GarmentCategory"])

    def test_vector_store_uses_upsert_for_catalog_items_and_embeddings(self) -> None:
        client = Mock()
        store = SupabaseVectorStore(client)
        store.upsert_catalog_enriched([{"product_id": "sku_1"}])
        client.upsert_many.assert_called_once_with("catalog_enriched", [{"product_id": "sku_1"}], on_conflict="product_id")

    def test_vector_store_dedupes_catalog_enriched_by_product_id(self) -> None:
        client = Mock()
        client.upsert_many.return_value = []
        store = SupabaseVectorStore(client)
        store.upsert_catalog_enriched(
            [
                {"product_id": "sku_1", "title": "First"},
                {"product_id": "sku_1", "title": "Second"},
            ]
        )
        client.upsert_many.assert_called_once_with(
            "catalog_enriched",
            [{"product_id": "sku_1", "title": "Second"}],
            on_conflict="product_id",
        )

    def test_vector_store_dedupes_embedding_rows_by_conflict_identity(self) -> None:
        client = Mock()
        client.upsert_many.return_value = []
        store = SupabaseVectorStore(client)
        store.insert_embeddings(
            [
                CatalogEmbeddingRecord(
                    row_id="1",
                    product_id="sku_1",
                    model="text-embedding-3-small",
                    dimensions=1536,
                    metadata={"price": "Unknown"},
                    document_text="doc 1",
                    embedding=[0.1, 0.2],
                ),
                CatalogEmbeddingRecord(
                    row_id="2",
                    product_id="sku_1",
                    model="text-embedding-3-small",
                    dimensions=1536,
                    metadata={"price": "Unknown"},
                    document_text="doc 2",
                    embedding=[0.3, 0.4],
                ),
            ]
        )
        client.upsert_many.assert_called_once()
        args, kwargs = client.upsert_many.call_args
        self.assertEqual("catalog_item_embeddings", args[0])
        self.assertEqual(1, len(args[1]))
        self.assertEqual("sku_1", args[1][0]["product_id"])
        self.assertEqual("doc 2", args[1][0]["document_text"])
        self.assertEqual("product_id,embedding_model,embedding_dimensions", kwargs["on_conflict"])

    def test_vector_store_skips_blank_embedding_identity(self) -> None:
        client = Mock()
        client.upsert_many.return_value = []
        store = SupabaseVectorStore(client)
        store.insert_embeddings(
            [
                CatalogEmbeddingRecord(
                    row_id="1",
                    product_id="",
                    model="text-embedding-3-small",
                    dimensions=1536,
                    metadata={"price": "Unknown"},
                    document_text="doc 1",
                    embedding=[0.1, 0.2],
                )
            ]
        )
        client.upsert_many.assert_not_called()

    def test_build_catalog_enriched_rows_maps_for_enriched_upsert(self) -> None:
        rows = [
            {
                "source_row_number": "7",
                "product_id": "sku_7",
                "title": "Oxford Shirt",
                "description": "desc",
                "price": "1999.0",
                "images_0_src": "https://img/1.jpg",
                "images_1_src": "https://img/2.jpg",
                "url": "https://example.com/sku_7",
                "row_status": "ok",
                "error_reason": "",
                "GarmentCategory": "top",
            }
        ]
        built = build_catalog_enriched_rows(rows)
        self.assertEqual(1, len(built))
        self.assertEqual("sku_7", built[0]["product_id"])
        self.assertEqual(7, built[0]["source_row_number"])
        self.assertEqual("Oxford Shirt", built[0]["title"])
        self.assertEqual("top", built[0]["GarmentCategory"])
        self.assertEqual("https://example.com/sku_7", built[0]["url"])

    def test_build_catalog_enriched_rows_synthesizes_canonical_url_from_store_and_handle(self) -> None:
        rows = [
            {
                "product_id": "sku_9",
                "title": "Resort Shirt",
                "store": "andamen",
                "handle": "palm-green-cotton-resort-shirt",
            }
        ]

        built = build_catalog_enriched_rows(rows)

        self.assertEqual(
            "https://www.andamen.com/products/palm-green-cotton-resort-shirt",
            built[0]["url"],
        )

    def test_build_catalog_enriched_rows_ignores_unnamed_columns(self) -> None:
        rows = [
            {
                "Unnamed: 0": "7",
                "product_id": "sku_8",
                "title": "Camp Collar Shirt",
                "GarmentCategory": "top",
            }
        ]
        built = build_catalog_enriched_rows(rows)
        self.assertEqual(1, len(built))
        self.assertNotIn("Unnamed: 0", built[0])

    def test_catalog_admin_sync_reports_missing_url_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            csv_path = Path(tmp_dir) / "catalog.csv"
            csv_path.write_text(
                "product_id,title,store,handle,url\n"
                "sku_1,Known URL,andamen,palm-green-cotton-resort-shirt,\n"
                "sku_2,Missing URL,unknown-store,no-handle,\n",
                encoding="utf-8",
            )
            vector_store = Mock()
            vector_store.upsert_catalog_enriched.return_value = [{"product_id": "sku_1"}, {"product_id": "sku_2"}]
            service = CatalogAdminService(vector_store=vector_store)

            result = service.sync_catalog_items(input_csv_path=str(csv_path))

        self.assertEqual(2, result["processed_rows"])
        self.assertEqual(2, result["saved_rows"])
        self.assertEqual(1, result["missing_url_rows"])

    def test_catalog_admin_backfills_canonical_urls_for_existing_rows(self) -> None:
        vector_store = Mock()
        vector_store.client.select_many.return_value = [
            {
                "product_id": "sku_1",
                "url": "",
                "raw_row_json": {
                    "store": "andamen",
                    "handle": "palm-green-cotton-resort-shirt",
                },
            },
            {
                "product_id": "sku_2",
                "url": "",
                "raw_row_json": {
                    "store": "unknown",
                    "handle": "missing-url",
                },
            },
        ]
        vector_store.upsert_catalog_enriched.return_value = [
            {
                "product_id": "sku_1",
                "url": "https://www.andamen.com/products/palm-green-cotton-resort-shirt",
            }
        ]
        service = CatalogAdminService(vector_store=vector_store)

        result = service.backfill_catalog_urls()

        self.assertEqual(2, result["processed_rows"])
        self.assertEqual(1, result["saved_rows"])
        self.assertEqual(1, result["missing_url_rows"])
        saved_rows = vector_store.upsert_catalog_enriched.call_args.args[0]
        self.assertEqual(
            "https://www.andamen.com/products/palm-green-cotton-resort-shirt",
            saved_rows[0]["url"],
        )


if __name__ == "__main__":
    unittest.main()
