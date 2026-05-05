from __future__ import annotations

from typing import Any, Dict, Optional

# derive_color_palette import removed — palette comes from deterministic interpreter via collated_output

from ..schemas import UserContext
from ..services.onboarding_gateway import ApplicationUserGateway


def _compute_profile_richness(
    gender: str,
    analysis_attributes: Dict[str, Any],
    derived_interpretations: Dict[str, Any],
    style_preference: Dict[str, Any],
) -> str:
    # May 2026: profile richness used to gate on primaryArchetype, but
    # archetype was dropped from the data model. Body+palette signals are
    # now what defines a "rich" profile; risk_tolerance is binary
    # (set or not). Tiers below intentionally don't gate on
    # risk_tolerance — a user without it still gets a default of
    # "balanced" downstream and can produce useful recommendations.
    has_gender = bool(gender.strip())
    has_seasonal = bool(
        str((derived_interpretations.get("SeasonalColorGroup") or {}).get("value") or "").strip()
    )
    body_attr_count = sum(
        1 for v in analysis_attributes.values()
        if isinstance(v, dict) and str(v.get("value") or "").strip()
    )

    if has_gender and has_seasonal and body_attr_count >= 3:
        return "full"
    if has_gender and has_seasonal and body_attr_count >= 1:
        return "moderate"
    if has_gender and has_seasonal:
        return "basic"
    return "minimal"


def build_user_context(
    user_id: str,
    *,
    onboarding_gateway: ApplicationUserGateway,
    analysis_status: Optional[Dict[str, Any]] = None,
) -> UserContext:
    """Load all saved user state into a single UserContext object.

    ``analysis_status`` lets the caller pass a pre-fetched analysis-status
    dict to avoid a redundant Supabase round trip. The orchestrator's
    onboarding gate already loads it once at the top of every turn — passing
    it through saves ~3 DB reads (profile + style snapshot + interpretation
    snapshot) at the user_context step. May 5, 2026.
    """
    status = analysis_status if analysis_status is not None else onboarding_gateway.get_analysis_status(user_id)
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

    # Seasonal color group and palette come directly from the deterministic
    # interpreter via collated_output — no draping override.

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
    # primaryArchetype was dropped May 2026 — recommendation no longer
    # requires a stored archetype. Body shape + palette + per-turn chat
    # carry the directional signal.
