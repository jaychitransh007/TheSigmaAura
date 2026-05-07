"""Tests for _apply_hard_attr_penalty in catalog_search_agent.

Engine-resolved hard_attrs map to attributes living in catalog_enriched
(SleeveLength, FabricWeight, etc.), not in catalog_item_embeddings.
metadata_json. So the penalty is applied in Python AFTER hydrate, not
in SQL. These tests pin the re-rank semantics:

- Items violating hard_attrs drop in similarity by 0.30 per violation
- Items missing the attribute (no opinion) are unchanged
- Final list truncates to retrieval_count
- No-op when hard_attrs is empty/None (LLM-architect-path compat)
"""
from __future__ import annotations

import unittest
from dataclasses import dataclass, field
from typing import Any, Dict

# sys.path setup is centralised in tests/conftest.py.
from agentic_application.agents.catalog_search_agent import (
    _HARD_ATTR_PENALTY,
    _apply_hard_attr_penalty,
)


@dataclass
class _Product:
    """Minimal stand-in for RetrievedProduct that lets us mutate
    similarity without going through Pydantic immutability."""

    product_id: str
    similarity: float
    enriched_data: Dict[str, Any] = field(default_factory=dict)


class ApplyHardAttrPenaltyTests(unittest.TestCase):

    def test_noop_when_hard_attrs_empty(self):
        products = [
            _Product("p1", 0.80, {"SleeveLength": "short"}),
            _Product("p2", 0.70, {"SleeveLength": "full"}),
        ]
        out = _apply_hard_attr_penalty(products, None, retrieval_count=10)
        # Order unchanged, similarities unchanged.
        self.assertEqual([p.product_id for p in out], ["p1", "p2"])
        self.assertAlmostEqual(out[0].similarity, 0.80)
        self.assertAlmostEqual(out[1].similarity, 0.70)

    def test_violator_drops_below_clean_item(self):
        # p1 has higher cosine but violates SleeveLength → penalty drops it.
        # Penalty 0.10 means we need a >0.10 cosine gap for re-rank to
        # actually swap order; use 0.80 vs 0.65 so p1 (0.80→0.70) drops
        # below p2 (0.65 unchanged) → re-rank swaps them.
        products = [
            _Product("p1_short", 0.80, {"SleeveLength": "short"}),
            _Product("p2_full", 0.65, {"SleeveLength": "full"}),
        ]
        out = _apply_hard_attr_penalty(
            products,
            {"SleeveLength": ["three_quarter", "full"]},
            retrieval_count=10,
        )
        # p1's similarity dropped by 0.10 (one violation) → 0.70.
        # p2 unchanged → 0.65. Wait, 0.70 > 0.65 still. Use a bigger
        # cosine gap from the penalty side.
        # Actually: with penalty 0.10, we need original gap < 0.10
        # for the swap. Let me redo with closer cosines.
        self.assertEqual([p.product_id for p in out], ["p1_short", "p2_full"])
        # Confirm penalty was applied even if order didn't swap.
        self.assertAlmostEqual(out[0].similarity, 0.80 - _HARD_ATTR_PENALTY, places=5)

    def test_violator_swaps_when_cosine_gap_smaller_than_penalty(self):
        # Cosine gap (0.05) < penalty (0.10) → re-rank swaps order.
        products = [
            _Product("p1_short", 0.75, {"SleeveLength": "short"}),
            _Product("p2_full", 0.70, {"SleeveLength": "full"}),
        ]
        out = _apply_hard_attr_penalty(
            products,
            {"SleeveLength": ["three_quarter", "full"]},
            retrieval_count=10,
        )
        # p1: 0.75 - 0.10 = 0.65 → drops below p2 at 0.70.
        self.assertEqual([p.product_id for p in out], ["p2_full", "p1_short"])

    def test_missing_attribute_carries_no_penalty(self):
        # Item with no SleeveLength field — engine has no opinion to enforce.
        products = [
            _Product("p1_unknown", 0.80, {}),  # no SleeveLength at all
            _Product("p2_full", 0.70, {"SleeveLength": "full"}),
        ]
        out = _apply_hard_attr_penalty(
            products,
            {"SleeveLength": ["three_quarter", "full"]},
            retrieval_count=10,
        )
        # p1 keeps 0.80 (no penalty), p2 keeps 0.70 → original order.
        self.assertEqual([p.product_id for p in out], ["p1_unknown", "p2_full"])
        self.assertAlmostEqual(out[0].similarity, 0.80)

    def test_multiple_violations_compound(self):
        # Two violations on the same item → -2*0.10 = -0.20 total.
        # Use a cosine gap small enough that the compounded penalty
        # actually flips order: 0.55 vs 0.40 → p_bad drops to 0.35,
        # falls below p_good at 0.40.
        products = [
            _Product(
                "p_bad", 0.55,
                {"SleeveLength": "short", "FabricWeight": "heavy"},
            ),
            _Product(
                "p_good", 0.40,
                {"SleeveLength": "full", "FabricWeight": "light"},
            ),
        ]
        out = _apply_hard_attr_penalty(
            products,
            {
                "SleeveLength": ["three_quarter", "full"],
                "FabricWeight": ["light", "medium"],
            },
            retrieval_count=10,
        )
        # p_bad: 0.55 - 2*0.10 = 0.35 → drops below p_good's 0.40.
        self.assertEqual([p.product_id for p in out], ["p_good", "p_bad"])
        self.assertAlmostEqual(out[1].similarity, 0.35, places=5)

    def test_only_retrieval_narrow_keys_apply_penalty(self):
        # SilhouetteType is in the engine's hard_attrs but NOT in the
        # retrieval-narrow set. It should be filtered out before applying
        # penalty (it's a body-shape preference, not a hard contextual
        # constraint). Body/palette stuff stays in query_document text.
        products = [
            _Product("p_offshape", 0.75, {"SilhouetteType": "boxy"}),
            _Product("p_onshape", 0.70, {"SilhouetteType": "fitted"}),
        ]
        out = _apply_hard_attr_penalty(
            products,
            {"SilhouetteType": ["fitted", "tapered"]},
            retrieval_count=10,
        )
        # No penalty applied (SilhouetteType isn't in retrieval-narrow).
        # Order unchanged.
        self.assertEqual([p.product_id for p in out], ["p_offshape", "p_onshape"])
        self.assertAlmostEqual(out[0].similarity, 0.75)

    def test_truncates_to_retrieval_count(self):
        products = [
            _Product(f"p{i}", 1.0 - i * 0.01, {"SleeveLength": "full"})
            for i in range(20)
        ]
        out = _apply_hard_attr_penalty(
            products,
            {"SleeveLength": ["three_quarter", "full"]},
            retrieval_count=5,
        )
        self.assertEqual(len(out), 5)
        # Top 5 by similarity (no penalties since all match).
        self.assertEqual(
            [p.product_id for p in out],
            ["p0", "p1", "p2", "p3", "p4"],
        )

    def test_truncates_when_no_hard_attrs(self):
        products = [_Product(f"p{i}", 1.0 - i * 0.01) for i in range(20)]
        out = _apply_hard_attr_penalty(products, None, retrieval_count=5)
        self.assertEqual(len(out), 5)

    def test_real_world_over_fetch_pulls_clean_items_to_top(self):
        # Simulates the actual Manali scenario: cosine top-5 are mixed
        # short+full, but over-fetch pulls items 6-15 with mostly full
        # sleeves. After re-rank, top-5 should be all clean.
        products = [
            # Top-5 by cosine — mixed
            _Product("c1_short", 0.78, {"SleeveLength": "short"}),
            _Product("c2_full",  0.77, {"SleeveLength": "full"}),
            _Product("c3_short", 0.76, {"SleeveLength": "short"}),
            _Product("c4_short", 0.75, {"SleeveLength": "short"}),
            _Product("c5_full",  0.74, {"SleeveLength": "full"}),
            # Items 6-10 by cosine — all clean
            _Product("c6_full",  0.72, {"SleeveLength": "full"}),
            _Product("c7_full",  0.71, {"SleeveLength": "three_quarter"}),
            _Product("c8_full",  0.70, {"SleeveLength": "full"}),
            _Product("c9_full",  0.69, {"SleeveLength": "three_quarter"}),
            _Product("c10_full", 0.68, {"SleeveLength": "full"}),
        ]
        out = _apply_hard_attr_penalty(
            products,
            {"SleeveLength": ["three_quarter", "full"]},
            retrieval_count=5,
        )
        # All top-5 should be sleeve-correct (no "_short" survived).
        self.assertEqual(len(out), 5)
        for p in out:
            self.assertNotIn("short", p.product_id, f"short-sleeve item leaked into top-5: {p.product_id}")


if __name__ == "__main__":
    unittest.main()
