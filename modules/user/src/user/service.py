import hashlib
import os
import subprocess
import tempfile
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

from platform_core.fallback_messages import graceful_policy_message
from platform_core.supabase_rest import SupabaseError
from platform_core.image_moderation import ImageModerationService, image_block_message
from platform_core.restricted_categories import ensure_allowed_garment_upload

from .repository import OnboardingRepository
from .schemas import FIXED_OTP, ImageCategory
from .style_archetype import interpret_style_preference, selection_session


REQUIRED_IMAGE_CATEGORIES = frozenset(("full_body", "headshot"))
IMAGE_STORAGE_TYPES = {
    "full_body": "fullshot",
    "headshot": "headshot",
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
        policy_logger: Optional[Callable[..., None]] = None,
        dependency_logger: Optional[Callable[..., None]] = None,
    ) -> None:
        self._repo = repo
        self._image_dir = Path(image_dir)
        self._image_dir.mkdir(parents=True, exist_ok=True)
        self._image_moderation = ImageModerationService()
        self._policy_logger = policy_logger
        self._dependency_logger = dependency_logger

    def set_policy_logger(self, policy_logger: Optional[Callable[..., None]]) -> None:
        self._policy_logger = policy_logger

    def set_dependency_logger(self, dependency_logger: Optional[Callable[..., None]]) -> None:
        self._dependency_logger = dependency_logger

    def send_otp(self, mobile: str) -> tuple[bool, str]:
        return True, f"OTP sent to {mobile}"

    def verify_otp(
        self,
        mobile: str,
        otp: str,
        *,
        acquisition_source: str = "unknown",
        acquisition_campaign: str = "",
        referral_code: str = "",
        icp_tag: str = "",
    ) -> tuple[bool, str, str]:
        if otp != FIXED_OTP:
            return False, "", "Invalid OTP"
        if self._repo is None:
            return False, "", "Service unavailable"
        existing = self._repo.get_profile_by_mobile(mobile)
        verified_at = datetime.now(timezone.utc).isoformat()
        otp_hash = _hash_otp_value(otp)
        if existing:
            if any((acquisition_source and acquisition_source != "unknown", acquisition_campaign, referral_code, icp_tag)):
                self._repo.update_acquisition_context(
                    existing["user_id"],
                    acquisition_source=acquisition_source,
                    acquisition_campaign=acquisition_campaign,
                    referral_code=referral_code,
                    icp_tag=icp_tag,
                )
            self._record_otp_verification_safe(
                existing["user_id"],
                otp_last_used_hash=otp_hash,
                otp_verified_at=verified_at,
            )
            self._emit_dependency_event(
                event_type="otp_verified",
                user_id=existing["user_id"],
                metadata_json={
                    "mobile": mobile,
                    "acquisition_source": acquisition_source or "unknown",
                    "acquisition_campaign": acquisition_campaign,
                    "referral_code": referral_code,
                    "icp_tag": icp_tag,
                    "new_user": False,
                },
            )
            return True, existing["user_id"], "Verified (existing user)"
        user_id = f"user_{uuid4().hex[:12]}"
        self._repo.create_profile(
            user_id=user_id,
            mobile=mobile,
            acquisition_source=acquisition_source or "unknown",
            acquisition_campaign=acquisition_campaign,
            referral_code=referral_code,
            icp_tag=icp_tag,
        )
        self._record_otp_verification_safe(
            user_id,
            otp_last_used_hash=otp_hash,
            otp_verified_at=verified_at,
        )
        self._emit_dependency_event(
            event_type="otp_verified",
            user_id=user_id,
            metadata_json={
                "mobile": mobile,
                "acquisition_source": acquisition_source or "unknown",
                "acquisition_campaign": acquisition_campaign,
                "referral_code": referral_code,
                "icp_tag": icp_tag,
                "new_user": True,
            },
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
        content_type: str = "",
    ) -> Optional[tuple[str, str]]:
        """Returns (encrypted_filename, file_path) or None."""
        if self._repo is None:
            return None
        existing = self._repo.get_profile_by_user_id(user_id)
        if not existing:
            return None
        self.ensure_safe_image_upload(
            user_id=user_id,
            file_data=file_data,
            filename=filename,
            content_type=content_type or "image/jpeg",
            purpose=f"onboarding_{category}",
            input_class=f"onboarding_{category}_image_upload",
        )

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

    def save_wardrobe_item(
        self,
        *,
        user_id: str,
        file_data: bytes,
        filename: str,
        content_type: str,
        source: str = "onboarding",
        title: str = "",
        description: str = "",
        garment_category: str = "",
        garment_subtype: str = "",
        primary_color: str = "",
        secondary_color: str = "",
        pattern_type: str = "",
        formality_level: str = "",
        occasion_fit: str = "",
        brand: str = "",
        notes: str = "",
    ) -> Optional[dict]:
        if self._repo is None:
            return None
        existing = self._repo.get_profile_by_user_id(user_id)
        if not existing:
            return None
        self.ensure_allowed_wardrobe_item(
            user_id=user_id,
            filename=filename,
            title=title,
            description=description,
            garment_category=garment_category,
            garment_subtype=garment_subtype,
            notes=notes,
            brand=brand,
            input_class="wardrobe_item_upload",
        )
        self.ensure_safe_image_upload(
            user_id=user_id,
            file_data=file_data,
            filename=filename,
            content_type=content_type,
            purpose="wardrobe_upload",
            input_class="wardrobe_item_upload",
        )

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
        encrypted_name = hashlib.sha256(f"{user_id}_wardrobe_{timestamp}".encode("utf-8")).hexdigest()
        ext = os.path.splitext(filename)[1] or ".jpg"
        stored_filename = f"{encrypted_name}{ext}"
        wardrobe_dir = self._image_dir / "wardrobe"
        wardrobe_dir.mkdir(parents=True, exist_ok=True)
        dest = wardrobe_dir / stored_filename
        with open(dest, "wb") as f:
            f.write(file_data)

        metadata_json = {
            "original_filename": filename,
            "mime_type": content_type or "image/jpeg",
            "file_size_bytes": len(file_data),
            "encrypted_filename": encrypted_name,
        }
        return self._repo.insert_wardrobe_item(
            user_id=user_id,
            source=source,
            title=title,
            description=description,
            image_path=str(dest),
            garment_category=garment_category,
            garment_subtype=garment_subtype,
            primary_color=primary_color,
            secondary_color=secondary_color,
            pattern_type=pattern_type,
            formality_level=formality_level,
            occasion_fit=occasion_fit,
            brand=brand,
            notes=notes,
            metadata_json=metadata_json,
        )

    def list_wardrobe_items(self, user_id: str) -> dict:
        if self._repo is None:
            return {"user_id": user_id, "count": 0, "items": []}
        items = list(self._repo.list_wardrobe_items(user_id) or [])
        return {
            "user_id": user_id,
            "count": len(items),
            "items": items,
        }

    def normalize_image_for_crop(
        self,
        *,
        file_data: bytes,
        filename: str,
        content_type: str,
    ) -> tuple[bytes, str, str]:
        self.ensure_safe_image_upload(
            user_id="",
            file_data=file_data,
            filename=filename,
            content_type=content_type,
            purpose="image_normalization",
            input_class="image_normalization",
        )
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

    def ensure_safe_image_upload(
        self,
        *,
        user_id: str,
        file_data: bytes,
        filename: str,
        content_type: str,
        purpose: str,
        input_class: str,
    ) -> None:
        result = self._image_moderation.moderate_bytes(
            file_data=file_data,
            filename=filename,
            content_type=content_type,
            purpose=purpose,
        )
        self._emit_policy_event(
            policy_event_type="image_upload_guardrail",
            input_class=input_class,
            reason_code=str(result.reason_code or ("safe_image" if result.allowed else "image_blocked")),
            decision="allowed" if result.allowed else "blocked",
            user_id=user_id,
            metadata_json={
                "purpose": purpose,
                "filename": filename,
                "content_type": content_type,
            },
        )
        if not result.allowed:
            raise ValueError(graceful_policy_message(str(result.reason_code or ""), default=image_block_message(result.reason_code)))

    def ensure_allowed_wardrobe_item(
        self,
        *,
        user_id: str,
        filename: str,
        title: str,
        description: str,
        garment_category: str,
        garment_subtype: str,
        notes: str,
        brand: str,
        input_class: str,
    ) -> None:
        try:
            ensure_allowed_garment_upload(
                filename,
                title,
                description,
                garment_category,
                garment_subtype,
                notes,
                brand,
            )
            self._emit_policy_event(
                policy_event_type="restricted_category_guardrail",
                input_class=input_class,
                reason_code="allowed_category",
                decision="allowed",
                user_id=user_id,
                metadata_json={
                    "filename": filename,
                    "garment_category": garment_category,
                    "garment_subtype": garment_subtype,
                },
            )
        except ValueError:
            self._emit_policy_event(
                policy_event_type="restricted_category_guardrail",
                input_class=input_class,
                reason_code="restricted_category_upload",
                decision="blocked",
                user_id=user_id,
                metadata_json={
                    "filename": filename,
                    "garment_category": garment_category,
                    "garment_subtype": garment_subtype,
                    "brand": brand,
                },
            )
            raise ValueError(graceful_policy_message("restricted_category_upload")) from None

    def _emit_policy_event(
        self,
        *,
        policy_event_type: str,
        input_class: str,
        reason_code: str,
        decision: str,
        user_id: str = "",
        metadata_json: Optional[dict[str, Any]] = None,
    ) -> None:
        if self._policy_logger is None:
            return
        try:
            self._policy_logger(
                policy_event_type=policy_event_type,
                input_class=input_class,
                reason_code=reason_code,
                decision=decision,
                user_id=user_id,
                source_channel="web",
                metadata_json=metadata_json or {},
            )
        except Exception:
            return

    def _emit_dependency_event(
        self,
        *,
        event_type: str,
        user_id: str,
        metadata_json: Optional[dict[str, Any]] = None,
    ) -> None:
        if self._dependency_logger is None:
            return
        try:
            self._dependency_logger(
                event_type=event_type,
                user_id=user_id,
                source_channel="web",
                metadata_json=metadata_json or {},
            )
        except Exception:
            return

    def _check_and_mark_complete(self, user_id: str) -> None:
        if self._repo is None:
            return
        profile = self._repo.get_profile_by_user_id(user_id)
        if not profile or not profile.get("profile_complete"):
            return
        uploaded = set(self._repo.get_image_categories(user_id))
        if REQUIRED_IMAGE_CATEGORIES <= uploaded and profile.get("style_preference_complete"):
            if profile.get("onboarding_complete"):
                return
            self._repo.mark_onboarding_complete(user_id)
            try:
                wardrobe_item_count = int(self._repo.count_wardrobe_items(user_id))
            except Exception:
                wardrobe_item_count = 0
            self._emit_dependency_event(
                event_type="onboarding_completed",
                user_id=user_id,
                metadata_json={
                    "wardrobe_item_count": wardrobe_item_count,
                    "acquisition_source": str(profile.get("acquisition_source") or "unknown"),
                },
            )

    def get_style_archetype_session(self, user_id: str) -> Optional[dict]:
        if self._repo is None:
            return None
        profile = self._repo.get_profile_by_user_id(user_id)
        if not profile:
            return None
        gender = str(profile.get("gender") or "")
        normalized_gender = "female" if gender == "female" else "male"
        session = selection_session(normalized_gender)
        session["user_id"] = user_id
        return session

    def save_style_preference(self, user_id: str, shown_images: list[dict], selections: list[dict]) -> Optional[dict]:
        if self._repo is None:
            return None
        profile = self._repo.get_profile_by_user_id(user_id)
        if not profile:
            return None
        gender = "female" if str(profile.get("gender") or "") == "female" else "male"
        style_preference = interpret_style_preference(gender, shown_images, selections)
        self._repo.insert_style_preference_snapshot(user_id=user_id, style_preference=style_preference)
        self._repo.mark_style_preference_complete(user_id)
        self._check_and_mark_complete(user_id)
        return style_preference

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
                "style_preference_complete": False,
                "onboarding_complete": False,
                "wardrobe_item_count": 0,
            }
        profile = self._repo.get_profile_by_user_id(user_id)
        if not profile:
            return {
                "user_id": user_id,
                "profile_complete": False,
                "images_uploaded": [],
                "style_preference_complete": False,
                "onboarding_complete": False,
                "wardrobe_item_count": 0,
            }
        categories = self._repo.get_image_categories(user_id)
        try:
            wardrobe_item_count = int(self._repo.count_wardrobe_items(user_id))
        except Exception:
            wardrobe_item_count = 0
        return {
            "user_id": profile["user_id"],
            "mobile": profile.get("mobile", ""),
            "acquisition_source": profile.get("acquisition_source", "unknown"),
            "acquisition_campaign": profile.get("acquisition_campaign", ""),
            "referral_code": profile.get("referral_code", ""),
            "icp_tag": profile.get("icp_tag", ""),
            "profile_complete": bool(profile.get("profile_complete")),
            "images_uploaded": categories,
            "style_preference_complete": bool(profile.get("style_preference_complete")),
            "onboarding_complete": bool(profile.get("onboarding_complete")),
            "wardrobe_item_count": wardrobe_item_count,
        }
