import base64
import hashlib
import json
import mimetypes
from pathlib import Path
import shutil
from typing import Any, Dict, List, Tuple
from urllib.parse import urlparse
from urllib.request import urlopen

from openai import OpenAI

from .config import UserProfilerConfig
from .schemas import BODY_ENUMS, textual_response_format, visual_response_format


def _load_prompt(path: Path) -> str:
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        raise ValueError(f"Prompt file is empty: {path}")
    return text


_PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
VISUAL_PROMPT = _load_prompt(_PROMPTS_DIR / "visual_prompt.txt")
TEXTUAL_PROMPT = _load_prompt(_PROMPTS_DIR / "textual_prompt.txt")


def _image_to_input_url(image_ref: str) -> str:
    if image_ref.startswith("http://") or image_ref.startswith("https://"):
        return image_ref

    path = Path(image_ref).expanduser().resolve()
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"Image file not found: {image_ref}")

    mime, _ = mimetypes.guess_type(str(path))
    if not mime:
        mime = "image/jpeg"
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{data}"


def _extract_response_json(response: Any) -> Dict[str, Any]:
    output_text = getattr(response, "output_text", "") or ""
    if output_text:
        return json.loads(output_text)

    payload = response.model_dump() if hasattr(response, "model_dump") else {}
    for block in payload.get("output", []) or []:
        for content in block.get("content", []) or []:
            text = content.get("text")
            if isinstance(text, str) and text.strip():
                return json.loads(text)

    raise ValueError("No parseable JSON returned by model.")


def _extract_visual_reasoning(payload: Dict[str, Any]) -> List[str]:
    notes: List[str] = []
    for block in payload.get("output", []) or []:
        for content in block.get("content", []) or []:
            if content.get("type") != "reasoning":
                continue
            for summary in content.get("summary", []) or []:
                text = (summary.get("text") or "").strip()
                if text:
                    notes.append(text)
            text = (content.get("text") or "").strip()
            if text:
                notes.append(text)
    return notes


def _guess_ext_from_mime(mime: str) -> str:
    ext = mimetypes.guess_extension(mime or "")
    if ext:
        return ext
    return ".jpg"


def store_image_artifact(image_ref: str, artifacts_dir: Path) -> Dict[str, str]:
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    if image_ref.startswith("http://") or image_ref.startswith("https://"):
        parsed = urlparse(image_ref)
        suffix = Path(parsed.path).suffix or ".jpg"
        name = f"input_{hashlib.sha1(image_ref.encode('utf-8')).hexdigest()[:12]}{suffix}"
        out_path = artifacts_dir / name
        with urlopen(image_ref, timeout=30) as resp:
            out_path.write_bytes(resp.read())
        return {"source_type": "url", "source": image_ref, "stored_path": str(out_path)}

    src = Path(image_ref).expanduser().resolve()
    if not src.exists() or not src.is_file():
        raise FileNotFoundError(f"Image file not found: {image_ref}")
    suffix = src.suffix or ".jpg"
    name = f"input_{hashlib.sha1(str(src).encode('utf-8')).hexdigest()[:12]}{suffix}"
    out_path = artifacts_dir / name
    shutil.copy2(src, out_path)
    return {"source_type": "file", "source": str(src), "stored_path": str(out_path)}


def _normalize_style_context(visual: Dict[str, Any], textual: Dict[str, Any]) -> Dict[str, Any]:
    profile = {key: visual[key] for key in BODY_ENUMS.keys()}
    profile["color_preferences"] = {}

    return {
        "profile": profile,
        "context": {
            "occasion": textual["occasion"],
            "archetype": textual["archetype"],
            "gender": visual["gender"],
            "age": visual["age"],
        },
    }


def infer_user_profile(
    *,
    api_key: str,
    image_ref: str,
    context_text: str,
    config: UserProfilerConfig,
) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    client = OpenAI(api_key=api_key)
    artifacts_dir = Path(config.output_dir) / "user_profiler"
    image_artifact = store_image_artifact(image_ref, artifacts_dir)
    image_url = _image_to_input_url(image_ref)

    visual_input = [
        {
            "role": "system",
            "content": [{"type": "input_text", "text": VISUAL_PROMPT}],
        },
        {
            "role": "user",
            "content": [
                {"type": "input_text", "text": "Analyze this person's image and return the required JSON."},
                {"type": "input_image", "image_url": image_url},
            ],
        },
    ]
    visual_response = client.responses.create(
        model=config.visual_model,
        input=visual_input,
        reasoning={"effort": config.visual_reasoning_effort},
        text={"format": visual_response_format()},
    )

    textual_input = [
        {
            "role": "system",
            "content": [{"type": "input_text", "text": TEXTUAL_PROMPT}],
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "input_text",
                    "text": (
                        "Classify this user context into occasion and archetype.\n"
                        f"User text: {context_text}"
                    ),
                }
            ],
        },
    ]
    textual_response = client.responses.create(
        model=config.textual_model,
        input=textual_input,
        text={"format": textual_response_format()},
    )

    visual_payload = visual_response.model_dump() if hasattr(visual_response, "model_dump") else {}
    textual_payload = textual_response.model_dump() if hasattr(textual_response, "model_dump") else {}

    visual = _extract_response_json(visual_response)
    textual = _extract_response_json(textual_response)
    style_input = _normalize_style_context(visual, textual)

    visual_request_log = {
        "model": config.visual_model,
        "reasoning": {"effort": config.visual_reasoning_effort},
        "input": [
            {
                "role": "system",
                "content": [{"type": "input_text", "text": VISUAL_PROMPT}],
            },
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": "Analyze this person's image and return the required JSON."},
                    {"type": "input_image", "image_url": image_artifact["stored_path"]},
                ],
            },
        ],
    }

    logs = {
        "image_artifact": image_artifact,
        "visual_call": {
            "model": config.visual_model,
            "reasoning_effort": config.visual_reasoning_effort,
            "input_summary": {
                "image_source_type": image_artifact["source_type"],
                "image_source": image_artifact["source"],
                "stored_image_path": image_artifact["stored_path"],
                "user_text": "Analyze this person's image and return the required JSON.",
            },
            "request": visual_request_log,
            "response": visual_payload,
            "reasoning_notes": _extract_visual_reasoning(visual_payload),
            "parsed_output": visual,
        },
        "textual_call": {
            "model": config.textual_model,
            "input_summary": {"context_text": context_text},
            "request": {
                "model": config.textual_model,
                "input": textual_input,
            },
            "response": textual_payload,
            "parsed_output": textual,
        },
    }
    return visual, textual, style_input, logs
