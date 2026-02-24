import json
from typing import Any, Dict


def parse_batch_output_jsonl(path: str) -> Dict[str, Dict[str, Any]]:
    parsed: Dict[str, Dict[str, Any]] = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            item = json.loads(line)
            custom_id = item.get("custom_id")
            if not custom_id:
                continue
            parsed[custom_id] = _extract_row_payload(item)
    return parsed


def _extract_row_payload(item: Dict[str, Any]) -> Dict[str, Any]:
    if item.get("error"):
        return {"row_status": "error", "error_reason": str(item["error"])}

    body = (item.get("response") or {}).get("body") or {}
    output_text = body.get("output_text")
    if output_text:
        try:
            payload = json.loads(output_text)
            payload["row_status"] = "ok"
            payload["error_reason"] = ""
            return payload
        except json.JSONDecodeError:
            return {"row_status": "error", "error_reason": "Invalid JSON in output_text"}

    # Fallback for structured output nested format.
    output = body.get("output") or []
    for block in output:
        content = block.get("content") or []
        for c in content:
            text = c.get("text")
            if isinstance(text, str):
                try:
                    payload = json.loads(text)
                    payload["row_status"] = "ok"
                    payload["error_reason"] = ""
                    return payload
                except json.JSONDecodeError:
                    pass

    return {"row_status": "error", "error_reason": "No parseable model payload"}

