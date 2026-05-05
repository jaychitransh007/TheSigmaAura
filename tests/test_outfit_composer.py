"""Unit tests for OutfitComposer (May 3 2026).

The Composer constructs outfits from a retrieved item pool. The tests
focus on contract enforcement: structural validation, hallucination
handling, retry behaviour, empty-pool short-circuit. All LLM calls are
mocked so the suite stays fast and deterministic.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
for p in (
    ROOT,
    ROOT / "modules" / "user" / "src",
    ROOT / "modules" / "agentic_application" / "src",
    ROOT / "modules" / "catalog" / "src",
    ROOT / "modules" / "platform_core" / "src",
    ROOT / "modules" / "user_profiler" / "src",
):
    sp = str(p)
    if sp not in sys.path:
        sys.path.insert(0, sp)

from agentic_application.agents.outfit_composer import (
    OutfitComposer,
    _build_user_payload,
    _validate_outfit,
)
from agentic_application.schemas import (
    CombinedContext,
    ComposedOutfit,
    LiveContext,
    RetrievedProduct,
    RetrievedSet,
    UserContext,
)


def _ctx(user_need: str = "casual outfit for the weekend") -> CombinedContext:
    return CombinedContext(
        user=UserContext(
            user_id="u1",
            gender="male",
            style_preference={"primaryArchetype": "classic", "riskTolerance": "low"},
            derived_interpretations={"BodyShape": {"value": "rectangle"}},
        ),
        live=LiveContext(
            user_need=user_need,
            occasion_signal="everyday",
            formality_hint="smart_casual",
        ),
        hard_filters={"gender_expression": "masculine"},
    )


def _product(pid: str, **enriched) -> RetrievedProduct:
    return RetrievedProduct(
        product_id=pid,
        similarity=0.9,
        metadata={"title": f"Product {pid}"},
        enriched_data={"garment_subtype": "shirt", **enriched},
    )


def _pool() -> list[RetrievedSet]:
    """Sample pool with all three direction types."""
    return [
        # Direction A — complete
        RetrievedSet(direction_id="A", query_id="A1", role="complete", products=[
            _product("a1_set1", garment_subtype="kurta_set"),
            _product("a1_set2", garment_subtype="suit_set"),
        ]),
        # Direction B — paired
        RetrievedSet(direction_id="B", query_id="B1", role="top", products=[
            _product("b_t1", garment_subtype="shirt"),
            _product("b_t2", garment_subtype="polo"),
        ]),
        RetrievedSet(direction_id="B", query_id="B2", role="bottom", products=[
            _product("b_b1", garment_subtype="trouser"),
            _product("b_b2", garment_subtype="jeans"),
        ]),
        # Direction C — three_piece
        RetrievedSet(direction_id="C", query_id="C1", role="top", products=[
            _product("c_t1", garment_subtype="shirt"),
        ]),
        RetrievedSet(direction_id="C", query_id="C2", role="bottom", products=[
            _product("c_b1", garment_subtype="trouser"),
        ]),
        RetrievedSet(direction_id="C", query_id="C3", role="outerwear", products=[
            _product("c_o1", garment_subtype="blazer"),
        ]),
    ]


def _mock_response(payload: dict) -> Mock:
    m = Mock()
    m.output_text = json.dumps(payload)
    return m


def _patch_composer():
    """Convenience: returns the patched OpenAI client mock."""
    return patch("agentic_application.agents.outfit_composer.OpenAI")


class OutfitComposerStructuralTests(unittest.TestCase):
    """The Composer must produce outfits whose structure matches the
    contract (1 item for complete, 2 for paired, 3 for three_piece) and
    every item_id must come from the input pool."""

    def test_composer_returns_outfits_from_pool(self) -> None:
        payload = {
            "outfits": [
                {"composer_id": "C1", "direction_id": "A", "direction_type": "complete",
                 "item_ids": ["a1_set1"], "name": "Cream Festive Kurta",
                 "rationale": "Complete kurta_set works for everyday."},
                {"composer_id": "C2", "direction_id": "B", "direction_type": "paired",
                 "item_ids": ["b_t1", "b_b1"], "name": "Smart-Casual Linen",
                 "rationale": "Shirt + trouser, smart_casual."},
            ],
            "overall_assessment": "moderate",
            "pool_unsuitable": False,
        }

        with patch("agentic_application.agents.outfit_composer.get_api_key", return_value="x"), _patch_composer() as oc:
            oc.return_value.responses.create.return_value = _mock_response(payload)
            result = OutfitComposer().compose(_ctx(), _pool())

        self.assertEqual(2, len(result.outfits))
        self.assertEqual("moderate", result.overall_assessment)
        self.assertFalse(result.pool_unsuitable)
        self.assertEqual(["C1", "C2"], [o.composer_id for o in result.outfits])
        # name is parsed off each outfit and surfaces as the user-facing card
        # title downstream — verify it round-trips through ComposedOutfit.
        self.assertEqual(
            ["Cream Festive Kurta", "Smart-Casual Linen"],
            [o.name for o in result.outfits],
        )

    def test_composer_tolerates_missing_name_field(self) -> None:
        """Defensive: if the LLM somehow returns an outfit without a name,
        the parser still constructs the ComposedOutfit (name defaults to
        "") so the orchestrator can fall back to "Outfit N"."""
        payload = {
            "outfits": [
                {"composer_id": "C1", "direction_id": "A", "direction_type": "complete",
                 "item_ids": ["a1_set1"], "rationale": "Missing name field."},
            ],
            "overall_assessment": "moderate",
            "pool_unsuitable": False,
        }

        with patch("agentic_application.agents.outfit_composer.get_api_key", return_value="x"), _patch_composer() as oc:
            oc.return_value.responses.create.return_value = _mock_response(payload)
            result = OutfitComposer().compose(_ctx(), _pool())

        self.assertEqual(1, len(result.outfits))
        self.assertEqual("", result.outfits[0].name)

    def test_composer_tolerates_null_name_value(self) -> None:
        """The strict schema requires `name`, but defensively handle the
        case where the LLM returns an explicit JSON null. Without this
        guard, str(None).strip() yields "None" — which would ship as the
        card title."""
        payload = {
            "outfits": [
                {"composer_id": "C1", "direction_id": "A", "direction_type": "complete",
                 "item_ids": ["a1_set1"], "name": None, "rationale": "Null name."},
            ],
            "overall_assessment": "moderate",
            "pool_unsuitable": False,
        }

        with patch("agentic_application.agents.outfit_composer.get_api_key", return_value="x"), _patch_composer() as oc:
            oc.return_value.responses.create.return_value = _mock_response(payload)
            result = OutfitComposer().compose(_ctx(), _pool())

        self.assertEqual(1, len(result.outfits))
        self.assertEqual("", result.outfits[0].name)

    def test_composer_truncates_excessively_long_name(self) -> None:
        """Schema caps `name` at maxLength=100, but defensively truncate
        in the parser too — a runaway model response shouldn't blow the
        UI title slot."""
        long_name = "A" * 250
        payload = {
            "outfits": [
                {"composer_id": "C1", "direction_id": "A", "direction_type": "complete",
                 "item_ids": ["a1_set1"], "name": long_name,
                 "rationale": "Schema cap should hold but parser truncates too."},
            ],
            "overall_assessment": "moderate",
            "pool_unsuitable": False,
        }

        with patch("agentic_application.agents.outfit_composer.get_api_key", return_value="x"), _patch_composer() as oc:
            oc.return_value.responses.create.return_value = _mock_response(payload)
            result = OutfitComposer().compose(_ctx(), _pool())

        self.assertEqual(100, len(result.outfits[0].name))

    def test_composer_drops_outfit_with_unknown_item_id(self) -> None:
        """Hallucinated item_id → that outfit is silently dropped from
        the result. Other valid outfits still ship."""
        payload = {
            "outfits": [
                {"composer_id": "C1", "direction_id": "A", "direction_type": "complete",
                 "item_ids": ["a1_set1"], "rationale": "Valid."},
                {"composer_id": "C2", "direction_id": "B", "direction_type": "paired",
                 "item_ids": ["b_t1", "BOGUS_HALLUCINATED_ID"], "rationale": "Hallucinated."},
            ],
            "overall_assessment": "moderate",
            "pool_unsuitable": False,
        }

        with patch("agentic_application.agents.outfit_composer.get_api_key", return_value="x"), _patch_composer() as oc:
            oc.return_value.responses.create.return_value = _mock_response(payload)
            result = OutfitComposer().compose(_ctx(), _pool(), retry_on_hallucination=False)

        self.assertEqual(1, len(result.outfits))
        self.assertEqual("C1", result.outfits[0].composer_id)

    def test_composer_drops_outfit_with_wrong_item_count(self) -> None:
        """direction_type=paired needs exactly 2 items; a 1-item or 3-item
        outfit is structurally invalid."""
        payload = {
            "outfits": [
                {"composer_id": "C1", "direction_id": "A", "direction_type": "complete",
                 "item_ids": ["a1_set1", "a1_set2"], "rationale": "Two complete items."},
                {"composer_id": "C2", "direction_id": "B", "direction_type": "paired",
                 "item_ids": ["b_t1"], "rationale": "Only one item."},
                {"composer_id": "C3", "direction_id": "C", "direction_type": "three_piece",
                 "item_ids": ["c_t1", "c_b1", "c_o1"], "rationale": "Valid three-piece."},
            ],
            "overall_assessment": "moderate",
            "pool_unsuitable": False,
        }

        with patch("agentic_application.agents.outfit_composer.get_api_key", return_value="x"), _patch_composer() as oc:
            oc.return_value.responses.create.return_value = _mock_response(payload)
            result = OutfitComposer().compose(_ctx(), _pool(), retry_on_hallucination=False)

        self.assertEqual(1, len(result.outfits))
        self.assertEqual("C3", result.outfits[0].composer_id)

    def test_composer_rejects_cross_direction_item(self) -> None:
        """A Direction B outfit must not pull an item from Direction C —
        validator checks that all item_ids belong to the named direction."""
        payload = {
            "outfits": [
                # b_t1 is fine, c_b1 is from Direction C — invalid in a B outfit.
                {"composer_id": "C1", "direction_id": "B", "direction_type": "paired",
                 "item_ids": ["b_t1", "c_b1"], "rationale": "Cross-direction mix."},
            ],
            "overall_assessment": "moderate",
            "pool_unsuitable": False,
        }
        with patch("agentic_application.agents.outfit_composer.get_api_key", return_value="x"), _patch_composer() as oc:
            oc.return_value.responses.create.return_value = _mock_response(payload)
            result = OutfitComposer().compose(_ctx(), _pool(), retry_on_hallucination=False)

        self.assertEqual(0, len(result.outfits))


class OutfitComposerRetryTests(unittest.TestCase):
    """When the first pass produces no valid outfits AND the Composer
    didn't flag the pool as unsuitable, we retry once with a stricter
    prompt suffix listing the valid IDs explicitly."""

    def test_composer_retries_on_full_hallucination(self) -> None:
        first_pass_all_bogus = {
            "outfits": [
                {"composer_id": "C1", "direction_id": "B", "direction_type": "paired",
                 "item_ids": ["BOGUS_1", "BOGUS_2"], "rationale": "Made up."},
            ],
            "overall_assessment": "moderate",
            "pool_unsuitable": False,
        }
        second_pass_valid = {
            "outfits": [
                {"composer_id": "C1", "direction_id": "B", "direction_type": "paired",
                 "item_ids": ["b_t1", "b_b1"], "rationale": "Valid retry."},
            ],
            "overall_assessment": "moderate",
            "pool_unsuitable": False,
        }
        with patch("agentic_application.agents.outfit_composer.get_api_key", return_value="x"), _patch_composer() as oc:
            oc.return_value.responses.create.side_effect = [
                _mock_response(first_pass_all_bogus),
                _mock_response(second_pass_valid),
            ]
            result = OutfitComposer().compose(_ctx(), _pool())

        self.assertEqual(2, oc.return_value.responses.create.call_count)
        self.assertEqual(1, len(result.outfits))
        self.assertEqual("b_t1", result.outfits[0].item_ids[0])

    def test_composer_returns_usage_on_result(self) -> None:
        """Token usage is carried on the result object, not on a shared
        instance attribute, so concurrent turns don't race."""
        payload = {
            "outfits": [
                {"composer_id": "C1", "direction_id": "A", "direction_type": "complete",
                 "item_ids": ["a1_set1"], "rationale": "ok"},
            ],
            "overall_assessment": "moderate",
            "pool_unsuitable": False,
        }
        mock_resp = Mock()
        mock_resp.output_text = json.dumps(payload)
        mock_resp.usage = Mock(input_tokens=600, output_tokens=200, total_tokens=800)
        with patch("agentic_application.agents.outfit_composer.get_api_key", return_value="x"), _patch_composer() as oc:
            oc.return_value.responses.create.return_value = mock_resp
            result = OutfitComposer().compose(_ctx(), _pool())

        self.assertIsInstance(result.usage, dict)
        self.assertIn("prompt_tokens", result.usage)
        self.assertIn("total_tokens", result.usage)

    def test_composer_retry_suffix_targets_direction_id_when_that_was_the_failure(self) -> None:
        """PR #80: when the first attempt failed because direction_id was
        a product_id (not the architect's letter), the retry suffix
        explicitly calls out the direction_id contract — not the legacy
        item_ids reminder. Validated via the user_payload string passed
        to the LLM on the retry call."""
        first_pass_bad_direction = {
            "outfits": [
                # direction_id is a product_id instead of "A"/"B".
                # Validator drops with "unknown direction_id" reason.
                {"composer_id": "C1", "direction_id": "POWERLOOK_xyz", "direction_type": "paired",
                 "item_ids": ["b_t1", "b_b1"], "rationale": "Made up direction."},
            ],
            "overall_assessment": "moderate",
            "pool_unsuitable": False,
        }
        second_pass_valid = {
            "outfits": [
                {"composer_id": "C1", "direction_id": "B", "direction_type": "paired",
                 "item_ids": ["b_t1", "b_b1"], "rationale": "Fixed direction_id."},
            ],
            "overall_assessment": "moderate",
            "pool_unsuitable": False,
        }
        with patch("agentic_application.agents.outfit_composer.get_api_key", return_value="x"), _patch_composer() as oc:
            oc.return_value.responses.create.side_effect = [
                _mock_response(first_pass_bad_direction),
                _mock_response(second_pass_valid),
            ]
            result = OutfitComposer().compose(_ctx(), _pool())

        # 2 calls — retry fired
        self.assertEqual(2, oc.return_value.responses.create.call_count)
        # 1 outfit on the rescue
        self.assertEqual(1, len(result.outfits))
        self.assertEqual(2, result.attempt_count)
        # Inspect the second call's user_payload — should mention
        # direction_id, NOT just the item_ids reminder.
        retry_user_payload = oc.return_value.responses.create.call_args_list[1].kwargs["input"][1]["content"][0]["text"]
        self.assertIn("direction_id MUST be one of", retry_user_payload)

    def test_composer_per_attempt_callback_fires_once_per_invoke(self) -> None:
        """PR #80: ``on_attempt`` callback is invoked once per LLM call so
        the orchestrator can persist a model_call_logs row per attempt
        instead of one summed row that hides retry token cost."""
        first_pass_bad = {
            "outfits": [
                {"composer_id": "C1", "direction_id": "BOGUS", "direction_type": "paired",
                 "item_ids": ["BOGUS_1", "BOGUS_2"], "rationale": "Bad."},
            ],
            "overall_assessment": "moderate",
            "pool_unsuitable": False,
        }
        second_pass_valid = {
            "outfits": [
                {"composer_id": "C1", "direction_id": "B", "direction_type": "paired",
                 "item_ids": ["b_t1", "b_b1"], "rationale": "Good."},
            ],
            "overall_assessment": "moderate",
            "pool_unsuitable": False,
        }
        captured: list[dict] = []
        with patch("agentic_application.agents.outfit_composer.get_api_key", return_value="x"), _patch_composer() as oc:
            oc.return_value.responses.create.side_effect = [
                _mock_response(first_pass_bad),
                _mock_response(second_pass_valid),
            ]
            result = OutfitComposer().compose(_ctx(), _pool(), on_attempt=captured.append)

        self.assertEqual(2, len(captured))
        self.assertEqual(1, captured[0]["attempt_no"])
        self.assertEqual(0, captured[0]["outfit_count_kept"])  # first attempt rescued nothing
        self.assertEqual(2, captured[1]["attempt_no"])
        self.assertEqual(1, captured[1]["outfit_count_kept"])  # retry fixed it
        self.assertEqual(2, result.attempt_count)

    def test_composer_no_retry_when_pool_unsuitable(self) -> None:
        """When the Composer self-reports pool_unsuitable, we trust it
        and don't burn another LLM call. Empty result, no retry."""
        payload = {
            "outfits": [],
            "overall_assessment": "unsuitable",
            "pool_unsuitable": True,
        }
        with patch("agentic_application.agents.outfit_composer.get_api_key", return_value="x"), _patch_composer() as oc:
            oc.return_value.responses.create.return_value = _mock_response(payload)
            result = OutfitComposer().compose(_ctx(), _pool())

        self.assertEqual(1, oc.return_value.responses.create.call_count)
        self.assertEqual(0, len(result.outfits))
        self.assertTrue(result.pool_unsuitable)


