import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple


RULES_PATH = Path(__file__).resolve().parent / "tier_a_filters_v1.json"

_OCCASION_ALIASES = {
    "work mode": "work_mode",
    "work_mode": "work_mode",
    "social casual": "social_casual",
    "social_casual": "social_casual",
    "night out": "night_out",
    "night_out": "night_out",
    "formal events": "formal_events",
    "formal_events": "formal_events",
    "festive": "festive",
    "beach & vacation": "beach_vacation",
    "beach_vacation": "beach_vacation",
    "dating": "dating",
    "wedding vibes": "wedding_vibes",
    "wedding_vibes": "wedding_vibes",
}

_ARCHETYPE_ALIASES = {
    "classic": "classic",
    "minimalist": "minimalist",
    "modern professional": "modern_professional",
    "modern_professional": "modern_professional",
    "romantic": "romantic",
    "glamorous": "glamorous",
    "dramatic": "dramatic",
    "creative": "creative",
    "natural": "natural",
    "sporty": "sporty",
    "trend-forward": "trend_forward",
    "trend forward": "trend_forward",
    "trend_forward": "trend_forward",
    "bohemian": "bohemian",
    "edgy": "edgy",
}

_GENDER_ALIASES = {"male": "male", "female": "female"}

_AGE_ALIASES = {
    "18-24": "18_24",
    "18_24": "18_24",
    "25-30": "25_30",
    "25_30": "25_30",
    "30-35": "30_35",
    "30_35": "30_35",
}

RELAXABLE_FILTERS = {"price", "age", "archetype"}


@dataclass(frozen=True)
class UserContext:
    occasion: str
    archetype: str
    gender: str
    age: str


def load_tier_a_rules(path: Path = RULES_PATH) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _normalize(value: str) -> str:
    return (value or "").strip().lower()


def _resolve_key(value: str, aliases: Dict[str, str], field_name: str) -> str:
    key = aliases.get(_normalize(value))
    if not key:
        raise ValueError(f"Unsupported {field_name}: {value}")
    return key


def _to_float(value: str) -> float:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return float("nan")


def parse_relaxed_filters(relax_args: List[str]) -> Set[str]:
    relax: Set[str] = set()
    for raw in relax_args:
        for token in raw.split(","):
            name = _normalize(token)
            if not name:
                continue
            if name not in RELAXABLE_FILTERS:
                raise ValueError(
                    f"Unsupported relax filter: {name}. "
                    f"Allowed: {', '.join(sorted(RELAXABLE_FILTERS))}"
                )
            relax.add(name)
    return relax


def _row_matches_filters(
    row: Dict[str, str],
    rules: Dict[str, Any],
    occasion_key: str,
    archetype_key: str,
    gender_key: str,
    age_key: str,
    relaxed_filters: Set[str],
) -> Tuple[bool, List[str]]:
    failures: List[str] = []

    if "price" not in relaxed_filters:
        price = _to_float(row.get("price", ""))
        pr = rules["price_range_inr"]
        if not (pr["min"] <= price <= pr["max"]):
            failures.append("price")

    def check_group(group_name: str, group_rules: Dict[str, List[str]]) -> None:
        for attr, allowed in group_rules.items():
            val = (row.get(attr, "") or "").strip()
            if not val or val not in allowed:
                failures.append(f"{group_name}:{attr}")

    check_group("occasion", rules["occasions"][occasion_key])
    if "archetype" not in relaxed_filters:
        check_group("archetype", rules["archetypes"][archetype_key])
    if "age" not in relaxed_filters:
        check_group("age", rules["age_bands"][age_key])

    gender_allowed = rules["gender_map"][gender_key]
    gender_expr = (row.get("GenderExpression", "") or "").strip()
    if not gender_expr or gender_expr not in gender_allowed:
        failures.append("gender:GenderExpression")

    return (len(failures) == 0, failures)


def filter_catalog_rows(
    rows: List[Dict[str, str]],
    ctx: UserContext,
    rules: Dict[str, Any],
    relaxed_filters: Set[str] | None = None,
) -> Tuple[List[Dict[str, str]], List[Dict[str, Any]]]:
    active_relax = relaxed_filters or set()
    occasion_key = _resolve_key(ctx.occasion, _OCCASION_ALIASES, "occasion")
    archetype_key = _resolve_key(ctx.archetype, _ARCHETYPE_ALIASES, "archetype")
    gender_key = _resolve_key(ctx.gender, _GENDER_ALIASES, "gender")
    age_key = _resolve_key(ctx.age, _AGE_ALIASES, "age")

    passed: List[Dict[str, str]] = []
    failed: List[Dict[str, Any]] = []
    for row in rows:
        ok, reasons = _row_matches_filters(
            row=row,
            rules=rules,
            occasion_key=occasion_key,
            archetype_key=archetype_key,
            gender_key=gender_key,
            age_key=age_key,
            relaxed_filters=active_relax,
        )
        if ok:
            passed.append(row)
        else:
            failed.append(
                {
                    "id": row.get("id", ""),
                    "title": row.get("title", ""),
                    "fail_reasons": reasons,
                }
            )
    return passed, failed


def read_csv_rows(path: str) -> List[Dict[str, str]]:
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        return list(reader)


def write_csv_rows(path: str, rows: List[Dict[str, str]]) -> None:
    if not rows:
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write("")
        return
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
