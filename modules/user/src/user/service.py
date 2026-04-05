import hashlib
import io
import logging
import mimetypes
import os
import subprocess
import tempfile
import base64
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
from .wardrobe_enrichment import infer_wardrobe_catalog_attributes


_log = logging.getLogger(__name__)

_HEIC_EXTENSIONS = frozenset((".heic", ".heif"))


def _convert_heic_to_jpeg(file_data: bytes, filename: str) -> tuple[bytes, str, str]:
    """Convert HEIC/HEIF images to JPEG. Returns (data, content_type, filename)."""
    ext = os.path.splitext(filename)[1].lower()
    if ext not in _HEIC_EXTENSIONS:
        return file_data, "", filename
    try:
        from PIL import Image
        from pillow_heif import register_heif_opener
        register_heif_opener()
        img = Image.open(io.BytesIO(file_data))
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=90)
        new_name = os.path.splitext(filename)[0] + ".jpg"
        _log.info("Converted %s from HEIC to JPEG (%d → %d bytes)", filename, len(file_data), buf.tell())
        return buf.getvalue(), "image/jpeg", new_name
    except Exception:
        _log.warning("HEIC conversion failed for %s, keeping original", filename, exc_info=True)
        return file_data, "", filename


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

    @staticmethod
    def _decode_data_url_image(image_data: str) -> tuple[bytes, str, str]:
        raw = str(image_data or "").strip()
        if not raw.startswith("data:") or ";base64," not in raw:
            raise ValueError("Attached image must be a valid base64 data URL.")
        header, encoded = raw.split(",", 1)
        mime_type = header.split(";")[0].split(":", 1)[1] if ":" in header else "image/jpeg"
        extension = mimetypes.guess_extension(mime_type) or ".jpg"
        try:
            data = base64.b64decode(encoded)
        except Exception as exc:
            raise ValueError("Attached image data could not be decoded.") from exc
        return data, mime_type, f"chat_upload{extension}"

    @staticmethod
    def _clean_attr(value: Any) -> str:
        text = str(value or "").strip()
        if text.lower() in {"", "null", "none", "unknown", "unspecified", "n_a", "n/a"}:
            return ""
        return text

    def _project_catalog_attributes(
        self,
        *,
        extracted: dict[str, Any],
        title: str,
        description: str,
        garment_category: str,
        garment_subtype: str,
        primary_color: str,
        secondary_color: str,
        pattern_type: str,
        formality_level: str,
        occasion_fit: str,
    ) -> dict[str, str]:
        attrs = dict((extracted or {}).get("attributes") or {})
        resolved_category = self._clean_attr(attrs.get("GarmentCategory")) or garment_category
        resolved_subtype = self._clean_attr(attrs.get("GarmentSubtype")) or garment_subtype or resolved_category
        resolved_primary_color = self._clean_attr(attrs.get("PrimaryColor")) or primary_color
        resolved_secondary_color = self._clean_attr(attrs.get("SecondaryColor")) or secondary_color
        resolved_pattern = self._clean_attr(attrs.get("PatternType")) or pattern_type
        resolved_formality = (
            self._clean_attr(attrs.get("FormalityLevel"))
            or self._clean_attr(attrs.get("FormalitySignalStrength"))
            or formality_level
        )
        resolved_occasion = self._clean_attr(attrs.get("OccasionFit")) or occasion_fit
        resolved_title = str(title or "").strip()
        if not resolved_title:
            resolved_title = " ".join(
                part
                for part in (resolved_primary_color.replace("_", " ").title() if resolved_primary_color else "", resolved_subtype.replace("_", " ").title() if resolved_subtype else "")
                if part
            ).strip()
        resolved_description = str(description or "").strip()
        if not resolved_description:
            desc_parts = [
                self._clean_attr(attrs.get("GarmentLength")).replace("_", " "),
                self._clean_attr(attrs.get("SilhouetteType")).replace("_", " "),
                self._clean_attr(attrs.get("FitType")).replace("_", " "),
            ]
            resolved_description = " ".join(part for part in desc_parts if part).strip()
        return {
            "title": resolved_title or "Wardrobe Item",
            "description": resolved_description,
            "garment_category": resolved_category,
            "garment_subtype": resolved_subtype,
            "primary_color": resolved_primary_color,
            "secondary_color": resolved_secondary_color,
            "pattern_type": resolved_pattern,
            "formality_level": resolved_formality,
            "occasion_fit": resolved_occasion,
        }

    @staticmethod
    def _wardrobe_role_of(item: dict[str, Any]) -> str:
        category = OnboardingService._clean_attr(item.get("garment_category") or item.get("garment_subtype")).lower()
        if category in {"dress", "jumpsuit", "co-ord", "coord", "suit"}:
            return "one_piece"
        if category in {"top", "shirt", "tshirt", "t-shirt", "tee", "blouse", "knitwear", "sweater"}:
            return "top"
        if category in {"blazer", "jacket", "coat", "cardigan", "outerwear", "overshirt"}:
            return "outerwear"
        if category in {"bottom", "trouser", "trousers", "pants", "jeans", "skirt", "shorts"}:
            return "bottom"
        if category in {"shoe", "shoes", "sneaker", "sneakers", "loafer", "loafers", "heel", "heels", "boot", "boots", "sandal", "sandals"}:
            return "shoe"
        return "other"

    @staticmethod
    def _occasion_keys_of(item: dict[str, Any]) -> set[str]:
        normalized = OnboardingService._clean_attr(item.get("occasion_fit")).lower().replace("-", " ").replace("_", " ")
        tokens = {token for token in normalized.split() if token}
        coverage: set[str] = set()
        if {"office", "work", "formal", "business"} & tokens:
            coverage.add("office")
        if {"casual", "weekend", "day", "everyday"} & tokens:
            coverage.add("casual")
        if {"evening", "party", "dinner", "date"} & tokens:
            coverage.add("evening")
        if {"travel", "trip", "vacation", "holiday"} & tokens:
            coverage.add("travel")
        return coverage

    def _get_wardrobe_item_by_id(self, *, user_id: str, wardrobe_item_id: str) -> Optional[dict]:
        if self._repo is None:
            return None
        items = list(self._repo.list_wardrobe_items(user_id, active_only=False) or [])
        for item in items:
            if str(item.get("id") or "") == str(wardrobe_item_id):
                return dict(item)
        return None

    def save_chat_wardrobe_image(
        self,
        *,
        user_id: str,
        image_data: str,
        title: str = "",
        description: str = "",
        notes: str = "",
    ) -> Optional[dict]:
        file_data, content_type, filename = self._decode_data_url_image(image_data)
        return self.save_wardrobe_item(
            user_id=user_id,
            file_data=file_data,
            filename=filename,
            content_type=content_type,
            source="chat",
            title=title,
            description=description,
            notes=notes,
        )

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

        converted_data, converted_ct, converted_name = _convert_heic_to_jpeg(file_data, filename)
        if converted_ct:
            file_data = converted_data
            content_type = converted_ct
            filename = converted_name

        ext = os.path.splitext(filename)[1] or ".jpg"
        stored_filename = f"{encrypted_name}{ext}"
        dest = self._image_dir / stored_filename
        with open(dest, "wb") as f:
            f.write(file_data)

        mime_type = content_type or "image/jpeg"
        if not content_type:
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

        converted_data, converted_ct, converted_name = _convert_heic_to_jpeg(file_data, filename)
        if converted_ct:
            file_data = converted_data
            content_type = converted_ct
            filename = converted_name

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
        projected = {
            "title": title,
            "description": description,
            "garment_category": garment_category,
            "garment_subtype": garment_subtype,
            "primary_color": primary_color,
            "secondary_color": secondary_color,
            "pattern_type": pattern_type,
            "formality_level": formality_level,
            "occasion_fit": occasion_fit,
        }
        try:
            extracted = infer_wardrobe_catalog_attributes(
                image_ref=str(dest),
                title=title,
                description=description,
                garment_category=garment_category,
                garment_subtype=garment_subtype,
                primary_color=primary_color,
                secondary_color=secondary_color,
                pattern_type=pattern_type,
                formality_level=formality_level,
                occasion_fit=occasion_fit,
                brand=brand,
                notes=notes,
            )
            metadata_json["catalog_attribute_extraction_status"] = "ok"
            metadata_json["catalog_attributes"] = dict(extracted.get("attributes") or {})
            metadata_json["catalog_attribute_model"] = str(extracted.get("model") or "")
            metadata_json["catalog_attribute_extracted_at"] = datetime.now(timezone.utc).isoformat()
            metadata_json["user_supplied_fields"] = dict(projected)
            projected = self._project_catalog_attributes(
                extracted=extracted,
                title=title,
                description=description,
                garment_category=garment_category,
                garment_subtype=garment_subtype,
                primary_color=primary_color,
                secondary_color=secondary_color,
                pattern_type=pattern_type,
                formality_level=formality_level,
                occasion_fit=occasion_fit,
            )
        except Exception as exc:
            _log.warning("Wardrobe enrichment failed for %s: %s", user_id, exc)
            metadata_json["catalog_attribute_extraction_status"] = "error"
            metadata_json["catalog_attribute_error"] = str(exc)
        return self._repo.insert_wardrobe_item(
            user_id=user_id,
            source=source,
            title=projected["title"],
            description=projected["description"],
            image_path=str(dest),
            garment_category=projected["garment_category"],
            garment_subtype=projected["garment_subtype"],
            primary_color=projected["primary_color"],
            secondary_color=projected["secondary_color"],
            pattern_type=projected["pattern_type"],
            formality_level=projected["formality_level"],
            occasion_fit=projected["occasion_fit"],
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

    def update_wardrobe_item(
        self,
        *,
        user_id: str,
        wardrobe_item_id: str,
        title: Optional[str] = None,
        description: Optional[str] = None,
        garment_category: Optional[str] = None,
        garment_subtype: Optional[str] = None,
        primary_color: Optional[str] = None,
        secondary_color: Optional[str] = None,
        pattern_type: Optional[str] = None,
        formality_level: Optional[str] = None,
        occasion_fit: Optional[str] = None,
        brand: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> Optional[dict]:
        if self._repo is None:
            return None
        existing = self._get_wardrobe_item_by_id(user_id=user_id, wardrobe_item_id=wardrobe_item_id)
        if not existing:
            return None

        merged = {
            "title": existing.get("title") if title is None else title,
            "description": existing.get("description") if description is None else description,
            "garment_category": existing.get("garment_category") if garment_category is None else garment_category,
            "garment_subtype": existing.get("garment_subtype") if garment_subtype is None else garment_subtype,
            "primary_color": existing.get("primary_color") if primary_color is None else primary_color,
            "secondary_color": existing.get("secondary_color") if secondary_color is None else secondary_color,
            "pattern_type": existing.get("pattern_type") if pattern_type is None else pattern_type,
            "formality_level": existing.get("formality_level") if formality_level is None else formality_level,
            "occasion_fit": existing.get("occasion_fit") if occasion_fit is None else occasion_fit,
            "brand": existing.get("brand") if brand is None else brand,
            "notes": existing.get("notes") if notes is None else notes,
        }
        self.ensure_allowed_wardrobe_item(
            user_id=user_id,
            filename=str(existing.get("image_url") or existing.get("image_path") or existing.get("title") or "wardrobe_item"),
            title=str(merged["title"] or ""),
            description=str(merged["description"] or ""),
            garment_category=str(merged["garment_category"] or ""),
            garment_subtype=str(merged["garment_subtype"] or ""),
            notes=str(merged["notes"] or ""),
            brand=str(merged["brand"] or ""),
            input_class="wardrobe_item_update",
        )
        return self._repo.update_wardrobe_item(
            wardrobe_item_id,
            title=str(merged["title"] or ""),
            description=str(merged["description"] or ""),
            garment_category=str(merged["garment_category"] or ""),
            garment_subtype=str(merged["garment_subtype"] or ""),
            primary_color=str(merged["primary_color"] or ""),
            secondary_color=str(merged["secondary_color"] or ""),
            pattern_type=str(merged["pattern_type"] or ""),
            formality_level=str(merged["formality_level"] or ""),
            occasion_fit=str(merged["occasion_fit"] or ""),
            brand=str(merged["brand"] or ""),
            notes=str(merged["notes"] or ""),
        )

    def delete_wardrobe_item(self, *, user_id: str, wardrobe_item_id: str) -> bool:
        if self._repo is None:
            return False
        existing = self._get_wardrobe_item_by_id(user_id=user_id, wardrobe_item_id=wardrobe_item_id)
        if not existing:
            return False
        self._repo.deactivate_wardrobe_item(wardrobe_item_id)
        return True

    def get_wardrobe_summary(self, user_id: str) -> dict:
        if self._repo is None:
            return {
                "user_id": user_id,
                "count": 0,
                "completeness_score_pct": 0,
                "summary": "",
                "category_counts": {},
                "occasion_coverage": [],
                "missing_categories": [],
                "gap_items": [],
            }

        items = list(self._repo.list_wardrobe_items(user_id) or [])
        role_counts = {
            "top": 0,
            "bottom": 0,
            "shoe": 0,
            "outerwear": 0,
            "one_piece": 0,
        }
        occasion_counts = {"office": 0, "casual": 0, "evening": 0, "travel": 0}
        for item in items:
            role = self._wardrobe_role_of(item)
            if role in role_counts:
                role_counts[role] += 1
            for key in self._occasion_keys_of(item):
                occasion_counts[key] += 1

        weighted_score = (
            min(role_counts["top"], 3) * 18
            + min(role_counts["bottom"], 2) * 18
            + min(role_counts["shoe"], 2) * 12
            + min(role_counts["outerwear"], 2) * 10
            + min(role_counts["one_piece"], 1) * 8
            + sum(8 for count in occasion_counts.values() if count > 0)
        )
        completeness_score_pct = min(int(weighted_score), 100)

        role_labels = {
            "top": "tops",
            "bottom": "bottoms",
            "shoe": "shoe options",
            "outerwear": "layers",
            "one_piece": "one-piece looks",
        }
        missing_categories = [label for key, label in role_labels.items() if role_counts[key] == 0]

        gap_items: list[str] = []
        if role_counts["bottom"] == 0:
            gap_items.append("a versatile trouser or skirt")
        if role_counts["shoe"] == 0:
            gap_items.append("a reliable everyday shoe")
        if role_counts["outerwear"] == 0:
            gap_items.append("a layering piece like a blazer or jacket")
        if role_counts["top"] < 2:
            gap_items.append("one more easy top to improve outfit rotation")
        if not any(occasion_counts.values()):
            gap_items.append("clear occasion tags so Aura can plan outfits more accurately")

        covered_occasions = [key for key, count in occasion_counts.items() if count > 0]
        if covered_occasions:
            summary = (
                f"Your wardrobe is {completeness_score_pct}% ready right now, with the strongest coverage in "
                + ", ".join(covered_occasions[:3])
                + "."
            )
        else:
            summary = f"Your wardrobe is {completeness_score_pct}% ready right now. Add a few tagged staples to unlock better planning."

        return {
            "user_id": user_id,
            "count": len(items),
            "completeness_score_pct": completeness_score_pct,
            "summary": summary,
            "category_counts": role_counts,
            "occasion_coverage": [
                {
                    "key": key,
                    "label": key.replace("_", " ").title(),
                    "item_count": count,
                    "covered": count > 0,
                }
                for key, count in occasion_counts.items()
            ],
            "missing_categories": missing_categories,
            "gap_items": gap_items[:4],
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
        image_rows = self._repo.get_images(user_id)
        categories = [r["category"] for r in image_rows]
        image_paths = {str(r["category"]): str(r.get("file_path") or "") for r in image_rows}
        try:
            wardrobe_item_count = int(self._repo.count_wardrobe_items(user_id))
        except Exception:
            wardrobe_item_count = 0
        return {
            "user_id": profile["user_id"],
            "mobile": profile.get("mobile", ""),
            "name": profile.get("name") or "",
            "date_of_birth": profile.get("date_of_birth") or "",
            "gender": profile.get("gender") or "",
            "height_cm": profile.get("height_cm") or "",
            "waist_cm": profile.get("waist_cm") or "",
            "profession": profile.get("profession") or "",
            "acquisition_source": profile.get("acquisition_source", "unknown"),
            "acquisition_campaign": profile.get("acquisition_campaign", ""),
            "referral_code": profile.get("referral_code", ""),
            "icp_tag": profile.get("icp_tag", ""),
            "profile_complete": bool(profile.get("profile_complete")),
            "images_uploaded": categories,
            "image_paths": image_paths,
            "style_preference_complete": bool(profile.get("style_preference_complete")),
            "onboarding_complete": bool(profile.get("onboarding_complete")),
            "wardrobe_item_count": wardrobe_item_count,
        }
