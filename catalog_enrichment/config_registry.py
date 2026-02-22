import json
from pathlib import Path
from typing import Any, Dict, List, Tuple


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = PROJECT_ROOT / "config"


def load_json_config(filename: str) -> Dict[str, Any]:
    path = CONFIG_DIR / filename
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_garment_attributes() -> Tuple[Dict[str, List[str]], List[str]]:
    cfg = load_json_config("garment_attributes.json")
    enum_attributes = dict(cfg.get("enum_attributes") or {})
    text_attributes = list(cfg.get("text_attributes") or [])
    return enum_attributes, text_attributes


def load_body_harmony_attributes() -> Dict[str, Any]:
    return load_json_config("body_harmony_attributes.json")


def load_user_context_attributes() -> Dict[str, Any]:
    return load_json_config("user_context_attributes.json")


def load_tier2_ranked_attributes() -> Dict[str, Any]:
    return load_json_config("tier2_ranked_attributes.json")


def load_tier1_ranked_attributes() -> Dict[str, Any]:
    return load_json_config("tier1_ranked_attributes.json")