class OutfitComposerEdgeCaseTests(unittest.TestCase):
    def test_composer_handles_empty_pool(self) -> None:
        """Empty retrieved sets — short-circuit before the LLM call."""
        with patch("agentic_application.agents.outfit_composer.get_api_key", return_value="x"), _patch_composer() as oc:
            result = OutfitComposer().compose(_ctx(), [])

        oc.return_value.responses.create.assert_not_called()
        self.assertEqual(0, len(result.outfits))
        self.assertTrue(result.pool_unsuitable)

    def test_composer_handles_malformed_json(self) -> None:
        """Garbage JSON from the LLM → empty result, never raises."""
        bad = Mock()
        bad.output_text = "not json {{{"
        with patch("agentic_application.agents.outfit_composer.get_api_key", return_value="x"), _patch_composer() as oc:
            oc.return_value.responses.create.return_value = bad
            result = OutfitComposer().compose(_ctx(), _pool(), retry_on_hallucination=False)

        self.assertEqual(0, len(result.outfits))
        self.assertEqual("unsuitable", result.overall_assessment)

    def test_composer_handles_followup_turn_with_previous_recommendations(self) -> None:
        """May 3, 2026 regression — turn `782216cd` crashed with
        `'list' object has no attribute 'get'` because the user_context
        block called `(ctx.previous_recommendations or {}).get(...)` on
        what is actually a List[Dict]. Today the field isn't read at all
        (we use `disliked_product_ids` instead); this test exercises the
        follow-up code path with a populated list to lock in the fix."""
        ctx = CombinedContext(
            user=UserContext(user_id="u1", gender="male"),
            live=LiveContext(
                user_need="Make it more royal",
                occasion_signal="wedding_ceremony",
                formality_hint="ceremonial",
                is_followup=True,
            ),
            hard_filters={"gender_expression": "masculine"},
            # The shape that triggered the crash — a non-empty list of
            # prior recommendations, not a dict.
            previous_recommendations=[
                {"candidate_id": "prev-1", "items": [{"product_id": "sku-1", "title": "Old kurta_set"}]},
                {"candidate_id": "prev-2", "items": [{"product_id": "sku-2", "title": "Old suit_set"}]},
            ],
            disliked_product_ids=["disliked-sku-9"],
        )
        payload = {
            "outfits": [
                {"composer_id": "C1", "direction_id": "A", "direction_type": "complete",
                 "item_ids": ["a1_set1"], "rationale": "Ceremonial kurta_set with deeper jewel tones."},
            ],
            "overall_assessment": "moderate",
            "pool_unsuitable": False,
        }
        with patch("agentic_application.agents.outfit_composer.get_api_key", return_value="x"), _patch_composer() as oc:
            oc.return_value.responses.create.return_value = _mock_response(payload)
            result = OutfitComposer().compose(ctx, _pool())

        self.assertEqual(1, len(result.outfits))
        # Verify the user_context block actually got built without
        # AttributeError — the call would not have reached this point
        # otherwise.
        oc.return_value.responses.create.assert_called_once()


