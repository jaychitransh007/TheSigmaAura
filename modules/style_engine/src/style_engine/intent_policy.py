from dataclasses import replace
from typing import Any, Dict, List, Tuple

from catalog_enrichment.config_registry import load_intent_policy_rules


def _norm(value: Any) -> str:
    return str(value or "").strip().lower()


def _tokenize(text: str) -> str:
    normalized = _norm(text)
    for ch in [",", ".", "!", "?", "/", "\\", "-", "_", "(", ")", "[", "]", "{", "}", ":", ";"]:
        normalized = normalized.replace(ch, " ")
    return f" {normalized} "


def _contains_keyword(tokens: str, keyword: str) -> bool:
    needle = f" {_tokenize(keyword).strip()} "
    return needle in tokens


def resolve_intent_policy(
    *,
    request_text: str,
    context: Dict[str, str],
    rules: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    cfg = rules or load_intent_policy_rules()
    policies = dict(cfg.get("policies") or {})
    tokens = _tokenize(request_text)
    occasion = _norm(context.get("occasion", ""))

    for policy_id, policy in policies.items():
        activation = dict(policy.get("activation") or {})
        occasion_in = {_norm(x) for x in (activation.get("occasion_in") or [])}
        if occasion_in and occasion not in occasion_in:
            continue

        any_keywords = [str(x) for x in (activation.get("any_keywords") or []) if str(x).strip()]
        hits = [kw for kw in any_keywords if _contains_keyword(tokens, kw)]
        if any_keywords and not hits:
            continue

        return {
            "policy_id": str(policy_id),
            "policy": policy,
            "keyword_hits": hits,
        }

    default_policy = str(cfg.get("default_policy", "") or "")
    if default_policy and default_policy in policies:
        return {
            "policy_id": default_policy,
            "policy": policies[default_policy],
            "keyword_hits": [],
        }

    return {"policy_id": "", "policy": {}, "keyword_hits": []}


def apply_intent_policy_filters(
    *,
    rows: List[Dict[str, Any]],
    policy: Dict[str, Any],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    if not policy:
        return rows, []

    constraints = dict(policy.get("hard_constraints") or {})
    required = dict(constraints.get("require_values") or {})
    blocked = dict(constraints.get("exclude_values") or {})
    blocked_categories = {_norm(x) for x in (constraints.get("exclude_categories") or [])}
    blocked_subtypes = {_norm(x) for x in (constraints.get("exclude_subtypes") or [])}
    blocked_title_keywords = [str(x) for x in (constraints.get("exclude_title_keywords") or []) if str(x).strip()]

    passed: List[Dict[str, Any]] = []
    failed: List[Dict[str, Any]] = []
    for row in rows:
        reasons: List[str] = []
        for attr, values in required.items():
            allowed = {_norm(v) for v in (values or [])}
            val = _norm(row.get(attr, ""))
            if allowed and val not in allowed:
                reasons.append(f"policy_required:{attr}")

        for attr, values in blocked.items():
            disallowed = {_norm(v) for v in (values or [])}
            val = _norm(row.get(attr, ""))
            if disallowed and val in disallowed:
                reasons.append(f"policy_excluded:{attr}")

        if blocked_categories and _norm(row.get("GarmentCategory", "")) in blocked_categories:
            reasons.append("policy_excluded:GarmentCategory")
        if blocked_subtypes and _norm(row.get("GarmentSubtype", "")) in blocked_subtypes:
            reasons.append("policy_excluded:GarmentSubtype")

        title_tokens = _tokenize(str(row.get("title", "")))
        for kw in blocked_title_keywords:
            if _contains_keyword(title_tokens, kw):
                reasons.append("policy_excluded:title_keyword")
                break

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


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return default


def _split_semicolon(raw: str) -> List[str]:
    if not raw:
        return []
    return [x.strip() for x in str(raw).split(";") if x.strip()]


def _split_pipe(raw: str) -> List[str]:
    if not raw:
        return []
    return [x.strip() for x in str(raw).split("|") if x.strip()]


def _compute_prior_delta(*, row: Dict[str, Any], policy_id: str, policy: Dict[str, Any]) -> Tuple[float, List[str]]:
    priors = dict(policy.get("ranking_priors") or {})
    delta = 0.0
    notes: List[str] = []

    for rule in priors.get("attribute_boosts") or []:
        attr = str(rule.get("attribute", "")).strip()
        if not attr:
            continue
        values = {_norm(v) for v in (rule.get("values") or [])}
        if _norm(row.get(attr, "")) in values:
            w = abs(float(rule.get("weight", 0.0) or 0.0))
            if w > 0:
                delta += w
                notes.append(f"{policy_id}:{attr}:+{w:.3f}")

    for rule in priors.get("attribute_penalties") or []:
        attr = str(rule.get("attribute", "")).strip()
        if not attr:
            continue
        values = {_norm(v) for v in (rule.get("values") or [])}
        if _norm(row.get(attr, "")) in values:
            w = abs(float(rule.get("weight", 0.0) or 0.0))
            if w > 0:
                delta -= w
                notes.append(f"{policy_id}:{attr}:-{w:.3f}")

    title_tokens = _tokenize(str(row.get("title", "")))
    for rule in priors.get("title_keyword_penalties") or []:
        keywords = [str(x) for x in (rule.get("keywords") or []) if str(x).strip()]
        if not keywords:
            continue
        hit = next((kw for kw in keywords if _contains_keyword(title_tokens, kw)), "")
        if not hit:
            continue
        w = abs(float(rule.get("weight", 0.0) or 0.0))
        if w > 0:
            delta -= w
            notes.append(f"{policy_id}:title:{hit}:-{w:.3f}")

    return delta, notes


def apply_intent_policy_priors(
    *,
    ranked_results: List[Any],
    policy_id: str,
    policy: Dict[str, Any],
) -> List[Any]:
    if not policy_id or not policy:
        return ranked_results

    adjusted: List[Any] = []
    for result in ranked_results:
        row = dict(result.row)
        delta, notes = _compute_prior_delta(row=row, policy_id=policy_id, policy=policy)
        if abs(delta) < 1e-9:
            adjusted.append(result)
            continue

        old_final = float(result.final_score)
        old_max = _to_float(row.get("tier2_max_score", old_final), default=max(old_final, 1e-6))
        new_final = old_final + delta
        new_max = old_max + max(0.0, delta)
        if new_max <= 0:
            new_max = 1e-6
        compatibility = max(0.0, min(1.0, new_final / new_max))

        flags = _split_pipe(str(row.get("tier2_flags", "")))
        flag = f"intent_policy:{policy_id}"
        if flag not in flags:
            flags.append(flag)

        reasons = _split_semicolon(str(row.get("tier2_reasons", "")))
        reasons.extend(notes)

        row["tier2_final_score"] = f"{new_final:.6f}"
        row["tier2_max_score"] = f"{new_max:.6f}"
        row["tier2_compatibility_confidence"] = f"{compatibility:.6f}"
        row["tier2_policy_delta"] = f"{delta:+.4f}"
        row["tier2_flags"] = "|".join(flags)
        row["tier2_reasons"] = " ; ".join(reasons)

        adjusted.append(
            replace(
                result,
                row=row,
                final_score=new_final,
                flags=flags,
                reasons=reasons,
            )
        )

    return sorted(adjusted, key=lambda r: r.final_score, reverse=True)
