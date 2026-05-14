"""Enum → phrase vocabulary for description generator.

Each axis maps enum values to two forms:
- `spec`: short phrase for spec bullets (factual, neutral)
- `lede`: longer phrase for prose lede (aspirational, playful)

Skip rule: values mapped to None or missing from the map are dropped
from both lede and bullets entirely. "none" / "undefined" / "not_applicable"
are intentionally absent — they're filtered before lookup.

Built against actual distinct values in catalog_enriched (2026-05-14
profile pass over 14,242 rows).
"""

# Values that should always cause the bullet/lede to be skipped.
SKIP_VALUES = {"none", "undefined", "not_applicable", "closed"}

# Per-axis: values to skip because they're the default / uninformative.
PER_AXIS_SKIP: dict[str, set[str]] = {
    "FabricTexture": {"smooth"},        # default; doesn't add info
    "ShoulderStructure": {"natural"},   # default
    "MotionBehavior": {"static"},       # default
    "WaistDefinition": {"undefined"},
    "HipDefinition": {"undefined"},
    "VolumePlacement": {"none"},
    "AsymmetryType": {"none"},
    "AttachmentStructure": {"none"},
    "ConstructionDetail": {"none"},
    "EmbellishmentZone": {"none"},
    "EmbellishmentType": {"none"},
    "EmbellishmentLevel": {"none"},
}


