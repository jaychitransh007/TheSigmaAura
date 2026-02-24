import json
from pathlib import Path
from typing import Any, Dict, List, Tuple


def _discover_config_dir() -> Path:
    here = Path(__file__).resolve()
    candidates = [
        "garment_attributes.json",
        "user_context_attributes.json",
        "tier2_ranked_attributes.json",
    ]
    for base in [here.parent] + list(here.parents):
        direct = base / "config"
        if all((direct / name).exists() for name in candidates):
            return direct
        module_style = base / "modules" / "style_engine" / "configs" / "config"
        if all((module_style / name).exists() for name in candidates):
            return module_style
    raise FileNotFoundError("Could not locate config directory with required JSON files.")


CONFIG_DIR = _discover_config_dir()


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


def load_reinforcement_framework() -> Dict[str, Any]:
    return load_json_config("reinforcement_framework_v1.json")
