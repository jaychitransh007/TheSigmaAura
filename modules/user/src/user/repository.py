from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from platform_core.supabase_rest import SupabaseRestClient


ANALYSIS_ATTRIBUTE_COLUMN_PREFIXES = {
    "ShoulderToHipRatio": "shoulder_to_hip_ratio",
    "TorsoToLegRatio": "torso_to_leg_ratio",
    "BodyShape": "body_shape",
    "VisualWeight": "visual_weight",
    "VerticalProportion": "vertical_proportion",
    "ArmVolume": "arm_volume",
    "MidsectionState": "midsection_state",
    "BustVolume": "bust_volume",
    "SkinSurfaceColor": "skin_surface_color",
    "HairColor": "hair_color",
    "HairColorTemperature": "hair_color_temperature",
    "EyeColor": "eye_color",
    "EyeClarity": "eye_clarity",
    "FaceShape": "face_shape",
    "NeckLength": "neck_length",
    "HairLength": "hair_length",
    "JawlineDefinition": "jawline_definition",
    "ShoulderSlope": "shoulder_slope",
}

INTERPRETATION_COLUMN_PREFIXES = {
    "HeightCategory": "height_category",
    "SeasonalColorGroup": "seasonal_color_group",
    "ContrastLevel": "contrast_level",
    "FrameStructure": "frame_structure",
    "WaistSizeBand": "waist_size_band",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class OnboardingRepository:
    def __init__(self, client: SupabaseRestClient) -> None:
        self.client = client

    # -- onboarding_profiles --------------------------------------------------

    def get_profile_by_mobile(self, mobile: str) -> Optional[Dict[str, Any]]:
        return self.client.select_one(
            "onboarding_profiles",
            filters={"mobile": f"eq.{mobile}"},
        )

    def get_profile_by_user_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        return self.client.select_one(
            "onboarding_profiles",
            filters={"user_id": f"eq.{user_id}"},
        )

    def create_profile(self, user_id: str, mobile: str) -> Dict[str, Any]:
        profile = self.client.insert_one("onboarding_profiles", {
            "user_id": user_id,
            "mobile": mobile,
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
        })
        self.insert_onboarding_profile_snapshot(user_id, snapshot_reason="created")
        return profile

    def record_otp_verification(
        self,
        user_id: str,
        *,
        otp_last_used_hash: str,
        otp_verified_at: str,
    ) -> Optional[Dict[str, Any]]:
        result = self.client.update_one(
            "onboarding_profiles",
            filters={"user_id": f"eq.{user_id}"},
            patch={
                "otp_last_used_hash": otp_last_used_hash,
                "otp_verified_at": otp_verified_at,
                "updated_at": _now_iso(),
            },
        )
        self.insert_onboarding_profile_snapshot(user_id, snapshot_reason="otp_verified")
        return result

    def update_profile(
        self,
        user_id: str,
        *,
        name: str,
        date_of_birth: str,
        gender: str,
        height_cm: float,
        waist_cm: float,
        profession: str,
    ) -> Optional[Dict[str, Any]]:
        result = self.client.update_one(
            "onboarding_profiles",
            filters={"user_id": f"eq.{user_id}"},
            patch={
                "name": name,
                "date_of_birth": date_of_birth,
                "gender": gender,
                "height_cm": height_cm,
                "waist_cm": waist_cm,
                "profession": profession,
                "profile_complete": True,
                "updated_at": _now_iso(),
            },
        )
        self.insert_onboarding_profile_snapshot(user_id, snapshot_reason="profile_saved")
        return result

    def mark_onboarding_complete(self, user_id: str) -> Optional[Dict[str, Any]]:
        result = self.client.update_one(
            "onboarding_profiles",
            filters={"user_id": f"eq.{user_id}"},
            patch={"onboarding_complete": True, "updated_at": _now_iso()},
        )
        self.insert_onboarding_profile_snapshot(user_id, snapshot_reason="onboarding_completed")
        return result

    def mark_style_preference_complete(self, user_id: str) -> Optional[Dict[str, Any]]:
        result = self.client.update_one(
            "onboarding_profiles",
            filters={"user_id": f"eq.{user_id}"},
            patch={"style_preference_complete": True, "updated_at": _now_iso()},
        )
        self.insert_onboarding_profile_snapshot(user_id, snapshot_reason="state_change")
        return result

    def insert_onboarding_profile_snapshot(self, user_id: str, *, snapshot_reason: str) -> Optional[Dict[str, Any]]:
        profile = self.get_profile_by_user_id(user_id)
        if not profile:
            return None
        images = {row.get("category"): row for row in self.get_images(user_id)}
        return self.client.insert_one("onboarding_profile_snapshots", {
            "user_id": user_id,
            "mobile": profile.get("mobile") or "",
            "otp_last_used_hash": profile.get("otp_last_used_hash") or "",
            "otp_verified_at": profile.get("otp_verified_at"),
            "name": profile.get("name") or "",
            "date_of_birth": profile.get("date_of_birth"),
            "gender": profile.get("gender"),
            "height_cm": profile.get("height_cm"),
            "waist_cm": profile.get("waist_cm"),
            "profession": profile.get("profession"),
            "profile_complete": bool(profile.get("profile_complete")),
            "onboarding_complete": bool(profile.get("onboarding_complete")),
            "style_preference_complete": bool(profile.get("style_preference_complete")),
            "has_full_body_image": "full_body" in images,
            "has_headshot_image": "headshot" in images,
            "full_body_encrypted_filename": (images.get("full_body") or {}).get("encrypted_filename") or "",
            "headshot_encrypted_filename": (images.get("headshot") or {}).get("encrypted_filename") or "",
            "snapshot_reason": snapshot_reason,
            "created_at": _now_iso(),
        })

    def get_latest_onboarding_profile_snapshot(self, user_id: str) -> Optional[Dict[str, Any]]:
        rows = self.client.select_many(
            "onboarding_profile_snapshots",
            filters={"user_id": f"eq.{user_id}"},
            order="created_at.desc",
            limit=1,
        )
        return rows[0] if rows else None

    # -- onboarding_images ----------------------------------------------------

    def upsert_image(
        self,
        user_id: str,
        category: str,
        encrypted_filename: str,
        original_filename: str,
        file_path: str,
        mime_type: str,
        file_size_bytes: int,
    ) -> Dict[str, Any]:
        existing = self.client.select_one(
            "onboarding_images",
            filters={
                "user_id": f"eq.{user_id}",
                "category": f"eq.{category}",
            },
        )
        if existing:
            result = self.client.update_one(
                "onboarding_images",
                filters={"id": f"eq.{existing['id']}"},
                patch={
                    "encrypted_filename": encrypted_filename,
                    "original_filename": original_filename,
                    "file_path": file_path,
                    "mime_type": mime_type,
                    "file_size_bytes": file_size_bytes,
                    "created_at": _now_iso(),
                },
            )
            self.insert_onboarding_profile_snapshot(user_id, snapshot_reason="image_uploaded")
            return result or existing
        row = self.client.insert_one("onboarding_images", {
            "user_id": user_id,
            "category": category,
            "encrypted_filename": encrypted_filename,
            "original_filename": original_filename,
            "file_path": file_path,
            "mime_type": mime_type,
            "file_size_bytes": file_size_bytes,
            "created_at": _now_iso(),
        })
        self.insert_onboarding_profile_snapshot(user_id, snapshot_reason="image_uploaded")
        return row

    def get_images(self, user_id: str) -> List[Dict[str, Any]]:
        return self.client.select_many(
            "onboarding_images",
            filters={"user_id": f"eq.{user_id}"},
        )

    def get_image_categories(self, user_id: str) -> List[str]:
        rows = self.get_images(user_id)
        return [r["category"] for r in rows]

    # -- user_style_preference_snapshots -------------------------------------

    def insert_style_preference_snapshot(self, *, user_id: str, style_preference: Dict[str, Any]) -> Dict[str, Any]:
        blend = style_preference.get("blendRatio") or {}
        return self.client.insert_one("user_style_preference_snapshots", {
            "user_id": user_id,
            "gender": style_preference.get("gender") or "male",
            "primary_archetype": style_preference.get("primaryArchetype") or "",
            "secondary_archetype": style_preference.get("secondaryArchetype"),
            "blend_ratio_primary": int(blend.get("primary") or 100),
            "blend_ratio_secondary": int(blend.get("secondary") or 0),
            "risk_tolerance": style_preference.get("riskTolerance") or "",
            "formality_lean": style_preference.get("formalityLean") or "",
            "pattern_type": style_preference.get("patternType") or "",
            "comfort_boundaries_json": style_preference.get("comfortBoundaries") or [],
            "archetype_scores_json": style_preference.get("archetypeScores") or {},
            "selected_image_ids_json": style_preference.get("selectedImageIds") or [],
            "selected_images_json": style_preference.get("selectedImages") or {},
            "selection_count": int(style_preference.get("selectionCount") or 0),
            "completed_at": style_preference.get("completedAt") or _now_iso(),
            "created_at": _now_iso(),
        })

    def get_latest_style_preference_snapshot(self, user_id: str) -> Optional[Dict[str, Any]]:
        rows = self.client.select_many(
            "user_style_preference_snapshots",
            filters={"user_id": f"eq.{user_id}"},
            order="created_at.desc",
            limit=1,
        )
        return rows[0] if rows else None

    # -- user_analysis_snapshots ---------------------------------------------

    def create_analysis_snapshot(
        self,
        *,
        user_id: str,
        model_name: str,
        status: str,
        error_message: str = "",
    ) -> Dict[str, Any]:
        return self.client.insert_one("user_analysis_snapshots", {
            "user_id": user_id,
            "model_name": model_name,
            "status": status,
            "error_message": error_message,
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
        })

    def update_analysis_snapshot(
        self,
        snapshot_id: str,
        **patch: Any,
    ) -> Optional[Dict[str, Any]]:
        next_patch = dict(patch)
        next_patch["updated_at"] = _now_iso()
        collated_output = next_patch.get("collated_output")
        if collated_output is not None:
            attributes = collated_output.get("attributes") or {}
            for attribute_name, prefix in ANALYSIS_ATTRIBUTE_COLUMN_PREFIXES.items():
                attribute = attributes.get(attribute_name) or {}
                next_patch[f"{prefix}_value"] = attribute.get("value") or ""
                next_patch[f"{prefix}_confidence"] = float(attribute.get("confidence") or 0.0)
                next_patch[f"{prefix}_evidence_note"] = attribute.get("evidence_note") or ""
        return self.client.update_one(
            "user_analysis_snapshots",
            filters={"id": f"eq.{snapshot_id}"},
            patch=next_patch,
        )

    def get_latest_analysis_snapshot(self, user_id: str) -> Optional[Dict[str, Any]]:
        rows = self.client.select_many(
            "user_analysis_snapshots",
            filters={"user_id": f"eq.{user_id}"},
            order="created_at.desc",
            limit=1,
        )
        return rows[0] if rows else None

    def get_previous_analysis_snapshot(self, user_id: str, exclude_id: str) -> Optional[Dict[str, Any]]:
        rows = self.client.select_many(
            "user_analysis_snapshots",
            filters={"user_id": f"eq.{user_id}"},
            order="created_at.desc",
            limit=5,
        )
        for row in rows:
            if str(row.get("id") or "") != exclude_id:
                return row
        return None

    # -- user_interpretation_snapshots ---------------------------------------

    def insert_interpretation_snapshot(
        self,
        *,
        user_id: str,
        analysis_snapshot_id: str,
        interpretations: Dict[str, Any],
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "analysis_snapshot_id": analysis_snapshot_id,
            "user_id": user_id,
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
        }
        for interpretation_name, prefix in INTERPRETATION_COLUMN_PREFIXES.items():
            interpretation = interpretations.get(interpretation_name) or {}
            payload[f"{prefix}_value"] = interpretation.get("value") or ""
            payload[f"{prefix}_confidence"] = float(interpretation.get("confidence") or 0.0)
            payload[f"{prefix}_evidence_note"] = interpretation.get("evidence_note") or ""
        return self.client.insert_one("user_interpretation_snapshots", payload)

    def get_latest_interpretation_snapshot(self, user_id: str) -> Optional[Dict[str, Any]]:
        rows = self.client.select_many(
            "user_interpretation_snapshots",
            filters={"user_id": f"eq.{user_id}"},
            order="created_at.desc",
            limit=1,
        )
        return rows[0] if rows else None

    def get_interpretation_snapshot_for_analysis(self, analysis_snapshot_id: str) -> Optional[Dict[str, Any]]:
        return self.client.select_one(
            "user_interpretation_snapshots",
            filters={"analysis_snapshot_id": f"eq.{analysis_snapshot_id}"},
        )

    # -- user_effective_seasonal_groups ----------------------------------------

    def insert_effective_seasonal_groups(
        self,
        *,
        user_id: str,
        seasonal_groups: List[Dict[str, Any]],
        source: str,
    ) -> Dict[str, Any]:
        return self.client.insert_one("user_effective_seasonal_groups", {
            "user_id": user_id,
            "seasonal_groups": seasonal_groups,
            "source": source,
            "created_at": _now_iso(),
        })

    def get_effective_seasonal_groups(self, user_id: str) -> Optional[Dict[str, Any]]:
        rows = self.client.select_many(
            "user_effective_seasonal_groups",
            filters={"user_id": f"eq.{user_id}", "superseded_at": "is.null"},
            order="created_at.desc",
            limit=1,
        )
        return rows[0] if rows else None

    def supersede_effective_seasonal_groups(self, row_id: str) -> Optional[Dict[str, Any]]:
        return self.client.update_one(
            "user_effective_seasonal_groups",
            filters={"id": f"eq.{row_id}"},
            patch={"superseded_at": _now_iso()},
        )
