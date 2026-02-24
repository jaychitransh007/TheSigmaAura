import unittest

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for p in (
    ROOT,
    ROOT / "modules" / "catalog_enrichment" / "src",
    ROOT / "modules" / "style_engine" / "src",
):
    sp = str(p)
    if sp not in sys.path:
        sys.path.insert(0, sp)


from style_engine.ranker import load_tier2_rules, rank_garments


def _row(**overrides: str) -> dict:
    base = {
        "id": "p1",
        "title": "Demo Garment",
        "PrimaryColor": "blue",
        "GarmentLength": "knee",
        "GarmentLength_confidence": "0.90",
        "SilhouetteType": "a_line",
        "SilhouetteType_confidence": "0.90",
        "FitType": "regular",
        "FitType_confidence": "0.80",
        "WaistDefinition": "defined",
        "WaistDefinition_confidence": "0.80",
        "NecklineType": "v_neck",
        "NecklineType_confidence": "0.90",
        "NecklineDepth": "moderate",
        "NecklineDepth_confidence": "0.85",
        "SleeveLength": "short",
        "SleeveLength_confidence": "0.80",
        "SkinExposureLevel": "medium",
        "SkinExposureLevel_confidence": "0.70",
        "VisualWeightPlacement": "distributed",
        "VisualWeightPlacement_confidence": "0.80",
        "BodyFocusZone": "waist",
        "BodyFocusZone_confidence": "0.70",
        "EmbellishmentLevel": "minimal",
        "EmbellishmentLevel_confidence": "0.70",
        "EmbellishmentZone": "waist",
        "EmbellishmentZone_confidence": "0.70",
        "FabricDrape": "fluid",
        "FabricDrape_confidence": "0.80",
        "FabricTexture": "smooth",
        "FabricTexture_confidence": "0.80",
        "FabricWeight": "light",
        "FabricWeight_confidence": "0.75",
        "PatternScale": "small",
        "PatternScale_confidence": "0.70",
        "PatternType": "solid",
        "PatternType_confidence": "0.80",
        "PatternOrientation": "vertical",
        "PatternOrientation_confidence": "0.80",
        "ColorTemperature": "warm",
        "ColorTemperature_confidence": "0.90",
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


def _profile(**overrides: str) -> dict:
    base = {
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
    base.update(overrides)
    return base


class Tier2RankerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.rules = load_tier2_rules()

    def test_invalid_strictness_raises(self) -> None:
        with self.assertRaises(ValueError):
            rank_garments(rows=[_row()], user_profile=_profile(), rules=self.rules, strictness="x")

    def test_explainability_contract_fields_exist(self) -> None:
        out = rank_garments(rows=[_row()], user_profile=_profile(), rules=self.rules)
        self.assertEqual(1, len(out))
        r = out[0].row
        for field in (
            "tier2_raw_score",
            "tier2_confidence_multiplier",
            "tier2_color_delta",
            "tier2_final_score",
            "tier2_max_score",
            "tier2_compatibility_confidence",
            "tier2_flags",
            "tier2_reasons",
            "tier2_penalties",
        ):
            self.assertIn(field, r)
        explain = out[0].explainability
        self.assertIn("conflict_engine", explain)
        self.assertIn("formula", explain)

    def test_color_never_excludes_item(self) -> None:
        profile = _profile(color_preferences={"never": ["blue"]})
        out = rank_garments(rows=[_row(PrimaryColor="blue")], user_profile=profile, rules=self.rules)
        self.assertEqual(0, len(out))

    def test_higher_confidence_improves_score(self) -> None:
        hi = _row(NecklineType_confidence="0.90", ColorTemperature_confidence="0.90")
        lo = _row(NecklineType_confidence="0.20", ColorTemperature_confidence="0.20")
        out = rank_garments(rows=[hi, lo], user_profile=_profile(), rules=self.rules)
        by_id = {r.row["id"] + "_" + r.row.get("NecklineType_confidence", ""): r.final_score for r in out}
        self.assertGreater(by_id["p1_0.90"], by_id["p1_0.20"])

    def test_not_permitted_penalty_applies(self) -> None:
        # Warm undertone prefers warm; cool is acceptable; this checks penalty on explicit mismatch by using COOL profile and warm garment.
        good = _row(id="good", ColorTemperature="cool")
        bad = _row(id="bad", ColorTemperature="warm")
        profile = _profile(SkinUndertone="COOL")
        out = rank_garments(rows=[good, bad], user_profile=profile, rules=self.rules)
        score = {r.row["id"]: r.final_score for r in out}
        self.assertGreater(score["good"], score["bad"])

    def test_strictness_profiles_affect_ranking_score(self) -> None:
        row = _row()
        profile = _profile(color_preferences={"liked": ["blue"]})
        safe = rank_garments(rows=[row], user_profile=profile, rules=self.rules, strictness="safe")[0].final_score
        balanced = rank_garments(rows=[row], user_profile=profile, rules=self.rules, strictness="balanced")[0].final_score
        bold = rank_garments(rows=[row], user_profile=profile, rules=self.rules, strictness="bold")[0].final_score
        self.assertLess(safe, balanced)
        self.assertLess(balanced, bold)

    def test_ranked_bh_weights_from_config_used(self) -> None:
        out = rank_garments(rows=[_row()], user_profile=_profile(), rules=self.rules)
        weights = out[0].explainability["effective_bh_weights"]
        self.assertAlmostEqual(1.0, sum(weights.values()), places=6)
        self.assertGreater(weights["HeightCategory"], weights["HairColor"])

    def test_color_loved_preference_boosts_score(self) -> None:
        row = _row(PrimaryColor="blue")
        neutral = rank_garments(rows=[row], user_profile=_profile(color_preferences={}), rules=self.rules)[0].final_score
        loved = rank_garments(
            rows=[row],
            user_profile=_profile(color_preferences={"loved": ["blue"]}),
            rules=self.rules,
        )[0].final_score
        self.assertGreater(loved, neutral)

    def test_compatibility_confidence_is_bounded(self) -> None:
        out = rank_garments(rows=[_row()], user_profile=_profile(), rules=self.rules)
        confidence = float(out[0].row["tier2_compatibility_confidence"])
        self.assertGreaterEqual(confidence, 0.0)
        self.assertLessEqual(confidence, 1.0)


if __name__ == "__main__":
    unittest.main()
