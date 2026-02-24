import json
from pathlib import Path
from typing import Any, Dict


_REQUIRED = [
    "body_harmony_attributes.json",
    "user_context_attributes.json",
]


def _discover_config_dir() -> Path:
    here = Path(__file__).resolve()
    for base in [here.parent] + list(here.parents):
        direct = base / "config"
        if all((direct / name).exists() for name in _REQUIRED):
            return direct
        module_style = base / "modules" / "style_engine" / "configs" / "config"
        if all((module_style / name).exists() for name in _REQUIRED):
            return module_style
    raise FileNotFoundError("Could not locate shared config directory.")


CONFIG_DIR = _discover_config_dir()


def load_json_config(filename: str) -> Dict[str, Any]:
    path = CONFIG_DIR / filename
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_body_harmony_attributes() -> Dict[str, Any]:
    return load_json_config("body_harmony_attributes.json")


def load_user_context_attributes() -> Dict[str, Any]:
    return load_json_config("user_context_attributes.json")
