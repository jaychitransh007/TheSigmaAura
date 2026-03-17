import csv
from typing import Any, Dict, List

from .attributes import ATTRIBUTE_NAMES


def merge_rows(
    original_rows: List[Dict[str, str]],
    parsed_results: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    merged: List[Dict[str, Any]] = []
    for idx, row in enumerate(original_rows):
        key = f"row_{idx}"
        result = parsed_results.get(key, {"row_status": "missing", "error_reason": "No result"})
        merged_row: Dict[str, Any] = dict(row)
        for attr in ATTRIBUTE_NAMES:
            merged_row[attr] = result.get(attr)
            merged_row[f"{attr}_confidence"] = result.get(f"{attr}_confidence")
        merged_row["row_status"] = result.get("row_status", "missing")
        merged_row["error_reason"] = result.get("error_reason", "")
        merged.append(merged_row)
    return merged


def write_csv(rows: List[Dict[str, Any]], path: str) -> None:
    if not rows:
        raise ValueError("No rows to write.")
    fieldnames = list(rows[0].keys())
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

