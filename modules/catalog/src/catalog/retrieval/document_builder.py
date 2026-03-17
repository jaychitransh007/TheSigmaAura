from typing import Dict, Iterable, List, Tuple

from .config import CatalogEmbeddingConfig
from .confidence_policy import confidence_aware_value, normalize_confidence
from .normalizers import clean_text, safe_text
from .schemas import CatalogDocument


ATTRIBUTE_SECTIONS: List[Tuple[str, List[str]]] = [
    ("GARMENT_IDENTITY", ["GarmentCategory", "GarmentSubtype", "GarmentLength", "StylingCompleteness", "GenderExpression"]),
    ("SILHOUETTE_AND_FIT", ["SilhouetteContour", "SilhouetteType", "VolumeProfile", "FitEase", "FitType", "ShoulderStructure", "WaistDefinition", "HipDefinition"]),
    ("NECKLINE_SLEEVE_EXPOSURE", ["NecklineType", "NecklineDepth", "SleeveLength", "SkinExposureLevel"]),
    ("FABRIC_AND_BUILD", ["FabricDrape", "FabricWeight", "FabricTexture", "StretchLevel", "EdgeSharpness", "ConstructionDetail"]),
    ("EMBELLISHMENT", ["EmbellishmentLevel", "EmbellishmentType", "EmbellishmentZone"]),
    ("VISUAL_DIRECTION", ["VerticalWeightBias", "VisualWeightPlacement", "StructuralFocus", "BodyFocusZone", "LineDirection"]),
    ("PATTERN_AND_COLOR", ["PatternType", "PatternScale", "PatternOrientation", "ContrastLevel", "ColorTemperature", "ColorSaturation", "ColorValue", "ColorCount", "PrimaryColor", "SecondaryColor"]),
    ("OCCASION_AND_SIGNAL", ["FormalitySignalStrength", "FormalityLevel", "OccasionFit", "OccasionSignal", "TimeOfDay"]),
]
EMBEDDABLE_ROW_STATUS = {"ok", "complete"}


def build_catalog_document(row: Dict[str, str], row_index: int, config: CatalogEmbeddingConfig) -> CatalogDocument:
    row_id = str(row.get("source_row_number") or row.get("") or row_index)
    product_id = str(row.get("product_id") or row.get("id") or "")
    lines = [
        "CATALOG_ROW:",
        f"- row_id: {row_id}",
        f"- product_id: {safe_text(product_id)}",
        f"- row_status: {safe_text(row.get('row_status'))}",
        f"- error_reason: {safe_text(row.get('error_reason'))}",
        "",
        "PRODUCT:",
        f"- title: {safe_text(row.get('title'))}",
        f"- description: {clean_text(row.get('description'), max_chars=config.max_description_chars)}",
        f"- price: {safe_text(row.get('price'))}",
        f"- product_url: {safe_text(row.get('url'))}",
        f"- image_primary: {safe_text(row.get('images_0_src') or row.get('images__0__src'))}",
        f"- image_secondary: {safe_text(row.get('images_1_src') or row.get('images__1__src'))}",
    ]
    for section_name, attributes in ATTRIBUTE_SECTIONS:
        lines.extend(["", f"{section_name}:"])
        for attribute in attributes:
            confidence = normalize_confidence(row.get(f"{attribute}_confidence"))
            value = confidence_aware_value(
                row.get(attribute),
                row.get(f"{attribute}_confidence"),
                min_keep_value=config.min_confidence_keep_value,
                min_mark_uncertain=config.min_confidence_mark_uncertain,
            )
            lines.append(f"- {attribute}: {value} [confidence={confidence:.2f}]")
    metadata = {
        "row_status": safe_text(row.get("row_status")),
        "GarmentCategory": safe_text(row.get("GarmentCategory")),
        "GarmentSubtype": safe_text(row.get("GarmentSubtype")),
        "StylingCompleteness": safe_text(row.get("StylingCompleteness")),
        "GenderExpression": safe_text(row.get("GenderExpression")),
        "FormalityLevel": safe_text(row.get("FormalityLevel")),
        "OccasionFit": safe_text(row.get("OccasionFit")),
        "TimeOfDay": safe_text(row.get("TimeOfDay")),
        "PrimaryColor": safe_text(row.get("PrimaryColor")),
        "price": safe_text(row.get("price")),
    }
    return CatalogDocument(
        row_id=row_id,
        product_id=product_id,
        metadata=metadata,
        document_text="\n".join(lines),
    )


def iter_catalog_documents(rows: Iterable[Dict[str, str]], config: CatalogEmbeddingConfig) -> Iterable[CatalogDocument]:
    count = 0
    for idx, row in enumerate(rows):
        if config.require_complete_rows_only and str(row.get("row_status") or "").strip().lower() not in EMBEDDABLE_ROW_STATUS:
            continue
        yield build_catalog_document(row, idx, config)
        count += 1
        if config.max_rows > 0 and count >= config.max_rows:
            break
