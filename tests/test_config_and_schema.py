import json
import unittest
from pathlib import Path

from catalog_enrichment.attributes import ATTRIBUTE_NAMES, ENUM_ATTRIBUTES, TEXT_ATTRIBUTES
from catalog_enrichment.config_registry import (
    load_body_harmony_attributes,
    load_garment_attributes,
    load_tier1_ranked_attributes,
    load_tier2_ranked_attributes,
    load_user_context_attributes,
)
from catalog_enrichment.schema_builder import build_schema


class ConfigAndSchemaTests(unittest.TestCase):
    def test_garment_config_counts_match_context_contract(self) -> None:
        enums, texts = load_garment_attributes()
        self.assertEqual(44, len(enums))
        self.assertEqual(2, len(texts))
        self.assertIn("PrimaryColor", texts)
        self.assertIn("SecondaryColor", texts)

    def test_attributes_module_is_config_backed(self) -> None:
        enums, texts = load_garment_attributes()
        self.assertEqual(enums, ENUM_ATTRIBUTES)
        self.assertEqual(texts, TEXT_ATTRIBUTES)
        self.assertEqual(set(list(enums.keys()) + texts), set(ATTRIBUTE_NAMES))

    def test_schema_contains_value_and_confidence_for_all_attributes(self) -> None:
        schema = build_schema()
        properties = schema["properties"]
        required = set(schema["required"])

        for attr in ATTRIBUTE_NAMES:
            self.assertIn(attr, properties)
            self.assertIn(f"{attr}_confidence", properties)
            self.assertIn(attr, required)
            self.assertIn(f"{attr}_confidence", required)

    def test_user_context_config_has_expected_dimensions(self) -> None:
        cfg = load_user_context_attributes()
        dims = cfg.get("dimensions") or {}
        self.assertEqual({"occasion", "archetype", "gender", "age"}, set(dims.keys()))
        self.assertIn("relaxable_filters", cfg)
        self.assertIn("tier1_filter_priority_order", cfg)

    def test_body_harmony_config_has_all_attributes(self) -> None:
        cfg = load_body_harmony_attributes()
        attrs = cfg.get("enum_attributes") or {}
        expected = {
            "HeightCategory",
            "BodyShape",
            "VisualWeight",
            "VerticalProportion",
            "ArmVolume",
            "MidsectionState",
            "WaistVisibility",
            "BustVolume",
            "SkinUndertone",
            "SkinSurfaceColor",
            "SkinContrast",
            "FaceShape",
            "NeckLength",
            "HairLength",
            "HairColor",
        }
        self.assertEqual(expected, set(attrs.keys()))

    def test_ranked_configs_reference_valid_garment_attributes(self) -> None:
        enums, _texts = load_garment_attributes()
        garment_attrs = set(enums.keys())

        tier1 = load_tier1_ranked_attributes()
        for attrs in (tier1.get("context_to_garment_attribute_priority_order") or {}).values():
            for attr in attrs:
                self.assertIn(attr, garment_attrs)

        tier2 = load_tier2_ranked_attributes()
        body_to_g = tier2.get("body_to_garment_priority_order") or {}
        for attrs in body_to_g.values():
            for attr in attrs:
                self.assertIn(attr, garment_attrs)

    def test_context_file_exists(self) -> None:
        self.assertTrue(Path("context_files/SINGLE_SOURCE_OF_TRUTH.md").exists())
        text = Path("context_files/SINGLE_SOURCE_OF_TRUTH.md").read_text(encoding="utf-8")
        self.assertIn("config/", text)

    def test_garment_config_file_is_valid_json(self) -> None:
        raw = Path("config/garment_attributes.json").read_text(encoding="utf-8")
        parsed = json.loads(raw)
        self.assertIn("enum_attributes", parsed)
        self.assertIn("text_attributes", parsed)


if __name__ == "__main__":
    unittest.main()
