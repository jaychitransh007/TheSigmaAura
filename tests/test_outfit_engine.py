import json
import unittest
from pathlib import Path

import sys

ROOT = Path(__file__).resolve().parents[1]
for p in (
    ROOT,
    ROOT / "modules" / "catalog_enrichment" / "src",
    ROOT / "modules" / "style_engine" / "src",
):
    sp = str(p)
    if sp not in sys.path:
        sys.path.insert(0, sp)

from catalog_enrichment.config_registry import load_outfit_assembly_rules
from style_engine.outfit_engine import rank_recommendation_candidates, resolve_recommendation_mode
from style_engine.ranker import load_tier2_rules


def _profile() -> dict:
    return {
        "HeightCategory": "AVERAGE",
        "BodyShape": "HOURGLASS",
        "VisualWeight": "BALANCED",
        "VerticalProportion": "BALANCED",
        "ArmVolume": "AVERAGE",
        "MidsectionState": "SOFT_AVERAGE",
        "WaistVisibility": "DEFINED",
        "BustVolume": "MEDIUM",
        "SkinUndertone": "WARM",
        "SkinSurfaceColor": "WHEATISH_MEDIUM",
        "SkinContrast": "MEDIUM_CONTRAST",
        "FaceShape": "OVAL",
        "NeckLength": "AVERAGE",
        "HairLength": "LONG",
        "HairColor": "DARK_BROWN",
        "color_preferences": {},
    }


def _base_row(**overrides: str) -> dict:
    base = {
        "id": "item_1",
        "title": "Demo Garment",
        "images__0__src": "https://img/1.jpg",
        "images__1__src": "https://img/2.jpg",
        "price": "2999",
        "GarmentCategory": "top",
        "GarmentSubtype": "shirt",
        "StylingCompleteness": "needs_bottomwear",
        "OccasionFit": "smart_casual",
        "FormalityLevel": "smart_casual",
        "PrimaryColor": "blue",
        "GarmentLength": "hip",
        "GarmentLength_confidence": "0.80",
        "SilhouetteType": "straight",
        "SilhouetteType_confidence": "0.85",
        "FitType": "regular",
        "FitType_confidence": "0.85",
        "WaistDefinition": "natural",
        "WaistDefinition_confidence": "0.80",
        "NecklineType": "collared",
        "NecklineType_confidence": "0.85",
        "NecklineDepth": "shallow",
        "NecklineDepth_confidence": "0.80",
        "SleeveLength": "full",
        "SleeveLength_confidence": "0.80",
        "SkinExposureLevel": "low",
        "SkinExposureLevel_confidence": "0.80",
        "VisualWeightPlacement": "distributed",
        "VisualWeightPlacement_confidence": "0.80",
        "BodyFocusZone": "full_length",
        "BodyFocusZone_confidence": "0.70",
        "EmbellishmentLevel": "minimal",
        "EmbellishmentLevel_confidence": "0.70",
        "EmbellishmentZone": "none",
        "EmbellishmentZone_confidence": "0.70",
        "FabricDrape": "soft_structured",
        "FabricDrape_confidence": "0.80",
        "FabricTexture": "smooth",
        "FabricTexture_confidence": "0.80",
        "FabricWeight": "medium",
        "FabricWeight_confidence": "0.80",
        "PatternScale": "small",
        "PatternScale_confidence": "0.75",
        "PatternType": "solid",
        "PatternType_confidence": "0.80",
        "PatternOrientation": "vertical",
        "PatternOrientation_confidence": "0.75",
        "ColorTemperature": "neutral",
        "ColorTemperature_confidence": "0.85",
        "ColorSaturation": "medium",
        "ColorSaturation_confidence": "0.85",
        "ColorValue": "mid",
        "ColorValue_confidence": "0.85",
        "ContrastLevel": "medium",
        "ContrastLevel_confidence": "0.85",
        "ColorCount": "two_color",
        "ColorCount_confidence": "0.80",
        "ConstructionDetail": "none",
        "ConstructionDetail_confidence": "0.80",
    }
    base.update(overrides)
    return base


class OutfitEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.rules = load_tier2_rules()
        self.outfit_rules = load_outfit_assembly_rules()
        self.rows = [
            _base_row(
                id="top_1",
                title="Office Shirt",
                GarmentCategory="top",
                GarmentSubtype="shirt",
                StylingCompleteness="needs_bottomwear",
                PatternType="solid",
                OccasionFit="workwear",
                FormalityLevel="semi_formal",
            ),
            _base_row(
                id="bottom_1",
                title="Tailored Trouser",
                GarmentCategory="bottom",
                GarmentSubtype="trouser",
                StylingCompleteness="needs_topwear",
                GarmentLength="ankle",
                PatternType="solid",
                SleeveLength="not_applicable",
                SleeveLength_confidence="1.0",
                OccasionFit="workwear",
                FormalityLevel="semi_formal",
            ),
            _base_row(
                id="dress_1",
                title="Evening Dress",
                GarmentCategory="one_piece",
                GarmentSubtype="dress",
                StylingCompleteness="complete",
                GarmentLength="knee",
                NecklineType="v_neck",
                NecklineDepth="moderate",
                PatternType="solid",
                OccasionFit="party",
                FormalityLevel="formal",
            ),
        ]

    def test_outfit_mode_returns_combo_candidates(self) -> None:
        ranked, meta = rank_recommendation_candidates(
            rows=self.rows,
            user_profile=_profile(),
            tier2_rules=self.rules,
            strictness="balanced",
            mode="outfit",
            request_text="",
        )
        self.assertEqual("outfit", meta.resolved_mode)
        self.assertTrue(any(r.row.get("recommendation_kind") == "outfit_combo" for r in ranked))
        self.assertTrue(any(r.row.get("recommendation_kind") == "single_garment" for r in ranked))

    def test_auto_mode_detects_garment_request(self) -> None:
        ranked, meta = rank_recommendation_candidates(
            rows=self.rows,
            user_profile=_profile(),
            tier2_rules=self.rules,
            strictness="balanced",
            mode="auto",
            request_text="I need a shirt for office.",
        )
        self.assertEqual("garment", meta.resolved_mode)
        self.assertTrue(all(r.row.get("recommendation_kind") == "single_garment" for r in ranked))
        self.assertTrue(
            all(
                str(r.row.get("GarmentCategory", "")).lower() == "top"
                or str(r.row.get("GarmentSubtype", "")).lower() == "shirt"
                for r in ranked
            )
        )

    def test_auto_mode_without_garment_keywords_prefers_outfits(self) -> None:
        ranked, meta = rank_recommendation_candidates(
            rows=self.rows,
            user_profile=_profile(),
            tier2_rules=self.rules,
            strictness="balanced",
            mode="auto",
            request_text="I need something for a dinner event.",
        )
        self.assertEqual("outfit", meta.resolved_mode)
        self.assertTrue(any(r.row.get("recommendation_kind") == "outfit_combo" for r in ranked))

    def test_combo_candidate_contains_component_metadata(self) -> None:
        ranked, _ = rank_recommendation_candidates(
            rows=self.rows,
            user_profile=_profile(),
            tier2_rules=self.rules,
            strictness="balanced",
            mode="outfit",
            request_text="",
        )
        combo = next(r for r in ranked if r.row.get("recommendation_kind") == "outfit_combo")
        component_ids = json.loads(str(combo.row.get("component_ids_json", "[]")))
        self.assertEqual(2, len(component_ids))
        self.assertTrue(str(combo.row.get("id", "")).startswith("combo::"))
        self.assertIn("pair_bonus", str(combo.row.get("tier2_reasons", "")))

    def test_invalid_recommendation_mode_raises(self) -> None:
        with self.assertRaises(ValueError):
            rank_recommendation_candidates(
                rows=self.rows,
                user_profile=_profile(),
                tier2_rules=self.rules,
                strictness="balanced",
                mode="invalid_mode",
                request_text="",
            )

    def test_resolve_mode_detects_hyphenated_keyword(self) -> None:
        resolved, categories, subtypes = resolve_recommendation_mode(
            mode="auto",
            request_text="Show me a t-shirt for office.",
            rules=self.outfit_rules,
        )
        self.assertEqual("garment", resolved)
        self.assertIn("tshirt", subtypes)
        self.assertIn("top", categories)

    def test_garment_mode_falls_back_if_no_targeted_match(self) -> None:
        ranked, meta = rank_recommendation_candidates(
            rows=self.rows,
            user_profile=_profile(),
            tier2_rules=self.rules,
            strictness="balanced",
            mode="auto",
            request_text="I want a saree for office.",
        )
        self.assertEqual("garment", meta.resolved_mode)
        self.assertGreater(len(ranked), 0)
        self.assertTrue(all(r.row.get("recommendation_kind") == "single_garment" for r in ranked))


if __name__ == "__main__":
    unittest.main()
