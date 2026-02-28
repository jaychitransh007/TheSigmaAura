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

from catalog_enrichment.config_registry import load_intent_policy_rules
from style_engine.intent_policy import apply_intent_policy_filters, resolve_intent_policy


class IntentPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        cfg = load_intent_policy_rules()
        self.policy = dict((cfg.get("policies") or {}).get("high_stakes_work") or {})

    def test_resolve_high_stakes_work_for_presentation_prompt(self) -> None:
        out = resolve_intent_policy(
            request_text="Big presentation day at work!",
            context={"occasion": "work_mode", "archetype": "classic"},
        )
        self.assertEqual("high_stakes_work", out["policy_id"])
        self.assertIn("presentation", " ".join(out["keyword_hits"]))

    def test_policy_filter_excludes_risky_work_items(self) -> None:
        rows = [
            {
                "id": "ok_1",
                "title": "Charcoal Sheath Dress",
                "OccasionSignal": "office",
                "OccasionFit": "workwear",
                "FormalityLevel": "formal",
                "EmbellishmentLevel": "minimal",
                "TimeOfDay": "day",
                "FitType": "tailored",
                "ColorSaturation": "muted",
                "GarmentSubtype": "dress",
                "GarmentCategory": "one_piece",
            },
            {
                "id": "bad_1",
                "title": "Black Beaded Maxi Dress",
                "OccasionSignal": "daily",
                "OccasionFit": "smart_casual",
                "FormalityLevel": "smart_casual",
                "EmbellishmentLevel": "statement",
                "TimeOfDay": "day_to_night",
                "FitType": "regular",
                "ColorSaturation": "high",
                "GarmentSubtype": "maxi_dress",
                "GarmentCategory": "one_piece",
            },
        ]
        passed, failed = apply_intent_policy_filters(rows=rows, policy=self.policy)
        self.assertEqual(["ok_1"], [r["id"] for r in passed])
        self.assertEqual(["bad_1"], [r["id"] for r in failed])


if __name__ == "__main__":
    unittest.main()
