ATTRIBUTES = {
    "GarmentLength": [
        "cropped", "waist", "hip", "mid_thigh", "thigh", "knee", "calf", "ankle", "floor",
    ],
    "SilhouetteType": [
        "straight", "fitted", "relaxed", "oversized", "flared", "a_line", "tapered",
        "boxy", "wrap", "peplum", "empire", "mermaid",
    ],
    "FitType": ["slim", "regular", "relaxed", "boxy", "tailored", "loose"],
    "VisualWeightPlacement": ["upper", "upper_biased", "center", "lower_biased", "lower", "distributed"],
    "NecklineType": [
        "crew", "v_neck", "scoop", "collared", "square", "high_neck", "boat", "halter",
        "sweetheart", "asymmetric", "notched", "mandarin",
    ],
    "NecklineDepth": ["closed", "shallow", "moderate", "deep", "very_deep"],
    "SleeveLength": ["sleeveless", "cap", "short", "elbow", "three_quarter", "full"],
    "SkinExposureLevel": ["very_low", "low", "medium", "high", "very_high"],
    "FormalitySignalStrength": ["low", "medium", "high", "very_high"],
    "OccasionFit": [
        "very_casual", "casual", "smart_casual", "semi_formal", "formal", "traditional",
        "festive", "party", "workwear", "active", "travel",
    ],
    "TimeOfDay": ["day", "evening", "night", "day_to_night"],
    "ColorTemperature": ["warm", "cool", "neutral", "mixed"],
    "ColorSaturation": ["muted", "medium", "high", "very_high"],
    "ColorCount": ["single", "tonal", "two_color", "three_color", "multi_color"],
    "ColorValue": ["very_light", "light", "mid", "dark", "very_dark"],
    "ConstructionDetail": ["none", "ruched", "gathered", "draped", "pleated", "smocked", "asymmetric_hem"],
    "ContrastLevel": ["low", "medium", "high", "very_high"],
    "PatternType": [
        "solid", "stripes_vertical", "stripes_horizontal", "checks", "abstract", "floral",
        "geometric", "ethnic", "motif", "textured", "animal",
    ],
    "PatternScale": ["small", "medium", "large", "mixed"],
    "PatternOrientation": ["vertical", "horizontal", "diagonal", "allover"],
    "FabricDrape": ["fluid", "semi_fluid", "crisp", "stiff"],
    "FabricWeight": ["very_light", "light", "medium", "heavy"],
    "FabricTexture": ["matte", "semi_sheen", "sheen", "textured", "metallic", "embroidered"],
    "WaistDefinition": ["undefined", "natural", "defined", "cinched", "dropped", "empire"],
    "EmbellishmentLevel": ["none", "minimal", "subtle", "moderate", "heavy", "statement"],
    "EmbellishmentZone": ["neckline", "shoulder", "waist", "hem", "sleeve", "back", "allover"],
    "BodyFocusZone": ["shoulders", "bust", "waist", "hips", "legs", "back", "full_length", "face_neck"],
}

ATTRIBUTE_NAMES = list(ATTRIBUTES.keys())

