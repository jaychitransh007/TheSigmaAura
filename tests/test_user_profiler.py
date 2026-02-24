import tempfile
import unittest
from pathlib import Path

import sys

ROOT = Path(__file__).resolve().parents[1]
for p in (
    ROOT,
    ROOT / "modules" / "catalog_enrichment" / "src",
    ROOT / "modules" / "style_engine" / "src",
    ROOT / "modules" / "user_profiler" / "src",
):
    sp = str(p)
    if sp not in sys.path:
        sys.path.insert(0, sp)


from user_profiler.schemas import BODY_ENUMS, TEXT_ENUMS, textual_response_format, visual_response_format
from user_profiler.config import UserProfilerConfig
from user_profiler.service import _image_to_input_url, store_image_artifact


class UserProfilerTests(unittest.TestCase):
    def test_visual_model_is_gpt_5_2_and_textual_is_gpt_5_mini(self) -> None:
        cfg = UserProfilerConfig()
        self.assertEqual("gpt-5.2", cfg.visual_model)
        self.assertEqual("gpt-5-mini", cfg.textual_model)
        self.assertEqual("high", cfg.visual_reasoning_effort)

    def test_visual_schema_has_all_body_fields_plus_gender_age(self) -> None:
        fmt = visual_response_format()
        schema = fmt["schema"]
        props = schema["properties"]
        required = set(schema["required"])

        for name in BODY_ENUMS.keys():
            self.assertIn(name, props)
            self.assertIn(name, required)

        self.assertIn("gender", props)
        self.assertIn("age", props)
        self.assertIn("gender", required)
        self.assertIn("age", required)

    def test_textual_schema_uses_context_enums(self) -> None:
        fmt = textual_response_format()
        schema = fmt["schema"]
        self.assertEqual(TEXT_ENUMS["occasion"], schema["properties"]["occasion"]["enum"])
        self.assertEqual(TEXT_ENUMS["archetype"], schema["properties"]["archetype"]["enum"])

    def test_image_to_input_url_supports_http(self) -> None:
        url = "https://example.com/a.jpg"
        self.assertEqual(url, _image_to_input_url(url))

    def test_image_to_input_url_supports_local_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "photo.jpg"
            path.write_bytes(b"fake-image-content")
            out = _image_to_input_url(str(path))
            self.assertTrue(out.startswith("data:image/jpeg;base64,"))

    def test_store_image_artifact_for_local_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "photo.jpg"
            src.write_bytes(b"fake-image-content")
            artifacts_dir = Path(tmp) / "artifacts"
            meta = store_image_artifact(str(src), artifacts_dir)
            self.assertEqual("file", meta["source_type"])
            self.assertTrue(Path(meta["stored_path"]).exists())


if __name__ == "__main__":
    unittest.main()
