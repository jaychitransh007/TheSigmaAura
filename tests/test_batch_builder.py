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

    def test_split_rows_token_cap_overrides_byte_cap(self) -> None:
        """When token-cap fires before byte-cap, the chunker still
        breaks correctly. Set a huge byte cap and tight token cap;
        verify each chunk holds at most one row."""
        from catalog.enrichment.main import (
            _estimate_request_input_tokens,
            _split_rows_for_max_batch_bytes,
        )
        rows = [
            {
                "description": f"Item {i}",
                "store": "Demo",
                "url": f"https://example.com/p/{i}",
                "images__0__src": f"https://cdn.shopify.com/{i}.jpg",
                "images__1__src": f"https://cdn.shopify.com/alt-{i}.jpg",
            }
            for i in range(5)
        ]
        config = PipelineConfig()
        per_row_tokens = _estimate_request_input_tokens(rows[0])
        chunks = _split_rows_for_max_batch_bytes(
            rows,
            config,
            max_batch_bytes=10_000_000_000,                 # effectively unlimited
            max_batch_input_tokens=per_row_tokens + 1,      # tight enough to break per row
        )
        self.assertEqual(len(chunks), 5)
        for chunk in chunks:
            self.assertEqual(len(chunk), 1)

    def test_split_rows_token_cap_zero_disables_token_check(self) -> None:
        """``max_batch_input_tokens=0`` is invalid (must be > 0 when set).
        The CLI flag converts ``0`` to ``None`` (= use config default
        or disable) — the function itself rejects 0 to catch bugs."""
        from catalog.enrichment.main import _split_rows_for_max_batch_bytes
        rows = [{"description": "x", "images__0__src": "https://x/y.jpg"}]
        config = PipelineConfig()
        with self.assertRaises(ValueError):
            _split_rows_for_max_batch_bytes(
                rows, config, max_batch_bytes=10_000_000, max_batch_input_tokens=0,
            )

    def test_split_rows_single_row_exceeds_token_cap_raises(self) -> None:
        from catalog.enrichment.main import (
            _estimate_request_input_tokens,
            _split_rows_for_max_batch_bytes,
        )
        row = {
            "description": "x",
            "store": "Demo",
            "url": "https://x/y",
            "images__0__src": "https://cdn.shopify.com/1.jpg",
        }
        config = PipelineConfig()
        per_row_tokens = _estimate_request_input_tokens(row)
        with self.assertRaises(RuntimeError):
            _split_rows_for_max_batch_bytes(
                [row], config,
                max_batch_bytes=10_000_000,
                max_batch_input_tokens=per_row_tokens - 1,
            )

    def test_split_rows_default_token_cap_from_config(self) -> None:
        """When ``max_batch_input_tokens`` is None, the function falls
        back to ``config.max_batch_input_tokens``."""
        from catalog.enrichment.main import _split_rows_for_max_batch_bytes
        rows = [
            {
                "description": f"Item {i}",
                "store": "Demo",
                "url": f"https://example.com/p/{i}",
                "images__0__src": f"https://cdn.shopify.com/{i}.jpg",
            }
            for i in range(3)
        ]
        config = PipelineConfig()
        # Default 1.5M tokens — easily fits 3 small rows in one chunk.
        chunks = _split_rows_for_max_batch_bytes(
            rows, config, max_batch_bytes=10_000_000_000, max_batch_input_tokens=None,
        )
        self.assertEqual(len(chunks), 1)
        self.assertEqual(len(chunks[0]), 3)

    def test_estimate_request_input_tokens_increases_with_image_count(self) -> None:
        from catalog.enrichment.main import _estimate_request_input_tokens
        no_images = {
            "description": "plain", "store": "Demo", "url": "https://x/y",
        }
        one_image = {**no_images, "images__0__src": "https://cdn/1.jpg"}
        two_images = {
            **no_images,
            "images__0__src": "https://cdn/1.jpg",
            "images__1__src": "https://cdn/2.jpg",
        }
        t0 = _estimate_request_input_tokens(no_images)
        t1 = _estimate_request_input_tokens(one_image)
        t2 = _estimate_request_input_tokens(two_images)
        self.assertGreater(t1, t0)
        self.assertGreater(t2, t1)
        # Each extra image adds ~300 tokens (matches _IMAGE_TOKENS_PER_IMAGE).
        self.assertEqual(t1 - t0, t2 - t1)

    def test_estimate_request_input_tokens_includes_system_prompt(self) -> None:
        """A request with no images and minimal text should still cost
        the system-prompt tokens (~3K) — the prompt is the floor."""
        from catalog.enrichment.main import _estimate_request_input_tokens
        empty_row = {"description": "", "store": "", "url": ""}
        tokens = _estimate_request_input_tokens(empty_row)
        # System prompt floor is several hundred tokens minimum.
        self.assertGreater(tokens, 500)

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
