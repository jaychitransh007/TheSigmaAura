import hashlib
import os
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from uuid import uuid4

from conversation_platform.supabase_rest import SupabaseError

from .repository import OnboardingRepository
from .schemas import FIXED_OTP, ImageCategory


REQUIRED_IMAGE_CATEGORIES = frozenset(("full_body", "headshot", "veins"))
IMAGE_STORAGE_TYPES = {
    "full_body": "fullshot",
    "headshot": "headshot",
    "veins": "veinshot",
}


def _encrypt_filename(user_id: str, category: str, timestamp: str) -> str:
    storage_type = IMAGE_STORAGE_TYPES.get(category, category)
    raw = f"{user_id}_{storage_type}_{timestamp}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _hash_otp_value(otp: str) -> str:
    return hashlib.sha256(otp.encode("utf-8")).hexdigest()


class OnboardingService:
    def __init__(
        self,
        repo: Optional[OnboardingRepository] = None,
        image_dir: str = "data/onboarding/images",
    ) -> None:
        self._repo = repo
        self._image_dir = Path(image_dir)
        self._image_dir.mkdir(parents=True, exist_ok=True)

    def send_otp(self, mobile: str) -> tuple[bool, str]:
        return True, f"OTP sent to {mobile}"

    def verify_otp(self, mobile: str, otp: str) -> tuple[bool, str, str]:
        if otp != FIXED_OTP:
            return False, "", "Invalid OTP"
        if self._repo is None:
            return False, "", "Service unavailable"
        existing = self._repo.get_profile_by_mobile(mobile)
        verified_at = datetime.now(timezone.utc).isoformat()
        otp_hash = _hash_otp_value(otp)
        if existing:
            self._record_otp_verification_safe(
                existing["user_id"],
                otp_last_used_hash=otp_hash,
                otp_verified_at=verified_at,
            )
            return True, existing["user_id"], "Verified (existing user)"
        user_id = f"user_{uuid4().hex[:12]}"
        self._repo.create_profile(user_id=user_id, mobile=mobile)
        self._record_otp_verification_safe(
            user_id,
            otp_last_used_hash=otp_hash,
            otp_verified_at=verified_at,
        )
        return True, user_id, "Verified (new user)"

    def save_profile(
        self,
        user_id: str,
        name: str,
        date_of_birth: str,
        gender: str,
        height_cm: float,
        waist_cm: float,
        profession: str,
    ) -> bool:
        if self._repo is None:
            return False
        existing = self._repo.get_profile_by_user_id(user_id)
        if not existing:
            return False
        self._repo.update_profile(
            user_id,
            name=name,
            date_of_birth=date_of_birth,
            gender=gender,
            height_cm=height_cm,
            waist_cm=waist_cm,
            profession=profession,
        )
        self._check_and_mark_complete(user_id)
        return True

    def save_image(
        self,
        user_id: str,
        category: ImageCategory,
        file_data: bytes,
        filename: str,
    ) -> Optional[tuple[str, str]]:
        """Returns (encrypted_filename, file_path) or None."""
        if self._repo is None:
            return None
        existing = self._repo.get_profile_by_user_id(user_id)
        if not existing:
            return None

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
        encrypted_name = _encrypt_filename(user_id, category, timestamp)

        ext = os.path.splitext(filename)[1] or ".jpg"
        stored_filename = f"{encrypted_name}{ext}"
        dest = self._image_dir / stored_filename
        with open(dest, "wb") as f:
            f.write(file_data)

        mime_type = "image/jpeg"
        if ext.lower() == ".png":
            mime_type = "image/png"
        elif ext.lower() == ".webp":
            mime_type = "image/webp"

        self._repo.upsert_image(
            user_id=user_id,
            category=category,
            encrypted_filename=encrypted_name,
            original_filename=filename,
            file_path=str(dest),
            mime_type=mime_type,
            file_size_bytes=len(file_data),
        )
        self._check_and_mark_complete(user_id)
        return encrypted_name, str(dest)

    def normalize_image_for_crop(
        self,
        *,
        file_data: bytes,
        filename: str,
        content_type: str,
    ) -> tuple[bytes, str, str]:
        if not self._is_heic_file(filename=filename, content_type=content_type):
            return file_data, content_type or "image/jpeg", filename

        suffix = Path(filename or "image.heic").suffix or ".heic"
        with tempfile.TemporaryDirectory() as tmp_dir:
            source_path = Path(tmp_dir) / f"source{suffix}"
            output_path = Path(tmp_dir) / "normalized.jpg"
            source_path.write_bytes(file_data)
            try:
                subprocess.run(
                    ["/usr/bin/sips", "-s", "format", "jpeg", str(source_path), "--out", str(output_path)],
                    check=True,
                    capture_output=True,
                    text=True,
                )
            except subprocess.CalledProcessError as exc:
                raise RuntimeError(f"Unable to convert HEIC image: {exc.stderr.strip() or exc.stdout.strip() or exc}") from exc

            normalized = output_path.read_bytes()
            normalized_name = f"{Path(filename).stem or 'image'}.jpg"
            return normalized, "image/jpeg", normalized_name

    def _check_and_mark_complete(self, user_id: str) -> None:
        if self._repo is None:
            return
        profile = self._repo.get_profile_by_user_id(user_id)
        if not profile or not profile.get("profile_complete"):
            return
        uploaded = set(self._repo.get_image_categories(user_id))
        if REQUIRED_IMAGE_CATEGORIES <= uploaded:
            self._repo.mark_onboarding_complete(user_id)

    def _record_otp_verification_safe(
        self,
        user_id: str,
        *,
        otp_last_used_hash: str,
        otp_verified_at: str,
    ) -> None:
        if self._repo is None:
            return
        try:
            self._repo.record_otp_verification(
                user_id,
                otp_last_used_hash=otp_last_used_hash,
                otp_verified_at=otp_verified_at,
            )
        except SupabaseError as exc:
            if self._is_missing_otp_metadata_column_error(exc):
                return
            raise

    def _is_missing_otp_metadata_column_error(self, exc: SupabaseError) -> bool:
        message = str(exc)
        return (
            "PGRST204" in message
            and "onboarding_profiles" in message
            and (
                "otp_last_used_hash" in message
                or "otp_verified_at" in message
            )
        )

    def _is_heic_file(self, *, filename: str, content_type: str) -> bool:
        suffix = Path(filename or "").suffix.lower()
        return suffix in {".heic", ".heif"} or content_type.lower() in {"image/heic", "image/heif"}

    def get_status(self, user_id: str) -> dict:
        if self._repo is None:
            return {
                "user_id": user_id,
                "profile_complete": False,
                "images_uploaded": [],
                "onboarding_complete": False,
            }
        profile = self._repo.get_profile_by_user_id(user_id)
        if not profile:
            return {
                "user_id": user_id,
                "profile_complete": False,
                "images_uploaded": [],
                "onboarding_complete": False,
            }
        categories = self._repo.get_image_categories(user_id)
        return {
            "user_id": profile["user_id"],
            "mobile": profile.get("mobile", ""),
            "profile_complete": bool(profile.get("profile_complete")),
            "images_uploaded": categories,
            "onboarding_complete": bool(profile.get("onboarding_complete")),
        }
