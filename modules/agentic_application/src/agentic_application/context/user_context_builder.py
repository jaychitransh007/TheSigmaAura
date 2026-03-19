from __future__ import annotations

from typing import Any, Dict

from ..schemas import UserContext
from ..services.onboarding_gateway import ApplicationUserGateway


def _compute_profile_richness(
    gender: str,
    analysis_attributes: Dict[str, Any],
    derived_interpretations: Dict[str, Any],
    style_preference: Dict[str, Any],
) -> str:
    has_gender = bool(gender.strip())
    has_primary_archetype = bool(
        str(style_preference.get("primaryArchetype") or "").strip()
    )
    has_seasonal = bool(
        str((derived_interpretations.get("SeasonalColorGroup") or {}).get("value") or "").strip()
    )
    body_attr_count = sum(
        1 for v in analysis_attributes.values()
        if isinstance(v, dict) and str(v.get("value") or "").strip()
    )

    if has_gender and has_seasonal and has_primary_archetype and body_attr_count >= 3:
        return "full"
    if has_gender and has_primary_archetype and body_attr_count >= 1:
        return "moderate"
    if has_gender and has_primary_archetype:
        return "basic"
    return "minimal"


def build_user_context(
    user_id: str,
    *,
    onboarding_gateway: ApplicationUserGateway,
) -> UserContext:
    """Load all saved user state into a single UserContext object."""
    status = onboarding_gateway.get_analysis_status(user_id)
    if status.get("status") != "completed":
        raise ValueError(
            "User analysis is not complete. Finish onboarding and profile analysis first."
        )

    profile = status.get("profile") or {}
    attributes = status.get("attributes") or {}
    derived = status.get("derived_interpretations") or {}
    style_pref = profile.get("style_preference") or {}
    wardrobe_items = onboarding_gateway.get_wardrobe_items(user_id)
    if not isinstance(wardrobe_items, list):
        wardrobe_items = []

    # Overlay effective seasonal groups from draping / comfort learning
    effective = onboarding_gateway.get_effective_seasonal_groups(user_id)
    if not isinstance(effective, list):
        effective = []
    if effective:
        seasonal = derived.get("SeasonalColorGroup")
        if isinstance(seasonal, dict):
            seasonal["value"] = effective[0].get("value", seasonal.get("value", ""))
            seasonal["additional_groups"] = effective[1:]
        else:
            derived["SeasonalColorGroup"] = {
                "value": effective[0].get("value", ""),
                "confidence": effective[0].get("probability", 0.0),
                "evidence_note": "From effective seasonal groups",
                "source_agent": effective[0].get("source", "draping"),
                "additional_groups": effective[1:],
            }

    gender = str(profile.get("gender") or "")
    richness = _compute_profile_richness(gender, attributes, derived, style_pref)

    return UserContext(
        user_id=user_id,
        gender=gender,
        date_of_birth=str(profile.get("date_of_birth") or "") or None,
        profession=str(profile.get("profession") or "") or None,
        height_cm=float(profile["height_cm"]) if profile.get("height_cm") else None,
        waist_cm=float(profile["waist_cm"]) if profile.get("waist_cm") else None,
        analysis_attributes=attributes,
        derived_interpretations=derived,
        style_preference=style_pref,
        wardrobe_items=wardrobe_items,
        profile_richness=richness,
    )


def validate_minimum_profile(user_context: UserContext) -> None:
    """Raise if the minimum profile for recommendation is not met."""
    if not user_context.gender.strip():
        raise ValueError("Profile missing required field: gender")
    seasonal = (
        user_context.derived_interpretations.get("SeasonalColorGroup") or {}
    ).get("value") or ""
    if not seasonal.strip():
        raise ValueError("Profile missing required field: SeasonalColorGroup")
    primary = str(
        user_context.style_preference.get("primaryArchetype") or ""
    ).strip()
    if not primary:
        raise ValueError("Profile missing required field: primaryArchetype")
