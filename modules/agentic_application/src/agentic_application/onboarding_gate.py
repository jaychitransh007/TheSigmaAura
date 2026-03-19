from __future__ import annotations

from typing import Any, Dict, List

from .profile_confidence import evaluate_profile_confidence
from .schemas import OnboardingGateResult


def evaluate(
    onboarding_status: Dict[str, Any] | None,
    analysis_status: Dict[str, Any] | None,
) -> OnboardingGateResult:
    onboarding_status = dict(onboarding_status) if isinstance(onboarding_status, dict) else {}
    analysis_status = dict(analysis_status) if isinstance(analysis_status, dict) else {}
    profile_confidence = evaluate_profile_confidence(onboarding_status, analysis_status)

    missing_steps: List[str] = []
    images = {str(value or "").strip() for value in (onboarding_status.get("images_uploaded") or [])}
    analysis_state = str(analysis_status.get("status") or "not_started").strip().lower()

    if not onboarding_status.get("profile_complete"):
        missing_steps.append("Complete your basic profile details.")
    if "full_body" not in images:
        missing_steps.append("Upload a full-body image.")
    if "headshot" not in images:
        missing_steps.append("Upload a headshot image.")
    if not onboarding_status.get("style_preference_complete"):
        missing_steps.append("Complete your style preference selection.")
    if not onboarding_status.get("onboarding_complete"):
        missing_steps.append("Finish mandatory onboarding before chat.")

    if analysis_state in {"pending", "running"}:
        missing_steps.append("Wait for profile analysis to complete.")
    elif analysis_state == "failed":
        missing_steps.append("Rerun your profile analysis.")
    elif analysis_state != "completed":
        missing_steps.append("Start profile analysis.")

    if onboarding_status.get("onboarding_complete") and analysis_state == "completed":
        return OnboardingGateResult(
            allowed=True,
            status="ready",
            message="Onboarding complete — chat is unlocked.",
            profile_confidence=profile_confidence,
        )

    if analysis_state in {"pending", "running"}:
        status = "analysis_pending"
        message = (
            "Your onboarding is complete, but profile analysis is still running. "
            "Chat unlocks once analysis finishes."
        )
    elif analysis_state == "failed":
        status = "analysis_failed"
        message = (
            "Your profile analysis needs attention before chat can unlock. "
            "Please rerun analysis and try again."
        )
    else:
        status = "onboarding_required"
        message = (
            "Complete mandatory onboarding before chat. "
            "Finish the remaining steps and your profile confidence will improve."
        )

    return OnboardingGateResult(
        allowed=False,
        status=status,
        message=message,
        missing_steps=_dedupe(missing_steps),
        improvement_actions=list(profile_confidence.improvement_actions),
        profile_confidence=profile_confidence,
    )


def _dedupe(values: List[str]) -> List[str]:
    ordered: List[str] = []
    seen: set[str] = set()
    for raw in values:
        value = str(raw or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered
