from typing import Any, Dict, List


# ── 12 Sub-Season Palette System ──
# Each sub-season has curated base, accent, and avoid lists sourced from
# established color analysis references (Sci\ART, Caygill, Kitchener).
# The 4-season lookup is derived by merging the sub-season palettes.

SUB_SEASON_PALETTE_MAP: Dict[str, Dict[str, List[str]]] = {
    # ── AUTUMN ──
    "Warm Autumn": {
        "base": ["warm camel", "golden brown", "warm bronze", "dark honey"],
        "accent": ["terracotta", "burnt sienna", "pumpkin", "warm coral", "amber"],
        "avoid": ["icy blue", "fuchsia", "silver", "stark white", "cool pink"],
    },
    "Deep Autumn": {
        "base": ["dark chocolate", "espresso", "warm charcoal", "deep olive"],
        "accent": ["burgundy", "forest green", "burnt orange", "deep teal", "rust"],
        "avoid": ["pastel pink", "powder blue", "light lavender", "stark white", "icy grey"],
    },
    "Soft Autumn": {
        "base": ["warm taupe", "soft khaki", "muted olive", "warm grey"],
        "accent": ["sage green", "muted terracotta", "dusty coral", "soft rust", "warm mauve"],
        "avoid": ["neon", "royal blue", "fuchsia", "stark black", "electric colors"],
    },
    # ── SPRING ──
    "Warm Spring": {
        "base": ["warm ivory", "golden beige", "camel", "warm sand"],
        "accent": ["coral", "warm peach", "golden yellow", "turquoise", "warm red"],
        "avoid": ["charcoal", "icy blue", "dark navy", "cool grey", "burgundy"],
    },
    "Light Spring": {
        "base": ["ivory", "light camel", "soft peach", "light gold"],
        "accent": ["light coral", "peach", "aqua", "bright salmon", "light turquoise"],
        "avoid": ["black", "charcoal", "dark brown", "deep burgundy", "dark navy"],
    },
    "Clear Spring": {
        "base": ["warm white", "bright beige", "clear camel", "light warm grey"],
        "accent": ["hot pink", "bright coral", "electric turquoise", "bright orange", "vivid green"],
        "avoid": ["muted olive", "dusty rose", "warm taupe", "muddy brown", "greyish tones"],
    },
    # ── SUMMER ──
    "Cool Summer": {
        "base": ["cool grey", "soft white", "blue-grey", "cool taupe"],
        "accent": ["dusty blue", "lavender", "cool rose", "soft teal", "periwinkle"],
        "avoid": ["orange", "golden yellow", "rust", "warm brown", "terracotta"],
    },
    "Light Summer": {
        "base": ["light grey", "soft white", "pale blue-grey", "cool beige"],
        "accent": ["powder blue", "soft pink", "light lavender", "dusty rose", "light mint"],
        "avoid": ["black", "dark brown", "burnt orange", "deep red", "dark olive"],
    },
    "Soft Summer": {
        "base": ["medium grey", "mauve-grey", "soft slate", "muted blue-grey"],
        "accent": ["dusty rose", "muted teal", "soft plum", "muted sage", "smoky blue"],
        "avoid": ["neon", "bright orange", "vivid yellow", "electric blue", "stark black"],
    },
    # ── WINTER ──
    "Cool Winter": {
        "base": ["charcoal", "cool white", "dark navy", "cool grey"],
        "accent": ["royal blue", "emerald", "deep fuchsia", "cool red", "deep purple"],
        "avoid": ["warm beige", "golden yellow", "peach", "warm brown", "muted gold"],
    },
    "Deep Winter": {
        "base": ["black", "dark charcoal", "midnight navy", "deep espresso"],
        "accent": ["true red", "deep emerald", "bright white", "deep royal blue", "deep berry"],
        "avoid": ["pastel", "light peach", "warm taupe", "muted olive", "soft coral"],
    },
    "Clear Winter": {
        "base": ["pure white", "black", "icy grey", "bright navy"],
        "accent": ["hot pink", "electric blue", "vivid emerald", "bright red", "icy violet"],
        "avoid": ["muted olive", "dusty rose", "warm taupe", "golden brown", "soft tones"],
    },
}

