"""Tests for the Gemini-2.5-Flash catalog enrichment migration.

Covers schema-builder shape, runner happy-path with mocked client,
and runner error paths (no images, JSON decode failure, bad response).

Live Gemini calls are deliberately NOT exercised — those happen
manually via ``ops/scripts/run_gemini_enrichment.py`` against the
staging API key.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
for p in (
    ROOT,
    ROOT / "modules" / "agentic_application" / "src",
    ROOT / "modules" / "catalog" / "src",
    ROOT / "modules" / "platform_core" / "src",
    ROOT / "modules" / "style_engine" / "src",
    ROOT / "modules" / "user" / "src",
    ROOT / "modules" / "user_profiler" / "src",
):
    sp = str(p)
    if sp not in sys.path:
        sys.path.insert(0, sp)

from catalog.enrichment.gemini_schema_builder import build_gemini_response_schema


class GeminiSchemaBuilderTests(unittest.TestCase):
    def test_enum_attribute_emits_uppercase_string_with_enum_and_nullable(self):
        enums = {"GarmentCategory": ["top", "bottom", "outerwear"]}
        schema = build_gemini_response_schema(enums, [])
        prop = schema["properties"]["GarmentCategory"]
        self.assertEqual(prop["type"], "STRING")
        self.assertEqual(prop["enum"], ["top", "bottom", "outerwear"])
        self.assertTrue(prop["nullable"])

    def test_each_enum_attribute_gets_a_confidence_companion(self):
        enums = {"GarmentCategory": ["top", "bottom"]}
        schema = build_gemini_response_schema(enums, [])
        conf = schema["properties"]["GarmentCategory_confidence"]
        self.assertEqual(conf["type"], "NUMBER")
        self.assertEqual(conf["minimum"], 0)
        self.assertEqual(conf["maximum"], 1)

    def test_text_attributes_emit_string_without_enum(self):
        schema = build_gemini_response_schema({}, ["PrimaryColor"])
        prop = schema["properties"]["PrimaryColor"]
        self.assertEqual(prop["type"], "STRING")
        self.assertNotIn("enum", prop)
        self.assertTrue(prop["nullable"])

    def test_required_lists_value_and_confidence_for_every_attribute(self):
        enums = {"A": ["x", "y"]}
        texts = ["B"]
        schema = build_gemini_response_schema(enums, texts)
        self.assertEqual(
            set(schema["required"]),
            {"A", "A_confidence", "B", "B_confidence"},
        )

    def test_object_root_type(self):
        schema = build_gemini_response_schema({"X": ["x"]}, [])
        self.assertEqual(schema["type"], "OBJECT")

    def test_loads_canonical_registry_without_error(self):
        # End-to-end check: build a schema from the actual canonical
        # attribute registry to catch accidental drift between the
        # schema builder and ``garment_attributes.json``.
        from catalog.enrichment.config_registry import load_garment_attributes
        enums, texts = load_garment_attributes()
        schema = build_gemini_response_schema(enums, texts)
        # Canonical post-Path-B: 55 enum + 2 text = 57 attributes
        # × 2 (value + confidence) = 114 properties.
        self.assertEqual(len(schema["properties"]), 114)
        self.assertEqual(len(schema["required"]), 114)


class GeminiEnrichmentRunnerTests(unittest.TestCase):
    """Runner tests use a fully mocked Gemini client. No network calls."""

    def setUp(self):
        # Patch genai.Client so the runner doesn't need a real API key.
        self.client_patcher = patch(
            "catalog.enrichment.gemini_runner.genai.Client",
            return_value=MagicMock(),
        )
        self.client_patcher.start()
        # Patch the API-key loader so missing env doesn't fail tests.
        self.key_patcher = patch(
            "catalog.enrichment.gemini_runner.get_gemini_api_key",
            return_value="test-key",
        )
        self.key_patcher.start()

    def tearDown(self):
        self.client_patcher.stop()
        self.key_patcher.stop()

    def _make_runner(self):
        from catalog.enrichment.gemini_runner import GeminiEnrichmentRunner
        return GeminiEnrichmentRunner()

    def _stub_response(self, json_text: str) -> MagicMock:
        response = MagicMock()
        response.text = json_text
        return response

    def test_happy_path_parses_payload_into_dict(self):
        runner = self._make_runner()
        runner._client.models.generate_content.return_value = self._stub_response(
            json.dumps({
                "GarmentCategory": "top",
                "GarmentCategory_confidence": 0.95,
            })
        )
        # Patch image download so we don't touch the network.
        with patch(
            "catalog.enrichment.gemini_runner._download_image",
            return_value=(b"fake-image-bytes", "image/jpeg"),
        ):
            result = runner.enrich_row({
                "product_id": "P-1",
                "description": "Navy blue tailored kurta",
                "images__0__src": "https://example.com/img1.jpg",
            })
        self.assertEqual(result["row_status"], "ok")
        self.assertEqual(result["GarmentCategory"], "top")
        self.assertEqual(result["GarmentCategory_confidence"], 0.95)
        self.assertEqual(result["custom_id"], "P-1")
        self.assertEqual(result["error_reason"], "")

    def test_invalid_json_returns_error_status(self):
        runner = self._make_runner()
        runner._client.models.generate_content.return_value = self._stub_response(
            "this is not json"
        )
        with patch(
            "catalog.enrichment.gemini_runner._download_image",
            return_value=(b"fake-image-bytes", "image/jpeg"),
        ):
            result = runner.enrich_row({
                "product_id": "P-2",
                "images__0__src": "https://example.com/img1.jpg",
            })
        self.assertEqual(result["row_status"], "error")
        self.assertIn("not valid JSON", result["error_reason"])
        self.assertIn("raw_response_excerpt", result)

    def test_no_accessible_images_returns_error(self):
        runner = self._make_runner()
        # Both image downloads fail.
        with patch(
            "catalog.enrichment.gemini_runner._download_image",
            side_effect=OSError("Connection refused"),
        ):
            result = runner.enrich_row({
                "product_id": "P-3",
                "images__0__src": "https://example.com/img1.jpg",
                "images__1__src": "https://example.com/img2.jpg",
            })
        self.assertEqual(result["row_status"], "error")
        self.assertIn("No accessible product images", result["error_reason"])
        # API was not called — no images to send.
        runner._client.models.generate_content.assert_not_called()

    def test_no_image_urls_returns_error_without_api_call(self):
        runner = self._make_runner()
        result = runner.enrich_row({
            "product_id": "P-4",
            "description": "Some description but no images",
        })
        self.assertEqual(result["row_status"], "error")
        runner._client.models.generate_content.assert_not_called()

    def test_empty_response_text_returns_error(self):
        runner = self._make_runner()
        runner._client.models.generate_content.return_value = self._stub_response("")
        with patch(
            "catalog.enrichment.gemini_runner._download_image",
            return_value=(b"fake-image-bytes", "image/jpeg"),
        ):
            result = runner.enrich_row({
                "product_id": "P-5",
                "images__0__src": "https://example.com/img.jpg",
            })
        self.assertEqual(result["row_status"], "error")
        self.assertIn("empty", result["error_reason"])

    def test_unexpected_exception_caught_and_returns_error(self):
        runner = self._make_runner()
        runner._client.models.generate_content.side_effect = RuntimeError("boom")
        with patch(
            "catalog.enrichment.gemini_runner._download_image",
            return_value=(b"fake-image-bytes", "image/jpeg"),
        ):
            result = runner.enrich_row({
                "product_id": "P-6",
                "images__0__src": "https://example.com/img.jpg",
            })
        self.assertEqual(result["row_status"], "error")
        self.assertIn("RuntimeError", result["error_reason"])
        self.assertIn("boom", result["error_reason"])

    def test_enrich_rows_preserves_order_with_concurrent_execution(self):
        runner = self._make_runner()
        # Each row gets a different stubbed response so we can verify ordering.
        responses = [
            self._stub_response(json.dumps({"GarmentCategory": cat, "GarmentCategory_confidence": 0.9}))
            for cat in ("top", "bottom", "outerwear", "one_piece", "set")
        ]
        runner._client.models.generate_content.side_effect = responses

        rows = [
            {"product_id": f"P-{i}", "images__0__src": f"https://example.com/{i}.jpg"}
            for i in range(5)
        ]
        with patch(
            "catalog.enrichment.gemini_runner._download_image",
            return_value=(b"fake-image-bytes", "image/jpeg"),
        ):
            results = runner.enrich_rows(rows)
        self.assertEqual(len(results), 5)
        for i, r in enumerate(results):
            self.assertEqual(r["custom_id"], f"P-{i}")
            self.assertEqual(r["row_status"], "ok")

    def test_enrich_rows_empty_input_returns_empty(self):
        runner = self._make_runner()
        self.assertEqual(runner.enrich_rows([]), [])


if __name__ == "__main__":
    unittest.main()
