import json
import sys
import unittest
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


from catalog.enrichment.attributes import ATTRIBUTE_NAMES, ENUM_ATTRIBUTES, TEXT_ATTRIBUTES
from catalog.enrichment.config_registry import (
    load_body_harmony_attributes,
    load_garment_attributes,
    load_outfit_assembly_rules,
    load_intent_policy_rules,
    load_reinforcement_framework,
    load_tier1_ranked_attributes,
    load_tier2_ranked_attributes,
    load_user_context_attributes,
)
from catalog.enrichment.schema_builder import build_schema


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
        # CURRENT_STATE.md was retired May 3, 2026 — its content was
        # redistributed across PRODUCT.md / APPLICATION_SPECS.md /
        # OPERATIONS.md / WORKFLOW_REFERENCE.md / RELEASE_READINESS.md /
        # DESIGN.md. APPLICATION_SPECS.md § Live System Reference now
        # carries the source-of-truth runtime content.
        self.assertTrue(Path("docs/APPLICATION_SPECS.md").exists())
        text = Path("docs/APPLICATION_SPECS.md").read_text(encoding="utf-8")
        self.assertIn("agentic_application", text)

    def test_garment_config_file_is_valid_json(self) -> None:
        raw = Path("modules/style_engine/configs/config/garment_attributes.json").read_text(encoding="utf-8")
        parsed = json.loads(raw)
        self.assertIn("enum_attributes", parsed)
        self.assertIn("text_attributes", parsed)

    def test_outfit_assembly_config_exists_and_loads(self) -> None:
        cfg = load_outfit_assembly_rules()
        self.assertIn("default_mode", cfg)
        self.assertIn("pair_bonus", cfg)
        self.assertIn("candidate_limits", cfg)
        self.assertTrue(Path("modules/style_engine/configs/config/outfit_assembly_v1.json").exists())

    def test_reinforcement_rewards_match_ui_contract(self) -> None:
        cfg = load_reinforcement_framework()
        rewards = cfg.get("reward_weights") or {}
        self.assertEqual(20, rewards.get("buy"))
        self.assertEqual(10, rewards.get("share"))
        self.assertEqual(2, rewards.get("like"))
        self.assertEqual(-5, rewards.get("dislike"))
        self.assertEqual(-1, rewards.get("no_action"))
        self.assertEqual(-1, rewards.get("skip"))

    def test_intent_policy_config_exists_and_loads(self) -> None:
        cfg = load_intent_policy_rules()
        self.assertIn("policies", cfg)
        self.assertIn("high_stakes_work", cfg.get("policies") or {})
        self.assertTrue(Path("modules/style_engine/configs/config/intent_policy_v1.json").exists())


if __name__ == "__main__":
    unittest.main()
