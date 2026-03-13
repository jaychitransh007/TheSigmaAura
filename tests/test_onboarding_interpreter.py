import unittest
from pathlib import Path

import sys

ROOT = Path(__file__).resolve().parents[1]
for p in (
    ROOT,
    ROOT / "modules" / "platform_core" / "src",
    ROOT / "modules" / "onboarding" / "src",
):
    sp = str(p)
    if sp not in sys.path:
        sys.path.insert(0, sp)

from onboarding.interpreter import derive_interpretations


def _attr(value, confidence=0.9, note="visible"):
    return {"value": value, "confidence": confidence, "evidence_note": note}


class OnboardingInterpreterTests(unittest.TestCase):
    def test_derives_warm_clear_medium_palette(self) -> None:
        attributes = {
            "SkinUndertone": _attr("Warm"),
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
        self.assertEqual("Clear Spring", out["SeasonalColorGroup"]["value"])
        self.assertEqual("Medium", out["ContrastLevel"]["value"])
        self.assertEqual("Medium and Balanced", out["FrameStructure"]["value"])
        self.assertEqual("Medium", out["WaistSizeBand"]["value"])

    def test_derives_cool_deep_high_contrast_palette(self) -> None:
        attributes = {
            "SkinUndertone": _attr("Cool"),
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
        self.assertEqual("Clear Winter", out["SeasonalColorGroup"]["value"])
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


if __name__ == "__main__":
    unittest.main()
