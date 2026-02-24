import json
from dataclasses import dataclass
from typing import Any, Dict, List, Sequence, Set, Tuple

from catalog_enrichment.config_registry import load_outfit_assembly_rules

from .ranker import RankResult, rank_garments


ALLOWED_MODES = {"auto", "outfit", "garment"}


@dataclass(frozen=True)
class RecommendationMeta:
    resolved_mode: str
    requested_categories: List[str]
    requested_subtypes: List[str]
    base_ranked_rows: int
    single_candidates: int
    combo_candidates: int
    returned_rows: int


def _norm(value: Any) -> str:
    return (str(value or "")).strip().lower()


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return default


def _split_reasons(raw: str) -> List[str]:
    if not raw:
        return []
    parts = [x.strip() for x in raw.split(";")]
    return [x for x in parts if x]


def _parse_flags(raw: str) -> List[str]:
    if not raw:
        return []
    return [x.strip() for x in raw.split("|") if x.strip()]


def _is_complete_single(row: Dict[str, Any], rules: Dict[str, Any]) -> bool:
    complete_values = {_norm(x) for x in (rules.get("single_complete_values") or [])}
    complete_categories = {_norm(x) for x in (rules.get("single_complete_categories") or [])}
    sc = _norm(row.get("StylingCompleteness", ""))
    category = _norm(row.get("GarmentCategory", ""))
    if sc in complete_values:
        return True
    if category in complete_categories:
        return True
    return False


def _is_top_candidate(row: Dict[str, Any], rules: Dict[str, Any]) -> bool:
    top_categories = {_norm(x) for x in (rules.get("top_categories") or [])}
    top_values = {_norm(x) for x in ((rules.get("combo_requirements") or {}).get("top_values") or [])}
    allow_unlabeled = bool((rules.get("combo_requirements") or {}).get("allow_unlabeled_top_bottom", True))
    category = _norm(row.get("GarmentCategory", ""))
    sc = _norm(row.get("StylingCompleteness", ""))
    if category in top_categories:
        return True
    if sc in top_values:
        return True
    return allow_unlabeled and category == "top"


def _is_bottom_candidate(row: Dict[str, Any], rules: Dict[str, Any]) -> bool:
    bottom_categories = {_norm(x) for x in (rules.get("bottom_categories") or [])}
    bottom_values = {_norm(x) for x in ((rules.get("combo_requirements") or {}).get("bottom_values") or [])}
    allow_unlabeled = bool((rules.get("combo_requirements") or {}).get("allow_unlabeled_top_bottom", True))
    category = _norm(row.get("GarmentCategory", ""))
    sc = _norm(row.get("StylingCompleteness", ""))
    if category in bottom_categories:
        return True
    if sc in bottom_values:
        return True
    return allow_unlabeled and category == "bottom"


def _tokenize(text: str) -> str:
    # Keep this light-weight for quick request intent detection.
    normalized = _norm(text)
    for ch in [",", ".", "!", "?", "/", "\\", "-", "_", "(", ")", "[", "]", "{", "}", ":", ";"]:
        normalized = normalized.replace(ch, " ")
    return f" {normalized} "


def detect_requested_garments(request_text: str, rules: Dict[str, Any]) -> Tuple[Set[str], Set[str]]:
    keywords = dict(rules.get("explicit_request_keywords") or {})
    by_category = dict(keywords.get("category") or {})
    by_subtype = dict(keywords.get("subtype") or {})
    tokens = _tokenize(request_text)

    categories: Set[str] = set()
    for category, words in by_category.items():
        for word in words or []:
            needle = f" {_tokenize(str(word)).strip()} "
            if needle in tokens:
                categories.add(_norm(category))
                break

    subtypes: Set[str] = set()
    for subtype, words in by_subtype.items():
        for word in words or []:
            needle = f" {_tokenize(str(word)).strip()} "
            if needle in tokens:
                subtypes.add(_norm(subtype))
                break
    return categories, subtypes


