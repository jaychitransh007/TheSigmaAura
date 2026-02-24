import json
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from typing import Dict, List

from .config import PipelineConfig
from .schema_builder import response_format


_PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "system_prompt.txt"


def _load_system_prompt() -> str:
    with _PROMPT_PATH.open("r", encoding="utf-8") as f:
        prompt = f.read().strip()
    if not prompt:
        raise ValueError(f"System prompt file is empty: {_PROMPT_PATH}")
    return prompt


SYSTEM_PROMPT = _load_system_prompt()


def build_request_body(row: Dict[str, str], config: PipelineConfig) -> Dict:
    text_blob = (
        f"Description: {row.get('description', '')}\n"
        f"Store: {row.get('store', '')}\n"
        f"Product URL: {row.get('url', '')}\n"
        "You must use both images together when inferring every attribute."
    )
    image_0 = _normalize_image_url((row.get("images__0__src", "") or "").strip())
    image_1 = _normalize_image_url((row.get("images__1__src", "") or "").strip())

    user_content = [{"type": "input_text", "text": text_blob}]
    if image_0:
        user_content.append({"type": "input_text", "text": "Image 1:"})
        user_content.append({"type": "input_image", "image_url": image_0})
    if image_1:
        user_content.append({"type": "input_text", "text": "Image 2:"})
        user_content.append({"type": "input_image", "image_url": image_1})

    return {
        "model": config.model,
        "input": [
            {
                "role": "system",
                "content": [{"type": "input_text", "text": SYSTEM_PROMPT}],
            },
            {
                "role": "user",
                "content": user_content,
            },
        ],
        "text": {"format": response_format()},
    }


def _normalize_image_url(url: str) -> str:
    if not url:
        return url
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["width"] = "768"
    new_query = urlencode(query)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, new_query, parts.fragment))


def build_batch_input_jsonl(rows: List[Dict[str, str]], output_jsonl_path: str, config: PipelineConfig) -> None:
    with open(output_jsonl_path, "w", encoding="utf-8") as out:
        for idx, row in enumerate(rows):
            req = {
                "custom_id": f"row_{idx}",
                "method": "POST",
                "url": config.endpoint,
                "body": build_request_body(row, config),
            }
            out.write(json.dumps(req, ensure_ascii=True) + "\n")


def build_retry_batch_input_jsonl(
    rows: List[Dict[str, str]],
    failed_indices: List[int],
    output_jsonl_path: str,
    config: PipelineConfig,
) -> None:
    with open(output_jsonl_path, "w", encoding="utf-8") as out:
        for idx in failed_indices:
            row = rows[idx]
            req = {
                "custom_id": f"row_{idx}",
                "method": "POST",
                "url": config.endpoint,
                "body": build_request_body(row, config),
            }
            out.write(json.dumps(req, ensure_ascii=True) + "\n")
