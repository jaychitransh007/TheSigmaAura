from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any, Dict, List, Optional

from fastapi import APIRouter

from user.analysis import UserAnalysisService
from user.api import create_onboarding_router
from user.repository import OnboardingRepository
from user.service import OnboardingService
from user.ui import get_onboarding_html, get_processing_html, get_wardrobe_manager_html

from platform_core.supabase_rest import SupabaseRestClient


class ApplicationUserGateway:
    """App-facing wrapper around user module dependencies."""

    def __init__(self, client: SupabaseRestClient) -> None:
        self._repo = OnboardingRepository(client)
        self._service = OnboardingService(repo=self._repo)
        self._analysis = UserAnalysisService(repo=self._repo)

    def set_policy_logger(self, policy_logger: Optional[Callable[..., None]]) -> None:
        self._service.set_policy_logger(policy_logger)

    def set_dependency_logger(self, dependency_logger: Optional[Callable[..., None]]) -> None:
        self._service.set_dependency_logger(dependency_logger)

    def get_analysis_status(self, user_id: str) -> dict:
        return dict(self._analysis.get_analysis_status(user_id) or {})

    def get_onboarding_status(self, user_id: str) -> dict:
        return dict(self._service.get_status(user_id) or {})

    def get_effective_seasonal_groups(self, user_id: str) -> list:
        row = self._repo.get_effective_seasonal_groups(user_id)
        if row:
            return list(row.get("seasonal_groups") or [])
        return []

    def resolve_user_id_by_mobile(self, mobile: str) -> Optional[str]:
        candidates = [str(mobile or "").strip()]
        normalized_digits = "".join(ch for ch in candidates[0] if ch.isdigit())
        if normalized_digits:
            candidates.append(normalized_digits)
            candidates.append(f"+{normalized_digits}")
        seen = set()
        for candidate in candidates:
            value = str(candidate or "").strip()
            if not value or value in seen:
                continue
            seen.add(value)
            row = self._repo.get_profile_by_mobile(value)
            if row and str(row.get("user_id") or "").strip():
                return str(row.get("user_id") or "").strip()
        return None

    def get_person_image_path(self, user_id: str) -> Optional[str]:
        images = self._repo.get_images(user_id)
        for img in images:
            if img.get("category") == "full_body":
                return img.get("file_path") or ""
        return None

    def get_wardrobe_items(self, user_id: str) -> list:
        items = list(self._repo.list_wardrobe_items(user_id) or [])
        enriched: list[dict[str, Any]] = []
        for item in items:
            row = dict(item)
            metadata = dict(row.get("metadata_json") or {})
            catalog_attrs = dict(metadata.get("catalog_attributes") or {})
            if catalog_attrs:
                row["catalog_attributes"] = catalog_attrs
                row["volume_profile"] = str(row.get("volume_profile") or catalog_attrs.get("VolumeProfile") or "")
                row["fit_type"] = str(row.get("fit_type") or catalog_attrs.get("FitType") or "")
                row["silhouette_type"] = str(row.get("silhouette_type") or catalog_attrs.get("SilhouetteType") or "")
                row["formality_level"] = str(row.get("formality_level") or catalog_attrs.get("FormalityLevel") or catalog_attrs.get("FormalitySignalStrength") or "")
                row["occasion_fit"] = str(row.get("occasion_fit") or catalog_attrs.get("OccasionFit") or "")
                row["pattern_type"] = str(row.get("pattern_type") or catalog_attrs.get("PatternType") or "")
            enriched.append(row)
        return enriched

    def save_uploaded_chat_wardrobe_item(
        self,
        *,
        user_id: str,
        image_data: str,
        title: str = "",
        description: str = "",
        notes: str = "",
        persist: bool = True,
    ) -> Optional[dict]:
        existing = self._repo.get_profile_by_user_id(user_id)
        if not existing:
            return None
        return self._service.save_chat_wardrobe_image(
            user_id=user_id,
            image_data=image_data,
            title=title,
            description=description,
            notes=notes,
            persist=persist,
        )

    def persist_pending_wardrobe_item(
        self,
        *,
        user_id: str,
        pending: dict,
    ) -> Optional[dict]:
        """Promote a previously enriched-but-unpersisted wardrobe upload
        to a real wardrobe row. Called by the orchestrator after the
        planner classifies an upload turn as one of the wardrobe-write
        intents (`pairing_request` / `outfit_check`)."""
        existing = self._repo.get_profile_by_user_id(user_id)
        if not existing:
            return None
        return self._service.persist_pending_wardrobe_item(
            user_id=user_id,
            pending=pending,
        )

    def save_chat_wardrobe_item(
        self,
        *,
        user_id: str,
        title: str = "",
        description: str = "",
        image_url: str = "",
        garment_category: str = "",
        garment_subtype: str = "",
        primary_color: str = "",
        secondary_color: str = "",
        pattern_type: str = "",
        formality_level: str = "",
        occasion_fit: str = "",
        brand: str = "",
        notes: str = "",
        metadata_json: Optional[dict] = None,
    ) -> Optional[dict]:
        existing = self._repo.get_profile_by_user_id(user_id)
        if not existing:
            return None
        self._service.ensure_allowed_wardrobe_item(
            user_id=user_id,
            filename=image_url or title or "chat_wardrobe_item",
            title=title,
            description=description,
            garment_category=garment_category,
            garment_subtype=garment_subtype,
            notes=notes,
            brand=brand,
            input_class="chat_wardrobe_item",
        )
        return self._repo.insert_wardrobe_item(
            user_id=user_id,
            source="chat",
            title=title,
            description=description,
            image_url=image_url,
            image_path="",
            garment_category=garment_category,
            garment_subtype=garment_subtype,
            primary_color=primary_color,
            secondary_color=secondary_color,
            pattern_type=pattern_type,
            formality_level=formality_level,
            occasion_fit=occasion_fit,
            brand=brand,
            notes=notes,
            metadata_json=metadata_json or {},
        )

    def save_decomposed_garments(
        self,
        *,
        user_id: str,
        garments: List[Dict[str, Any]],
        turn_id: str = "",
        conversation_id: str = "",
    ) -> List[Dict[str, Any]]:
        """Save individual garments decomposed from an outfit photo.

        Each garment with ``image_data`` (base64 data URL of the cropped region)
        goes through the full wardrobe save pipeline including vision-based
        attribute extraction (46 attributes).
        """
        _log = logging.getLogger(__name__)
        saved: List[Dict[str, Any]] = []
        for garment in garments:
            image_data = str(garment.get("image_data") or "").strip()
            title = str(garment.get("title") or "").strip()
            notes = "Decomposed from outfit photo."
            try:
                if image_data:
                    item = self.save_uploaded_chat_wardrobe_item(
                        user_id=user_id,
                        image_data=image_data,
                        title=title,
                        description=title,
                        notes=notes,
                    )
                else:
                    item = self.save_chat_wardrobe_item(
                        user_id=user_id,
                        title=title,
                        garment_category=str(garment.get("garment_category") or "").strip(),
                        garment_subtype=str(garment.get("garment_subtype") or "").strip(),
                        primary_color=str(garment.get("primary_color") or "").strip(),
                        secondary_color=str(garment.get("secondary_color") or "").strip(),
                        pattern_type=str(garment.get("pattern_type") or "").strip(),
                        formality_level=str(garment.get("formality_level") or "").strip(),
                        occasion_fit=str(garment.get("occasion_fit") or "").strip(),
                        notes=notes,
                        metadata_json={
                            "source": "outfit_decomposition",
                            "source_turn_id": turn_id,
                            "source_conversation_id": conversation_id,
                        },
                    )
                if item is not None:
                    saved.append(item)
            except Exception:
                _log.warning("Failed to save decomposed garment: %s", title, exc_info=True)
        return saved

    def delete_wardrobe_item(self, *, user_id: str, wardrobe_item_id: str) -> bool:
        return self._service.delete_wardrobe_item(user_id=user_id, wardrobe_item_id=wardrobe_item_id)

    def create_router(self) -> APIRouter:
        return create_onboarding_router(self._service, self._analysis)

    def render_onboarding_html(self, *, user_id: str = "", focus: str = "") -> str:
        if str(focus or "").strip().lower() == "wardrobe":
            return get_wardrobe_manager_html(user_id=user_id)
        return get_onboarding_html()

    def render_processing_html(self, *, user_id: str = "") -> str:
        return get_processing_html(user_id=user_id)

    def render_wardrobe_manager_html(self, *, user_id: str = "") -> str:
        return get_wardrobe_manager_html(user_id=user_id)
