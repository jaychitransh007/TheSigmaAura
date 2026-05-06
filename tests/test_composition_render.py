"""Tests for query_document rendering (Phase 4.7e).

Verify the rendered text matches the format the LLM architect emits
today (``prompt/outfit_architect.md`` lines 207–248): PRIMARY_BRIEF
first, sectioned blocks below, one ``- Attribute: values`` line per
non-empty attribute, role-specific suppressions applied."""
from __future__ import annotations

import sys
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

from agentic_application.composition.engine import (
    CompositionInputs,
    compose_direction,
)
from agentic_application.composition.render import render_query_document
from agentic_application.composition.yaml_loader import load_style_graph
from agentic_application.schemas import UserContext


class RenderShapeTests(unittest.TestCase):
    def test_minimal_attributes_renders_primary_brief_only(self):
        text = render_query_document(
            composed_attributes={
                "FabricDrape": ("soft_structured",),
                "FormalityLevel": ("smart_casual",),
            },
            role="top",
            direction_type="paired",
        )
        # PRIMARY_BRIEF is present.
        self.assertIn("PRIMARY_BRIEF:", text)
        self.assertIn("- FabricDrape: soft_structured", text)
        self.assertIn("- FormalityLevel: smart_casual", text)
        # GarmentCategory + StylingCompleteness are derived for the role.
        self.assertIn("- GarmentCategory: top", text)
        self.assertIn("- StylingCompleteness: needs_bottomwear", text)
        # Sections with no attributes are omitted entirely (no empty
        # GARMENT_REQUIREMENTS header on this minimal input).
        self.assertNotIn("GARMENT_REQUIREMENTS:", text)

    def test_section_headers_appear_when_their_attributes_present(self):
        text = render_query_document(
            composed_attributes={
                "FabricDrape": ("fluid",),
                "SilhouetteType": ("a_line",),       # GARMENT_REQUIREMENTS
                "EmbellishmentType": ("embroidery",),  # EMBELLISHMENT
                "VerticalWeightBias": ("upper_biased",),  # VISUAL_DIRECTION
                "FabricTexture": ("smooth",),         # FABRIC_AND_BUILD
                "PatternScale": ("small",),           # PATTERN_AND_COLOR
            },
            role="top",
            direction_type="paired",
        )
        for header in (
            "PRIMARY_BRIEF:",
            "GARMENT_REQUIREMENTS:",
            "EMBELLISHMENT:",
            "VISUAL_DIRECTION:",
            "FABRIC_AND_BUILD:",
            "PATTERN_AND_COLOR:",
        ):
            self.assertIn(header, text)

    def test_ordering_within_primary_brief_matches_prompt_spec(self):
        text = render_query_document(
            composed_attributes={
                "PrimaryColor": ("rust",),
                "FormalityLevel": ("smart_casual",),
                "FabricDrape": ("fluid",),
            },
            role="complete",
            direction_type="complete",
        )
        # FabricDrape line must come before FormalityLevel which must
        # come before PrimaryColor — the prompt's PRIMARY_BRIEF order
        # is: ... FabricDrape ... PatternType ... PrimaryColor ...
        # FormalityLevel ... TimeOfDay.
        i_drape = text.index("- FabricDrape")
        i_color = text.index("- PrimaryColor")
        i_form = text.index("- FormalityLevel")
        self.assertLess(i_drape, i_color)
        self.assertLess(i_color, i_form)

    def test_position_zero_first_in_comma_join(self):
        text = render_query_document(
            composed_attributes={
                "FabricDrape": ("soft_structured", "fluid", "crisp"),
            },
            role="top",
            direction_type="paired",
        )
        self.assertIn(
            "- FabricDrape: soft_structured, fluid, crisp", text
        )

    def test_empty_attribute_value_omits_line(self):
        text = render_query_document(
            composed_attributes={
                "FabricDrape": (),  # empty → no line
                "FabricWeight": ("medium",),
            },
            role="top",
            direction_type="paired",
        )
        self.assertNotIn("FabricDrape", text)
        self.assertIn("- FabricWeight: medium", text)


class RoleSpecificTests(unittest.TestCase):
    def test_bottom_role_suppresses_sleeve_length(self):
        text = render_query_document(
            composed_attributes={
                "SleeveLength": ("full",),
                "FabricDrape": ("fluid",),
            },
            role="bottom",
            direction_type="paired",
        )
        self.assertNotIn("SleeveLength", text)
        self.assertIn("FabricDrape", text)
        self.assertIn("- GarmentCategory: bottom", text)
        self.assertIn("- StylingCompleteness: needs_topwear", text)

    def test_outerwear_role_keeps_sleeve_length(self):
        text = render_query_document(
            composed_attributes={
                "SleeveLength": ("full",),
            },
            role="outerwear",
            direction_type="three_piece",
        )
        self.assertIn("- SleeveLength: full", text)
        self.assertIn("- GarmentCategory: outerwear", text)
        self.assertIn("- StylingCompleteness: needs_innerwear", text)

    def test_complete_role_drives_one_piece_category(self):
        text = render_query_document(
            composed_attributes={"FabricDrape": ("fluid",)},
            role="complete",
            direction_type="complete",
        )
        self.assertIn("- GarmentCategory: one_piece", text)
        self.assertIn("- StylingCompleteness: complete", text)

    def test_explicit_attribute_overrides_derived_default(self):
        # If the engine's contributions provided GarmentCategory or
        # StylingCompleteness, the renderer respects them rather than
        # computing role-derived defaults.
        text = render_query_document(
            composed_attributes={
                "GarmentCategory": ("set",),  # Indian-traditional set
                "StylingCompleteness": ("complete",),
            },
            role="complete",
            direction_type="complete",
        )
        self.assertIn("- GarmentCategory: set", text)


class EngineIntegrationTests(unittest.TestCase):
    """End-to-end: compose_direction must produce non-empty
    query_document on its QuerySpecs (4.7d previously emitted empty
    strings; 4.7e wires the renderer in)."""

    @classmethod
    def setUpClass(cls):
        cls.graph = load_style_graph()

    def test_compose_direction_renders_query_documents(self):
        result = compose_direction(
            inputs=CompositionInputs(
                gender="female",
                body_shape="Hourglass",
                frame_structure="Light and Narrow",
                seasonal_color_group="Soft Autumn",
                archetype="modern_professional",
                risk_tolerance="moderate",
                occasion_signal="daily_office_mnc",
                formality_hint="smart_casual",
                weather_context="warm_temperate",
                time_of_day="daytime",
            ),
            graph=self.graph,
            user=UserContext(user_id="t", gender="female"),
        )
        self.assertIsNotNone(result.direction)
        for q in result.direction.queries:
            self.assertTrue(q.query_document, f"empty query_document on role={q.role}")
            self.assertIn("PRIMARY_BRIEF:", q.query_document)
            # GarmentCategory derived from role.
            if q.role == "top":
                self.assertIn("- GarmentCategory: top", q.query_document)
            elif q.role == "bottom":
                self.assertIn("- GarmentCategory: bottom", q.query_document)


if __name__ == "__main__":
    unittest.main()
