import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import sys
from fastapi import FastAPI
from fastapi.testclient import TestClient

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
from user.api import create_onboarding_router
from user.ui import get_onboarding_html, get_processing_html
from platform_core.supabase_rest import SupabaseError


class OnboardingTests(unittest.TestCase):
    def test_verify_otp_records_hash_for_new_user(self) -> None:
        repo = Mock()
        repo.get_profile_by_mobile.return_value = None

        with tempfile.TemporaryDirectory() as tmp_dir:
            service = OnboardingService(repo=repo, image_dir=tmp_dir)
            verified, user_id, message = service.verify_otp(
                "+919876543210",
                "123456",
                acquisition_source="instagram",
                referral_code="friend42",
            )

        self.assertTrue(verified)
        self.assertTrue(user_id.startswith("user_"))
        self.assertIn("new user", message.lower())
        repo.create_profile.assert_called_once()
        self.assertEqual("instagram", repo.create_profile.call_args.kwargs["acquisition_source"])
        self.assertEqual("friend42", repo.create_profile.call_args.kwargs["referral_code"])
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

    def test_verify_otp_emits_dependency_event_and_updates_existing_acquisition_context(self) -> None:
        repo = Mock()
        repo.get_profile_by_mobile.return_value = {"user_id": "user_existing"}
        dependency_logger = Mock()

        with tempfile.TemporaryDirectory() as tmp_dir:
            service = OnboardingService(repo=repo, image_dir=tmp_dir, dependency_logger=dependency_logger)
            verified, user_id, message = service.verify_otp(
                "+919876543210",
                "123456",
                acquisition_source="referral",
                acquisition_campaign="friends",
                referral_code="abc123",
                icp_tag="working-professional",
            )

        self.assertTrue(verified)
        self.assertEqual("user_existing", user_id)
        self.assertIn("existing user", message.lower())
        repo.update_acquisition_context.assert_called_once()
        dependency_logger.assert_called_once()
        self.assertEqual("otp_verified", dependency_logger.call_args.kwargs["event_type"])
        self.assertEqual("referral", dependency_logger.call_args.kwargs["metadata_json"]["acquisition_source"])

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
        self.assertTrue(any(call.args[0][0] == "/usr/bin/sips" for call in run_mock.call_args_list))

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

    def test_save_image_blocks_explicit_nude_upload(self) -> None:
        repo = Mock()
        repo.get_profile_by_user_id.return_value = {"user_id": "user_123"}
        policy_logger = Mock()

        with tempfile.TemporaryDirectory() as tmp_dir:
            service = OnboardingService(repo=repo, image_dir=tmp_dir, policy_logger=policy_logger)
            with self.assertRaises(ValueError):
                service.save_image(
                    user_id="user_123",
                    category="full_body",
                    file_data=b"jpeg-bytes",
                    filename="nude_selfie.jpg",
                    content_type="image/jpeg",
                )

        repo.upsert_image.assert_not_called()
        self.assertEqual("blocked", policy_logger.call_args.kwargs["decision"])
        self.assertEqual("image_upload_guardrail", policy_logger.call_args.kwargs["policy_event_type"])

    def test_save_wardrobe_item_blocks_explicit_nude_upload(self) -> None:
        repo = Mock()
        repo.get_profile_by_user_id.return_value = {"user_id": "user_123"}

        with tempfile.TemporaryDirectory() as tmp_dir:
            service = OnboardingService(repo=repo, image_dir=tmp_dir)
            with self.assertRaises(ValueError):
                service.save_wardrobe_item(
                    user_id="user_123",
                    file_data=b"jpeg-bytes",
                    filename="topless_item.jpg",
                    content_type="image/jpeg",
                )

        repo.insert_wardrobe_item.assert_not_called()

    def test_save_image_blocks_minor_upload(self) -> None:
        repo = Mock()
        repo.get_profile_by_user_id.return_value = {"user_id": "user_123"}

        with tempfile.TemporaryDirectory() as tmp_dir:
            service = OnboardingService(repo=repo, image_dir=tmp_dir)
            with self.assertRaises(ValueError) as ctx:
                service.save_image(
                    user_id="user_123",
                    category="headshot",
                    file_data=b"jpeg-bytes",
                    filename="child_portrait.jpg",
                    content_type="image/jpeg",
                )

        self.assertIn("adult outfit", str(ctx.exception))
        repo.upsert_image.assert_not_called()

    def test_save_wardrobe_item_blocks_restricted_category_upload(self) -> None:
        repo = Mock()
        repo.get_profile_by_user_id.return_value = {"user_id": "user_123"}
        policy_logger = Mock()

        with tempfile.TemporaryDirectory() as tmp_dir:
            service = OnboardingService(repo=repo, image_dir=tmp_dir, policy_logger=policy_logger)
            with self.assertRaises(ValueError) as ctx:
                service.save_wardrobe_item(
                    user_id="user_123",
                    file_data=b"jpeg-bytes",
                    filename="bralette.jpg",
                    content_type="image/jpeg",
                    title="Silk bralette",
                    garment_category="lingerie",
                )

        self.assertIn("not supported here", str(ctx.exception))
        repo.insert_wardrobe_item.assert_not_called()
        self.assertEqual("restricted_category_guardrail", policy_logger.call_args.kwargs["policy_event_type"])
        self.assertEqual("blocked", policy_logger.call_args.kwargs["decision"])

    def test_save_image_logs_allowed_policy_event(self) -> None:
        repo = Mock()
        repo.get_profile_by_user_id.return_value = {"user_id": "user_123"}
        policy_logger = Mock()

        with tempfile.TemporaryDirectory() as tmp_dir:
            service = OnboardingService(repo=repo, image_dir=tmp_dir, policy_logger=policy_logger)
            repo.upsert_image.return_value = {"id": "img-1"}
            result = service.save_image(
                user_id="user_123",
                category="headshot",
                file_data=b"jpeg-bytes",
                filename="portrait.jpg",
                content_type="image/jpeg",
            )

        self.assertIsNotNone(result)
        policy_logger.assert_called_once()
        self.assertEqual("allowed", policy_logger.call_args.kwargs["decision"])
        self.assertEqual("safe", policy_logger.call_args.kwargs["reason_code"])

    def test_save_wardrobe_item_logs_allowed_category_and_image_policy_events(self) -> None:
        repo = Mock()
        repo.get_profile_by_user_id.return_value = {"user_id": "user_123"}
        repo.insert_wardrobe_item.return_value = {"id": "w1"}
        policy_logger = Mock()

        with tempfile.TemporaryDirectory() as tmp_dir:
            service = OnboardingService(repo=repo, image_dir=tmp_dir, policy_logger=policy_logger)
            service.save_wardrobe_item(
                user_id="user_123",
                file_data=b"jpeg-bytes",
                filename="blazer.jpg",
                content_type="image/jpeg",
                title="Navy Blazer",
                garment_category="blazer",
                garment_subtype="tailored_blazer",
            )

        self.assertEqual(2, policy_logger.call_count)
        first = policy_logger.call_args_list[0].kwargs
        second = policy_logger.call_args_list[1].kwargs
        self.assertEqual("restricted_category_guardrail", first["policy_event_type"])
        self.assertEqual("allowed", first["decision"])
        self.assertEqual("image_upload_guardrail", second["policy_event_type"])
        self.assertEqual("allowed", second["decision"])

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
        repo.count_wardrobe_items.return_value = 3

        with tempfile.TemporaryDirectory() as tmp_dir:
            service = OnboardingService(repo=repo, image_dir=tmp_dir)
            status = service.get_status("user_status")

        self.assertTrue(status["profile_complete"])
        self.assertTrue(status["style_preference_complete"])
        self.assertFalse(status["onboarding_complete"])
        self.assertEqual(["full_body", "headshot"], status["images_uploaded"])
        self.assertEqual(3, status["wardrobe_item_count"])

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

    def test_save_wardrobe_item_persists_image_and_metadata(self) -> None:
        repo = Mock()
        repo.get_profile_by_user_id.return_value = {"user_id": "user_style"}
        repo.insert_wardrobe_item.return_value = {"id": "w1", "user_id": "user_style", "source": "onboarding"}

        with tempfile.TemporaryDirectory() as tmp_dir:
            service = OnboardingService(repo=repo, image_dir=tmp_dir)
            out = service.save_wardrobe_item(
                user_id="user_style",
                file_data=b"img-bytes",
                filename="blazer.jpg",
                content_type="image/jpeg",
                title="Navy Blazer",
                garment_category="outerwear",
                primary_color="navy",
            )

            self.assertIsNotNone(out)
            kwargs = repo.insert_wardrobe_item.call_args.kwargs
            self.assertEqual("user_style", kwargs["user_id"])
            self.assertEqual("Navy Blazer", kwargs["title"])
            self.assertEqual("outerwear", kwargs["garment_category"])
            self.assertEqual("navy", kwargs["primary_color"])
            self.assertIn("wardrobe", kwargs["image_path"])
            self.assertTrue(Path(kwargs["image_path"]).exists())
            self.assertEqual("blazer.jpg", kwargs["metadata_json"]["original_filename"])

    def test_onboarding_router_supports_wardrobe_upload_and_list(self) -> None:
        service = Mock()
        analysis_service = Mock()
        service.save_wardrobe_item.return_value = {
            "id": "w1",
            "user_id": "user_style",
            "source": "onboarding",
            "title": "Navy Blazer",
            "description": "",
            "image_url": "",
            "image_path": "data/onboarding/images/wardrobe/file.jpg",
            "garment_category": "outerwear",
            "garment_subtype": "",
            "primary_color": "navy",
            "secondary_color": "",
            "pattern_type": "",
            "formality_level": "",
            "occasion_fit": "",
            "brand": "",
            "notes": "",
            "metadata_json": {"original_filename": "blazer.jpg"},
            "is_active": True,
            "created_at": "",
            "updated_at": "",
        }
        service.list_wardrobe_items.return_value = {
            "user_id": "user_style",
            "count": 1,
            "items": [service.save_wardrobe_item.return_value],
        }

        app = FastAPI()
        app.include_router(create_onboarding_router(service, analysis_service))
        client = TestClient(app)

        upload = client.post(
            "/v1/onboarding/wardrobe/items",
            data={
                "user_id": "user_style",
                "title": "Navy Blazer",
                "garment_category": "outerwear",
                "primary_color": "navy",
            },
            files={"file": ("blazer.jpg", b"img", "image/jpeg")},
        )
        self.assertEqual(200, upload.status_code)
        self.assertEqual("Navy Blazer", upload.json()["title"])

        listing = client.get("/v1/onboarding/wardrobe/user_style")
        self.assertEqual(200, listing.status_code)
        self.assertEqual(1, listing.json()["count"])
        self.assertEqual("Navy Blazer", listing.json()["items"][0]["title"])


if __name__ == "__main__":
    unittest.main()
