import csv
from pathlib import Path
from typing import Any, Dict, Iterable, List


def _is_ignored_catalog_key(key: str, ignored: set[str]) -> bool:
    normalized = str(key or "").strip()
    if normalized in ignored:
        return True
    return normalized.lower().startswith("unnamed:")


def read_catalog_rows(csv_path: str) -> List[Dict[str, str]]:
    path = Path(csv_path)
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_jsonl(path: str, rows: Iterable[dict]) -> None:
    import json

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=True) + "\n")


def build_catalog_item_rows(rows: Iterable[Dict[str, str]]) -> List[Dict[str, Any]]:
    output: List[Dict[str, Any]] = []
    for index, row in enumerate(rows):
        product_id = str(row.get("id") or "").strip()
        if not product_id:
            continue
        row_id = str(row.get("") or index)
        price_value = str(row.get("price") or "").strip()
        try:
            price = float(price_value) if price_value else None
        except ValueError:
            price = None
        output.append(
            {
                "catalog_row_id": row_id,
                "product_id": product_id,
                "title": str(row.get("title") or ""),
                "description": str(row.get("description") or ""),
                "price": price,
                "primary_image_url": str(row.get("images__0__src") or ""),
                "secondary_image_url": str(row.get("images__1__src") or ""),
                "product_url": str(row.get("url") or ""),
                "row_status": str(row.get("row_status") or ""),
                "error_reason": str(row.get("error_reason") or ""),
                "metadata_json": dict(row),
            }
        )
    return output


def build_catalog_enriched_rows(rows: Iterable[Dict[str, str]]) -> List[Dict[str, Any]]:
    output: List[Dict[str, Any]] = []
    ignored = {
        "",
        "id",
        "product_id",
        "source_row_number",
        "title",
        "description",
        "price",
        "images__0__src",
        "images__1__src",
        "images_0_src",
        "images_1_src",
        "url",
        "row_status",
        "error_reason",
    }
    for index, row in enumerate(rows):
        product_id = str(row.get("product_id") or row.get("id") or "").strip()
        if not product_id:
            continue
        source_row_number = str(row.get("source_row_number") or row.get("") or "").strip()
        price_value = str(row.get("price") or "").strip()
        try:
            price = float(price_value) if price_value else None
        except ValueError:
            price = None

        record: Dict[str, Any] = {
            "product_id": product_id,
            "source_row_number": int(source_row_number) if source_row_number.isdigit() else index,
            "title": str(row.get("title") or ""),
            "description": str(row.get("description") or ""),
            "price": price,
            "images_0_src": str(row.get("images_0_src") or row.get("images__0__src") or ""),
            "images_1_src": str(row.get("images_1_src") or row.get("images__1__src") or ""),
            "url": str(row.get("url") or ""),
            "row_status": str(row.get("row_status") or ""),
            "error_reason": str(row.get("error_reason") or ""),
            "raw_row_json": dict(row),
        }
        for key, value in row.items():
            if _is_ignored_catalog_key(key, ignored):
                continue
            record[key] = value
        output.append(record)
    return output