class OutfitComposerHelperTests(unittest.TestCase):
    """Direct tests of the validation + payload-building helpers — the
    integration tests above bottle up enough that a regression in the
    helpers would be hard to attribute."""

    def test_validate_outfit_passes_for_valid_paired(self) -> None:
        outfit = ComposedOutfit(
            composer_id="C1", direction_id="B", direction_type="paired",
            item_ids=["b_t1", "b_b1"], rationale="ok",
        )
        pool_ids = {"A": {"a1"}, "B": {"b_t1", "b_b1", "b_t2"}, "C": {"c_t1"}}
        self.assertIsNone(_validate_outfit(outfit, pool_ids))

    def test_validate_outfit_flags_unknown_direction_type(self) -> None:
        outfit = ComposedOutfit(
            composer_id="C1", direction_id="B", direction_type="quartet",
            item_ids=["b_t1", "b_b1", "b_t2", "b_b2"], rationale="invalid",
        )
        err = _validate_outfit(outfit, {"B": {"b_t1", "b_b1", "b_t2", "b_b2"}})
        self.assertIsNotNone(err)
        self.assertIn("unknown direction_type", err)

    def test_user_payload_includes_pool_grouped_by_direction(self) -> None:
        payload = _build_user_payload(_ctx(), _pool())
        data = json.loads(payload)
        self.assertIn("user", data)
        self.assertIn("pool", data)
        self.assertEqual({"A", "B", "C"}, set(data["pool"].keys()))
        self.assertEqual("complete", data["pool"]["A"]["direction_type"])
        self.assertEqual("paired", data["pool"]["B"]["direction_type"])
        self.assertEqual("three_piece", data["pool"]["C"]["direction_type"])
        self.assertIn("complete", data["pool"]["A"])
        self.assertIn("top", data["pool"]["B"])
        self.assertIn("bottom", data["pool"]["B"])
        self.assertIn("outerwear", data["pool"]["C"])


if __name__ == "__main__":
    unittest.main()
