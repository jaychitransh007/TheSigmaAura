import json
from typing import Any, Dict, List

from .attributes import ATTRIBUTE_NAMES


def build_run_report(merged_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    total = len(merged_rows)
    ok = sum(1 for r in merged_rows if r.get("row_status") == "ok")
    errored = total - ok
    metrics: Dict[str, Any] = {
        "total_rows": total,
        "ok_rows": ok,
        "errored_rows": errored,
        "attributes": {},
    }

    for attr in ATTRIBUTE_NAMES:
        attr_values = [r.get(attr) for r in merged_rows]
        conf_values = [r.get(f"{attr}_confidence") for r in merged_rows]
        null_count = sum(1 for v in attr_values if v is None or v == "")
        valid_conf = [float(v) for v in conf_values if isinstance(v, (int, float))]
        metrics["attributes"][attr] = {
            "null_rate": (null_count / total) if total else 0,
            "mean_confidence": (sum(valid_conf) / len(valid_conf)) if valid_conf else 0,
        }
    return metrics


def write_report(report: Dict[str, Any], path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=True, indent=2)

