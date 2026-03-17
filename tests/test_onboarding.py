import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import sys

ROOT = Path(__file__).resolve().parents[1]
for p in (
    ROOT,
    ROOT / "modules" / "platform_core" / "src",
    ROOT / "modules" / "user" / "src",
    ROOT / "modules" / "user_profiler" / "src",
):
    sp = str(p)
    if sp not in sys.path:
        sys.path.insert(0, sp)

from user.service import OnboardingService, _encrypt_filename
from user.style_archetype import ARCHETYPE_ORDER
from user.analysis import UserAnalysisService
from user.ui import get_onboarding_html, get_processing_html
from platform_core.supabase_rest import SupabaseError


class OnboardingTests(unittest.TestCase):
    def test_verify_otp_records_hash_for_new_user(self) -> None:
        repo = Mock()
        repo.get_profile_by_mobile.return_value = None

        with tempfile.TemporaryDirectory() as tmp_dir:
            service = OnboardingService(repo=repo, image_dir=tmp_dir)
            verified, user_id, message = service.verify_otp("+919876543210", "123456")

        self.assertTrue(verified)
        self.assertTrue(user_id.startswith("user_"))
        self.assertIn("new user", message.lower())
        repo.create_profile.assert_called_once()
        repo.record_otp_verification.assert_called_once()
        otp_hash = repo.record_otp_verification.call_args.kwargs["otp_last_used_hash"]
        self.assertEqual(hashlib.sha256(b"123456").hexdigest(), otp_hash)

    def test_verify_otp_records_hash_for_existing_user(self) -> None:
        repo = Mock()
        repo.get_profile_by_mobile.return_value = {"user_id": "user_existing"}

        with tempfile.TemporaryDirectory() as tmp_dir:
            service = OnboardingService(repo=repo, image_dir=tmp_dir)
            verified, user_id, message = service.verify_otp("+919876543210", "123456")

        self.assertTrue(verified)
        self.assertEqual("user_existing", user_id)
        self.assertIn("existing user", message.lower())
        repo.create_profile.assert_not_called()
        repo.record_otp_verification.assert_called_once()

    def test_verify_otp_ignores_missing_otp_metadata_columns(self) -> None:
        repo = Mock()
        repo.get_profile_by_mobile.return_value = {"user_id": "user_existing"}
        repo.record_otp_verification.side_effect = SupabaseError(
            "Supabase request failed (400) PATCH http://127.0.0.1:55321/rest/v1/onboarding_profiles?user_id=eq.user_existing: "
            '{"code":"PGRST204","message":"Could not find the \\"otp_last_used_hash\\" column of \\"onboarding_profiles\\" in the schema cache"}'
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            service = OnboardingService(repo=repo, image_dir=tmp_dir)
            verified, user_id, message = service.verify_otp("+919876543210", "123456")

        self.assertTrue(verified)
        self.assertEqual("user_existing", user_id)
        self.assertIn("existing user", message.lower())

    def test_encrypt_filename_uses_requested_storage_labels(self) -> None:
        encrypted = _encrypt_filename("user_123", "full_body", "20260310101010123456")
        expected = hashlib.sha256(b"user_123_fullshot_20260310101010123456").hexdigest()
        self.assertEqual(expected, encrypted)

    def test_normalize_image_for_crop_converts_heic_with_sips(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            service = OnboardingService(repo=Mock(), image_dir=tmp_dir)

            def fake_run(cmd, check, capture_output, text):
                output_path = Path(cmd[-1])
                output_path.write_bytes(b"jpeg-bytes")
                return Mock()

            with patch("user.service.subprocess.run", side_effect=fake_run) as run_mock:
                normalized, mime_type, filename = service.normalize_image_for_crop(
                    file_data=b"heic-bytes",
                    filename="portrait.HEIC",
                    content_type="image/heic",
                )

        self.assertEqual(b"jpeg-bytes", normalized)
        self.assertEqual("image/jpeg", mime_type)
        self.assertEqual("portrait.jpg", filename)
        run_mock.assert_called_once()

    def test_normalize_image_for_crop_passthrough_for_jpeg(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            service = OnboardingService(repo=Mock(), image_dir=tmp_dir)
            normalized, mime_type, filename = service.normalize_image_for_crop(
                file_data=b"jpeg-bytes",
                filename="portrait.jpg",
                content_type="image/jpeg",
            )

        self.assertEqual(b"jpeg-bytes", normalized)
        self.assertEqual("image/jpeg", mime_type)
        self.assertEqual("portrait.jpg", filename)

    def test_onboarding_html_contains_modular_step_flow_and_crop_frame(self) -> None:
        html = get_onboarding_html()
        self.assertIn("Step 1 of 10", html)
        self.assertIn("OTP for local testing", html)
        self.assertIn("2:3 frame", html)
        self.assertIn("Profession", html)
        self.assertIn("uploadHeadshotBtn", html)
        self.assertIn("/v1/onboarding/images/normalize", html)
        self.assertIn("determineResumeDestination", html)
        self.assertIn("/onboard/processing?user=", html)
        self.assertIn("Select the outfits that feel like you.", html)
        self.assertIn("/v1/onboarding/style/session/", html)
        self.assertIn("/v1/onboarding/style/complete", html)
        self.assertIn("saveStyleBtn", html)

    def test_processing_html_contains_profile_summary_section(self) -> None:
        html = get_processing_html("user_123")
        self.assertIn("Stored Profile Details", html)
        self.assertIn("profileGrid", html)
        self.assertIn("Mobile Number", html)
        self.assertIn("Re-Run Analysis", html)
        self.assertIn("Re-Run This Section", html)
        self.assertIn("/v1/onboarding/analysis/rerun-agent", html)
        self.assertIn("Logout", html)

    def test_analysis_reuses_pending_snapshot_instead_of_creating_duplicate_attempt(self) -> None:
        repo = Mock()
        repo.get_latest_analysis_snapshot.return_value = {"id": "snap_1", "status": "pending"}

        service = UserAnalysisService(repo=repo)
        run = service.ensure_analysis_started("user_123")

        self.assertEqual("snap_1", run["id"])
        repo.create_analysis_snapshot.assert_not_called()

    def test_get_style_archetype_session_returns_eight_base_images(self) -> None:
        repo = Mock()
        repo.get_profile_by_user_id.return_value = {
            "user_id": "user_style",
            "gender": "female",
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
            service = OnboardingService(repo=repo, image_dir=tmp_dir)
            session = service.get_style_archetype_session("user_style")

        assert session is not None
        self.assertEqual("user_style", session["user_id"])
        self.assertEqual("female", session["gender"])
        self.assertEqual(3, session["minSelections"])
        self.assertEqual(5, session["maxSelections"])
        self.assertEqual(8, len(session["layer1"]))
        self.assertEqual(ARCHETYPE_ORDER, [image["primaryArchetype"] for image in session["layer1"]])

    def test_get_status_exposes_style_preference_completion(self) -> None:
        repo = Mock()
        repo.get_profile_by_user_id.return_value = {
            "user_id": "user_status",
            "mobile": "+919999999999",
            "profile_complete": True,
            "style_preference_complete": True,
            "onboarding_complete": False,
        }
        repo.get_image_categories.return_value = ["full_body", "headshot"]

        with tempfile.TemporaryDirectory() as tmp_dir:
            service = OnboardingService(repo=repo, image_dir=tmp_dir)
            status = service.get_status("user_status")

        self.assertTrue(status["profile_complete"])
        self.assertTrue(status["style_preference_complete"])
        self.assertFalse(status["onboarding_complete"])
        self.assertEqual(["full_body", "headshot"], status["images_uploaded"])

    def test_save_style_preference_persists_selected_images_map_and_count(self) -> None:
        repo = Mock()
        repo.get_profile_by_user_id.return_value = {
            "user_id": "user_style",
            "gender": "female",
            "profile_complete": True,
            "style_preference_complete": False,
        }
        repo.get_image_categories.return_value = ["full_body", "headshot"]
        shown_images = [
            {"id": "P001", "primaryArchetype": "classic", "secondaryArchetype": None, "intensity": "moderate", "context": "neutral"},
            {"id": "P002", "primaryArchetype": "dramatic", "secondaryArchetype": None, "intensity": "moderate", "context": "neutral"},
            {"id": "P003", "primaryArchetype": "romantic", "secondaryArchetype": None, "intensity": "moderate", "context": "neutral"},
        ]
        selections = [
            {"image": shown_images[0], "layer": 1, "position": None, "selectionOrder": 1},
            {"image": shown_images[1], "layer": 1, "position": None, "selectionOrder": 2},
            {"image": shown_images[2], "layer": 1, "position": None, "selectionOrder": 3},
        ]

        with tempfile.TemporaryDirectory() as tmp_dir:
            service = OnboardingService(repo=repo, image_dir=tmp_dir)
            result = service.save_style_preference("user_style", shown_images, selections)

        assert result is not None
        self.assertEqual({"1": "P001.png", "2": "P002.png", "3": "P003.png"}, result["selectedImages"])
        self.assertEqual(3, result["selectionCount"])
        repo.insert_style_preference_snapshot.assert_called_once()
        saved_payload = repo.insert_style_preference_snapshot.call_args.kwargs["style_preference"]
        self.assertEqual({"1": "P001.png", "2": "P002.png", "3": "P003.png"}, saved_payload["selectedImages"])
        self.assertEqual(3, saved_payload["selectionCount"])


if __name__ == "__main__":
    unittest.main()
