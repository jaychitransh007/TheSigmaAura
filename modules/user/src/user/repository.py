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
    "SubSeason": "sub_season",
    "SkinHairContrast": "skin_hair_contrast",
    "ColorDimensionProfile": "color_dimension_profile",
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

    def create_profile(
        self,
        user_id: str,
        mobile: str,
        *,
        acquisition_source: str = "unknown",
        acquisition_campaign: str = "",
        referral_code: str = "",
        icp_tag: str = "",
    ) -> Dict[str, Any]:
        profile = self.client.insert_one("onboarding_profiles", {
            "user_id": user_id,
            "mobile": mobile,
            "acquisition_source": acquisition_source or "unknown",
            "acquisition_campaign": acquisition_campaign or "",
            "referral_code": referral_code or "",
            "icp_tag": icp_tag or "",
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
        })
        self.insert_onboarding_profile_snapshot(user_id, snapshot_reason="created")
        return profile

    def update_acquisition_context(
        self,
        user_id: str,
        *,
        acquisition_source: str = "",
        acquisition_campaign: str = "",
        referral_code: str = "",
        icp_tag: str = "",
    ) -> Optional[Dict[str, Any]]:
        patch: Dict[str, Any] = {"updated_at": _now_iso()}
        if acquisition_source:
            patch["acquisition_source"] = acquisition_source
        if acquisition_campaign:
            patch["acquisition_campaign"] = acquisition_campaign
        if referral_code:
            patch["referral_code"] = referral_code
        if icp_tag:
            patch["icp_tag"] = icp_tag
        result = self.client.update_one(
            "onboarding_profiles",
            filters={"user_id": f"eq.{user_id}"},
            patch=patch,
        )
        self.insert_onboarding_profile_snapshot(user_id, snapshot_reason="acquisition_updated")
        return result

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

    def patch_profile(self, user_id: str, **fields: Any) -> Optional[Dict[str, Any]]:
        """Update only the provided profile fields. Does NOT set profile_complete."""
        if not fields:
            return None
        patch = {k: v for k, v in fields.items() if v is not None}
        if not patch:
            return None
        patch["updated_at"] = _now_iso()
        result = self.client.update_one(
            "onboarding_profiles",
            filters={"user_id": f"eq.{user_id}"},
            patch=patch,
        )
        self.insert_onboarding_profile_snapshot(user_id, snapshot_reason="field_update")
        return result

    def mark_onboarding_complete(self, user_id: str) -> Optional[Dict[str, Any]]:
        result = self.client.update_one(
            "onboarding_profiles",
            filters={"user_id": f"eq.{user_id}"},
            patch={"onboarding_complete": True, "updated_at": _now_iso()},
        )
        self.insert_onboarding_profile_snapshot(user_id, snapshot_reason="onboarding_completed")
        return result

    # May 2026: mark_style_preference_complete deleted. The column it
    # used to update (style_preference_complete) was dropped in the same
    # migration; the only caller now inlines insert_onboarding_profile_snapshot
    # directly with snapshot_reason="state_change". Removed instead of
    # left as a shim so the API surface doesn't drift (PR #47 review).

    def insert_onboarding_profile_snapshot(self, user_id: str, *, snapshot_reason: str) -> Optional[Dict[str, Any]]:
        profile = self.get_profile_by_user_id(user_id)
        if not profile:
            return None
        images = {row.get("category"): row for row in self.get_images(user_id)}
        return self.client.insert_one("onboarding_profile_snapshots", {
            "user_id": user_id,
            "mobile": profile.get("mobile") or "",
            "acquisition_source": profile.get("acquisition_source") or "unknown",
            "acquisition_campaign": profile.get("acquisition_campaign") or "",
            "referral_code": profile.get("referral_code") or "",
            "icp_tag": profile.get("icp_tag") or "",
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

    # -- user_wardrobe_items -------------------------------------------------

    def list_wardrobe_items(self, user_id: str, *, active_only: bool = True) -> List[Dict[str, Any]]:
        filters: Dict[str, str] = {"user_id": f"eq.{user_id}"}
        if active_only:
            filters["is_active"] = "eq.true"
        return self.client.select_many(
            "user_wardrobe_items",
            filters=filters,
            order="created_at.desc",
        )

    def count_wardrobe_items(self, user_id: str, *, active_only: bool = True) -> int:
        return len(self.list_wardrobe_items(user_id, active_only=active_only))

    def insert_wardrobe_item(
        self,
        *,
        user_id: str,
        source: str,
        title: str = "",
        description: str = "",
        image_url: str = "",
        image_path: str = "",
        garment_category: str = "",
        garment_subtype: str = "",
        primary_color: str = "",
        secondary_color: str = "",
        pattern_type: str = "",
        formality_level: str = "",
        occasion_fit: str = "",
        brand: str = "",
        notes: str = "",
        metadata_json: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return self.client.insert_one("user_wardrobe_items", {
            "user_id": user_id,
            "source": source,
            "title": title,
            "description": description,
            "image_url": image_url,
            "image_path": image_path,
            "garment_category": garment_category,
            "garment_subtype": garment_subtype,
            "primary_color": primary_color,
            "secondary_color": secondary_color,
            "pattern_type": pattern_type,
            "formality_level": formality_level,
            "occasion_fit": occasion_fit,
            "brand": brand,
            "notes": notes,
            "metadata_json": metadata_json or {},
            "is_active": True,
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
        })

    def update_wardrobe_item(self, wardrobe_item_id: str, **patch: Any) -> Optional[Dict[str, Any]]:
        next_patch = dict(patch)
        next_patch["updated_at"] = _now_iso()
        return self.client.update_one(
            "user_wardrobe_items",
            filters={"id": f"eq.{wardrobe_item_id}"},
            patch=next_patch,
        )

    def deactivate_wardrobe_item(self, wardrobe_item_id: str) -> Optional[Dict[str, Any]]:
        return self.update_wardrobe_item(wardrobe_item_id, is_active=False)

    # -- user_style_preference_snapshots -------------------------------------

    def insert_style_preference_snapshot(self, *, user_id: str, style_preference: Dict[str, Any]) -> Dict[str, Any]:
        # May 2026: archetype/secondary/blend/formality/pattern/comfort/
        # archetype_scores/selected_image_ids/selected_images/selection_count
        # all dropped from the table. Only risk_tolerance and gender remain.
        # Coerce risk_tolerance to the new 3-value scale at write time so
        # legacy callers that still pass 5-value strings degrade gracefully.
        raw_risk = str(style_preference.get("riskTolerance") or "").strip().lower()
        risk_tolerance = {
            "conservative": "conservative",
            "moderate-conservative": "conservative",
            "moderate": "balanced",
            "balanced": "balanced",
            "moderate-adventurous": "expressive",
            "adventurous": "expressive",
            "expressive": "expressive",
            "": "balanced",
        }.get(raw_risk, raw_risk)
        return self.client.insert_one("user_style_preference_snapshots", {
            "user_id": user_id,
            "gender": style_preference.get("gender") or "male",
            "risk_tolerance": risk_tolerance,
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

    def insert_draping_overlay(
        self,
        *,
        user_id: str,
        analysis_snapshot_id: str,
        round_number: int,
        round_question: str,
        image_a_path: str,
        image_b_path: str,
        color_a: str,
        color_b: str,
        label_a: str,
        label_b: str,
        choice: str,
        confidence: float,
        reasoning: str,
        winner_label: str,
    ) -> Dict[str, Any]:
        return self.client.insert_one("draping_overlay_images", {
            "user_id": user_id,
            "analysis_snapshot_id": analysis_snapshot_id,
            "round_number": round_number,
            "round_question": round_question,
            "image_a_path": image_a_path,
            "image_b_path": image_b_path,
            "color_a": color_a,
            "color_b": color_b,
            "label_a": label_a,
            "label_b": label_b,
            "choice": choice,
            "confidence": confidence,
            "reasoning": reasoning,
            "winner_label": winner_label,
            "created_at": _now_iso(),
        })

    def get_draping_overlays(self, user_id: str) -> List[Dict[str, Any]]:
        return self.client.select_many(
            "draping_overlay_images",
            filters={"user_id": f"eq.{user_id}"},
            order="created_at.desc,round_number.asc",
            limit=6,
        ) or []

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
