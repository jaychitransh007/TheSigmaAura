import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

from .attributes import ATTRIBUTE_NAMES, ENUM_ATTRIBUTES, TEXT_ATTRIBUTES


PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "system_prompt.txt"

# Pairs used to understand overlap between legacy and new attribute families.
COMPARABLE_PAIRS: List[Tuple[str, str]] = [
    ("SilhouetteContour", "SilhouetteType"),
    ("FitEase", "FitType"),
    ("VerticalWeightBias", "VisualWeightPlacement"),
]

# Key attributes where we expect explicit "X rules:" sections in prompt.
CRITICAL_RULE_SECTIONS = [
    "FitEase",
    "VolumeProfile",
    "SilhouetteContour",
    "GarmentLength",
    "SleeveLength",
    "WaistDefinition",
    "PatternType",
    "PatternScale",
    "SilhouetteType",
    "FitType",
    "VisualWeightPlacement",
]


def _duplicates(values: List[str]) -> List[str]:
    seen = set()
    dupes = set()
    for v in values:
        if v in seen:
            dupes.add(v)
        seen.add(v)
    return sorted(dupes)


def run_schema_audit(prompt_path: Path = PROMPT_PATH) -> Dict[str, Any]:
    errors: List[str] = []
    warnings: List[str] = []
    info: List[str] = []

    # Enum validation.
    enum_counts: Dict[str, int] = {}
    for attr, values in ENUM_ATTRIBUTES.items():
        enum_counts[attr] = len(values)
        if not values:
            errors.append(f"{attr}: enum list is empty")
            continue

        dupes = _duplicates(values)
        if dupes:
            errors.append(f"{attr}: duplicate enum values: {', '.join(dupes)}")

        invalid_tokens = [v for v in values if not v or "," in v]
        if invalid_tokens:
            errors.append(
                f"{attr}: malformed enum values (empty or contains comma): {', '.join(invalid_tokens)}"
            )

    # Prompt checks.
    prompt_text = ""
    if not prompt_path.exists():
        errors.append(f"Prompt file missing: {prompt_path}")
    else:
        prompt_text = prompt_path.read_text(encoding="utf-8")
        lowered = prompt_text.lower()

        missing_mentions = [a for a in ATTRIBUTE_NAMES if a.lower() not in lowered]
        if missing_mentions:
            warnings.append(
                "Prompt does not mention some attributes explicitly: "
                + ", ".join(sorted(missing_mentions))
            )

        missing_sections = [
            a
            for a in CRITICAL_RULE_SECTIONS
            if f"{a.lower()} rules:" not in lowered
        ]
        if missing_sections:
            warnings.append(
                "Prompt missing explicit rules sections for critical attributes: "
                + ", ".join(missing_sections)
            )

    # Diff report for overlapping families.
    pair_diffs: Dict[str, Dict[str, List[str]]] = {}
    for left, right in COMPARABLE_PAIRS:
        left_set = set(ENUM_ATTRIBUTES.get(left, []))
        right_set = set(ENUM_ATTRIBUTES.get(right, []))
        pair_diffs[f"{left}__vs__{right}"] = {
            f"only_in_{left}": sorted(left_set - right_set),
            f"only_in_{right}": sorted(right_set - left_set),
            "intersection": sorted(left_set & right_set),
        }

    info.append(
        f"Schema attributes: {len(ATTRIBUTE_NAMES)} total "
        f"({len(ENUM_ATTRIBUTES)} enum + {len(TEXT_ATTRIBUTES)} text)"
    )

    status = "pass" if not errors else "fail"
    return {
        "status": status,
        "errors": errors,
        "warnings": warnings,
        "info": info,
        "enum_counts": enum_counts,
        "pair_diffs": pair_diffs,
        "prompt_path": str(prompt_path),
    }


def write_audit_report(report: Dict[str, Any], path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=True, indent=2)