VOCAB: dict[str, dict[str, dict[str, str]]] = {
    "FitEase": {
        "slim":      {"spec": "Slim", "lede": "slim through the body"},
        "regular":   {"spec": "Regular", "lede": "easy regular fit"},
        "relaxed":   {"spec": "Relaxed", "lede": "relaxed and roomy"},
        "oversized": {"spec": "Oversized", "lede": "oversized in all the right places"},
    },
    "FitType": {
        "regular":  {"spec": "Regular", "lede": "regular cut"},
        "tailored": {"spec": "Tailored", "lede": "tailored close"},
        "relaxed":  {"spec": "Relaxed", "lede": "relaxed cut"},
        "loose":    {"spec": "Loose", "lede": "loose silhouette"},
        "slim":     {"spec": "Slim", "lede": "slim cut"},
        "boxy":     {"spec": "Boxy", "lede": "boxy silhouette"},
    },
    "GarmentLength": {
        "hip":       {"spec": "Hip-length", "lede": "hits at the hip"},
        "floor":     {"spec": "Floor-length", "lede": "sweeps the floor"},
        "ankle":     {"spec": "Ankle-length", "lede": "ankle-grazing"},
        "calf":      {"spec": "Calf-length", "lede": "lands at the calf"},
        "knee":      {"spec": "Knee-length", "lede": "ends at the knee"},
        "waist":     {"spec": "Waist-length", "lede": "cropped to the waist"},
        "mid_thigh": {"spec": "Mid-thigh", "lede": "mid-thigh"},
        "cropped":   {"spec": "Cropped", "lede": "cropped"},
        "thigh":     {"spec": "Thigh-length", "lede": "thigh-grazing"},
    },
    "FabricDrape": {
        "soft_structured": {"spec": "Soft-structured", "lede": "soft-structured fabric that holds its shape"},
        "fluid":           {"spec": "Fluid drape", "lede": "fluid drape with real movement"},
        "crisp":           {"spec": "Crisp", "lede": "crisp fabric with clean lines"},
        "rigid":           {"spec": "Structured", "lede": "structured fabric that holds form"},
    },
    "FabricWeight": {
        "very_light": {"spec": "Very lightweight", "lede": "feather-light"},
        "light":      {"spec": "Lightweight", "lede": "lightweight"},
        "medium":     {"spec": "Medium weight", "lede": "medium weight"},
        "heavy":      {"spec": "Heavyweight", "lede": "substantial and weighty"},
    },
    "FabricTexture": {
        "smooth":       {"spec": "Smooth weave", "lede": "smooth and clean"},
        "embroidered":  {"spec": "Embroidered", "lede": "richly embroidered"},
        "textured":     {"spec": "Textured", "lede": "textured surface"},
        "sheen":        {"spec": "Subtle sheen", "lede": "a soft sheen"},
        "sheer":        {"spec": "Sheer", "lede": "sheer and delicate"},
        "knit":         {"spec": "Knit", "lede": "knitted texture"},
        "metallic":     {"spec": "Metallic finish", "lede": "metallic shimmer"},
        "slub":         {"spec": "Slub texture", "lede": "slubby, organic texture"},
        "ribbed":       {"spec": "Ribbed", "lede": "ribbed weave"},
        "pleated":      {"spec": "Pleated", "lede": "pleated detailing"},
        "matte":        {"spec": "Matte finish", "lede": "matte finish"},
        "handloom":     {"spec": "Handloom", "lede": "handloom-woven"},
        "low_luster":   {"spec": "Low-luster", "lede": "low-luster finish"},
        "performance":  {"spec": "Performance fabric", "lede": "performance weave"},
    },
    "SurfaceFinish": {
        "matte":               {"spec": "Matte", "lede": "matte finish"},
        "sheen":               {"spec": "Soft sheen", "lede": "soft sheen"},
        "low_luster":          {"spec": "Low luster", "lede": "low-luster finish"},
        "high_shine_metallic": {"spec": "High-shine metallic", "lede": "high-shine metallic"},
        "antique_metallic":    {"spec": "Antique metallic", "lede": "antique metallic glow"},
        "brushed_metallic":    {"spec": "Brushed metallic", "lede": "brushed metallic"},
    },
    "NecklineType": {
        "collared":   {"spec": "Collared", "lede": "collared neckline"},
        "v_neck":     {"spec": "V-neck", "lede": "v-neckline"},
        "scoop":      {"spec": "Scoop neck", "lede": "scoop neckline"},
        "mandarin":   {"spec": "Mandarin collar", "lede": "mandarin collar"},
        "crew":       {"spec": "Crew neck", "lede": "crew neckline"},
        "sweetheart": {"spec": "Sweetheart", "lede": "sweetheart neckline"},
        "square":     {"spec": "Square neck", "lede": "square neckline"},
        "high_neck":  {"spec": "High neck", "lede": "high neckline"},
        "notched":    {"spec": "Notched", "lede": "notched lapel"},
        "halter":     {"spec": "Halter", "lede": "halter neckline"},
        "boat":       {"spec": "Boat neck", "lede": "boat neckline"},
        "asymmetric": {"spec": "Asymmetric", "lede": "asymmetric neckline"},
    },
    "SleeveLength": {
        "full":           {"spec": "Full sleeves", "lede": "full sleeves"},
        "three_quarter":  {"spec": "Three-quarter sleeves", "lede": "three-quarter sleeves"},
        "sleeveless":     {"spec": "Sleeveless", "lede": "sleeveless"},
        "short":          {"spec": "Short sleeves", "lede": "short sleeves"},
        "elbow":          {"spec": "Elbow-length sleeves", "lede": "elbow-length sleeves"},
        "cap":            {"spec": "Cap sleeves", "lede": "cap sleeves"},
    },
    "SleeveVolume": {
        "moderate": {"spec": "Moderate volume", "lede": ""},
        "slim":     {"spec": "Slim sleeves", "lede": "slim sleeves"},
        "puff":     {"spec": "Puff sleeves", "lede": "puff sleeves"},
        "bishop":   {"spec": "Bishop sleeves", "lede": "bishop sleeves"},
        "dramatic": {"spec": "Dramatic sleeves", "lede": "dramatic statement sleeves"},
    },
    "ShoulderExposure": {
        "cap_exposed":   {"spec": "Cap-exposed", "lede": "cap-exposed shoulder"},
        "one_shoulder":  {"spec": "One-shoulder", "lede": "one-shoulder cut"},
        "off_shoulder":  {"spec": "Off-shoulder", "lede": "off-shoulder"},
        "strapless":     {"spec": "Strapless", "lede": "strapless"},
        "cold_shoulder": {"spec": "Cold-shoulder", "lede": "cold-shoulder cutouts"},
    },
    "WaistDefinition": {
        "natural":  {"spec": "Natural waist", "lede": "sits at the natural waist"},
        "defined":  {"spec": "Defined waist", "lede": "defined waist"},
        "cinched":  {"spec": "Cinched waist", "lede": "cinched at the waist"},
        "empire":   {"spec": "Empire waist", "lede": "empire waist"},
        "belted":   {"spec": "Belted", "lede": "belted at the waist"},
        "dropped":  {"spec": "Dropped waist", "lede": "dropped waist"},
    },
    "PatternType": {
        # "solid" intentionally absent — solid = no pattern, drop the bullet.
        "floral":             {"spec": "Floral print", "lede": "floral print"},
        "motif":              {"spec": "Motif print", "lede": "motif print"},
        "ethnic":             {"spec": "Ethnic motif", "lede": "ethnic motifs"},
        "textured":           {"spec": "Textured pattern", "lede": "textured pattern"},
        "stripes_vertical":   {"spec": "Vertical stripes", "lede": "vertical stripes"},
        "stripes_horizontal": {"spec": "Horizontal stripes", "lede": "horizontal stripes"},
        "abstract":           {"spec": "Abstract print", "lede": "abstract print"},
        "geometric":          {"spec": "Geometric print", "lede": "geometric print"},
        "checks":             {"spec": "Checks", "lede": "checked pattern"},
        "animal":             {"spec": "Animal print", "lede": "animal print"},
    },
    "EmbellishmentLevel": {
        "minimal":   {"spec": "Minimal embellishment", "lede": "subtly embellished"},
        "moderate":  {"spec": "Moderate embellishment", "lede": "tastefully embellished"},
        "heavy":     {"spec": "Heavy embellishment", "lede": "richly embellished"},
        "subtle":    {"spec": "Subtle embellishment", "lede": "delicately embellished"},
        "statement": {"spec": "Statement embellishment", "lede": "statement-making embellishment"},
    },
    "EmbellishmentType": {
        "embroidery":       {"spec": "Embroidery", "lede": "embroidered detailing"},
        "print":            {"spec": "Print", "lede": "printed pattern"},
        "mixed":            {"spec": "Mixed embellishment", "lede": "mixed detailing"},
        "beading":          {"spec": "Beadwork", "lede": "beadwork"},
        "self_texture":     {"spec": "Self-texture", "lede": "self-textured surface"},
        "sequins":          {"spec": "Sequins", "lede": "sequin accents"},
        "applique":         {"spec": "Appliqué", "lede": "appliqué detailing"},
        "mirror_work":      {"spec": "Mirror work", "lede": "mirror work"},
        "studs":            {"spec": "Studs", "lede": "stud accents"},
        "distressing":      {"spec": "Distressed", "lede": "distressed finish"},
        "tonal_embroidery": {"spec": "Tonal embroidery", "lede": "tonal embroidery"},
        "lace":             {"spec": "Lace", "lede": "lace detailing"},
        "chikankari":       {"spec": "Chikankari", "lede": "chikankari embroidery"},
        "kantha":           {"spec": "Kantha", "lede": "kantha stitching"},
    },
    "OccasionFit": {
        "festive":      {"spec": "Festive", "lede": "festive-ready"},
        "casual":       {"spec": "Casual", "lede": "everyday casual"},
        "smart_casual": {"spec": "Smart casual", "lede": "smart casual"},
        "traditional":  {"spec": "Traditional", "lede": "traditional"},
        "very_casual":  {"spec": "Very casual", "lede": "laid-back"},
        "party":        {"spec": "Party", "lede": "party-ready"},
        "workwear":     {"spec": "Workwear", "lede": "office-ready"},
        "semi_formal":  {"spec": "Semi-formal", "lede": "semi-formal"},
        "active":       {"spec": "Active", "lede": "built for movement"},
        "travel":       {"spec": "Travel", "lede": "travel-ready"},
        "formal":       {"spec": "Formal", "lede": "formal"},
    },
    "FormalityLevel": {
        "casual":       {"spec": "Casual", "lede": "casual"},
        "smart_casual": {"spec": "Smart casual", "lede": "smart casual"},
        "semi_formal":  {"spec": "Semi-formal", "lede": "semi-formal"},
        "formal":       {"spec": "Formal", "lede": "formal"},
        "ceremonial":   {"spec": "Ceremonial", "lede": "ceremonial"},
    },
    "MotionBehavior": {
        # "fluid" intentionally has empty lede — it duplicates FabricDrape=fluid
        # in prose. Bullet spec still works.
        "fluid":   {"spec": "Fluid movement", "lede": ""},
        "swish":   {"spec": "Swishes when you walk", "lede": "swishes with every step"},
        "static":  {"spec": "Structured", "lede": ""},
        "flutter": {"spec": "Flutter movement", "lede": "flutters beautifully"},
        "trail":   {"spec": "Trailing drape", "lede": "trails behind you"},
        "bounce":  {"spec": "Bounce", "lede": "with bounce"},
    },
    "BorderContrast": {
        "high":   {"spec": "High-contrast border", "lede": "high-contrast border"},
        "medium": {"spec": "Contrast border", "lede": "contrasting border"},
        "low":    {"spec": "Tonal border", "lede": "tonal border"},
    },
    "ColorTemperature": {
        "warm":    {"spec": "Warm tones", "lede": "warm"},
        "cool":    {"spec": "Cool tones", "lede": "cool"},
        "neutral": {"spec": "Neutral tones", "lede": "neutral"},
        "mixed":   {"spec": "Mixed tones", "lede": "mixed"},
    },
    "ColorValue": {
        "very_light": {"spec": "Very light", "lede": "very light"},
        "light":      {"spec": "Light", "lede": "light"},
        "mid":        {"spec": "Mid-toned", "lede": "mid-toned"},
        "dark":       {"spec": "Dark", "lede": "deep"},
        "very_dark":  {"spec": "Very dark", "lede": "very dark"},
    },
    "AttachmentStructure": {
        "attached_panel":    {"spec": "Attached panel", "lede": "with an attached panel"},
        "detachable_layer":  {"spec": "Detachable layer", "lede": "with a detachable layer"},
        "attached_drape":    {"spec": "Attached drape", "lede": "with an attached drape"},
        "attached_sash":     {"spec": "Attached sash", "lede": "with an attached sash"},
        "attached_cape":     {"spec": "Attached cape", "lede": "with an attached cape"},
        "attached_dupatta":  {"spec": "Attached dupatta", "lede": "with an attached dupatta"},
    },
    "ConstructionDetail": {
        "pleated":         {"spec": "Pleated", "lede": "pleated construction"},
        "gathered":        {"spec": "Gathered", "lede": "gathered detailing"},
        "draped":          {"spec": "Draped", "lede": "draped silhouette"},
        "utility":         {"spec": "Utility detailing", "lede": "utility detailing"},
        "deconstructed":   {"spec": "Deconstructed", "lede": "deconstructed cut"},
        "asymmetric_hem":  {"spec": "Asymmetric hem", "lede": "asymmetric hem"},
        "smocked":         {"spec": "Smocked", "lede": "smocked"},
        "ruched":          {"spec": "Ruched", "lede": "ruched detailing"},
        "experimental":    {"spec": "Experimental cut", "lede": "experimental cut"},
    },
}


def lookup(axis: str, value: str | None) -> dict[str, str] | None:
    """Return {spec, lede} for an axis value, or None if it should be skipped."""
    if not value:
        return None
    v = value.strip().lower()
    if v in SKIP_VALUES:
        return None
    if v in PER_AXIS_SKIP.get(axis, set()):
        return None
    axis_map = VOCAB.get(axis)
    if not axis_map:
        return None
    return axis_map.get(v)
