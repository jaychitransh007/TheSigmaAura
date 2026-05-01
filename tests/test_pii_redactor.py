"""Tests for the PII redaction layer (Item 7, May 1, 2026)."""

from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import Mock


ROOT = Path(__file__).resolve().parents[1]
for p in (
    ROOT,
    ROOT / "modules" / "platform_core" / "src",
    ROOT / "modules" / "user_profiler" / "src",
):
    sp = str(p)
    if sp not in sys.path:
        sys.path.insert(0, sp)


from platform_core.pii_redactor import (
    redact_string,
    redact_value,
    redact_profile,
)
from platform_core.repositories import ConversationRepository


class StringRedactionTests(unittest.TestCase):
    def test_redacts_email_addresses(self) -> None:
        out = redact_string("Contact me at jane.doe@example.com please")
        self.assertEqual("Contact me at [EMAIL] please", out)

    def test_redacts_multiple_emails_in_one_string(self) -> None:
        out = redact_string("from a@b.io to c.d@e.co")
        self.assertEqual("from [EMAIL] to [EMAIL]", out)

    def test_redacts_phone_numbers(self) -> None:
        out = redact_string("Call +1 (415) 555-1234 or 9876543210")
        self.assertIn("[PHONE]", out)
        self.assertNotIn("415", out)
        self.assertNotIn("9876543210", out)

    def test_redacts_ssn_pattern(self) -> None:
        out = redact_string("SSN 123-45-6789 belongs to ...")
        self.assertEqual("SSN [SSN] belongs to ...", out)

    def test_passes_through_normal_text(self) -> None:
        out = redact_string("What should I wear to the wedding?")
        self.assertEqual("What should I wear to the wedding?", out)

    def test_handles_empty_and_non_string(self) -> None:
        self.assertEqual("", redact_string(""))
        self.assertEqual(None, redact_string(None))  # type: ignore[arg-type]


class RedactValueRecursionTests(unittest.TestCase):
    def test_recurses_into_nested_dicts(self) -> None:
        payload = {
            "user_message": "send to alice@example.com",
            "metadata": {"contact_phone": "415-555-1234"},
        }
        out = redact_value(payload)
        self.assertEqual("send to [EMAIL]", out["user_message"])
        self.assertEqual("[PHONE]", out["metadata"]["contact_phone"])

    def test_recurses_into_lists(self) -> None:
        payload = ["jane@a.io", "no email here", {"phone": "555-555-5555"}]
        out = redact_value(payload)
        self.assertEqual("[EMAIL]", out[0])
        self.assertEqual("no email here", out[1])
        self.assertEqual("[PHONE]", out[2]["phone"])

    def test_leaves_primitives_alone(self) -> None:
        self.assertEqual(42, redact_value(42))
        self.assertTrue(redact_value(True))


class ProfileBandFoldTests(unittest.TestCase):
    def test_height_cm_folds_to_band(self) -> None:
        out = redact_profile({"height_cm": 158, "BodyShape": "Hourglass"})
        self.assertNotIn("height_cm", out)
        self.assertEqual("Petite", out["height_band"])
        self.assertEqual("Hourglass", out["BodyShape"])  # untouched

    def test_height_cm_average_band(self) -> None:
        self.assertEqual("Average", redact_profile({"height_cm": 168})["height_band"])

    def test_height_cm_tall_band(self) -> None:
        self.assertEqual("Tall", redact_profile({"height_cm": 180})["height_band"])

    def test_waist_cm_folds_to_band(self) -> None:
        out = redact_profile({"waist_cm": 78})
        self.assertNotIn("waist_cm", out)
        self.assertEqual("Medium", out["waist_band"])

    def test_dob_folds_to_5_year_age_band(self) -> None:
        # Pick a DOB that will land cleanly in a band regardless of run date.
        # Band edges align on every 5 years from 0.
        out = redact_profile({"date_of_birth": "1990-01-01"})
        self.assertNotIn("date_of_birth", out)
        self.assertIn(out["age_band"].split("-")[0], ("30", "35", "40", "45", "50", "55", "60"))
        self.assertRegex(out["age_band"], r"^\d+-\d+$|^65\+$|^<18$")

    def test_drops_name_and_phone_fields(self) -> None:
        out = redact_profile({
            "name": "Jane Doe",
            "mobile": "9999999999",
            "phone": "415-555-1234",
            "BodyShape": "Hourglass",
        })
        self.assertNotIn("name", out)
        self.assertNotIn("mobile", out)
        self.assertNotIn("phone", out)
        self.assertEqual("Hourglass", out["BodyShape"])


class RepositoryRedactionWiringTests(unittest.TestCase):
    """Item 7: log_model_call and insert_turn_trace redact PII by default."""

    def test_log_model_call_redacts_request_json_user_message(self) -> None:
        client = Mock()
        client.insert_one.return_value = {"id": "m1"}
        repo = ConversationRepository(client)
        repo.log_model_call(
            conversation_id="c1", turn_id="t1",
            service="agentic_application", call_type="copilot_planner",
            model="gpt-5.4",
            request_json={"message": "email me at user@example.com"},
            response_json={},
            reasoning_notes=[],
        )
        payload = client.insert_one.call_args.args[1]
        self.assertEqual("email me at [EMAIL]", payload["request_json"]["message"])

    def test_log_model_call_explicit_redact_pii_false_passes_through(self) -> None:
        client = Mock()
        client.insert_one.return_value = {"id": "m1"}
        repo = ConversationRepository(client)
        repo.log_model_call(
            conversation_id="c1", turn_id="t1",
            service="x", call_type="y", model="z",
            request_json={"raw": "user@example.com"},
            response_json={}, reasoning_notes=[],
            redact_pii=False,
        )
        payload = client.insert_one.call_args.args[1]
        self.assertEqual("user@example.com", payload["request_json"]["raw"])

    def test_insert_turn_trace_redacts_user_message_and_profile(self) -> None:
        client = Mock()
        client.insert_one.return_value = {"id": "tt1"}
        repo = ConversationRepository(client)
        repo.insert_turn_trace(
            turn_id="t1", conversation_id="c1", user_id="u1",
            user_message="contact 555-555-5555 for details",
            profile_snapshot={"height_cm": 165, "BodyShape": "Pear"},
        )
        payload = client.insert_one.call_args.args[1]
        self.assertEqual("contact [PHONE] for details", payload["user_message"])
        self.assertNotIn("height_cm", payload["profile_snapshot"])
        self.assertEqual("Average", payload["profile_snapshot"]["height_band"])
        self.assertEqual("Pear", payload["profile_snapshot"]["BodyShape"])


class GdprDeletionHelperTests(unittest.TestCase):
    """Item 7: delete_user_observability_data sweeps every observability table."""

    def test_returns_zero_counts_for_unknown_user(self) -> None:
        client = Mock()
        client.select_one.return_value = None
        repo = ConversationRepository(client)
        counts = repo.delete_user_observability_data("ghost-user")
        # Tables keyed on internal user_id should all return 0
        for table in (
            "turn_traces", "feedback_events", "dependency_validation_events",
            "catalog_interaction_history", "user_comfort_learning",
            "confidence_history", "virtual_tryon_images",
        ):
            self.assertEqual(0, counts[table])


if __name__ == "__main__":
    unittest.main()
