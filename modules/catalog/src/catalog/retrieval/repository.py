import csv
from pathlib import Path
from typing import Any, Dict, Iterable, List


_STORE_DOMAINS = {
    "andamen": "andamen.com",
    "bunaai": "bunaai.com",
    "dashanddot": "dashanddot.com",
    "houseoffett": "houseoffett.com",
    "ikkivi": "ikkivi.com",
    "kalki": "kalkifashion.com",
    "kharakapas": "kharakapas.com",
    "lovepangolin": "lovepangolin.com",
    "nicobar": "nicobar.com",
    "powerlook": "powerlook.in",
    "saltattire": "saltattire.com",
    "suta": "suta.in",
    "thebearhouse": "thebearhouse.com",
    "thehouseofrare": "thehouseofrare.com",
}


def _is_ignored_catalog_key(key: str, ignored: set[str]) -> bool:
    normalized = str(key or "").strip()
    if normalized in ignored:
        return True
    return normalized.lower().startswith("unnamed:")


def canonical_product_url(*, raw_url: str = "", store: str = "", handle: str = "") -> str:
    url = str(raw_url or "").strip()
    if url.startswith("http://") or url.startswith("https://"):
        return url
    if url.startswith("/"):
        url = url[1:]
    if url and "." in url and "/" in url:
        return f"https://{url}"

    normalized_store = str(store or "").strip().lower()
    normalized_handle = str(handle or "").strip().strip("/")
    if not normalized_handle:
        normalized_handle = url
    normalized_handle = str(normalized_handle or "").strip().strip("/")
    if not normalized_handle:
        return ""

    domain = _STORE_DOMAINS.get(normalized_store)
    if not domain:
        return ""
    return f"https://www.{domain}/products/{normalized_handle}"


def _has_row_status_column(rows: List[Dict[str, str]]) -> bool:
    return bool(rows) and "row_status" in rows[0]


def _has_product_id_column(rows: List[Dict[str, str]]) -> bool:
    if not rows:
        return False
    return "product_id" in rows[0] or "id" in rows[0]


def _infer_product_id(rows: List[Dict[str, str]]) -> None:
    """Auto-generate product_id from URL when the CSV lacks a product_id column."""
    import hashlib
    from urllib.parse import urlparse

    for row in rows:
        url = str(row.get("url") or "").strip()
        if url:
            # Extract store name from domain and product handle from path
            parsed = urlparse(url if url.startswith("http") else f"https://{url}")
            domain = parsed.hostname or ""
            # Use first part of domain as store prefix (e.g. "campussutra" from "campussutra.com")
            store = domain.replace("www.", "").split(".")[0].upper() if domain else "UNKNOWN"
            # Use last path segment as handle
            handle = parsed.path.rstrip("/").rsplit("/", 1)[-1] if parsed.path else ""
            if handle:
                row["product_id"] = f"{store}_{handle}"
            else:
                row["product_id"] = f"{store}_{hashlib.md5(url.encode()).hexdigest()[:12]}"
        else:
            title = str(row.get("title") or "").strip()
            if title:
                import hashlib
                row["product_id"] = f"AUTO_{hashlib.md5(title.encode()).hexdigest()[:12]}"


def _infer_row_status(rows: List[Dict[str, str]]) -> None:
    """Auto-set row_status='ok' for rows that have product_id and title when the CSV lacks a row_status column."""
    for row in rows:
        pid = str(row.get("product_id") or row.get("id") or "").strip()
        title = str(row.get("title") or "").strip()
        row["row_status"] = "ok" if pid and title else "missing"


def read_catalog_rows(csv_path: str) -> List[Dict[str, str]]:
    path = Path(csv_path)
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not _has_product_id_column(rows):
        _infer_product_id(rows)
    if not _has_row_status_column(rows):
        _infer_row_status(rows)
    return rows


def write_jsonl(path: str, rows: Iterable[dict]) -> None:
    import json

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=True) + "\n")



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
        canonical_url = canonical_product_url(
            raw_url=str(row.get("url") or ""),
            store=str(row.get("store") or ""),
            handle=str(row.get("handle") or ""),
        )

        record: Dict[str, Any] = {
            "product_id": product_id,
            "source_row_number": int(source_row_number) if source_row_number.isdigit() else index,
            "title": str(row.get("title") or ""),
            "description": str(row.get("description") or ""),
            "price": price,
            "images_0_src": str(row.get("images_0_src") or row.get("images__0__src") or ""),
            "images_1_src": str(row.get("images_1_src") or row.get("images__1__src") or ""),
            "url": canonical_url,
            "row_status": str(row.get("row_status") or ""),
            "error_reason": str(row.get("error_reason") or ""),
            "raw_row_json": dict(row),
        }
        for key, value in row.items():
            if _is_ignored_catalog_key(key, ignored):
                continue
            clean = str(value).strip() if value is not None else ""
            if key.endswith("_confidence") or key.endswith("_score"):
                try:
                    record[key] = float(clean) if clean else None
                except ValueError:
                    record[key] = None
            else:
                record[key] = clean if clean else None
        output.append(record)
    return output


__all__ = [
    "build_catalog_enriched_rows",
    "canonical_product_url",
    "read_catalog_rows",
    "write_jsonl",
]
