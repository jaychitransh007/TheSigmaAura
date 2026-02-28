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
from catalog_enrichment.config_registry import load_intent_policy_rules
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
        self.intent_policies = load_intent_policy_rules()
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

    def test_high_stakes_policy_applies_prior_delta(self) -> None:
        policy = dict((self.intent_policies.get("policies") or {}).get("high_stakes_work") or {})
        rows = [
            _base_row(
                id="office_1",
                title="Navy Sheath Office Dress",
                GarmentCategory="one_piece",
                GarmentSubtype="sheath",
                StylingCompleteness="complete",
                OccasionFit="workwear",
                OccasionSignal="office",
                FormalityLevel="semi_formal",
                FitType="tailored",
                GarmentLength="knee",
                EmbellishmentLevel="minimal",
            ),
            _base_row(
                id="casual_1",
                title="Black Beaded Maxi Dress",
                GarmentCategory="one_piece",
                GarmentSubtype="dress",
                StylingCompleteness="complete",
                OccasionFit="smart_casual",
                OccasionSignal="daily",
                FormalityLevel="smart_casual",
                GarmentLength="floor",
                EmbellishmentLevel="statement",
            ),
        ]
        ranked, _ = rank_recommendation_candidates(
            rows=rows,
            user_profile=_profile(),
            tier2_rules=self.rules,
            strictness="balanced",
            mode="outfit",
            include_combos=False,
            request_text="Big presentation day at work!",
            intent_policy_id="high_stakes_work",
            intent_policy=policy,
        )
        deltas = {str(r.row.get("id")): float(r.row.get("tier2_policy_delta", "0")) for r in ranked}
        self.assertGreater(deltas["office_1"], 0.0)
        self.assertLess(deltas["casual_1"], 0.0)
        self.assertEqual("office_1", str(ranked[0].row.get("id")))

    def test_complete_only_excludes_incomplete_one_piece_rows(self) -> None:
        rows = [
            _base_row(
                id="incomplete_one_piece",
                title="Kurti Needs Bottom",
                GarmentCategory="one_piece",
                GarmentSubtype="kurti",
                StylingCompleteness="needs_bottomwear",
                OccasionFit="workwear",
                FormalityLevel="semi_formal",
            ),
            _base_row(
                id="complete_dress",
                title="Office Sheath Dress",
                GarmentCategory="one_piece",
                GarmentSubtype="dress",
                StylingCompleteness="complete",
                OccasionFit="workwear",
                FormalityLevel="semi_formal",
            ),
        ]
        ranked, _ = rank_recommendation_candidates(
            rows=rows,
            user_profile=_profile(),
            tier2_rules=self.rules,
            strictness="balanced",
            mode="outfit",
            include_combos=False,
            request_text="Need complete look for office",
            max_results=5,
        )
        ids = [str(r.row.get("id", "")) for r in ranked]
        self.assertIn("complete_dress", ids)
        self.assertNotIn("incomplete_one_piece", ids)

    def test_complete_only_excludes_outerwear_without_explicit_outerwear_request(self) -> None:
        rows = [
            _base_row(
                id="outerwear_1",
                title="Office Trench Coat",
                GarmentCategory="outerwear",
                GarmentSubtype="coat",
                StylingCompleteness="complete",
                OccasionFit="workwear",
                FormalityLevel="semi_formal",
            ),
            _base_row(
                id="dress_1",
                title="Office Dress",
                GarmentCategory="one_piece",
                GarmentSubtype="dress",
                StylingCompleteness="complete",
                OccasionFit="workwear",
                FormalityLevel="semi_formal",
            ),
        ]
        ranked, _ = rank_recommendation_candidates(
            rows=rows,
            user_profile=_profile(),
            tier2_rules=self.rules,
            strictness="balanced",
            mode="outfit",
            include_combos=False,
            request_text="Big presentation day at work",
            max_results=5,
        )
        ids = [str(r.row.get("id", "")) for r in ranked]
        self.assertIn("dress_1", ids)
        self.assertNotIn("outerwear_1", ids)

    def test_complete_only_allows_outerwear_when_explicitly_requested(self) -> None:
        rows = [
            _base_row(
                id="outerwear_1",
                title="Office Blazer",
                GarmentCategory="outerwear",
                GarmentSubtype="blazer",
                StylingCompleteness="complete",
                OccasionFit="workwear",
                FormalityLevel="semi_formal",
            ),
            _base_row(
                id="dress_1",
                title="Office Dress",
                GarmentCategory="one_piece",
                GarmentSubtype="dress",
                StylingCompleteness="complete",
                OccasionFit="workwear",
                FormalityLevel="semi_formal",
            ),
        ]
        ranked, _ = rank_recommendation_candidates(
            rows=rows,
            user_profile=_profile(),
            tier2_rules=self.rules,
            strictness="balanced",
            mode="outfit",
            include_combos=False,
            request_text="Need a blazer for my office presentation",
            max_results=5,
        )
        ids = [str(r.row.get("id", "")) for r in ranked]
        self.assertIn("outerwear_1", ids)


if __name__ == "__main__":
    unittest.main()
