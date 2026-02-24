import csv
import copy
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple

from catalog_enrichment.config_registry import load_tier2_ranked_attributes


RULES_PATH = Path(__file__).resolve().parent / "tier2_rules_v1.json"


@dataclass(frozen=True)
class RankResult:
    row: Dict[str, Any]
    final_score: float
    raw_score: float
    confidence_multiplier: float
    color_delta: float
    reasons: List[str]
    penalties: List[str]
    flags: List[str]
    explainability: Dict[str, Any]


def load_tier2_rules(path: Path = RULES_PATH) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def read_csv_rows(path: str) -> List[Dict[str, str]]:
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        return list(reader)


def write_ranked_csv(path: str, rows: List[Dict[str, Any]]) -> None:
    if not rows:
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write("")
        return
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return default


def _norm(s: str) -> str:
    return (s or "").strip().lower()


def _build_w_ga(affected: List[str], decay: float) -> Dict[str, float]:
    raw = [decay ** i for i in range(len(affected))]
    denom = sum(raw) if raw else 1.0
    return {g: raw[i] / denom for i, g in enumerate(affected)}


def _resolve_bh_weights(rules: Dict[str, Any]) -> Dict[str, float]:
    bh_weighting = rules.get("bh_weighting") or {}
    mode = str(bh_weighting.get("mode", "fixed")).strip().lower()
    if mode == "ranked_decay":
        ordered = list(bh_weighting.get("ordered_attributes") or [])
        if not ordered:
            return dict(rules.get("bh_weights") or {})
        decay = float(bh_weighting.get("decay_factor", 0.8))
        raw = [decay ** i for i in range(len(ordered))]
        denom = sum(raw) if raw else 1.0
        return {ordered[i]: raw[i] / denom for i in range(len(ordered))}
    return dict(rules.get("bh_weights") or {})


def _match_score(value: str, rule: Dict[str, List[str]], scores: Dict[str, float]) -> float:
    if value in rule.get("not_permitted", []):
        return scores["not_permitted"]
    if value in rule.get("preferred", []):
        return scores["preferred"]
    if value in rule.get("acceptable", []):
        return scores["acceptable"]
    return scores["unlisted"]


def _resolve_rule(
    body_attr: str,
    body_value: str,
    garment_attr: str,
    rulebook: Dict[str, Any],
) -> Dict[str, List[str]]:
    # Rules are expected under body_rules[body_attr][body_value][garment_attr].
    body_rules = (((rulebook.get("body_rules") or {}).get(body_attr) or {}).get(body_value) or {})
    rule = body_rules.get(garment_attr) or {}
    resolved = {
        "preferred": list(rule.get("preferred") or []),
        "acceptable": list(rule.get("acceptable") or []),
        "not_permitted": list(rule.get("not_permitted") or []),
    }
    if resolved["preferred"] or resolved["acceptable"] or resolved["not_permitted"]:
        return resolved
    return _heuristic_rule(body_attr=body_attr, body_value=body_value, garment_attr=garment_attr)


