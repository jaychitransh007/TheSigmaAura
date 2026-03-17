import unittest

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for p in (
    ROOT,
    ROOT / "modules" / "catalog" / "src",
    ROOT / "modules" / "platform_core" / "src",
    ROOT / "modules" / "user_profiler" / "src",
    ROOT / "modules" / "style_engine" / "src",
):
    sp = str(p)
    if sp not in sys.path:
        sys.path.insert(0, sp)


from catalog.enrichment.batch_builder import _normalize_image_url, build_request_body
from catalog.enrichment.config import PipelineConfig
from catalog.enrichment.main import (
    _extract_batch_error_message,
    _is_billing_hard_limit_error,
    _is_enqueued_token_limit_error,
    _request_line_bytes,
    _split_rows_for_max_batch_bytes,
)


class BatchBuilderTests(unittest.TestCase):
    def test_normalize_image_url_adds_width(self) -> None:
        url = "https://cdn.shopify.com/a.jpg"
        out = _normalize_image_url(url)
        self.assertEqual("https://cdn.shopify.com/a.jpg?width=768", out)

    def test_normalize_image_url_overrides_existing_width(self) -> None:
        url = "https://cdn.shopify.com/a.jpg?foo=1&width=512&bar=2"
        out = _normalize_image_url(url)
        self.assertIn("foo=1", out)
        self.assertIn("bar=2", out)
        self.assertIn("width=768", out)
        self.assertNotIn("width=512", out)

    def test_build_request_body_uses_model_and_prompt_and_images(self) -> None:
        row = {
            "description": "A sample",
            "store": "Demo",
            "url": "https://example.com/p/1",
            "images__0__src": "https://cdn.shopify.com/1.jpg?width=100",
            "images__1__src": "https://cdn.shopify.com/2.jpg",
        }
        body = build_request_body(row=row, config=PipelineConfig())
        self.assertEqual("gpt-5-mini", body["model"])
        content = body["input"][1]["content"]
        image_urls = [item["image_url"] for item in content if item.get("type") == "input_image"]
        self.assertEqual(2, len(image_urls))
        self.assertTrue(all("width=768" in u for u in image_urls))

    def test_split_rows_for_max_batch_bytes_splits_into_multiple_chunks(self) -> None:
        rows = [
            {
                "description": "Item one",
                "store": "Demo",
                "url": "https://example.com/p/1",
                "images__0__src": "https://cdn.shopify.com/1.jpg",
                "images__1__src": "https://cdn.shopify.com/2.jpg",
            },
            {
                "description": "Item two",
                "store": "Demo",
                "url": "https://example.com/p/2",
                "images__0__src": "https://cdn.shopify.com/3.jpg",
                "images__1__src": "https://cdn.shopify.com/4.jpg",
            },
        ]
        config = PipelineConfig()
        first_line_bytes = _request_line_bytes(rows[0], 0, config)
        chunks = _split_rows_for_max_batch_bytes(rows, config, max_batch_bytes=first_line_bytes + 8)
        self.assertEqual(2, len(chunks))
        self.assertEqual(1, len(chunks[0]))
        self.assertEqual(1, len(chunks[1]))

    def test_split_rows_for_max_batch_bytes_raises_when_row_exceeds_limit(self) -> None:
        rows = [
            {
                "description": "Item one",
                "store": "Demo",
                "url": "https://example.com/p/1",
                "images__0__src": "https://cdn.shopify.com/1.jpg",
                "images__1__src": "https://cdn.shopify.com/2.jpg",
            }
        ]
        config = PipelineConfig()
        first_line_bytes = _request_line_bytes(rows[0], 0, config)
        with self.assertRaises(RuntimeError):
            _split_rows_for_max_batch_bytes(rows, config, max_batch_bytes=first_line_bytes - 1)

    def test_detect_enqueued_token_limit_error(self) -> None:
        message = (
            "Enqueued token limit reached for gpt-5-mini in organization org_x. "
            "Limit: 5,000,000 enqueued tokens."
        )
        self.assertTrue(_is_enqueued_token_limit_error(message))
        self.assertFalse(_is_enqueued_token_limit_error("random network timeout"))

    def test_detect_billing_hard_limit_error(self) -> None:
        message = "Error code: 400 - {'error': {'code': 'billing_hard_limit_reached'}}"
        self.assertTrue(_is_billing_hard_limit_error(message))
        self.assertFalse(_is_billing_hard_limit_error("random network timeout"))

    def test_extract_batch_error_message_from_failed_batch(self) -> None:
        batch_data = {
            "status": "failed",
            "errors": {
                "data": [
                    {
                        "code": "token_limit",
                        "message": "Enqueued token limit reached for gpt-5-mini.",
                    }
                ]
            },
        }
        msg = _extract_batch_error_message(batch_data)
        self.assertIn("token_limit", msg)
        self.assertIn("Enqueued token limit reached", msg)


if __name__ == "__main__":
    unittest.main()
