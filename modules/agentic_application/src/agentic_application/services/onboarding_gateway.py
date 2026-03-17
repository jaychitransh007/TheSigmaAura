from __future__ import annotations

from typing import Optional

from fastapi import APIRouter

from user.analysis import UserAnalysisService
from user.api import create_onboarding_router
from user.repository import OnboardingRepository
from user.service import OnboardingService
from user.ui import get_onboarding_html, get_processing_html

from platform_core.supabase_rest import SupabaseRestClient


class ApplicationUserGateway:
    """App-facing wrapper around user module dependencies."""

    def __init__(self, client: SupabaseRestClient) -> None:
        self._repo = OnboardingRepository(client)
        self._service = OnboardingService(repo=self._repo)
        self._analysis = UserAnalysisService(repo=self._repo)

    def get_analysis_status(self, user_id: str) -> dict:
        return dict(self._analysis.get_analysis_status(user_id) or {})

    def get_onboarding_status(self, user_id: str) -> dict:
        return dict(self._service.get_status(user_id) or {})

    def get_effective_seasonal_groups(self, user_id: str) -> list:
        row = self._repo.get_effective_seasonal_groups(user_id)
        if row:
            return list(row.get("seasonal_groups") or [])
        return []

    def get_person_image_path(self, user_id: str) -> Optional[str]:
        images = self._repo.get_images(user_id)
        for img in images:
            if img.get("category") == "full_body":
                return img.get("file_path") or ""
        return None

    def create_router(self) -> APIRouter:
        return create_onboarding_router(self._service, self._analysis)

    def render_onboarding_html(self) -> str:
        return get_onboarding_html()

    def render_processing_html(self, *, user_id: str = "") -> str:
        return get_processing_html(user_id=user_id)


# Backward compatibility alias
ApplicationOnboardingGateway = ApplicationUserGateway
