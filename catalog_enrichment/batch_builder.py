import json
from typing import Dict, List

from .config import PipelineConfig
from .schema_builder import response_format


SYSTEM_PROMPT = (
    "You are a precision garment analyst trained to extract body-fit and silhouette "
    "attributes from fashion product images. Return strict JSON only per schema. "
    "Never guess; if uncertain return null with low confidence."
)


def build_request_body(row: Dict[str, str], config: PipelineConfig) -> Dict:
    text_blob = (
        f"Description: {row.get('description', '')}\n"
        f"Store: {row.get('store', '')}\n"
        f"Product URL: {row.get('url', '')}"
    )
    image_url = row.get("image", "")

    return {
        "model": config.model,
        "input": [
            {
                "role": "system",
                "content": [{"type": "input_text", "text": SYSTEM_PROMPT}],
            },
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": text_blob},
                    {"type": "input_image", "image_url": image_url},
                ],
            },
        ],
        "text": {"format": response_format()},
    }


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