def _heuristic_rule(body_attr: str, body_value: str, garment_attr: str) -> Dict[str, List[str]]:
    # Heuristic fallback so Tier 2 remains functional even with partial rule tables.
    bv = str(body_value).strip().upper()
    empty = {"preferred": [], "acceptable": [], "not_permitted": []}

    if body_attr == "HeightCategory" and garment_attr == "GarmentLength":
        if bv in {"PETITE", "SHORT"}:
            return {"preferred": ["mid_thigh", "knee", "calf"], "acceptable": ["thigh", "ankle"], "not_permitted": ["floor"]}
        if bv in {"TALL", "VERY_TALL"}:
            return {"preferred": ["calf", "ankle", "floor"], "acceptable": ["knee", "mid_thigh"], "not_permitted": ["cropped"]}
        return {"preferred": ["knee", "calf", "ankle"], "acceptable": ["mid_thigh", "floor"], "not_permitted": []}

    if body_attr == "BodyShape":
        if garment_attr == "SilhouetteType":
            mapping = {
                "PEAR": (["a_line", "wrap", "straight"], ["fitted", "empire"], ["boxy"]),
                "INVERTED_TRIANGLE": (["a_line", "flared", "wrap"], ["straight"], ["boxy", "oversized"]),
                "RECTANGLE": (["wrap", "a_line", "peplum"], ["fitted", "straight"], []),
                "APPLE": (["empire", "a_line", "straight"], ["wrap"], ["boxy", "oversized"]),
                "HOURGLASS": (["fitted", "wrap", "a_line"], ["straight"], []),
            }
            p, a, n = mapping.get(bv, (["straight", "a_line"], ["wrap", "fitted"], []))
            return {"preferred": p, "acceptable": a, "not_permitted": n}
        if garment_attr == "WaistDefinition":
            if bv in {"APPLE", "OVAL", "DIAMOND"}:
                return {"preferred": ["natural", "undefined", "empire"], "acceptable": ["defined"], "not_permitted": ["dropped"]}
            return {"preferred": ["defined", "natural"], "acceptable": ["cinched", "belted"], "not_permitted": []}

    if body_attr == "VisualWeight" and garment_attr == "VisualWeightPlacement":
        m = {
            "SHOULDER_DOMINANT": {"preferred": ["lower_biased", "lower", "distributed"], "acceptable": ["center"], "not_permitted": ["upper"]},
            "BUST_DOMINANT": {"preferred": ["center", "lower_biased", "distributed"], "acceptable": ["upper_biased"], "not_permitted": ["upper"]},
            "MIDSECTION_DOMINANT": {"preferred": ["upper_biased", "lower_biased", "distributed"], "acceptable": ["center"], "not_permitted": []},
            "HIP_THIGH_DOMINANT": {"preferred": ["upper", "upper_biased", "distributed"], "acceptable": ["center"], "not_permitted": ["lower"]},
            "BALANCED": {"preferred": ["distributed", "center"], "acceptable": ["upper_biased", "lower_biased"], "not_permitted": []},
        }
        return m.get(bv, empty)

    if body_attr == "VerticalProportion":
        if garment_attr == "WaistDefinition":
            if bv == "SHORT_TORSO_LONG_LEGS":
                return {"preferred": ["natural", "dropped"], "acceptable": ["undefined"], "not_permitted": ["empire"]}
            if bv == "LONG_TORSO_SHORT_LEGS":
                return {"preferred": ["defined", "belted", "cinched", "empire"], "acceptable": ["natural"], "not_permitted": ["dropped"]}
        if garment_attr == "GarmentLength":
            if bv == "SHORT_TORSO_LONG_LEGS":
                return {"preferred": ["knee", "calf"], "acceptable": ["mid_thigh", "ankle"], "not_permitted": ["floor"]}
            if bv == "LONG_TORSO_SHORT_LEGS":
                return {"preferred": ["mid_thigh", "knee"], "acceptable": ["calf"], "not_permitted": ["floor"]}

    if body_attr == "ArmVolume":
        if garment_attr == "SleeveLength":
            m = {
                "SLENDER": {"preferred": ["sleeveless", "cap", "short"], "acceptable": ["elbow", "three_quarter", "full"], "not_permitted": []},
                "AVERAGE": {"preferred": ["short", "elbow", "three_quarter", "full"], "acceptable": ["cap", "sleeveless"], "not_permitted": []},
                "FULL_SOFT": {"preferred": ["elbow", "three_quarter", "full"], "acceptable": ["short"], "not_permitted": ["sleeveless", "cap"]},
                "TONED_ATHLETIC": {"preferred": ["short", "sleeveless", "elbow"], "acceptable": ["three_quarter", "full"], "not_permitted": []},
            }
            return m.get(bv, empty)

    if body_attr == "MidsectionState" and garment_attr == "WaistDefinition":
        m = {
            "TONED_ATHLETIC": {"preferred": ["defined", "cinched", "belted"], "acceptable": ["natural"], "not_permitted": []},
            "SOFT_AVERAGE": {"preferred": ["natural", "undefined"], "acceptable": ["defined"], "not_permitted": ["cinched"]},
            "LOWER_BELLY_BIAS": {"preferred": ["undefined", "natural", "empire"], "acceptable": ["defined"], "not_permitted": ["cinched", "belted"]},
            "HIGH_MIDRIFF_FULLNESS": {"preferred": ["empire", "undefined"], "acceptable": ["natural"], "not_permitted": ["cinched", "belted"]},
        }
        return m.get(bv, empty)

    if body_attr == "WaistVisibility" and garment_attr == "WaistDefinition":
        m = {
            "DEFINED": {"preferred": ["defined", "belted", "cinched"], "acceptable": ["natural"], "not_permitted": ["dropped"]},
            "SOFT": {"preferred": ["natural", "defined"], "acceptable": ["undefined"], "not_permitted": ["cinched"]},
            "STRAIGHT": {"preferred": ["defined", "belted", "empire"], "acceptable": ["natural"], "not_permitted": []},
        }
        return m.get(bv, empty)

    if body_attr == "BustVolume":
        if garment_attr == "NecklineType":
            m = {
                "LOW": {"preferred": ["square", "boat", "crew"], "acceptable": ["v_neck", "scoop"], "not_permitted": []},
                "MEDIUM": {"preferred": ["v_neck", "square", "scoop", "boat"], "acceptable": ["crew", "collared"], "not_permitted": []},
                "FULL": {"preferred": ["v_neck", "scoop", "square"], "acceptable": ["collared", "notched"], "not_permitted": ["high_neck", "crew"]},
            }
            return m.get(bv, empty)
        if garment_attr == "NecklineDepth":
            if bv == "FULL":
                return {"preferred": ["shallow", "moderate"], "acceptable": ["deep"], "not_permitted": ["very_deep", "closed"]}
            if bv == "LOW":
                return {"preferred": ["moderate", "deep"], "acceptable": ["shallow"], "not_permitted": []}
            return {"preferred": ["shallow", "moderate"], "acceptable": ["deep", "closed"], "not_permitted": []}

    if body_attr == "SkinUndertone" and garment_attr == "ColorTemperature":
        m = {
            "COOL": {"preferred": ["cool", "neutral"], "acceptable": ["mixed"], "not_permitted": ["warm"]},
            "WARM": {"preferred": ["warm", "neutral"], "acceptable": ["mixed"], "not_permitted": ["cool"]},
            "NEUTRAL": {"preferred": ["neutral", "warm", "cool"], "acceptable": ["mixed"], "not_permitted": []},
            "OLIVE": {"preferred": ["warm", "neutral"], "acceptable": ["mixed"], "not_permitted": ["cool"]},
        }
        return m.get(bv, empty)

    if body_attr == "SkinSurfaceColor":
        if garment_attr == "ColorValue":
            m = {
                "FAIR": {"preferred": ["light", "mid"], "acceptable": ["dark"], "not_permitted": ["very_light"]},
                "WHEATISH_LIGHT": {"preferred": ["mid", "light"], "acceptable": ["dark"], "not_permitted": []},
                "WHEATISH_MEDIUM": {"preferred": ["mid", "dark"], "acceptable": ["light"], "not_permitted": []},
                "DUSKY": {"preferred": ["mid", "dark", "very_dark"], "acceptable": ["light"], "not_permitted": []},
                "DARK": {"preferred": ["light", "mid", "very_dark"], "acceptable": ["dark"], "not_permitted": []},
                "DEEP": {"preferred": ["light", "mid", "dark"], "acceptable": ["very_dark"], "not_permitted": []},
            }
            return m.get(bv, empty)

    if body_attr == "SkinContrast" and garment_attr == "ContrastLevel":
        m = {
            "MUTED_SOFT": {"preferred": ["low", "medium"], "acceptable": ["high"], "not_permitted": ["very_high"]},
            "MEDIUM_CONTRAST": {"preferred": ["medium", "high"], "acceptable": ["low"], "not_permitted": []},
            "HIGH_CONTRAST": {"preferred": ["high", "very_high"], "acceptable": ["medium"], "not_permitted": ["low"]},
        }
        return m.get(bv, empty)

    if body_attr == "FaceShape" and garment_attr == "NecklineType":
        m = {
            "ROUND": {"preferred": ["v_neck", "notched", "collared"], "acceptable": ["square", "scoop"], "not_permitted": ["crew", "high_neck"]},
            "SQUARE": {"preferred": ["scoop", "sweetheart", "boat"], "acceptable": ["v_neck", "square"], "not_permitted": []},
            "HEART": {"preferred": ["scoop", "square", "boat"], "acceptable": ["v_neck", "sweetheart"], "not_permitted": []},
            "OBLONG": {"preferred": ["boat", "crew", "square"], "acceptable": ["scoop"], "not_permitted": ["very_deep"]},
        }
        return m.get(bv, {"preferred": ["v_neck", "square", "scoop"], "acceptable": ["boat", "crew"], "not_permitted": []})

    if body_attr == "NeckLength" and garment_attr == "NecklineDepth":
        m = {
            "SHORT": {"preferred": ["moderate", "deep"], "acceptable": ["shallow"], "not_permitted": ["closed"]},
            "AVERAGE": {"preferred": ["shallow", "moderate"], "acceptable": ["deep", "closed"], "not_permitted": []},
            "LONG": {"preferred": ["closed", "shallow", "moderate"], "acceptable": ["deep"], "not_permitted": []},
        }
        return m.get(bv, empty)

    if body_attr == "HairLength" and garment_attr == "NecklineType":
        m = {
            "PIXIE_SHORT": {"preferred": ["high_neck", "square", "boat", "v_neck"], "acceptable": ["crew", "collared"], "not_permitted": []},
            "BOB_CHIN": {"preferred": ["boat", "square", "v_neck"], "acceptable": ["scoop", "crew"], "not_permitted": []},
            "SHOULDER_LENGTH": {"preferred": ["v_neck", "square", "scoop"], "acceptable": ["boat", "crew"], "not_permitted": []},
            "LONG": {"preferred": ["v_neck", "halter", "scoop"], "acceptable": ["square", "notched"], "not_permitted": ["crew"]},
        }
        return m.get(bv, empty)

    if body_attr == "HairColor" and garment_attr == "ContrastLevel":
        m = {
            "JET_BLACK": {"preferred": ["high", "very_high"], "acceptable": ["medium"], "not_permitted": ["low"]},
            "DARK_BROWN": {"preferred": ["medium", "high"], "acceptable": ["low"], "not_permitted": []},
            "MEDIUM_BROWN": {"preferred": ["medium"], "acceptable": ["low", "high"], "not_permitted": []},
            "GOLDEN_BROWN": {"preferred": ["low", "medium"], "acceptable": ["high"], "not_permitted": ["very_high"]},
            "BLONDE": {"preferred": ["low", "medium"], "acceptable": ["high"], "not_permitted": ["very_high"]},
            "AUBURN_RED": {"preferred": ["medium", "high"], "acceptable": ["low"], "not_permitted": []},
            "HIGHLIGHTED": {"preferred": ["medium", "high"], "acceptable": ["very_high"], "not_permitted": []},
            "FASHION_COLOR": {"preferred": ["low", "medium"], "acceptable": ["high"], "not_permitted": ["very_high"]},
        }
        return m.get(bv, empty)

    return empty


