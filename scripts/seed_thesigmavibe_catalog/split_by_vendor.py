#!/usr/bin/env python3
"""Split the combined Shopify import CSV into one file per vendor.

Output: data/shopify_imports/{vendor_slug}.csv

Each output is a self-contained Shopify CSV: header row + all rows
belonging to that vendor (including the product-level row, variant rows,
and image-only rows for each product). Image-only rows have empty Vendor
field, so we group by Handle and tag every row in a handle-group to the
product-level vendor we saw on the first row of that handle.
"""
import csv
import re
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
WORKTREE = HERE.parent.parent
INPUT_CSV = WORKTREE / "data" / "thesigmavibe_shopify_import.csv"
OUTPUT_DIR = WORKTREE / "data" / "shopify_imports"

_SLUG = re.compile(r"[^a-z0-9]+")


def slug(text: str) -> str:
    return _SLUG.sub("-", (text or "").lower()).strip("-")


def main() -> int:
    csv.field_size_limit(sys.maxsize)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Read once to map Handle → Vendor (vendor only set on first row of a product).
    handle_to_vendor: dict[str, str] = {}
    fieldnames: list[str] = []
    with open(INPUT_CSV, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        for r in reader:
            handle = r.get("Handle", "")
            vendor = (r.get("Vendor") or "").strip()
            if handle and vendor and handle not in handle_to_vendor:
                handle_to_vendor[handle] = vendor

    # Open one writer per vendor.
    writers: dict[str, csv.DictWriter] = {}
    files: dict[str, any] = {}
    counts: dict[str, int] = defaultdict(int)

    try:
        with open(INPUT_CSV, "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for r in reader:
                handle = r.get("Handle", "")
                vendor = handle_to_vendor.get(handle, "unknown")
                if vendor not in writers:
                    out_path = OUTPUT_DIR / f"{slug(vendor)}.csv"
                    fp = open(out_path, "w", encoding="utf-8", newline="")
                    writer = csv.DictWriter(fp, fieldnames=fieldnames)
                    writer.writeheader()
                    writers[vendor] = writer
                    files[vendor] = fp
                writers[vendor].writerow(r)
                counts[vendor] += 1
    finally:
        for fp in files.values():
            fp.close()

    print(f"Wrote {len(writers)} per-vendor files to {OUTPUT_DIR}/")
    print()
    print(f"{'Vendor':<20} {'Rows':>10} {'Size':>10}")
    print("-" * 44)
    for vendor in sorted(counts, key=counts.get, reverse=True):
        out_path = OUTPUT_DIR / f"{slug(vendor)}.csv"
        size_bytes = out_path.stat().st_size
        size_str = f"{size_bytes / 1024 / 1024:.1f} MB" if size_bytes > 1024 * 1024 else f"{size_bytes / 1024:.0f} KB"
        print(f"{vendor:<20} {counts[vendor]:>10} {size_str:>10}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
