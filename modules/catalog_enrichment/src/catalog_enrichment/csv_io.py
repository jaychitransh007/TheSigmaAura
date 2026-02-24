import csv
from typing import Dict, List

from .config import MANDATORY_COLUMNS


def read_csv_rows(path: str) -> List[Dict[str, str]]:
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError("Input CSV has no headers.")
        _validate_headers(reader.fieldnames)
        rows = list(reader)
        if not rows:
            raise ValueError("Input CSV has no data rows.")
        return rows


def _validate_headers(headers: List[str]) -> None:
    normalized = {h.strip(): h for h in headers}
    missing = [c for c in MANDATORY_COLUMNS if c not in normalized]
    if missing:
        raise ValueError(
            f"Missing mandatory columns: {', '.join(missing)}. "
            f"Required columns: {', '.join(MANDATORY_COLUMNS)}"
        )