def _collect_active_rule_entries(
    user_profile: Dict[str, Any],
    rules: Dict[str, Any],
    bh_weights: Dict[str, float],
) -> Dict[str, List[Tuple[str, float, Dict[str, List[str]]]]]:
    affected = rules["affected_garment_attributes"]
    entries: Dict[str, List[Tuple[str, float, Dict[str, List[str]]]]] = {}
    for body_attr, w_bh in bh_weights.items():
        body_value = user_profile.get(body_attr)
        if not body_value:
            continue
        for garment_attr in affected.get(body_attr, []):
            r = _resolve_rule(body_attr, str(body_value), garment_attr, rules)
            if not (r["preferred"] or r["acceptable"] or r["not_permitted"]):
                continue
            entries.setdefault(garment_attr, []).append((body_attr, w_bh, r))

    for g in entries:
        entries[g].sort(key=lambda x: x[1], reverse=True)
    return entries


def _conflict_engine(
    active_entries: Dict[str, List[Tuple[str, float, Dict[str, List[str]]]]]
) -> Dict[str, Any]:
    acceptable_fallback_count = 0
    priority_override_count = 0
    events: List[Dict[str, Any]] = []
    not_permitted_union: Dict[str, List[str]] = {}

    for garment_attr, entries in active_entries.items():
        np_union = set()
        for _, _, r in entries:
            np_union.update(r["not_permitted"])
        not_permitted_union[garment_attr] = sorted(np_union)

        if len(entries) < 2:
            continue

        pref_sets = [set(r["preferred"]) for _, _, r in entries if r["preferred"]]
        if len(pref_sets) < 2:
            continue

        inter = set.intersection(*pref_sets) if pref_sets else set()
        if inter:
            events.append({"garment_attr": garment_attr, "type": "intersection", "values": sorted(inter)})
            continue

        high_body_attr, _, high_rule = entries[0]
        high_pref = set(high_rule["preferred"])
        fallback_values = set()
        fallback_with = None
        for low_body_attr, _, low_rule in entries[1:]:
            cand = high_pref.intersection(set(low_rule["acceptable"]))
            if cand:
                fallback_values = cand
                fallback_with = low_body_attr
                break

        if fallback_values:
            acceptable_fallback_count += 1
            events.append(
                {
                    "garment_attr": garment_attr,
                    "type": "acceptable_fallback",
                    "high_priority_attr": high_body_attr,
                    "fallback_with": fallback_with,
                    "values": sorted(fallback_values),
                }
            )
            continue

        priority_override_count += 1
        events.append(
            {
                "garment_attr": garment_attr,
                "type": "priority_override",
                "winner": high_body_attr,
                "values": sorted(high_pref),
            }
        )

    return {
        "acceptable_fallback_count": acceptable_fallback_count,
        "priority_override_count": priority_override_count,
        "events": events,
        "not_permitted_union": not_permitted_union,
    }