def resolve_recommendation_mode(
    *,
    mode: str,
    request_text: str,
    rules: Dict[str, Any],
) -> Tuple[str, Set[str], Set[str]]:
    requested_mode = _norm(mode) or _norm(rules.get("default_mode", "auto"))
    if requested_mode not in ALLOWED_MODES:
        raise ValueError("Invalid recommendation mode. Use one of: auto, outfit, garment")
    categories, subtypes = detect_requested_garments(request_text=request_text, rules=rules)
    if requested_mode == "auto":
        if categories or subtypes:
            return "garment", categories, subtypes
        return "outfit", categories, subtypes
    return requested_mode, categories, subtypes


def _formality_distance(a: str, b: str, order: Sequence[str]) -> int:
    norm_order = [_norm(x) for x in order]
    ia = norm_order.index(_norm(a)) if _norm(a) in norm_order else -1
    ib = norm_order.index(_norm(b)) if _norm(b) in norm_order else -1
    if ia < 0 or ib < 0:
        return 99
    return abs(ia - ib)


def _occasion_related(a: str, b: str, related_groups: Sequence[Sequence[str]]) -> bool:
    na = _norm(a)
    nb = _norm(b)
    for group in related_groups:
        g = {_norm(x) for x in group}
        if na in g and nb in g:
            return True
    return False


def _pattern_kind(value: str) -> str:
    v = _norm(value)
    if not v:
        return "unknown"
    if v == "solid":
        return "solid"
    return "patterned"


def _heavy_embellishment(value: str) -> bool:
    return _norm(value) in {"heavy", "statement"}


def _oversized_silhouette(value: str) -> bool:
    return _norm(value) in {"oversized", "boxy"}


def _pair_bonus(
    top_row: Dict[str, Any],
    bottom_row: Dict[str, Any],
    rules: Dict[str, Any],
) -> Tuple[float, List[str], List[str]]:
    bonus_cfg = dict(rules.get("pair_bonus") or {})
    bonus = 0.0
    reasons: List[str] = []
    penalties: List[str] = []

    # Occasion fit coherence.
    top_occ = _norm(top_row.get("OccasionFit", ""))
    bot_occ = _norm(bottom_row.get("OccasionFit", ""))
    occ_cfg = dict(bonus_cfg.get("occasion_fit") or {})
    related_groups = list(rules.get("occasion_fit_related_groups") or [])
    if top_occ and bot_occ:
        if top_occ == bot_occ:
            delta = float(occ_cfg.get("exact", 0.0))
            bonus += delta
            reasons.append(f"occasion_fit_exact:{top_occ}")
        elif _occasion_related(top_occ, bot_occ, related_groups):
            delta = float(occ_cfg.get("related", 0.0))
            bonus += delta
            reasons.append(f"occasion_fit_related:{top_occ}/{bot_occ}")
        else:
            delta = float(occ_cfg.get("mismatch", 0.0))
            bonus += delta
            penalties.append(f"occasion_fit_mismatch:{top_occ}/{bot_occ}")

    # Formality coherence.
    formality_order = list(rules.get("formality_order") or [])
    d = _formality_distance(top_row.get("FormalityLevel", ""), bottom_row.get("FormalityLevel", ""), formality_order)
    form_cfg = dict(bonus_cfg.get("formality") or {})
    if d == 0:
        delta = float(form_cfg.get("close", 0.0))
        bonus += delta
        reasons.append("formality_match")
    elif d == 1:
        delta = float(form_cfg.get("adjacent", 0.0))
        bonus += delta
        reasons.append("formality_adjacent")
    elif d != 99:
        delta = float(form_cfg.get("far", 0.0))
        bonus += delta
        penalties.append("formality_far")

    # Color temperature coherence.
    color_cfg = dict(bonus_cfg.get("color_temperature") or {})
    ct_a = _norm(top_row.get("ColorTemperature", ""))
    ct_b = _norm(bottom_row.get("ColorTemperature", ""))
    if ct_a and ct_b:
        if ct_a == ct_b:
            delta = float(color_cfg.get("exact", 0.0))
            bonus += delta
            reasons.append(f"color_temp_match:{ct_a}")
        elif "mixed" in {ct_a, ct_b}:
            delta = float(color_cfg.get("mixed_bridge", 0.0))
            bonus += delta
            reasons.append(f"color_temp_bridge:{ct_a}/{ct_b}")
        else:
            delta = float(color_cfg.get("mismatch", 0.0))
            bonus += delta
            penalties.append(f"color_temp_mismatch:{ct_a}/{ct_b}")

    # Pattern balance.
    pattern_cfg = dict(bonus_cfg.get("pattern_balance") or {})
    p_a = _pattern_kind(str(top_row.get("PatternType", "")))
    p_b = _pattern_kind(str(bottom_row.get("PatternType", "")))
    if p_a == "solid" and p_b == "solid":
        delta = float(pattern_cfg.get("both_solid", 0.0))
        bonus += delta
        reasons.append("pattern_both_solid")
    elif "solid" in {p_a, p_b}:
        delta = float(pattern_cfg.get("one_solid", 0.0))
        bonus += delta
        reasons.append("pattern_one_solid")
    elif p_a == "patterned" and p_b == "patterned":
        delta = float(pattern_cfg.get("both_patterned", 0.0))
        bonus += delta
        penalties.append("pattern_both_patterned")

    # Heavy embellishment clash.
    emb_cfg = dict(bonus_cfg.get("embellishment_balance") or {})
    if _heavy_embellishment(top_row.get("EmbellishmentLevel", "")) and _heavy_embellishment(
        bottom_row.get("EmbellishmentLevel", "")
    ):
        delta = float(emb_cfg.get("heavy_clash", 0.0))
        bonus += delta
        penalties.append("embellishment_heavy_clash")

    # Silhouette oversized clash.
    sil_cfg = dict(bonus_cfg.get("silhouette_balance") or {})
    if _oversized_silhouette(top_row.get("SilhouetteType", "")) and _oversized_silhouette(
        bottom_row.get("SilhouetteType", "")
    ):
        delta = float(sil_cfg.get("dual_oversized", 0.0))
        bonus += delta
        penalties.append("silhouette_dual_oversized")

    min_bonus = float(bonus_cfg.get("min", -1.0))
    max_bonus = float(bonus_cfg.get("max", 1.0))
    bonus = max(min_bonus, min(max_bonus, bonus))
    return bonus, reasons, penalties


