import unittest

from catalog_enrichment.batch_builder import _normalize_image_url, build_request_body
from catalog_enrichment.config import PipelineConfig


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


if __name__ == "__main__":
    unittest.main()