def _confidence_multiplier(conflicts: Dict[str, Any], rules: Dict[str, Any]) -> float:
    a = int(conflicts["acceptable_fallback_count"])
    p = int(conflicts["priority_override_count"])
    m = rules["confidence_multipliers"]
    if p >= 2:
        return m["priority_override"]["2_plus"]
    if p == 1:
        return m["priority_override"]["1"]
    if a >= 2:
        return m["acceptable_fallback"]["2_3"]
    if a == 1:
        return m["acceptable_fallback"]["1"]
    return m["full_intersection"]


def _strictness_profile(rules: Dict[str, Any], strictness: str) -> Dict[str, float]:
    profiles = rules.get("strictness_profiles") or {}
    p = profiles.get(strictness, profiles.get("balanced", {}))
    return {
        "confidence_multiplier_scale": float(p.get("confidence_multiplier_scale", 1.0)),
        "negative_penalty_scale": float(p.get("negative_penalty_scale", 1.0)),
        "color_delta_scale": float(p.get("color_delta_scale", 1.0)),
        "skin_merge_penalty_scale": float(p.get("skin_merge_penalty_scale", 1.0)),
    }


def _color_delta(row: Dict[str, Any], user_profile: Dict[str, Any], rules: Dict[str, Any]) -> Tuple[float, List[str], bool]:
    primary = (row.get("PrimaryColor", "") or "").strip().lower()
    prefs = user_profile.get("color_preferences") or {}
    never = {x.lower() for x in (prefs.get("never") or [])}
    loved = {x.lower() for x in (prefs.get("loved") or [])}
    liked = {x.lower() for x in (prefs.get("liked") or [])}
    disliked = {x.lower() for x in (prefs.get("disliked") or [])}

    notes: List[str] = []
    if primary and primary in never:
        notes.append("color_never")
        return 0.0, notes, True

    delta_map = rules["color_preference_delta"]
    delta = 0.0
    if primary and primary in loved:
        delta += float(delta_map["loved"])
        notes.append("color_loved")
    elif primary and primary in liked:
        delta += float(delta_map["liked"])
        notes.append("color_liked")
    elif primary and primary in disliked:
        delta += float(delta_map["disliked"])
        notes.append("color_disliked")
    return delta, notes, False