def _as_single_candidate(result: RankResult) -> RankResult:
    row = dict(result.row)
    garment_id = str(row.get("id", ""))
    title = str(row.get("title", ""))
    image_0 = str(row.get("images__0__src", ""))
    image_1 = str(row.get("images__1__src", ""))
    reasons = _split_reasons(str(row.get("tier2_reasons", "")))
    penalties = _split_reasons(str(row.get("tier2_penalties", "")))
    flags = _parse_flags(str(row.get("tier2_flags", "")))

    row["recommendation_kind"] = "single_garment"
    row["outfit_id"] = f"single::{garment_id}"
    row["component_count"] = "1"
    row["component_ids_json"] = json.dumps([garment_id], ensure_ascii=True)
    row["component_titles_json"] = json.dumps([title], ensure_ascii=True)
    row["component_image_urls_json"] = json.dumps([image_0, image_1], ensure_ascii=True)

    explainability = dict(result.explainability)
    explainability["recommendation_kind"] = "single_garment"
    explainability["component_ids"] = [garment_id]

    return RankResult(
        row=row,
        final_score=result.final_score,
        raw_score=result.raw_score,
        confidence_multiplier=result.confidence_multiplier,
        color_delta=result.color_delta,
        reasons=reasons,
        penalties=penalties,
        flags=flags,
        explainability=explainability,
    )


