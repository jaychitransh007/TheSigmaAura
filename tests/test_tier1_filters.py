import unittest

from catalog_enrichment.styling_filters import (
    UserContext,
    filter_catalog_rows,
    load_tier_a_rules,
    parse_relaxed_filters,
)


def _base_pass_row() -> dict:
    return {
        "id": "1",
        "title": "Pass Garment",
        "price": "2999",
        "OccasionFit": "workwear",
        "OccasionSignal": "office",
        "FormalityLevel": "formal",
        "TimeOfDay": "day",
        "SilhouetteType": "straight",
        "FitType": "regular",
        "PatternType": "solid",
        "ColorSaturation": "muted",
        "ContrastLevel": "low",
        "EmbellishmentLevel": "none",
        "GenderExpression": "feminine",
        "SkinExposureLevel": "low",
        "NecklineDepth": "shallow",
        "PatternScale": "small",
    }


class Tier1FilterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.rules = load_tier_a_rules()
        self.ctx = UserContext(
            occasion="Work Mode",
            archetype="Classic",
            gender="Female",
            age="25-30",
        )

    def test_parse_relax_filters_valid(self) -> None:
        out = parse_relaxed_filters(["age,price", "archetype"])
        self.assertEqual({"age", "price", "archetype"}, out)

    def test_parse_relax_filters_invalid_raises(self) -> None:
        with self.assertRaises(ValueError):
            parse_relaxed_filters(["foo"])

    def test_strict_filter_passes_matching_row(self) -> None:
        rows = [_base_pass_row()]
        passed, failed = filter_catalog_rows(rows=rows, ctx=self.ctx, rules=self.rules)
        self.assertEqual(1, len(passed))
        self.assertEqual(0, len(failed))

    def test_price_failure_can_be_relaxed(self) -> None:
        bad = _base_pass_row()
        bad["price"] = "1500"
        passed, failed = filter_catalog_rows(rows=[bad], ctx=self.ctx, rules=self.rules)
        self.assertEqual(0, len(passed))
        self.assertIn("price", failed[0]["fail_reasons"])

        passed_relaxed, failed_relaxed = filter_catalog_rows(
            rows=[bad],
            ctx=self.ctx,
            rules=self.rules,
            relaxed_filters={"price"},
        )
        self.assertEqual(1, len(passed_relaxed))
        self.assertEqual(0, len(failed_relaxed))

    def test_occasion_archetype_incompatibility_and_relaxation(self) -> None:
        ctx = UserContext(
            occasion="Work Mode",
            archetype="Glamorous",  # not compatible with work_mode
            gender="Female",
            age="25-30",
        )
        row = _base_pass_row()
        # Make row satisfy "glamorous" archetype constraints so only the
        # occasion-archetype gate decides pass/fail.
        row.update(
            {
                "SilhouetteType": "fitted",
                "FitType": "slim",
                "PatternType": "solid",
                "ColorSaturation": "high",
                "ContrastLevel": "high",
                "EmbellishmentLevel": "moderate",
            }
        )
        rows = [row]
        passed, failed = filter_catalog_rows(rows=rows, ctx=ctx, rules=self.rules)
        self.assertEqual(0, len(passed))
        self.assertIn("occasion_archetype", failed[0]["fail_reasons"])

        passed_relaxed, failed_relaxed = filter_catalog_rows(
            rows=rows,
            ctx=ctx,
            rules=self.rules,
            relaxed_filters={"occasion_archetype"},
        )
        self.assertEqual(1, len(passed_relaxed))
        self.assertEqual(0, len(failed_relaxed))

    def test_gender_filter_blocks_mismatch(self) -> None:
        bad = _base_pass_row()
        bad["GenderExpression"] = "masculine"
        passed, failed = filter_catalog_rows(rows=[bad], ctx=self.ctx, rules=self.rules)
        self.assertEqual(0, len(passed))
        self.assertIn("gender:GenderExpression", failed[0]["fail_reasons"])


if __name__ == "__main__":
    unittest.main()
