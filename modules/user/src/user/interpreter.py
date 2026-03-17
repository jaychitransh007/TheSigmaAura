from typing import Any, Dict


def derive_interpretations(
    attributes: Dict[str, Dict[str, Any]],
    *,
    height_cm: float = 0.0,
    waist_cm: float = 0.0,
) -> Dict[str, Dict[str, Any]]:
    outputs = {
        "HeightCategory": _derive_height_category(height_cm),
        "SeasonalColorGroup": _derive_seasonal_color_group(attributes),
        "ContrastLevel": _derive_contrast_level(attributes),
        "FrameStructure": _derive_frame_structure(attributes, height_cm=height_cm),
        "WaistSizeBand": _derive_waist_size_band(waist_cm),
    }
    for payload in outputs.values():
        payload["source_agent"] = "deterministic_interpreter"
    return outputs


def _derive_seasonal_color_group(attributes: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    skin_undertone = _value(attributes, "SkinUndertone")
    skin_surface = _value(attributes, "SkinSurfaceColor")
    hair_color = _value(attributes, "HairColor")
    hair_temp = _value(attributes, "HairColorTemperature")
    eye_color = _value(attributes, "EyeColor")
    eye_clarity = _value(attributes, "EyeClarity")

    missing = [name for name, value in {
        "SkinUndertone": skin_undertone,
        "SkinSurfaceColor": skin_surface,
        "HairColor": hair_color,
        "HairColorTemperature": hair_temp,
        "EyeColor": eye_color,
        "EyeClarity": eye_clarity,
    }.items() if not value or value == "Unable to Assess"]
    if missing:
        return {
            "value": "Unable to Assess",
            "confidence": 0.0,
            "evidence_note": "Missing required inputs: " + ", ".join(missing) + ".",
        }

    warmth_score = 0
    warmth_score += {"Warm": 2, "Neutral": 0, "Cool": -2}.get(skin_undertone, 0)
    warmth_score += {"Warm": 2, "Neutral": 0, "Cool": -2}.get(hair_temp, 0)
    branch = "warm" if warmth_score > 0 else "cool"

    depth_score = (
        _skin_depth_value(skin_surface)
        + _hair_depth_value(hair_color)
        + _eye_depth_value(eye_color)
    ) / 3.0
    contrast_spread = max(
        _skin_depth_value(skin_surface),
        _hair_depth_value(hair_color),
        _eye_depth_value(eye_color),
    ) - min(
        _skin_depth_value(skin_surface),
        _hair_depth_value(hair_color),
        _eye_depth_value(eye_color),
    )
    if depth_score <= 3.0:
        depth_band = "light"
    elif depth_score >= 7.0:
        depth_band = "deep"
    else:
        depth_band = "medium"

    clarity_score = {
        "Soft / Muted": 0.15,
        "Balanced": 0.55,
        "Bright / Clear": 0.9,
    }.get(eye_clarity, 0.55)

    if branch == "warm":
        if depth_band == "light":
            season = "Light Spring" if clarity_score >= 0.75 else "Warm Spring"
        elif depth_band == "deep":
            season = "Deep Autumn"
        else:
            if clarity_score >= 0.82:
                season = "Clear Spring"
            elif clarity_score <= 0.28:
                season = "Soft Autumn"
            elif depth_score >= 5.6:
                season = "Warm Autumn"
            else:
                season = "Warm Spring"
    else:
        if depth_band == "light":
            season = "Light Summer" if clarity_score <= 0.65 else "Cool Summer"
        elif depth_band == "deep":
            if clarity_score >= 0.88:
                season = "Clear Winter"
            elif depth_score >= 8.0:
                season = "Deep Winter"
            else:
                season = "Cool Winter"
        else:
            if clarity_score >= 0.85 and contrast_spread >= 6:
                season = "Clear Winter"
            elif clarity_score <= 0.24:
                season = "Soft Summer"
            elif depth_score >= 5.8 and clarity_score >= 0.68:
                season = "Cool Winter"
            else:
                season = "Cool Summer"

    confidence = _aggregate_confidence(
        attributes,
        ["SkinUndertone", "SkinSurfaceColor", "HairColor", "HairColorTemperature", "EyeColor", "EyeClarity"],
    )
    if skin_undertone == "Neutral" or hair_temp == "Neutral":
        confidence -= 0.08
    if depth_band == "medium":
        confidence -= 0.04
    confidence = max(0.0, min(0.99, confidence))

    return {
        "value": season,
        "confidence": confidence,
        "evidence_note": f"{skin_undertone} undertone, {hair_temp.lower()} hair temperature, {depth_band} overall depth, and {eye_clarity.lower()} clarity place the palette in {season}.",
    }


def _derive_contrast_level(attributes: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    skin_surface = _value(attributes, "SkinSurfaceColor")
    hair_color = _value(attributes, "HairColor")
    eye_color = _value(attributes, "EyeColor")
    missing = [name for name, value in {
        "SkinSurfaceColor": skin_surface,
        "HairColor": hair_color,
        "EyeColor": eye_color,
    }.items() if not value or value == "Unable to Assess"]
    if missing:
        return {
            "value": "Unable to Assess",
            "confidence": 0.0,
            "evidence_note": "Missing required inputs: " + ", ".join(missing) + ".",
        }

    values = [
        _skin_depth_value(skin_surface),
        _hair_depth_value(hair_color),
        _eye_depth_value(eye_color),
    ]
    spread = max(values) - min(values)
    if spread <= 2:
        label = "Low"
    elif spread <= 3:
        label = "Medium-Low"
    elif spread <= 5:
        label = "Medium"
    elif spread == 6:
        label = "Medium-High"
    else:
        label = "High"

    confidence = _aggregate_confidence(attributes, ["SkinSurfaceColor", "HairColor", "EyeColor"])
    return {
        "value": label,
        "confidence": confidence,
        "evidence_note": f"Feature depth spread is {spread:.1f} across skin, hair, and eyes, mapping to {label} contrast.",
    }


def _derive_frame_structure(attributes: Dict[str, Dict[str, Any]], *, height_cm: float = 0.0) -> Dict[str, Any]:
    visual_weight = _value(attributes, "VisualWeight")
    shoulder_slope = _value(attributes, "ShoulderSlope")
    arm_volume = _value(attributes, "ArmVolume")
    missing = [name for name, value in {
        "VisualWeight": visual_weight,
        "ShoulderSlope": shoulder_slope,
        "ArmVolume": arm_volume,
    }.items() if not value or value == "Unable to Assess"]
    if missing:
        return {
            "value": "Unable to Assess",
            "confidence": 0.0,
            "evidence_note": "Missing required inputs: " + ", ".join(missing) + ".",
        }

    if visual_weight in {"Light", "Medium-Light"}:
        weight_band = "Light"
    elif visual_weight in {"Medium-Heavy", "Heavy"}:
        weight_band = "Solid"
    else:
        weight_band = "Medium"

    width_score = 0
    width_score += {"Square": 1, "Average": 0, "Sloped": -1}.get(shoulder_slope, 0)
    width_score += {"Full": 1, "Medium": 0, "Slim": -1}.get(arm_volume, 0)
    if height_cm >= 182:
        width_score += 0.5
    elif height_cm and height_cm <= 160:
        width_score -= 0.5

    if width_score >= 1:
        width_band = "Broad"
    elif width_score <= -1:
        width_band = "Narrow"
    else:
        width_band = "Balanced"

    label = {
        ("Light", "Narrow"): "Light and Narrow",
        ("Light", "Broad"): "Light and Broad",
        ("Light", "Balanced"): "Medium and Balanced",
        ("Medium", "Narrow"): "Medium and Balanced",
        ("Medium", "Broad"): "Medium and Balanced",
        ("Medium", "Balanced"): "Medium and Balanced",
        ("Solid", "Narrow"): "Solid and Narrow",
        ("Solid", "Broad"): "Solid and Broad",
        ("Solid", "Balanced"): "Medium and Balanced",
    }[(weight_band, width_band)]

    confidence = _aggregate_confidence(attributes, ["VisualWeight", "ShoulderSlope", "ArmVolume"])
    return {
        "value": label,
        "confidence": confidence,
        "evidence_note": f"{visual_weight} visual weight with {shoulder_slope.lower()} shoulders and {arm_volume.lower()} arm volume reads as {label}.",
    }


def _derive_height_category(height_cm: float) -> Dict[str, Any]:
    if height_cm <= 0:
        return {
            "value": "Unable to Assess",
            "confidence": 0.0,
            "evidence_note": "Missing height measurement from onboarding profile.",
        }

    if height_cm < 160:
        label = "Petite"
    elif height_cm <= 175:
        label = "Average"
    else:
        label = "Tall"

    return {
        "value": label,
        "confidence": 1.0,
        "evidence_note": f"Derived directly from entered height of {height_cm:.1f} cm.",
    }


def _derive_waist_size_band(waist_cm: float) -> Dict[str, Any]:
    if waist_cm <= 0:
        return {
            "value": "Unable to Assess",
            "confidence": 0.0,
            "evidence_note": "Missing waist measurement from onboarding profile.",
        }

    if waist_cm < 65:
        label = "Very Small"
    elif waist_cm < 75:
        label = "Small"
    elif waist_cm < 90:
        label = "Medium"
    elif waist_cm < 110:
        label = "Large"
    else:
        label = "Very Large"

    return {
        "value": label,
        "confidence": 1.0,
        "evidence_note": f"Derived directly from entered waist measurement of {waist_cm:.1f} cm.",
    }


def _aggregate_confidence(attributes: Dict[str, Dict[str, Any]], keys: list[str]) -> float:
    values = [float(attributes.get(key, {}).get("confidence") or 0.0) for key in keys]
    if not values:
        return 0.0
    return round(max(0.0, min(values) * 0.65 + (sum(values) / len(values)) * 0.35), 3)


def _value(attributes: Dict[str, Dict[str, Any]], key: str) -> Any:
    item = attributes.get(key) or {}
    return item.get("value")


def _skin_depth_value(value: str) -> int:
    return {"Fair": 2, "Light": 3, "Medium": 5, "Tan": 6, "Dark": 8, "Deep": 9}.get(value, 5)


def _hair_depth_value(value: str) -> int:
    return {
        "White": 1,
        "Blonde": 2,
        "Light Brown": 4,
        "Auburn": 5,
        "Red": 5,
        "Grey": 5,
        "Medium Brown": 6,
        "Dark Brown": 8,
        "Black": 9,
    }.get(value, 6)


def _eye_depth_value(value: str) -> int:
    return {
        "Blue": 2,
        "Grey": 2,
        "Green": 3,
        "Hazel": 4,
        "Light Brown": 5,
        "Medium Brown": 6,
        "Dark Brown": 8,
        "Black-Brown": 9,
    }.get(value, 5)