def _build_combo_candidate(
    *,
    top: RankResult,
    bottom: RankResult,
    pair_bonus: float,
    pair_reasons: List[str],
    pair_penalties: List[str],
) -> RankResult:
    top_row = top.row
    bottom_row = bottom.row
    top_id = str(top_row.get("id", ""))
    bottom_id = str(bottom_row.get("id", ""))
    outfit_id = f"combo::{top_id}|{bottom_id}"

    final_score = ((top.final_score + bottom.final_score) / 2.0) + pair_bonus
    raw_score = ((top.raw_score + bottom.raw_score) / 2.0) + pair_bonus
    max_score = ((_to_float(top_row.get("tier2_max_score", 0.0)) + _to_float(bottom_row.get("tier2_max_score", 0.0))) / 2.0) + max(0.0, pair_bonus)
    if max_score <= 0:
        compatibility_conf = 0.0
    else:
        compatibility_conf = max(0.0, min(1.0, final_score / max_score))

    top_flags = set(_parse_flags(str(top_row.get("tier2_flags", ""))))
    bottom_flags = set(_parse_flags(str(bottom_row.get("tier2_flags", ""))))
    flags = sorted(top_flags.union(bottom_flags).union({"combo"}))

    top_reasons = _split_reasons(str(top_row.get("tier2_reasons", "")))[:2]
    bottom_reasons = _split_reasons(str(bottom_row.get("tier2_reasons", "")))[:2]
    reasons = (
        [f"pair_bonus:{pair_bonus:+.3f}"]
        + pair_reasons
        + [f"top:{x}" for x in top_reasons]
        + [f"bottom:{x}" for x in bottom_reasons]
    )

    top_penalties = _split_reasons(str(top_row.get("tier2_penalties", "")))[:2]
    bottom_penalties = _split_reasons(str(bottom_row.get("tier2_penalties", "")))[:2]
    penalties = pair_penalties + [f"top:{x}" for x in top_penalties] + [f"bottom:{x}" for x in bottom_penalties]

    row = dict(top_row)
    row["id"] = outfit_id
    row["title"] = f"{top_row.get('title', '')} + {bottom_row.get('title', '')}"
    row["images__0__src"] = str(top_row.get("images__0__src", ""))
    row["images__1__src"] = str(bottom_row.get("images__0__src", "") or bottom_row.get("images__1__src", ""))
    row["tier2_raw_score"] = f"{raw_score:.6f}"
    row["tier2_confidence_multiplier"] = f"{((top.confidence_multiplier + bottom.confidence_multiplier) / 2.0):.4f}"
    row["tier2_color_delta"] = f"{((top.color_delta + bottom.color_delta) / 2.0):.4f}"
    row["tier2_final_score"] = f"{final_score:.6f}"
    row["tier2_max_score"] = f"{max_score:.6f}"
    row["tier2_compatibility_confidence"] = f"{compatibility_conf:.6f}"
    row["tier2_flags"] = "|".join(flags)
    row["tier2_reasons"] = " ; ".join(reasons)
    row["tier2_penalties"] = " ; ".join(penalties)
    row["recommendation_kind"] = "outfit_combo"
    row["outfit_id"] = outfit_id
    row["component_count"] = "2"
    row["component_ids_json"] = json.dumps([top_id, bottom_id], ensure_ascii=True)
    row["component_titles_json"] = json.dumps(
        [str(top_row.get("title", "")), str(bottom_row.get("title", ""))],
        ensure_ascii=True,
    )
    row["component_image_urls_json"] = json.dumps(
        [
            str(top_row.get("images__0__src", "")),
            str(bottom_row.get("images__0__src", "")),
        ],
        ensure_ascii=True,
    )

    explainability = {
        "recommendation_kind": "outfit_combo",
        "component_ids": [top_id, bottom_id],
        "component_scores": {
            top_id: top.final_score,
            bottom_id: bottom.final_score,
        },
        "pair_bonus": pair_bonus,
        "pair_reasons": pair_reasons,
        "pair_penalties": pair_penalties,
        "top_explainability": top.explainability,
        "bottom_explainability": bottom.explainability,
        "formula": "((top_score + bottom_score)/2) + pair_bonus",
    }

    return RankResult(
        row=row,
        final_score=final_score,
        raw_score=raw_score,
        confidence_multiplier=(top.confidence_multiplier + bottom.confidence_multiplier) / 2.0,
        color_delta=(top.color_delta + bottom.color_delta) / 2.0,
        reasons=reasons,
        penalties=penalties,
        flags=flags,
        explainability=explainability,
    )


