#!/usr/bin/env python3
"""Print distinct values per enrichment axis from the dumped CSV."""
import csv
import sys
from collections import Counter
from pathlib import Path

WORKTREE = Path(__file__).resolve().parents[2]
CSV_PATH = WORKTREE / "data" / "catalog_enriched_full.csv"

AXES = [
    "GarmentCategory", "GarmentSubtype", "GarmentLength",
    "SilhouetteContour", "SilhouetteType", "VolumeProfile",
    "FitEase", "FitType", "ShoulderStructure", "ShoulderExposure",
    "NecklineType", "NecklineDepth", "SleeveLength", "SleeveVolume",
    "SkinExposureLevel", "WaistDefinition", "HipDefinition", "BlouseLength",
    "FabricDrape", "FabricWeight", "FabricTexture", "FabricTransparency",
    "SurfaceFinish", "LayeringVisibility", "StretchLevel", "EdgeSharpness",
    "ConstructionDetail",
    "EmbellishmentLevel", "EmbellishmentType", "EmbellishmentZone",
    "VolumePlacement", "AsymmetryType", "AttachmentStructure", "MotionBehavior",
    "BorderContrast", "VerticalWeightBias", "VisualWeightPlacement",
    "StructuralFocus", "BodyFocusZone", "LineDirection",
    "PatternType", "PatternScale", "PatternOrientation",
    "ContrastLevel", "ColorTemperature", "ColorSaturation", "ColorValue", "ColorCount",
    "FormalitySignalStrength", "FormalityLevel",
    "OccasionFit", "OccasionSignal", "TimeOfDay",
    "GenderExpression", "StylingCompleteness",
]


def main() -> int:
    csv.field_size_limit(sys.maxsize)
    counters: dict[str, Counter] = {ax: Counter() for ax in AXES}
    with open(CSV_PATH, "r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            for ax in AXES:
                v = (row.get(ax) or "").strip()
                if v:
                    counters[ax][v] += 1
    for ax in AXES:
        if not counters[ax]:
            continue
        print(f"\n### {ax} ({len(counters[ax])} values)")
        for v, n in counters[ax].most_common():
            print(f"  {v:35s} {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
