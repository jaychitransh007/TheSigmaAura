"""Tests for the Phase 4.7a style-graph YAML loader.

The loader (``agentic_application.composition.yaml_loader``) is the gate to
every other 4.7 sub-PR — if it fails to round-trip the canonical 8 YAMLs,
the composition engine cannot run. These tests assert:

- Every YAML loads without errors and produces non-empty containers.
- Required structural anchors are present (BodyShape / FrameStructure on
  body_frame, primary_archetype / risk_tolerance / formality_lean on
  archetype, SubSeason on palette, etc.).
- Every attribute name referenced under ``flatters`` / ``avoid`` round-trips
  against ``garment_attributes.json`` — no unknown names sneak in.
- The loader is idempotent: two calls return the same instance, two
  freshly-loaded instances (cache cleared between) are structurally equal.
- A missing YAML raises a clear ``FileNotFoundError``.
- An unknown attribute name raises ``StyleGraphValidationError``.
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

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

from agentic_application.composition.yaml_loader import (
    AttributeMapping,
    ColorHarmonyType,
    FusionRule,
    OccasionEntry,
    PairingRule,
    PairingRuleGroup,
    QueryStructureEntry,
    StyleGraph,
    StyleGraphValidationError,
    WeatherEntry,
    clear_cache,
    load_style_graph,
)


CANON_STYLE_GRAPH_DIR = ROOT / "knowledge" / "style_graph"
CANON_GARMENT_ATTRS = (
    ROOT / "modules" / "style_engine" / "configs" / "config" / "garment_attributes.json"
)


class StyleGraphLoadTests(unittest.TestCase):
    """Happy-path coverage against the real on-disk YAMLs."""

    def setUp(self) -> None:
        clear_cache()

    def test_all_eight_yamls_load(self):
        graph = load_style_graph()
        self.assertIsInstance(graph, StyleGraph)
        self.assertGreater(len(graph.occasion), 30, "occasion.yaml should have 30+ entries")
        self.assertEqual(len(graph.weather), 10, "weather.yaml should have 10 climate buckets")
        self.assertEqual(
            set(graph.query_structure.keys()),
            {"occasion_recommendation", "pairing_request", "fallback"},
        )
        self.assertEqual(len(graph.body_frame_female), 16)
        self.assertEqual(len(graph.body_frame_male), 16)
        self.assertEqual(len(graph.pairing_rules), 9)

    def test_required_structural_anchors_present(self):
        graph = load_style_graph()
        for body in (graph.body_frame_female, graph.body_frame_male):
            self.assertIn("BodyShape", body)
            self.assertIn("FrameStructure", body)
        for required in ("primary_archetype", "risk_tolerance", "formality_lean"):
            self.assertIn(required, graph.archetype)
        self.assertIn("SubSeason", graph.palette)

    def test_occasion_entry_carries_metadata(self):
        graph = load_style_graph()
        occ = graph.occasion["daily_office_mnc"]
        self.assertIsInstance(occ, OccasionEntry)
        self.assertEqual(occ.archetype, "work_mode")
        self.assertEqual(occ.formality, "smart_casual")
        self.assertEqual(occ.time, "daytime")
        self.assertIn("spring", occ.seasons)
        self.assertGreater(len(occ.mapping.flatters), 0)
        self.assertGreater(len(occ.mapping.avoid), 0)

    def test_weather_entry_carries_metadata(self):
        graph = load_style_graph()
        hh = graph.weather["hot_humid"]
        self.assertIsInstance(hh, WeatherEntry)
        self.assertTrue(hh.description)
        self.assertTrue(hh.temp_range_c)
        self.assertGreater(len(hh.indian_regions), 0)
        self.assertIn("FabricWeight", hh.mapping.flatters)

    def test_query_structure_carries_default_and_alternatives(self):
        graph = load_style_graph()
        rec = graph.query_structure["occasion_recommendation"]
        diwali = rec["diwali"]
        self.assertIsInstance(diwali, QueryStructureEntry)
        self.assertEqual(diwali.default_structure, "complete")
        self.assertEqual(diwali.intent, "occasion_recommendation")
        # Diwali has cultural_variants (indian_traditional / indian_fusion).
        self.assertIn("indian_traditional", diwali.cultural_variants)

        # pairing_request entries carry fills_slots, not cultural_variants.
        pair = graph.query_structure["pairing_request"]
        anchor_top = pair["anchor_top"]
        self.assertEqual(anchor_top.fills_slots, ("bottom", "outerwear"))
        self.assertEqual(anchor_top.cultural_variants, {})

    def test_pairing_rule_group_carries_typed_rules(self):
        graph = load_style_graph()
        formality = graph.pairing_rules["formality_alignment"]
        self.assertIsInstance(formality, PairingRuleGroup)
        self.assertEqual(formality.rule_type, "hard_constraint")
        # rules → typed PairingRule instances
        rule = formality.rules["formality_within_one_step"]
        self.assertIsInstance(rule, PairingRule)
        # formality_within_one_step carries the canonical scale + matrix
        self.assertEqual(
            rule.formality_scale,
            ("casual", "smart_casual", "semi_formal", "formal", "ceremonial"),
        )
        self.assertIn("casual", rule.compatibility_matrix)
        # examples_valid / examples_invalid lift cleanly into tuples
        self.assertGreater(len(rule.examples_valid), 0)
        self.assertGreater(len(rule.examples_invalid), 0)

    def test_pairing_rule_numeric_value_field_preserved(self):
        # max_dominant_colors is the only sub-rule with `value: 3`.
        graph = load_style_graph()
        max_colors = graph.pairing_rules["color_story"].rules["max_dominant_colors"]
        self.assertEqual(max_colors.value, 3)

    def test_pairing_rule_group_color_harmony_types_typed(self):
        graph = load_style_graph()
        color_story = graph.pairing_rules["color_story"]
        # The 5 named harmony types live under color_harmony_types,
        # not under rules — verify they decode into typed instances.
        self.assertEqual(
            set(color_story.color_harmony_types.keys()),
            {"monochromatic", "analogous", "complementary", "tonal", "neutral_plus_anchor"},
        )
        mono = color_story.color_harmony_types["monochromatic"]
        self.assertIsInstance(mono, ColorHarmonyType)
        self.assertIn("ColorCount", mono.flatters)

    def test_pairing_rule_group_fusion_rules_typed(self):
        graph = load_style_graph()
        cultural = graph.pairing_rules["cultural_coherence"]
        self.assertEqual(
            set(cultural.fusion_rules.keys()),
            {
                "indian_traditional_only",
                "indo_western_fusion",
                "western_only",
                "heavy_traditional_no_western_fusion",
            },
        )
        rule = cultural.fusion_rules["indo_western_fusion"]
        self.assertIsInstance(rule, FusionRule)
        self.assertTrue(rule.description)

    def test_pairing_rule_group_level_metadata_lifted(self):
        graph = load_style_graph()
        # anchor_constraints carries a group-level description.
        anchor = graph.pairing_rules["anchor_constraints"]
        self.assertTrue(anchor.description)
        # scale_balance carries a group-level statement_definition.
        scale = graph.pairing_rules["scale_balance"]
        self.assertTrue(scale.statement_definition)

    def test_pairing_rules_attribute_names_validated(self):
        # Tampering: inject an unknown attribute under a sub-rule's flatters
        # block. Loader must catch it the same way it catches unknowns in
        # the other YAMLs.
        import shutil, tempfile, yaml as _yaml

        tmp = Path(tempfile.mkdtemp())
        try:
            sg = tmp / "style_graph"
            shutil.copytree(CANON_STYLE_GRAPH_DIR, sg)
            pr_path = sg / "pairing_rules.yaml"
            with open(pr_path) as f:
                doc = _yaml.safe_load(f)
            doc["pairing_rules"]["bridal_specific"]["rules"]["bridal_lehenga_pairing"][
                "flatters"
            ]["BogusAttr"] = ["x"]
            with open(pr_path, "w") as f:
                _yaml.safe_dump(doc, f)
            clear_cache()
            with self.assertRaises(StyleGraphValidationError) as cm:
                load_style_graph(sg)
            self.assertIn("BogusAttr", str(cm.exception))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
            clear_cache()

    def test_attribute_mapping_values_are_tuples(self):
        graph = load_style_graph()
        hourglass = graph.body_frame_female["BodyShape"]["Hourglass"]
        self.assertIsInstance(hourglass, AttributeMapping)
        for values in hourglass.flatters.values():
            self.assertIsInstance(values, tuple)
        for values in hourglass.avoid.values():
            self.assertIsInstance(values, tuple)

    def test_known_attributes_match_garment_attributes_json(self):
        with open(CANON_GARMENT_ATTRS, "r", encoding="utf-8") as f:
            doc = json.load(f)
        expected = set((doc.get("enum_attributes") or {}).keys()) | set(
            doc.get("text_attributes") or []
        )
        graph = load_style_graph()
        self.assertEqual(graph.known_attributes, frozenset(expected))

    def test_every_referenced_attribute_is_known(self):
        """Round-trip: walk every flatters/avoid block and confirm each
        attribute name is in graph.known_attributes."""
        graph = load_style_graph()
        known = graph.known_attributes
        bad: list[str] = []

        def _check(label, mapping: AttributeMapping):
            for attr in mapping.flatters:
                if attr not in known:
                    bad.append(f"{label}.flatters: {attr}")
            for attr in mapping.avoid:
                if attr not in known:
                    bad.append(f"{label}.avoid: {attr}")

        for dim_name, values in graph.body_frame_female.items():
            for v_name, m in values.items():
                _check(f"body_frame_female.{dim_name}.{v_name}", m)
        for dim_name, values in graph.body_frame_male.items():
            for v_name, m in values.items():
                _check(f"body_frame_male.{dim_name}.{v_name}", m)
        for dim_name, values in graph.archetype.items():
            for v_name, m in values.items():
                _check(f"archetype.{dim_name}.{v_name}", m)
        for dim_name, values in graph.palette.items():
            for v_name, m in values.items():
                _check(f"palette.{dim_name}.{v_name}", m)
        for name, occ in graph.occasion.items():
            _check(f"occasion.{name}", occ.mapping)
        for name, w in graph.weather.items():
            _check(f"weather.{name}", w.mapping)
        for intent, entries in graph.query_structure.items():
            for name, e in entries.items():
                _check(f"query_structure.{intent}.{name}", e.mapping)

        self.assertEqual(bad, [], f"Unknown attribute names: {bad}")


class IdempotencyTests(unittest.TestCase):
    """Calling load_style_graph repeatedly must not drift."""

    def setUp(self) -> None:
        clear_cache()

    def test_two_calls_return_same_instance(self):
        a = load_style_graph()
        b = load_style_graph()
        self.assertIs(a, b)

    def test_freshly_loaded_pair_is_structurally_equal(self):
        a = load_style_graph()
        clear_cache()
        b = load_style_graph()
        self.assertIsNot(a, b)
        # Keys + sizes line up.
        self.assertEqual(set(a.occasion.keys()), set(b.occasion.keys()))
        self.assertEqual(set(a.weather.keys()), set(b.weather.keys()))
        self.assertEqual(set(a.body_frame_female.keys()), set(b.body_frame_female.keys()))
        # Spot-check a deep entry on dataclass equality.
        self.assertEqual(
            a.body_frame_female["BodyShape"]["Hourglass"],
            b.body_frame_female["BodyShape"]["Hourglass"],
        )
        self.assertEqual(a.occasion["daily_office_mnc"], b.occasion["daily_office_mnc"])
        # Top-level dataclass equality (frozen + field-by-field).
        self.assertEqual(a, b)


class FailureModeTests(unittest.TestCase):
    """Exercise the validation paths against a tampered copy of the YAML
    tree in a temp directory."""

    def setUp(self) -> None:
        clear_cache()
        self.tmp = Path(tempfile.mkdtemp())
        self.style_graph = self.tmp / "style_graph"
        shutil.copytree(CANON_STYLE_GRAPH_DIR, self.style_graph)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)
        clear_cache()

    def test_missing_yaml_raises_filenotfound(self):
        (self.style_graph / "weather.yaml").unlink()
        with self.assertRaises(FileNotFoundError) as cm:
            load_style_graph(self.style_graph)
        self.assertIn("weather.yaml", str(cm.exception))

    def test_unknown_attribute_raises_validation_error(self):
        # Inject an unknown attribute into a copy of weather.yaml by
        # parsing + rewriting — robust against whitespace differences.
        import yaml as _yaml

        weather_path = self.style_graph / "weather.yaml"
        with open(weather_path, "r", encoding="utf-8") as f:
            doc = _yaml.safe_load(f)
        doc["weather"]["hot_humid"]["flatters"]["NotARealAttribute"] = ["foo"]
        with open(weather_path, "w", encoding="utf-8") as f:
            _yaml.safe_dump(doc, f)

        with self.assertRaises(StyleGraphValidationError) as cm:
            load_style_graph(self.style_graph)
        self.assertIn("NotARealAttribute", str(cm.exception))

    def test_missing_required_dimension_raises_validation_error(self):
        # Strip BodyShape out of female.yaml — loader must catch it.
        path = self.style_graph / "body_frame" / "female.yaml"
        text = path.read_text()
        bad = text.replace("BodyShape:", "BodyShapeMissing:", 1)
        path.write_text(bad)
        with self.assertRaises(StyleGraphValidationError) as cm:
            load_style_graph(self.style_graph)
        self.assertIn("BodyShape", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
