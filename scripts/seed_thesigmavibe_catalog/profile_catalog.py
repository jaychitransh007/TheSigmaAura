#!/usr/bin/env python3
"""Profile the dumped catalog CSV.

Reports row counts, subtype distribution, distinct values per axis,
image / price / URL coverage, and inspects raw_row_json for brand.
"""
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urlparse

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
    "PrimaryColor", "SecondaryColor",
]


def main() -> int:
    if not CSV_PATH.exists():
        print(f"ERROR: {CSV_PATH} not found. Run dump_catalog.py first.", file=sys.stderr)
        return 1

    csv.field_size_limit(sys.maxsize)

    total = 0
    with_image_0 = 0
    with_image_1 = 0
    with_price = 0
    with_url = 0
    with_description = 0
    with_title = 0

    axis_values: dict[str, Counter] = {ax: Counter() for ax in AXES}
    retailer_prefix = Counter()
    url_hosts = Counter()
    raw_row_keys = Counter()
    raw_row_brand_samples = []

    sample_rows = []

    with open(CSV_PATH, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        columns = reader.fieldnames or []
        for row in reader:
            total += 1
            if (row.get("images_0_src") or "").strip():
                with_image_0 += 1
            if (row.get("images_1_src") or "").strip():
                with_image_1 += 1
            if (row.get("price") or "").strip():
                with_price += 1
            if (row.get("description") or "").strip():
                with_description += 1
            if (row.get("title") or "").strip():
                with_title += 1

            url = (row.get("url") or "").strip()
            if url:
                with_url += 1
                try:
                    host = urlparse(url).netloc.lower()
                    if host.startswith("www."):
                        host = host[4:]
                    url_hosts[host] += 1
                except Exception:
                    pass

            pid = (row.get("product_id") or "")
            if "_" in pid:
                retailer_prefix[pid.split("_")[0]] += 1

            for ax in AXES:
                v = (row.get(ax) or "").strip()
                if v:
                    axis_values[ax][v] += 1

            rr_raw = (row.get("raw_row_json") or "").strip()
            if rr_raw:
                try:
                    rr = json.loads(rr_raw)
                    if isinstance(rr, dict):
                        for k in rr.keys():
                            raw_row_keys[k] += 1
                        for bk in ("brand", "Brand", "vendor", "Vendor", "manufacturer"):
                            if bk in rr and rr[bk]:
                                if len(raw_row_brand_samples) < 10:
                                    raw_row_brand_samples.append((bk, str(rr[bk])[:80]))
                                break
                except Exception:
                    pass

            if len(sample_rows) < 5:
                sample_rows.append(row)

    print(f"Total rows: {total}")
    print(f"  with image_0_src: {with_image_0}")
    print(f"  with image_1_src: {with_image_1}")
    print(f"  with price:       {with_price}")
    print(f"  with url:         {with_url}")
    print(f"  with title:       {with_title}")
    print(f"  with description: {with_description}")
    print(f"\nColumns: {len(columns)}")

    print(f"\n--- Retailer prefix (product_id split on '_') ---")
    for prefix, n in retailer_prefix.most_common(20):
        print(f"  {prefix:20s} {n}")

    print(f"\n--- URL hosts (top 20) ---")
    for host, n in url_hosts.most_common(20):
        print(f"  {host:40s} {n}")

    print(f"\n--- GarmentSubtype distribution ---")
    for v, n in axis_values["GarmentSubtype"].most_common(40):
        print(f"  {v:30s} {n}")

    print(f"\n--- GarmentCategory distribution ---")
    for v, n in axis_values["GarmentCategory"].most_common():
        print(f"  {v:30s} {n}")

    print(f"\n--- GenderExpression distribution ---")
    for v, n in axis_values["GenderExpression"].most_common():
        print(f"  {v:30s} {n}")

    print(f"\n--- raw_row_json keys (top 30) ---")
    for k, n in raw_row_keys.most_common(30):
        print(f"  {k:30s} {n}")

    print(f"\n--- raw_row_json brand samples ---")
    for bk, v in raw_row_brand_samples:
        print(f"  {bk}: {v}")
    if not raw_row_brand_samples:
        print("  (no brand field found in raw_row_json)")

    print(f"\n--- Distinct value counts per axis ---")
    for ax in AXES:
        n_values = len(axis_values[ax])
        coverage = sum(axis_values[ax].values())
        if coverage:
            print(f"  {ax:30s} {n_values:4d} distinct, {coverage}/{total} populated ({100*coverage/total:.0f}%)")

    print(f"\n--- Sample 5 product_id + title + url ---")
    for r in sample_rows:
        print(f"  pid={r.get('product_id')!r:40s} title={(r.get('title') or '')[:50]!r:55s} url={(r.get('url') or '')[:60]}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
