"""Description + handle + tag generators for the Shopify import.

All deterministic. No LLM at generation time.
"""
import re
from html import escape

from brands import brand_from_url
from hooks import pick_hook
from vocabulary import lookup

CONFIDENCE_FLOOR_LEDE = 0.6
CONFIDENCE_FLOOR_BULLETS = 0.5


def _get(row: dict, key: str) -> str:
    return (row.get(key) or "").strip()


def _conf(row: dict, axis: str) -> float:
    raw = (row.get(f"{axis}_confidence") or "").strip()
    if not raw:
        return 1.0  # absent confidence column → trust the value
    try:
        return float(raw)
    except ValueError:
        return 1.0


def _attr_for_prose(row: dict, axis: str) -> dict | None:
    """Return vocab entry for an axis if confidence ≥ lede floor."""
    if _conf(row, axis) < CONFIDENCE_FLOOR_LEDE:
        return None
    return lookup(axis, _get(row, axis))


def _attr_for_bullet(row: dict, axis: str) -> dict | None:
    """Return vocab entry for an axis if confidence ≥ bullet floor."""
    if _conf(row, axis) < CONFIDENCE_FLOOR_BULLETS:
        return None
    return lookup(axis, _get(row, axis))


def _humanize_subtype(subtype: str) -> str:
    return subtype.replace("_", " ").title() if subtype else ""


# Sets and ethnic single-garment subtypes treated as the "ethnic" branch.
ETHNIC_SUBTYPES = {
    "saree", "salwar_set", "kurta_set", "kurta", "kurti",
    "anarkali", "salwar_suit", "suit_set", "lehenga_set",
    "ethnic_set", "nehru_jacket", "tunic", "gown", "blouse",
}


def is_ethnic(subtype: str) -> bool:
    return (subtype or "").strip().lower() in ETHNIC_SUBTYPES


def _humanize_color(color: str) -> str:
    return (color or "").replace("_", " ").strip().lower()


def build_lede(row: dict) -> str:
    """Build the lede paragraph: hook + color + 1-2 attribute phrases.

    Structure: ``{Hook (sans final period)} — in {color phrase}, with {middle phrases}.``
    Falls back gracefully when any piece is missing.
    """
    product_id = _get(row, "product_id")
    subtype = _get(row, "GarmentSubtype")
    category = _get(row, "GarmentCategory")

    hook = pick_hook(product_id, subtype, category)
    hook_body = hook.rstrip(".")

    primary_color = _humanize_color(_get(row, "PrimaryColor"))
    secondary_color = _humanize_color(_get(row, "SecondaryColor"))

    color_phrase = ""
    if primary_color:
        if secondary_color and secondary_color != primary_color:
            color_phrase = f"in {primary_color} with {secondary_color} accents"
        else:
            color_phrase = f"in {primary_color}"

    # Middle phrases: fabric drape, embellishment, and (for non-bottom)
    # motion behavior. Skip motion on bottoms — "swishes" doesn't fit jeans.
    middle: list[str] = []
    fabric_phrase = _attr_for_prose(row, "FabricDrape")
    if fabric_phrase and fabric_phrase.get("lede"):
        middle.append(fabric_phrase["lede"])

    embellishment_phrase = _attr_for_prose(row, "EmbellishmentLevel")
    if embellishment_phrase and embellishment_phrase.get("lede"):
        middle.append(embellishment_phrase["lede"])

    if category != "bottom":
        motion_phrase = _attr_for_prose(row, "MotionBehavior")
        if motion_phrase and motion_phrase.get("lede"):
            middle.append(motion_phrase["lede"])

    middle = [m for m in middle if m][:2]

    if color_phrase and middle:
        # No connector "with" — middle phrases often contain "with" themselves
        # (e.g., "crisp fabric with clean lines"). Comma-join keeps it natural.
        return f"{hook_body} — {color_phrase}, {', '.join(middle)}."
    if color_phrase:
        return f"{hook_body} — {color_phrase}."
    if middle:
        joined = ", ".join(middle)
        return f"{hook_body}. {joined[0].upper() + joined[1:]}."
    return hook


def _bullet(label: str, value: str) -> str:
    return f"<li><strong>{escape(label)}:</strong> {escape(value)}</li>"