def _skin_merge_penalty(row: Dict[str, Any], user_profile: Dict[str, Any], rules: Dict[str, Any]) -> Tuple[float, List[str]]:
    surface = str(user_profile.get("SkinSurfaceColor", "")).strip()
    color_value = (row.get("ColorValue", "") or "").strip()
    blocked = rules.get("skin_color_merge_protection", {}).get(surface, [])
    if color_value in blocked:
        return -0.08, [f"color_merge:{surface}->{color_value}"]
    return 0.0, []


def rank_garments(
    rows: List[Dict[str, Any]],
    user_profile: Dict[str, Any],
    rules: Dict[str, Any],
    strictness: str = "balanced",
) -> List[RankResult]:
    rules = copy.deepcopy(rules)
    ranked_cfg = load_tier2_ranked_attributes()

    ranked_bh = dict((ranked_cfg.get("bh_weighting") or {}))
    if ranked_bh:
        rules["bh_weighting"] = ranked_bh
    ranked_body_to_garment = dict((ranked_cfg.get("body_to_garment_priority_order") or {}))
    if ranked_body_to_garment:
        rules["affected_garment_attributes"] = ranked_body_to_garment
    ranked_ga = dict((ranked_cfg.get("ga_weighting") or {}))
    if ranked_ga.get("decay_factor") is not None:
        rules["decay_factor_w_ga"] = float(ranked_ga["decay_factor"])

    strict = (strictness or "balanced").strip().lower()
    available_profiles = set((rules.get("strictness_profiles") or {}).keys())
    if not available_profiles:
        available_profiles = {"safe", "balanced", "bold"}
    if strict not in available_profiles:
        raise ValueError(f"Invalid strictness. Use one of: {', '.join(sorted(available_profiles))}")

    profile = _strictness_profile(rules, strict)
    scores = rules["match_scores"]
    decay = float(rules["decay_factor_w_ga"])
    bh_weights: Dict[str, float] = _resolve_bh_weights(rules)
    affected = rules["affected_garment_attributes"]

    active_entries = _collect_active_rule_entries(user_profile=user_profile, rules=rules, bh_weights=bh_weights)
    conflicts = _conflict_engine(active_entries)
    base_conf_multiplier = _confidence_multiplier(conflicts, rules)
    conf_multiplier = min(1.25, base_conf_multiplier * profile["confidence_multiplier_scale"])

    results: List[RankResult] = []
    for row in rows:
        raw = 0.0
        max_raw = 0.0
        contributions: List[Tuple[str, str, float, float, float, float]] = []
        penalties: List[str] = []
        flags: List[str] = []

        for body_attr, w_bh in bh_weights.items():
            body_value = user_profile.get(body_attr)
            if not body_value:
                continue
            w_ga = _build_w_ga(affected.get(body_attr, []), decay)
            for garment_attr, wg in w_ga.items():
                value = (row.get(garment_attr, "") or "").strip()
                if not value:
                    continue
                rule = _resolve_rule(body_attr, str(body_value), garment_attr, rules)
                if not (rule["preferred"] or rule["acceptable"] or rule["not_permitted"]):
                    continue

                # Not Permitted union wins for this garment attribute.
                np_union = set(conflicts["not_permitted_union"].get(garment_attr, []))
                if value in np_union:
                    m = scores["not_permitted"]
                else:
                    m = _match_score(value=value, rule=rule, scores=scores)

                conf = _to_float(row.get(f"{garment_attr}_confidence", 0.0), default=0.0)
                conf_adj = conf if conf >= 0.45 else conf * 0.5
                c = float(w_bh) * float(wg) * float(m) * conf_adj
                max_raw += float(w_bh) * float(wg) * 1.0 * 1.0
                if c < 0:
                    c *= profile["negative_penalty_scale"]
                raw += c
                contributions.append((body_attr, garment_attr, float(w_bh), float(wg), float(m), c))

        merge_penalty, merge_notes = _skin_merge_penalty(row=row, user_profile=user_profile, rules=rules)
        merge_penalty *= profile["skin_merge_penalty_scale"]
        raw += merge_penalty
        penalties.extend(merge_notes)

        color_delta, color_notes, color_hard_exclude = _color_delta(row=row, user_profile=user_profile, rules=rules)
        color_delta *= profile["color_delta_scale"]
        penalties.extend(color_notes)
        if color_hard_exclude:
            flags.append("excluded_color_never")
            continue

        final = raw * conf_multiplier + color_delta
        max_score = max_raw * conf_multiplier + max(0.0, color_delta)
        compatibility_confidence = 0.0
        if max_score > 0:
            compatibility_confidence = final / max_score
        compatibility_confidence = max(0.0, min(1.0, compatibility_confidence))
        if final < float(rules["nearest_match_threshold"]):
            flags.append("nearest_match")
        if conf_multiplier < float(rules["limited_match_threshold"]):
            flags.append("limited_match")

        top_pos = sorted([x for x in contributions if x[5] > 0], key=lambda x: x[5], reverse=True)[:5]
        top_neg = sorted([x for x in contributions if x[5] < 0], key=lambda x: x[5])[:5]
        reasons = [f"{a}->{g}:{c:.4f}" for a, g, _, _, _, c in top_pos]
        penalties.extend([f"{a}->{g}:{c:.4f}" for a, g, _, _, _, c in top_neg])

        explainability = {
            "raw_score": raw,
            "base_confidence_multiplier": base_conf_multiplier,
            "confidence_multiplier": conf_multiplier,
            "color_delta": color_delta,
            "final_score": final,
            "max_score": max_score,
            "compatibility_confidence": compatibility_confidence,
            "strictness": strict,
            "strictness_profile": profile,
            "bh_weighting_mode": (rules.get("bh_weighting") or {}).get("mode", "fixed"),
            "effective_bh_weights": bh_weights,
            "conflict_engine": conflicts,
            "contribution_count": len(contributions),
            "top_positive_contributions": reasons,
            "top_negative_contributions": [f"{a}->{g}:{c:.4f}" for a, g, _, _, _, c in top_neg],
            "formula": "sum(W_bh(a) * sum(W_ga(a,g) * match(a,g) * conf(g))) * confidence_multiplier + color_delta",
        }

        out_row = dict(row)
        out_row["tier2_raw_score"] = f"{raw:.6f}"
        out_row["tier2_confidence_multiplier"] = f"{conf_multiplier:.4f}"
        out_row["tier2_color_delta"] = f"{color_delta:.4f}"
        out_row["tier2_final_score"] = f"{final:.6f}"
        out_row["tier2_max_score"] = f"{max_score:.6f}"
        out_row["tier2_compatibility_confidence"] = f"{compatibility_confidence:.6f}"
        out_row["tier2_flags"] = "|".join(flags)
        out_row["tier2_reasons"] = " ; ".join(reasons)
        out_row["tier2_penalties"] = " ; ".join(penalties)

        results.append(
            RankResult(
                row=out_row,
                final_score=final,
                raw_score=raw,
                confidence_multiplier=conf_multiplier,
                color_delta=color_delta,
                reasons=reasons,
                penalties=penalties,
                flags=flags,
                explainability=explainability,
            )
        )

    return sorted(results, key=lambda r: r.final_score, reverse=True)