# Legacy 4-season map derived from sub-season palettes (union of base sub-seasons)
SEASON_PALETTE_MAP: Dict[str, Dict[str, List[str]]] = {
    season: {
        "base": SUB_SEASON_PALETTE_MAP[f"{'Warm' if season in ('Autumn','Spring') else 'Cool'} {season}"]["base"],
        "accent": SUB_SEASON_PALETTE_MAP[f"{'Warm' if season in ('Autumn','Spring') else 'Cool'} {season}"]["accent"],
        "avoid": SUB_SEASON_PALETTE_MAP[f"{'Warm' if season in ('Autumn','Spring') else 'Cool'} {season}"]["avoid"],
    }
    for season in ("Spring", "Summer", "Autumn", "Winter")
}


def derive_color_palette(
    season: str,
    confidence: float,
    *,
    sub_season: str = "",
    secondary_season: str = "",
    dimension_profile: Dict[str, Any] | None = None,
) -> Dict[str, Dict[str, Any]]:
    """Derive base/accent/avoid palettes from sub-season with boundary blending.

    When sub_season is provided, uses the curated 12-sub-season palette.
    When confidence is low or a secondary_season is close, blends palettes:
    - Base colors from primary sub-season
    - Accent colors include top-2 from adjacent sub-season as "also try"
    - Avoid list narrowed to intersection of both seasons (boundary users
      can often wear colors one season avoids but the other endorses)
    """
    # Try sub-season palette first, fall back to 4-season
    palette = SUB_SEASON_PALETTE_MAP.get(sub_season) or SEASON_PALETTE_MAP.get(season)
    if not palette:
        unable: Dict[str, Any] = {
            "value": [],
            "confidence": 0.0,
            "evidence_note": f"Cannot derive palette: '{sub_season or season}' is not recognized.",
        }
        return {"BaseColors": dict(unable), "AccentColors": dict(unable), "AvoidColors": dict(unable)}

    base = list(palette["base"])
    accent = list(palette["accent"])
    avoid = list(palette["avoid"])
    palette_source = sub_season or season

    # Boundary blending when confidence is low or secondary season is close
    is_boundary = confidence < 0.6 or bool(secondary_season)
    if is_boundary and secondary_season:
        # Find the adjacent sub-season palette
        adj_sub = ""
        if sub_season:
            neighbors = SUB_SEASON_ADJACENCY.get(sub_season, [])
            for n in neighbors:
                if secondary_season in n or n.endswith(secondary_season):
                    adj_sub = n
                    break
        adj_palette = SUB_SEASON_PALETTE_MAP.get(adj_sub) or SEASON_PALETTE_MAP.get(secondary_season)
        if adj_palette:
            # Add top-2 adjacent accents as "also try"
            for color in adj_palette["accent"][:2]:
                if color not in accent:
                    accent.append(color)
            # Narrow avoid to intersection — boundary users can wear some "avoid" colors
            adj_avoid = set(adj_palette["avoid"])
            avoid = [c for c in avoid if c in adj_avoid]
            palette_source = f"{palette_source} (blended with {adj_sub or secondary_season})"

    return {
        "BaseColors": {
            "value": base,
            "confidence": confidence,
            "evidence_note": f"Foundation neutrals for {palette_source} palette.",
        },
        "AccentColors": {
            "value": accent,
            "confidence": confidence,
            "evidence_note": f"Statement colors for {palette_source}." + (" Includes adjacent season crossovers." if is_boundary else ""),
        },
        "AvoidColors": {
            "value": avoid,
            "confidence": confidence,
            "evidence_note": f"Colors that clash with {palette_source}." + (" Narrowed to shared avoids for boundary case." if is_boundary else ""),
        },
    }


def derive_interpretations(
    attributes: Dict[str, Dict[str, Any]],
    *,
    height_cm: float = 0.0,
    waist_cm: float = 0.0,
) -> Dict[str, Dict[str, Any]]:
    seasonal = _derive_seasonal_color_group(attributes)
    outputs = {
        "HeightCategory": _derive_height_category(height_cm),
        "SeasonalColorGroup": seasonal,
        "ContrastLevel": _derive_contrast_level(attributes),
        "SkinHairContrast": _derive_skin_hair_contrast(attributes),
        "SubSeason": _derive_sub_season(seasonal),
        "ColorDimensionProfile": _derive_color_dimension_profile(seasonal),
        "FrameStructure": _derive_frame_structure(attributes, height_cm=height_cm),
        "WaistSizeBand": _derive_waist_size_band(waist_cm),
    }
    seasonal = outputs["SeasonalColorGroup"]
    sub_season_val = outputs.get("SubSeason", {}).get("value", "")
    secondary = seasonal.get("secondary_season") or ""
    dim_profile = seasonal.get("dimension_profile") or {}
    outputs.update(derive_color_palette(
        seasonal.get("value", ""),
        seasonal.get("confidence", 0.0),
        sub_season=sub_season_val,
        secondary_season=secondary,
        dimension_profile=dim_profile,
    ))
    for payload in outputs.values():
        if isinstance(payload, dict):
            payload["source_agent"] = "deterministic_interpreter"
    return outputs