def _filter_garment_results(
    results: List[RankResult],
    requested_categories: Set[str],
    requested_subtypes: Set[str],
) -> List[RankResult]:
    if not requested_categories and not requested_subtypes:
        return list(results)
    selected: List[RankResult] = []
    for r in results:
        category = _norm(r.row.get("GarmentCategory", ""))
        subtype = _norm(r.row.get("GarmentSubtype", ""))
        if requested_categories and category in requested_categories:
            selected.append(r)
            continue
        if requested_subtypes and subtype in requested_subtypes:
            selected.append(r)
    return selected


def rank_recommendation_candidates(
    *,
    rows: List[Dict[str, Any]],
    user_profile: Dict[str, Any],
    tier2_rules: Dict[str, Any],
    strictness: str = "balanced",
    mode: str = "auto",
    request_text: str = "",
    max_results: int = 0,
) -> Tuple[List[RankResult], RecommendationMeta]:
    assembly_rules = load_outfit_assembly_rules()
    base_ranked = rank_garments(rows=rows, user_profile=user_profile, rules=tier2_rules, strictness=strictness)
    resolved_mode, requested_categories, requested_subtypes = resolve_recommendation_mode(
        mode=mode,
        request_text=request_text,
        rules=assembly_rules,
    )

    single_candidates: List[RankResult] = []
    combo_candidates: List[RankResult] = []

    if resolved_mode == "garment":
        targeted = _filter_garment_results(base_ranked, requested_categories, requested_subtypes)
        working = targeted if targeted else base_ranked
        single_candidates = [_as_single_candidate(r) for r in working]
    else:
        complete_only = [r for r in base_ranked if _is_complete_single(r.row, assembly_rules)]
        if not complete_only:
            complete_only = list(base_ranked)
        single_candidates = [_as_single_candidate(r) for r in complete_only]

        limits = dict(assembly_rules.get("candidate_limits") or {})
        tops = [r for r in base_ranked if _is_top_candidate(r.row, assembly_rules)]
        bottoms = [r for r in base_ranked if _is_bottom_candidate(r.row, assembly_rules)]
        tops = tops[: int(limits.get("max_top_items", 24))]
        bottoms = bottoms[: int(limits.get("max_bottom_items", 24))]
        max_pairs_per_top = int(limits.get("max_pairs_per_top", 6))
        max_total_combos = int(limits.get("max_total_combos", 120))

        seen: Set[Tuple[str, str]] = set()
        for top in tops:
            pair_bucket: List[RankResult] = []
            top_id = str(top.row.get("id", ""))
            for bottom in bottoms:
                bottom_id = str(bottom.row.get("id", ""))
                if not top_id or not bottom_id or top_id == bottom_id:
                    continue
                dedupe_key = tuple(sorted([top_id, bottom_id]))
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)
                bonus, pair_reasons, pair_penalties = _pair_bonus(top.row, bottom.row, assembly_rules)
                pair_bucket.append(
                    _build_combo_candidate(
                        top=top,
                        bottom=bottom,
                        pair_bonus=bonus,
                        pair_reasons=pair_reasons,
                        pair_penalties=pair_penalties,
                    )
                )
            pair_bucket.sort(key=lambda x: x.final_score, reverse=True)
            combo_candidates.extend(pair_bucket[:max_pairs_per_top])
            if len(combo_candidates) >= max_total_combos:
                break
        combo_candidates = sorted(combo_candidates, key=lambda x: x.final_score, reverse=True)[:max_total_combos]

    merged = sorted(single_candidates + combo_candidates, key=lambda x: x.final_score, reverse=True)
    if max_results > 0:
        merged = merged[:max_results]
    for rank, result in enumerate(merged, start=1):
        result.row["rank"] = str(rank)

    meta = RecommendationMeta(
        resolved_mode=resolved_mode,
        requested_categories=sorted(requested_categories),
        requested_subtypes=sorted(requested_subtypes),
        base_ranked_rows=len(base_ranked),
        single_candidates=len(single_candidates),
        combo_candidates=len(combo_candidates),
        returned_rows=len(merged),
    )
    return merged, meta