def build_bullets(row: dict) -> list[str]:
    """Build the spec bullets list. Returns list of <li> HTML strings."""
    subtype = _get(row, "GarmentSubtype")
    category = _get(row, "GarmentCategory")
    bullets: list[str] = []

    # Fit (skip for ethnic single drape garments).
    if subtype != "saree":
        fit = _attr_for_bullet(row, "FitEase")
        if fit:
            bullets.append(_bullet("Fit", fit["spec"]))

    # Fabric: drape goes in "Fabric" bullet. Texture gets its own bullet
    # only when it's interesting (smooth is skipped via PER_AXIS_SKIP).
    fabric_drape = _attr_for_bullet(row, "FabricDrape")
    if fabric_drape:
        bullets.append(_bullet("Fabric", fabric_drape["spec"]))
    fabric_texture = _attr_for_bullet(row, "FabricTexture")
    if fabric_texture:
        bullets.append(_bullet("Texture", fabric_texture["spec"]))

    # Pattern (skip if solid).
    pattern = _attr_for_bullet(row, "PatternType")
    if pattern:
        bullets.append(_bullet("Pattern", pattern["spec"]))

    # Neckline (top / one_piece / set categories).
    if category in {"top", "one_piece", "set", "outerwear"} and subtype != "saree":
        neckline = _attr_for_bullet(row, "NecklineType")
        if neckline:
            bullets.append(_bullet("Neckline", neckline["spec"]))

    # Sleeves.
    if category in {"top", "one_piece", "set", "outerwear"} and subtype != "saree":
        sleeve = _attr_for_bullet(row, "SleeveLength")
        if sleeve:
            sleeve_label = sleeve["spec"]
            sleeve_vol = _attr_for_bullet(row, "SleeveVolume")
            if sleeve_vol and sleeve_vol["spec"].lower() != "moderate volume":
                sleeve_label = f"{sleeve['spec']} ({sleeve_vol['spec'].lower()})"
            bullets.append(_bullet("Sleeves", sleeve_label))

    # Length (mostly for one_piece, bottom, outerwear).
    if category in {"one_piece", "bottom", "outerwear", "top"}:
        length = _attr_for_bullet(row, "GarmentLength")
        if length:
            bullets.append(_bullet("Length", length["spec"]))

    # Embellishment.
    embellishment_type = _attr_for_bullet(row, "EmbellishmentType")
    if embellishment_type:
        bullets.append(_bullet("Embellishment", embellishment_type["spec"]))

    # Border (ethnic-specific).
    border = _attr_for_bullet(row, "BorderContrast")
    if border and is_ethnic(subtype):
        bullets.append(_bullet("Border", border["spec"]))

    # Attached structure (dupatta, drape, cape).
    attach = _attr_for_bullet(row, "AttachmentStructure")
    if attach:
        bullets.append(_bullet("Detail", attach["spec"]))

    # Occasion.
    occasion = _attr_for_bullet(row, "OccasionFit")
    if occasion:
        bullets.append(_bullet("Occasion", occasion["spec"]))

    # Sizes (always last).
    bullets.append(_bullet("Sizes", "XS, S, M, L, XL"))

    return bullets


def build_description_html(row: dict) -> str:
    """Assemble the full HTML description: lede paragraph + spec bullets."""
    lede = build_lede(row)
    bullets = build_bullets(row)
    bullets_html = "\n".join(bullets)
    return (
        f"<p>{escape(lede)}</p>\n"
        f"<p><strong>The vibe:</strong></p>\n"
        f"<ul>\n{bullets_html}\n</ul>"
    )


_HANDLE_NORMALIZE = re.compile(r"[^a-z0-9]+")


def _kebab(text: str) -> str:
    text = (text or "").lower()
    text = _HANDLE_NORMALIZE.sub("-", text)
    return text.strip("-")


def build_handle(brand: str, title: str, product_id: str) -> str:
    """Deterministic, collision-free handle: {brand}-{title-words}-{pid_suffix}."""
    brand_slug = _kebab(brand) or "vibe"
    title_words = _kebab(title)
    # Limit title slug to 60 chars to keep URLs readable.
    if len(title_words) > 60:
        title_words = title_words[:60].rsplit("-", 1)[0]
    pid_suffix = _kebab(product_id)[-10:] if product_id else ""
    parts = [brand_slug]
    if title_words:
        parts.append(title_words)
    if pid_suffix:
        parts.append(pid_suffix)
    return "-".join(parts)


def build_tags(row: dict, brand: str) -> str:
    """Comma-separated tag list. Drives Shopify auto-collections later."""
    tags: list[str] = []
    if brand:
        tags.append(brand)
    category = _get(row, "GarmentCategory")
    if category:
        tags.append(category.replace("_", " ").title())
    subtype = _get(row, "GarmentSubtype")
    if subtype:
        tags.append(_humanize_subtype(subtype))
    gender = _get(row, "GenderExpression")
    if gender:
        tags.append({"feminine": "Women", "masculine": "Men", "unisex": "Unisex"}.get(gender.lower(), gender.title()))
    occasion = _get(row, "OccasionFit")
    if occasion:
        tags.append(occasion.replace("_", " ").title())
    pattern = _get(row, "PatternType")
    if pattern and pattern.lower() != "solid":
        tags.append(pattern.replace("_", " ").title())
    primary = _get(row, "PrimaryColor")
    if primary:
        tags.append(primary.replace("_", " ").strip().title())
    return ", ".join(tags)


def build_type(row: dict) -> str:
    return _humanize_subtype(_get(row, "GarmentSubtype"))


def build_seo_title(title: str, brand: str) -> str:
    base = title or ""
    if brand and brand.lower() not in base.lower():
        base = f"{base} | {brand}"
    return base[:70]


def build_seo_description(lede: str) -> str:
    # Strip nothing — lede is plain text already.
    return lede[:160]
