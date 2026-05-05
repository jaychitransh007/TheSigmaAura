from __future__ import annotations

from typing import Any, Dict, Iterable, List

from .schemas import ProfileConfidence, ProfileConfidenceFactor


def evaluate_profile_confidence(
    onboarding_status: Dict[str, Any] | None,
    analysis_status: Dict[str, Any] | None,
) -> ProfileConfidence:
    onboarding_status = dict(onboarding_status) if isinstance(onboarding_status, dict) else {}
    analysis_status = dict(analysis_status) if isinstance(analysis_status, dict) else {}

    images = {str(value or "").strip() for value in (onboarding_status.get("images_uploaded") or [])}
    style_pref = ((analysis_status.get("profile") or {}).get("style_preference") or {})
    derived = dict(analysis_status.get("derived_interpretations") or {})
    analysis_state = str(analysis_status.get("status") or "not_started").strip().lower()

    factors: List[ProfileConfidenceFactor] = []
    factors.append(
        _factor(
            factor="profile_complete",
            satisfied=bool(onboarding_status.get("profile_complete")),
            max_score=20.0,
            detail="Basic profile details are complete.",
            improvement_action="Complete your basic profile details.",
        )
    )
    factors.append(
        _factor(
            factor="full_body_image",
            satisfied="full_body" in images,
            max_score=15.0,
            detail="A full-body image is available for body-aware analysis.",
            improvement_action="Upload a clear full-body photo.",
        )
    )
    factors.append(
        _factor(
            factor="headshot_image",
            satisfied="headshot" in images,
            max_score=15.0,
            detail="A headshot is available for color and detail analysis.",
            improvement_action="Upload a clear headshot.",
        )
    )
    factors.append(
        _factor(
            factor="risk_tolerance_set",
            satisfied=bool(str(style_pref.get("riskTolerance") or "").strip()),
            max_score=20.0,
            detail="Risk tolerance is set so we can calibrate boldness.",
            improvement_action="Tell us how adventurous you'd like to dress so we can calibrate.",
        )
    )
    factors.append(
        _factor(
            factor="analysis_completed",
            satisfied=analysis_state == "completed",
            max_score=15.0,
            detail="Profile analysis has completed successfully.",
            improvement_action="Wait for profile analysis to finish or rerun it if it failed.",
            partial_score=7.5 if analysis_state in {"pending", "running"} else 0.0,
        )
    )
    factors.append(
        _factor(
            factor="seasonal_color_group",
            satisfied=bool(_nested_value(derived, "SeasonalColorGroup")),
            max_score=7.5,
            detail="Seasonal color interpretation is available.",
            improvement_action="Add clearer images or rerun profile analysis to improve color interpretation.",
        )
    )
    # primary_archetype factor dropped May 2026 — archetype is no
    # longer a stored user attribute.
    total = sum(item.max_score for item in factors) or 100.0
    earned = sum(item.score for item in factors)
    score_pct = int(round((earned / total) * 100))

    # Compute attribute-level analysis confidence (average of individual attribute confidences)
    conf_total = 0.0
    conf_count = 0
    attributes = dict(analysis_status.get("attributes") or {})
    for _attr_name, attr_val in attributes.items():
        if isinstance(attr_val, dict):
            c = attr_val.get("confidence")
            if isinstance(c, (int, float)):
                conf_total += float(c)
                conf_count += 1
    derived = dict(analysis_status.get("derived_interpretations") or {})
    for _interp_name, interp_val in derived.items():
        if isinstance(interp_val, dict):
            c = interp_val.get("confidence")
            if isinstance(c, (int, float)):
                conf_total += float(c)
                conf_count += 1
    analysis_confidence_pct = int(round((conf_total / conf_count) * 100)) if conf_count > 0 else score_pct

    satisfied = [item.factor for item in factors if item.satisfied]
    missing = [item.factor for item in factors if not item.satisfied]
    improvement_actions = _dedupe(item.improvement_action for item in factors if not item.satisfied and item.improvement_action)

    return ProfileConfidence(
        score_pct=score_pct,
        analysis_confidence_pct=analysis_confidence_pct,
        satisfied_factors=satisfied,
        missing_factors=missing,
        improvement_actions=improvement_actions,
        factors=factors,
    )


def _factor(
    *,
    factor: str,
    satisfied: bool,
    max_score: float,
    detail: str,
    improvement_action: str,
    partial_score: float = 0.0,
) -> ProfileConfidenceFactor:
    score = max_score if satisfied else max(0.0, min(partial_score, max_score))
    return ProfileConfidenceFactor(
        factor=factor,
        satisfied=satisfied,
        score=score,
        max_score=max_score,
        detail=detail,
        improvement_action="" if satisfied else improvement_action,
    )


def _nested_value(payload: Dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if isinstance(value, dict):
        return str(value.get("value") or "").strip()
    return str(value or "").strip()


def _dedupe(values: Iterable[str]) -> List[str]:
    ordered: List[str] = []
    seen: set[str] = set()
    for raw in values:
        value = str(raw or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered
