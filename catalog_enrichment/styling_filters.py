import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

from .config_registry import (
    load_reinforcement_framework,
    load_tier1_ranked_attributes,
    load_user_context_attributes,
)


RULES_PATH = Path(__file__).resolve().parent / "tier_a_filters_v1.json"
USER_CONTEXT_CONFIG = load_user_context_attributes()
TIER1_RANKED_CONFIG = load_tier1_ranked_attributes()
REINFORCEMENT_FRAMEWORK = load_reinforcement_framework()


def _build_alias_map(dimension_name: str) -> Dict[str, str]:
    dimension = (USER_CONTEXT_CONFIG.get("dimensions") or {}).get(dimension_name) or {}
    aliases = dict(dimension.get("aliases") or {})
    canonical_values = list(dimension.get("canonical_values") or [])
    for val in canonical_values:
        aliases.setdefault(str(val), str(val))
    return aliases


_OCCASION_ALIASES = _build_alias_map("occasion")
_ARCHETYPE_ALIASES = _build_alias_map("archetype")
_GENDER_ALIASES = _build_alias_map("gender")
_AGE_ALIASES = _build_alias_map("age")

RELAXABLE_FILTERS = set(USER_CONTEXT_CONFIG.get("relaxable_filters") or [])
if not RELAXABLE_FILTERS:
    RELAXABLE_FILTERS = {"price", "age", "archetype", "occasion_archetype"}


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
        normalized = _normalize(value)
        canonical = sorted(set(aliases.values()))
        if field_name == "archetype" and normalized in _OCCASION_ALIASES:
            raise ValueError(
                f"Unsupported archetype: {value}. It looks like an occasion value. "
                f"Use --occasion for values like '{value}'. "
                f"Valid archetypes: {', '.join(canonical)}"
            )
        if field_name == "occasion" and normalized in _ARCHETYPE_ALIASES:
            raise ValueError(
                f"Unsupported occasion: {value}. It looks like an archetype value. "
                f"Use --archetype for values like '{value}'. "
                f"Valid occasions: {', '.join(canonical)}"
            )
        raise ValueError(f"Unsupported {field_name}: {value}. Valid values: {', '.join(canonical)}")
    return key


def _to_float(value: str) -> float:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return float("nan")


def _is_truthy_str(value: str) -> bool:
    v = (value or "").strip().lower()
    return v in {"1", "true", "yes", "y", "in_stock", "available"}


def _is_falsy_str(value: str) -> bool:
    v = (value or "").strip().lower()
    return v in {"0", "false", "no", "n", "out_of_stock", "unavailable", "sold_out"}


def _is_in_stock(row: Dict[str, str]) -> bool:
    # Current stage: inventory is a dummy pass-through gate.
    # Keep this hook for future activation when reliable inventory
    # signals are available in catalog rows.
    _ = row
    return True


def _is_policy_safety_excluded(row: Dict[str, str], safety_exclusions: Dict[str, Any]) -> bool:
    category = (row.get("GarmentCategory", "") or "").strip().lower()
    subtype = (row.get("GarmentSubtype", "") or "").strip().lower()
    text_blob = " ".join(
        [
            row.get("title", "") or "",
            row.get("description", "") or "",
            row.get("product_type", "") or "",
            row.get("handle", "") or "",
        ]
    ).lower()

    if category and category in {x.lower() for x in (safety_exclusions.get("excluded_categories") or [])}:
        return True
    if subtype and subtype in {x.lower() for x in (safety_exclusions.get("excluded_subtypes") or [])}:
        return True
    for kw in (safety_exclusions.get("keyword_exclusions") or []):
        if kw.lower() in text_blob:
            return True
    return False


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

    if "occasion_archetype" not in relaxed_filters:
        allowed_archetypes = set(rules["occasion_archetype_compatibility"][occasion_key])
        if archetype_key not in allowed_archetypes:
            failures.append("occasion_archetype")

    if "price" not in relaxed_filters:
        price = _to_float(row.get("price", ""))
        pr = rules["price_range_inr"]
        if not (pr["min"] <= price <= pr["max"]):
            failures.append("price")

    ranked_by_context = dict(TIER1_RANKED_CONFIG.get("context_to_garment_attribute_priority_order") or {})

    def check_group(group_name: str, group_rules: Dict[str, List[str]]) -> None:
        ordered_attrs = list(ranked_by_context.get(group_name) or [])
        for attr in group_rules.keys():
            if attr not in ordered_attrs:
                ordered_attrs.append(attr)
        for attr in ordered_attrs:
            allowed = group_rules.get(attr)
            if allowed is None:
                continue
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
                    "row_idx": row.get("_row_idx", ""),
                    "id": row.get("id", ""),
                    "title": row.get("title", ""),
                    "fail_reasons": reasons,
                }
            )
    return passed, failed


def filter_catalog_rows_minimal_hard(
    rows: List[Dict[str, str]],
    ctx: UserContext,
    rules: Dict[str, Any],
) -> Tuple[List[Dict[str, str]], List[Dict[str, Any]]]:
    occasion_key = _resolve_key(ctx.occasion, _OCCASION_ALIASES, "occasion")
    gender_key = _resolve_key(ctx.gender, _GENDER_ALIASES, "gender")

    rl_profile = (
        (REINFORCEMENT_FRAMEWORK.get("hard_filter_profiles") or {}).get("rl_ready_minimal") or {}
    )
    profile_price = (rl_profile.get("price_range_inr") or {}) if rl_profile else {}
    price_range = profile_price or rules.get("price_range_inr") or {"min": 2000, "max": 5000}
    safety_exclusions = dict(rl_profile.get("safety_exclusions") or {})

    occasion_rules = dict((rules.get("occasions") or {}).get(occasion_key) or {})
    gender_allowed = set((rules.get("gender_map") or {}).get(gender_key) or [])

    passed: List[Dict[str, str]] = []
    failed: List[Dict[str, Any]] = []
    for row in rows:
        reasons: List[str] = []

        if not _is_in_stock(row):
            reasons.append("inventory")

        price = _to_float(row.get("price", ""))
        if not (float(price_range.get("min", 2000)) <= price <= float(price_range.get("max", 5000))):
            reasons.append("price")

        for attr, allowed in occasion_rules.items():
            val = (row.get(attr, "") or "").strip()
            if not val or val not in allowed:
                reasons.append(f"occasion:{attr}")

        gender_expr = (row.get("GenderExpression", "") or "").strip()
        if not gender_expr or gender_expr not in gender_allowed:
            reasons.append("gender:GenderExpression")

        if _is_policy_safety_excluded(row, safety_exclusions):
            reasons.append("policy_safety")

        if reasons:
            failed.append(
                {
                    "row_idx": row.get("_row_idx", ""),
                    "id": row.get("id", ""),
                    "title": row.get("title", ""),
                    "fail_reasons": reasons,
                }
            )
        else:
            passed.append(row)

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