def _derive_seasonal_color_group(attributes: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """Dimension-first seasonal color analysis.

    Computes warmth, depth, contrast, and chroma scores from raw attributes,
    then derives the primary season. A ``dimension_profile`` dict is attached
    to the output for downstream use (sub-season assignment, palette tweaks,
    architect styling decisions).
    """
    skin_surface = _value(attributes, "SkinSurfaceColor")
    hair_color = _value(attributes, "HairColor")
    hair_temp = _value(attributes, "HairColorTemperature")
    eye_color = _value(attributes, "EyeColor")
    # Backward compat: accept both old "EyeClarity" and new "EyeChroma"
    eye_chroma = _value(attributes, "EyeChroma") or _value(attributes, "EyeClarity")
    # New Phase A attributes (may be absent for users analysed before this change)
    skin_undertone = _value(attributes, "SkinUndertone")
    skin_chroma = _value(attributes, "SkinChroma")

    # Core 5 are required; new attributes are optional enhancements
    missing = [name for name, value in {
        "SkinSurfaceColor": skin_surface,
        "HairColor": hair_color,
        "HairColorTemperature": hair_temp,
        "EyeColor": eye_color,
        "EyeChroma": eye_chroma,
    }.items() if not value or value == "Unable to Assess"]
    if missing:
        return {
            "value": "Unable to Assess",
            "confidence": 0.0,
            "evidence_note": "Missing required inputs: " + ", ".join(missing) + ".",
        }

    # ── Warmth score: weighted multi-attribute consensus ──
    # SkinUndertone (weight 3) + HairColorTemperature (weight 2) + EyeColor (weight 1)
    # Normalized to -2..+2 range. Replaces the old single-attribute binary branch.
    undertone_warmth = {
        "Warm": 2, "Neutral-Warm": 1, "Olive": 0,
        "Neutral-Cool": -1, "Cool": -2,
    }.get(skin_undertone or "", None)
    hair_warmth = {"Warm": 2, "Neutral": 0, "Cool": -2}.get(hair_temp, 0)
    eye_warmth = {
        "Black-Brown": 1, "Dark Brown": 0.5, "Medium Brown": 0.5,
        "Light Brown": 0.5, "Hazel": 0, "Green": 0,
        "Blue": -1, "Grey": -1,
    }.get(eye_color, 0)

    if undertone_warmth is not None:
        # Full 3-signal weighted warmth
        warmth_score = (undertone_warmth * 3 + hair_warmth * 2 + eye_warmth * 1) / 6.0
    else:
        # Fallback for users without SkinUndertone (pre-Phase A analysis)
        warmth_score = (hair_warmth * 2 + eye_warmth * 1) / 3.0

    ambiguous_temperature = abs(warmth_score) < 0.5
    branch = "warm" if warmth_score > 0 else "cool"

    # ── Depth score ──
    skin_depth = _skin_depth_value(skin_surface)
    hair_depth = _hair_depth_value(hair_color)
    eye_depth = _eye_depth_value(eye_color)
    depth_score = (skin_depth + hair_depth + eye_depth) / 3.0

    if depth_score <= 3.0:
        depth_band = "light"
    elif depth_score >= 7.0:
        depth_band = "deep"
    else:
        depth_band = "medium"

    # ── Skin-hair contrast (first-class dimension) ──
    skin_hair_contrast = abs(skin_depth - hair_depth)

    # ── Chroma score ──
    eye_chroma_score = {
        "Soft / Muted": 0.15, "Balanced": 0.55, "Bright / Clear": 0.9,
    }.get(eye_chroma, 0.55)
    skin_chroma_score = {
        "Muted": 0.15, "Moderate": 0.55, "Clear": 0.9,
    }.get(skin_chroma or "", 0.55)  # default to moderate if not available
    chroma_score = (eye_chroma_score + skin_chroma_score) / 2.0

    # ── Season selection ──
    if branch == "warm":
        if depth_band == "deep" or (depth_band == "medium" and depth_score >= 5.6):
            season = "Autumn"
        else:
            season = "Spring"
    else:
        if depth_band == "deep" or (depth_band == "medium" and depth_score >= 5.8):
            season = "Winter"
        else:
            season = "Summer"

    # ── Confidence ──
    conf_keys = ["SkinSurfaceColor", "HairColor", "HairColorTemperature", "EyeColor"]
    # Use whichever name exists in the attributes
    if "EyeChroma" in attributes:
        conf_keys.append("EyeChroma")
    elif "EyeClarity" in attributes:
        conf_keys.append("EyeClarity")
    if skin_undertone:
        conf_keys.append("SkinUndertone")
    if skin_chroma:
        conf_keys.append("SkinChroma")
    confidence = _aggregate_confidence(attributes, conf_keys)
    if ambiguous_temperature:
        confidence -= 0.10
    if depth_band == "medium":
        confidence -= 0.04
    confidence = max(0.0, min(0.99, confidence))

    # ── Dimension profile (attached to output for downstream use) ──
    dimension_profile = {
        "warmth_score": round(warmth_score, 3),
        "depth_score": round(depth_score, 2),
        "skin_hair_contrast": skin_hair_contrast,
        "chroma_score": round(chroma_score, 3),
        "ambiguous_temperature": ambiguous_temperature,
    }

    undertone_note = f", {skin_undertone.lower()} undertone" if skin_undertone else ""
    return {
        "value": season,
        "confidence": confidence,
        "evidence_note": (
            f"Warmth score {warmth_score:+.2f} ({branch}){undertone_note}, "
            f"{depth_band} depth ({depth_score:.1f}), "
            f"chroma {chroma_score:.2f} → {season}."
        ),
        "dimension_profile": dimension_profile,
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


def _derive_skin_hair_contrast(attributes: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """First-class skin-hair contrast score for pattern/outfit contrast decisions."""
    skin = _value(attributes, "SkinSurfaceColor")
    hair = _value(attributes, "HairColor")
    if not skin or not hair or skin == "Unable to Assess" or hair == "Unable to Assess":
        return {"value": "Unable to Assess", "confidence": 0.0, "evidence_note": "Missing skin or hair data."}
    score = abs(_skin_depth_value(skin) - _hair_depth_value(hair))
    if score <= 2:
        label = "Low"
    elif score <= 4:
        label = "Medium"
    else:
        label = "High"
    confidence = _aggregate_confidence(attributes, ["SkinSurfaceColor", "HairColor"])
    return {
        "value": label,
        "confidence": confidence,
        "numeric_score": score,
        "evidence_note": f"Skin depth ({skin}) vs hair depth ({hair}) = {score} point spread → {label} skin-hair contrast.",
    }


# ── 12 Sub-Season Assignment ──

# Which dimension is dominant determines the sub-season within each primary season.
# Warm Autumn (highest warmth), Deep Autumn (highest depth), Soft Autumn (lowest chroma)
# Warm Spring (highest warmth), Light Spring (lowest depth), Clear Spring (highest chroma)
# Cool Summer (coolest warmth), Light Summer (lowest depth), Soft Summer (lowest chroma)
# Cool Winter (coolest warmth), Deep Winter (highest depth), Clear Winter (highest chroma)

_SUB_SEASON_RULES: Dict[str, List[tuple[str, str, str]]] = {
    # season: [(sub_season, dimension, direction), ...]
    # direction: "highest" = largest value wins, "lowest" = smallest value wins
    "Autumn": [
        ("Warm Autumn", "warmth_score", "highest"),
        ("Deep Autumn", "depth_score", "highest"),
        ("Soft Autumn", "chroma_score", "lowest"),
    ],
    "Spring": [
        ("Warm Spring", "warmth_score", "highest"),
        ("Light Spring", "depth_score", "lowest"),
        ("Clear Spring", "chroma_score", "highest"),
    ],
    "Summer": [
        ("Cool Summer", "warmth_score", "lowest"),
        ("Light Summer", "depth_score", "lowest"),
        ("Soft Summer", "chroma_score", "lowest"),
    ],
    "Winter": [
        ("Cool Winter", "warmth_score", "lowest"),
        ("Deep Winter", "depth_score", "highest"),
        ("Clear Winter", "chroma_score", "highest"),
    ],
}

# Adjacency: sub-seasons that share a dominant dimension can borrow from each other.
SUB_SEASON_ADJACENCY: Dict[str, List[str]] = {
    "Warm Autumn": ["Warm Spring"],
    "Deep Autumn": ["Deep Winter"],
    "Soft Autumn": ["Soft Summer"],
    "Warm Spring": ["Warm Autumn"],
    "Light Spring": ["Light Summer"],
    "Clear Spring": ["Clear Winter"],
    "Cool Summer": ["Cool Winter"],
    "Light Summer": ["Light Spring"],
    "Soft Summer": ["Soft Autumn"],
    "Cool Winter": ["Cool Summer"],
    "Deep Winter": ["Deep Autumn"],
    "Clear Winter": ["Clear Spring"],
}


def _derive_sub_season(seasonal_result: Dict[str, Any]) -> Dict[str, Any]:
    """Assign one of 12 sub-seasons based on which dimension is most dominant."""
    season = seasonal_result.get("value", "")
    profile = seasonal_result.get("dimension_profile") or {}
    if season not in _SUB_SEASON_RULES or not profile:
        return {
            "value": season or "Unable to Assess",
            "confidence": 0.0,
            "evidence_note": "Cannot determine sub-season without dimension profile.",
        }

    rules = _SUB_SEASON_RULES[season]
    # Score each sub-season by how extreme the user is on its defining dimension
    best_sub = season  # fallback
    best_score = -999.0
    for sub_name, dim_key, direction in rules:
        raw = float(profile.get(dim_key, 0.5))
        score = raw if direction == "highest" else -raw
        if score > best_score:
            best_score = score
            best_sub = sub_name

    neighbors = SUB_SEASON_ADJACENCY.get(best_sub, [])
    return {
        "value": best_sub,
        "confidence": seasonal_result.get("confidence", 0.0),
        "adjacent_sub_seasons": neighbors,
        "evidence_note": f"Within {season}, dominant dimension maps to {best_sub}. Adjacent: {', '.join(neighbors) if neighbors else 'none'}.",
    }


def _derive_color_dimension_profile(seasonal_result: Dict[str, Any]) -> Dict[str, Any]:
    """Surface the raw dimension scores as a first-class derived interpretation."""
    profile = seasonal_result.get("dimension_profile") or {}
    if not profile:
        return {"value": "unavailable", "confidence": 0.0, "evidence_note": "No dimension profile computed."}
    return {
        "value": "computed",
        "confidence": seasonal_result.get("confidence", 0.0),
        "warmth_score": profile.get("warmth_score", 0.0),
        "depth_score": profile.get("depth_score", 0.0),
        "skin_hair_contrast": profile.get("skin_hair_contrast", 0),
        "chroma_score": profile.get("chroma_score", 0.5),
        "ambiguous_temperature": profile.get("ambiguous_temperature", False),
        "evidence_note": (
            f"warmth={profile.get('warmth_score', 0):+.2f}, "
            f"depth={profile.get('depth_score', 0):.1f}, "
            f"contrast={profile.get('skin_hair_contrast', 0)}, "
            f"chroma={profile.get('chroma_score', 0):.2f}, "
            f"ambiguous={profile.get('ambiguous_temperature', False)}"
        ),
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
    # Height bonus/penalty removed — height doesn't change observed arm
    # volume or shoulder slope. A 155cm person with Full arms is broad;
    # a 185cm person with Slim arms is narrow. The old ±0.5 penalty
    # caused short+Full users to be misclassified as Balanced.

    if width_score >= 1:
        width_band = "Broad"
    elif width_score <= -1:
        width_band = "Narrow"
    else:
        width_band = "Balanced"

    label = {
        ("Light", "Narrow"): "Light and Narrow",
        ("Light", "Balanced"): "Light and Narrow",
        ("Light", "Broad"): "Light and Broad",
        ("Medium", "Narrow"): "Medium and Balanced",
        ("Medium", "Balanced"): "Medium and Balanced",
        ("Medium", "Broad"): "Medium and Balanced",
        ("Solid", "Narrow"): "Solid and Narrow",
        ("Solid", "Balanced"): "Solid and Balanced",
        ("Solid", "Broad"): "Solid and Broad",
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
