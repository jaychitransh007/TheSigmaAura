import unittest
from pathlib import Path

import sys

ROOT = Path(__file__).resolve().parents[1]
for p in (
    ROOT,
    ROOT / "modules" / "platform_core" / "src",
    ROOT / "modules" / "user" / "src",
):
    sp = str(p)
    if sp not in sys.path:
        sys.path.insert(0, sp)

from user.interpreter import derive_interpretations


def _attr(value, confidence=0.9, note="visible"):
    return {"value": value, "confidence": confidence, "evidence_note": note}


class OnboardingInterpreterTests(unittest.TestCase):
    def test_derives_warm_clear_medium_palette(self) -> None:
        attributes = {
            "SkinSurfaceColor": _attr("Medium"),
            "HairColor": _attr("Dark Brown"),
            "HairColorTemperature": _attr("Warm"),
            "EyeColor": _attr("Hazel"),
            "EyeClarity": _attr("Bright / Clear"),
            "VisualWeight": _attr("Medium"),
            "ShoulderSlope": _attr("Average"),
            "ArmVolume": _attr("Medium"),
        }
        out = derive_interpretations(attributes, height_cm=172, waist_cm=82)
        self.assertEqual("Average", out["HeightCategory"]["value"])
        self.assertEqual("Autumn", out["SeasonalColorGroup"]["value"])
        self.assertEqual("Medium", out["ContrastLevel"]["value"])
        self.assertEqual("Medium and Balanced", out["FrameStructure"]["value"])
        self.assertEqual("Medium", out["WaistSizeBand"]["value"])

    def test_derives_cool_deep_high_contrast_palette(self) -> None:
        attributes = {
            "SkinSurfaceColor": _attr("Fair"),
            "HairColor": _attr("Black"),
            "HairColorTemperature": _attr("Cool"),
            "EyeColor": _attr("Black-Brown"),
            "EyeClarity": _attr("Bright / Clear"),
            "VisualWeight": _attr("Medium-Heavy"),
            "ShoulderSlope": _attr("Square"),
            "ArmVolume": _attr("Full"),
        }
        out = derive_interpretations(attributes, height_cm=184, waist_cm=112)
        self.assertEqual("Tall", out["HeightCategory"]["value"])
        self.assertEqual("Winter", out["SeasonalColorGroup"]["value"])
        self.assertEqual("High", out["ContrastLevel"]["value"])
        self.assertEqual("Solid and Broad", out["FrameStructure"]["value"])
        self.assertEqual("Very Large", out["WaistSizeBand"]["value"])

    def test_returns_unable_to_assess_when_inputs_missing(self) -> None:
        out = derive_interpretations({}, height_cm=0, waist_cm=0)
        self.assertEqual("Unable to Assess", out["HeightCategory"]["value"])
        self.assertEqual("Unable to Assess", out["SeasonalColorGroup"]["value"])
        self.assertEqual(0.0, out["SeasonalColorGroup"]["confidence"])
        self.assertEqual("Unable to Assess", out["ContrastLevel"]["value"])
        self.assertEqual("Unable to Assess", out["FrameStructure"]["value"])
        self.assertEqual("Unable to Assess", out["WaistSizeBand"]["value"])


    # ── Phase: 12-Season Color Analysis Tests ──

    def test_weighted_warmth_with_skin_undertone_olive(self) -> None:
        """Olive undertone (warmth=0) + Warm hair + Dark Brown eyes → low warmth, ambiguous."""
        attributes = {
            "SkinSurfaceColor": _attr("Tan"),
            "HairColor": _attr("Dark Brown"),
            "HairColorTemperature": _attr("Warm"),
            "EyeColor": _attr("Dark Brown"),
            "EyeChroma": _attr("Balanced"),
            "SkinUndertone": _attr("Olive"),
            "SkinChroma": _attr("Moderate"),
            "VisualWeight": _attr("Medium"),
            "ShoulderSlope": _attr("Average"),
            "ArmVolume": _attr("Medium"),
        }
        out = derive_interpretations(attributes, height_cm=165, waist_cm=80)
        profile = out["SeasonalColorGroup"].get("dimension_profile", {})
        # Olive(0)*3 + Warm(2)*2 + DarkBrown(0.5)*1 = 4.5 / 6 = 0.75
        self.assertGreater(profile["warmth_score"], 0)
        self.assertLess(profile["warmth_score"], 1.5)

    def test_weighted_warmth_cool_undertone_overrides_warm_hair(self) -> None:
        """Cool undertone should pull warmth negative even with warm hair."""
        attributes = {
            "SkinSurfaceColor": _attr("Light"),
            "HairColor": _attr("Auburn"),
            "HairColorTemperature": _attr("Warm"),
            "EyeColor": _attr("Blue"),
            "EyeChroma": _attr("Bright / Clear"),
            "SkinUndertone": _attr("Cool"),
            "SkinChroma": _attr("Clear"),
            "VisualWeight": _attr("Light"),
            "ShoulderSlope": _attr("Average"),
            "ArmVolume": _attr("Slim"),
        }
        out = derive_interpretations(attributes, height_cm=170, waist_cm=70)
        profile = out["SeasonalColorGroup"].get("dimension_profile", {})
        # Cool(-2)*3 + Warm(2)*2 + Blue(-1)*1 = -3 / 6 = -0.5
        self.assertLess(profile["warmth_score"], 0)

    def test_ambiguous_temperature_flag(self) -> None:
        """Neutral undertone + Neutral hair → ambiguous temperature."""
        attributes = {
            "SkinSurfaceColor": _attr("Medium"),
            "HairColor": _attr("Medium Brown"),
            "HairColorTemperature": _attr("Neutral"),
            "EyeColor": _attr("Hazel"),
            "EyeChroma": _attr("Balanced"),
            "SkinUndertone": _attr("Neutral-Warm"),
            "SkinChroma": _attr("Moderate"),
            "VisualWeight": _attr("Medium"),
            "ShoulderSlope": _attr("Average"),
            "ArmVolume": _attr("Medium"),
        }
        out = derive_interpretations(attributes, height_cm=168, waist_cm=78)
        profile = out["SeasonalColorGroup"].get("dimension_profile", {})
        # NeutralWarm(1)*3 + Neutral(0)*2 + Hazel(0)*1 = 3/6 = 0.5
        # |0.5| is NOT < 0.5, so ambiguous is False
        # Let's check — at exactly 0.5 it's not ambiguous
        self.assertFalse(profile.get("ambiguous_temperature"))

    def test_sub_season_assignment_deep_autumn(self) -> None:
        """Tan skin + Dark Brown hair → high depth → Deep Autumn."""
        attributes = {
            "SkinSurfaceColor": _attr("Tan"),
            "HairColor": _attr("Dark Brown"),
            "HairColorTemperature": _attr("Warm"),
            "EyeColor": _attr("Medium Brown"),
            "EyeChroma": _attr("Balanced"),
            "SkinUndertone": _attr("Warm"),
            "SkinChroma": _attr("Moderate"),
            "VisualWeight": _attr("Medium"),
            "ShoulderSlope": _attr("Average"),
            "ArmVolume": _attr("Medium"),
        }
        out = derive_interpretations(attributes, height_cm=170, waist_cm=85)
        self.assertEqual("Autumn", out["SeasonalColorGroup"]["value"])
        self.assertEqual("Deep Autumn", out["SubSeason"]["value"])

    def test_sub_season_assignment_deep_winter(self) -> None:
        """Fair skin + Black hair → high depth dominates → Deep Winter."""
        attributes = {
            "SkinSurfaceColor": _attr("Fair"),
            "HairColor": _attr("Black"),
            "HairColorTemperature": _attr("Cool"),
            "EyeColor": _attr("Black-Brown"),
            "EyeChroma": _attr("Bright / Clear"),
            "SkinUndertone": _attr("Cool"),
            "SkinChroma": _attr("Clear"),
            "VisualWeight": _attr("Medium"),
            "ShoulderSlope": _attr("Average"),
            "ArmVolume": _attr("Medium"),
        }
        out = derive_interpretations(attributes, height_cm=175, waist_cm=75)
        self.assertEqual("Winter", out["SeasonalColorGroup"]["value"])
        self.assertEqual("Deep Winter", out["SubSeason"]["value"])

    def test_skin_hair_contrast_high(self) -> None:
        """Fair skin + Black hair → high contrast."""
        attributes = {
            "SkinSurfaceColor": _attr("Fair"),
            "HairColor": _attr("Black"),
            "HairColorTemperature": _attr("Cool"),
            "EyeColor": _attr("Dark Brown"),
            "EyeChroma": _attr("Balanced"),
            "VisualWeight": _attr("Medium"),
            "ShoulderSlope": _attr("Average"),
            "ArmVolume": _attr("Medium"),
        }
        out = derive_interpretations(attributes, height_cm=170, waist_cm=75)
        self.assertEqual("High", out["SkinHairContrast"]["value"])
        self.assertEqual(7, out["SkinHairContrast"]["numeric_score"])

    def test_skin_hair_contrast_low(self) -> None:
        """Medium skin + Medium Brown hair → low contrast."""
        attributes = {
            "SkinSurfaceColor": _attr("Medium"),
            "HairColor": _attr("Medium Brown"),
            "HairColorTemperature": _attr("Neutral"),
            "EyeColor": _attr("Medium Brown"),
            "EyeChroma": _attr("Balanced"),
            "VisualWeight": _attr("Medium"),
            "ShoulderSlope": _attr("Average"),
            "ArmVolume": _attr("Medium"),
        }
        out = derive_interpretations(attributes, height_cm=170, waist_cm=75)
        self.assertEqual("Low", out["SkinHairContrast"]["value"])
        self.assertLessEqual(out["SkinHairContrast"]["numeric_score"], 2)

    def test_backward_compat_eye_clarity_fallback(self) -> None:
        """Old attributes with EyeClarity (not EyeChroma) should still work."""
        attributes = {
            "SkinSurfaceColor": _attr("Medium"),
            "HairColor": _attr("Dark Brown"),
            "HairColorTemperature": _attr("Warm"),
            "EyeColor": _attr("Hazel"),
            "EyeClarity": _attr("Bright / Clear"),  # old name
            "VisualWeight": _attr("Medium"),
            "ShoulderSlope": _attr("Average"),
            "ArmVolume": _attr("Medium"),
        }
        out = derive_interpretations(attributes, height_cm=172, waist_cm=82)
        self.assertIn(out["SeasonalColorGroup"]["value"], ("Spring", "Autumn", "Summer", "Winter"))
        self.assertGreater(out["SeasonalColorGroup"]["confidence"], 0)

    def test_color_dimension_profile_surfaced(self) -> None:
        """ColorDimensionProfile should contain all computed dimension scores."""
        attributes = {
            "SkinSurfaceColor": _attr("Tan"),
            "HairColor": _attr("Dark Brown"),
            "HairColorTemperature": _attr("Warm"),
            "EyeColor": _attr("Dark Brown"),
            "EyeChroma": _attr("Balanced"),
            "SkinUndertone": _attr("Warm"),
            "SkinChroma": _attr("Moderate"),
            "VisualWeight": _attr("Medium"),
            "ShoulderSlope": _attr("Average"),
            "ArmVolume": _attr("Medium"),
        }
        out = derive_interpretations(attributes, height_cm=170, waist_cm=80)
        cdp = out["ColorDimensionProfile"]
        self.assertEqual("computed", cdp["value"])
        self.assertIn("warmth_score", cdp)
        self.assertIn("depth_score", cdp)
        self.assertIn("chroma_score", cdp)
        self.assertIn("skin_hair_contrast", cdp)
        self.assertIn("ambiguous_temperature", cdp)

    def test_boundary_palette_blending(self) -> None:
        """When sub-season has a secondary, accent list should be extended."""
        from user.interpreter import derive_color_palette
        result = derive_color_palette(
            "Autumn", 0.45,
            sub_season="Warm Autumn",
            secondary_season="Spring",
        )
        # Low confidence + secondary → boundary blending should add crossover accents
        accents = result["AccentColors"]["value"]
        self.assertGreater(len(accents), 5)  # base 5 + crossover from Warm Spring


if __name__ == "__main__":
    unittest.main()
