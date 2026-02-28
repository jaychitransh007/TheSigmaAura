import json
import copy
from typing import Any, Dict, List, Optional, Set, Tuple

from openai import OpenAI

from catalog_enrichment.config_registry import load_outfit_assembly_rules, load_reinforcement_framework
from style_engine.intent_policy import (
    apply_intent_policy_filters,
    resolve_intent_policy,
)
from style_engine.filters import (
    UserContext,
    filter_catalog_rows,
    filter_catalog_rows_minimal_hard,
    load_tier_a_rules,
    parse_relaxed_filters,
    read_csv_rows,
)
from style_engine.outfit_engine import (
    resolve_recommendation_mode,
    rank_recommendation_candidates,
)
from style_engine.ranker import load_tier2_rules
from user_profiler.config import UserProfilerConfig, get_api_key
from user_profiler.schemas import BODY_ENUMS
from user_profiler.service import infer_text_context, infer_visual_profile


# ---------------------------------------------------------------------------
# Intent & Mode Router Agent
# ---------------------------------------------------------------------------

class IntentModeRouterAgent:
    """Resolves mode_preference (auto|garment|outfit) into resolved_mode."""

    def __init__(self) -> None:
        self.outfit_rules = load_outfit_assembly_rules()

    def resolve_mode(
        self,
        *,
        mode_preference: str = "auto",
        target_garment_type: Optional[str] = None,
        request_text: str = "",
    ) -> Dict[str, Any]:
        effective_mode = mode_preference
        if effective_mode == "auto":
            if target_garment_type:
                effective_mode = "garment"
            else:
                effective_mode = "outfit"

        resolved_mode, requested_categories, requested_subtypes = resolve_recommendation_mode(
            mode=effective_mode,
            request_text=request_text,
            rules=self.outfit_rules,
        )

        complete_the_look_offer = resolved_mode == "garment"

        return {
            "resolved_mode": resolved_mode,
            "complete_the_look_offer": complete_the_look_offer,
            "requested_categories": sorted(requested_categories),
            "requested_subtypes": sorted(requested_subtypes),
        }


# ---------------------------------------------------------------------------
# User Profile & Identity Agent
# ---------------------------------------------------------------------------

class UserProfileAgent:
    """Owns explicit user profile: sizes, fit prefs, brand prefs, consent. Merge via last-write-wins."""

    @staticmethod
    def merge_profile(
        existing: Optional[Dict[str, Any]],
        size_overrides: Optional[Dict[str, Any]] = None,
        initial_profile: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        profile = dict(existing or {})
        if initial_profile:
            for key, value in initial_profile.items():
                if value is not None:
                    profile[key] = value
        if size_overrides:
            sizes = dict(profile.get("sizes") or {})
            for key, value in size_overrides.items():
                if value is not None:
                    sizes[key] = value
            profile["sizes"] = sizes
        return profile

    @staticmethod
    def profile_fields_used(profile: Dict[str, Any]) -> List[str]:
        fields: List[str] = []
        for key, value in profile.items():
            if value and key != "color_preferences":
                fields.append(key)
        return fields


# ---------------------------------------------------------------------------
# Body Harmony & Archetype Agent
# ---------------------------------------------------------------------------

class BodyHarmonyAgent:
    """Owns inferred body-harmony attributes and archetype confidence."""

    def __init__(self, config: UserProfilerConfig):
        self.config = config
        self._client: Optional[OpenAI] = None

    @property
    def client(self) -> OpenAI:
        if self._client is None:
            self._client = OpenAI(api_key=get_api_key())
        return self._client

    def infer_visual(self, image_ref: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        return infer_visual_profile(client=self.client, image_ref=image_ref, config=self.config)

    @staticmethod
    def extract_body_profile(visual: Dict[str, Any]) -> Dict[str, Any]:
        profile = {key: visual[key] for key in BODY_ENUMS.keys()}
        profile["color_preferences"] = {}
        return profile

    @staticmethod
    def style_constraints_from_profile(profile: Dict[str, Any]) -> List[str]:
        constraints: List[str] = []
        if profile:
            constraints.append("body_harmony")
        return constraints


# Legacy aliases for backward compatibility with existing orchestrator / tests.
ProfileAgent = BodyHarmonyAgent


class IntentAgent:
    def __init__(self, config: UserProfilerConfig):
        self.config = config
        self._client: Optional[OpenAI] = None

    @property
    def client(self) -> OpenAI:
        if self._client is None:
            self._client = OpenAI(api_key=get_api_key())
        return self._client

    def infer_text(self, message: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        return infer_text_context(client=self.client, context_text=message, config=self.config)


# ---------------------------------------------------------------------------
# Style Sub-Agents
# ---------------------------------------------------------------------------

class StyleRequirementInterpreter:
    """Parses request text into occasion, vibe, and constraint signals for downstream agents."""

    @staticmethod
    def interpret(request_text: str, context: Dict[str, str]) -> Dict[str, Any]:
        return {
            "occasion": context.get("occasion", ""),
            "archetype": context.get("archetype", ""),
            "request_text": request_text,
        }


class CatalogFilterSubAgent:
    """Tier-1 hard filtering: inventory, price, occasion, gender, policy safety."""

    def __init__(self) -> None:
        self.tier1_rules = load_tier_a_rules()

    def filter_rows(
        self,
        *,
        rows: List[Dict[str, str]],
        ctx: UserContext,
        hard_filter_profile: str,
        relax_filters: Optional[List[str]] = None,
    ) -> Tuple[List[Dict[str, str]], List[Dict[str, Any]], List[str]]:
        if hard_filter_profile == "legacy":
            relaxed = parse_relaxed_filters(relax_filters or [])
            passed, failed = filter_catalog_rows(
                rows=rows,
                ctx=ctx,
                rules=self.tier1_rules,
                relaxed_filters=relaxed,
            )
            return passed, failed, sorted(relaxed)

        passed, failed = filter_catalog_rows_minimal_hard(rows=rows, ctx=ctx, rules=self.tier1_rules)
        return passed, failed, []


class GarmentRankerSubAgent:
    """Tier-2 personalized ranking of individual garments."""

    def __init__(self) -> None:
        self.tier2_rules = load_tier2_rules()

    def rank(
        self,
        *,
        rows: List[Dict[str, str]],
        user_profile: Dict[str, Any],
        strictness: str,
        mode: str,
        include_combos: bool,
        request_text: str,
        max_results: int,
        intent_policy_id: str,
        intent_policy: Dict[str, Any],
    ) -> Tuple[Any, Any]:
        return rank_recommendation_candidates(
            rows=rows,
            user_profile=user_profile,
            tier2_rules=self.tier2_rules,
            strictness=strictness,
            mode=mode,
            include_combos=include_combos,
            request_text=request_text,
            max_results=max_results,
            intent_policy_id=intent_policy_id,
            intent_policy=intent_policy,
        )


class IntentPolicySubAgent:
    """Resolves and applies intent policy constraints and ranking priors."""

    @staticmethod
    def resolve(request_text: str, context: Dict[str, str]) -> Dict[str, Any]:
        return resolve_intent_policy(request_text=request_text, context=context)

    @staticmethod
    def apply_filters(rows: List[Dict[str, Any]], policy: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        return apply_intent_policy_filters(rows=rows, policy=policy)


class BrandVarianceComfortSubAgent:
    """Applies brand sizing heuristics and comfort/ease rules. Placeholder for MVP."""

    @staticmethod
    def apply(
        items: List[Dict[str, Any]],
        size_overrides: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        # MVP: pass-through. Brand variance and comfort adjustments will be
        # added when per-brand heuristic data is available.
        return items


# ---------------------------------------------------------------------------
# Recommendation Agent (orchestrates style sub-agents)
# ---------------------------------------------------------------------------

class RecommendationAgent:
    def __init__(self, catalog_csv_path: str):
        self.catalog_csv_path = catalog_csv_path
        self.catalog_filter = CatalogFilterSubAgent()
        self.garment_ranker = GarmentRankerSubAgent()
        self.intent_policy_agent = IntentPolicySubAgent()
        self.brand_variance_agent = BrandVarianceComfortSubAgent()
        self.outfit_rules = load_outfit_assembly_rules()
        # Keep direct references for legacy compatibility.
        self.tier1_rules = self.catalog_filter.tier1_rules
        self.tier2_rules = self.garment_ranker.tier2_rules

    @staticmethod
    def _norm(value: Any) -> str:
        return str(value or "").strip().lower()

    def _count_complete_candidates(self, rows: List[Dict[str, Any]]) -> int:
        complete_values = {self._norm(x) for x in (self.outfit_rules.get("single_complete_values") or [])}
        complete_categories = {self._norm(x) for x in (self.outfit_rules.get("single_complete_categories") or [])}
        combo_req = dict(self.outfit_rules.get("combo_requirements") or {})
        incomplete_values = {
            self._norm(x) for x in ((combo_req.get("top_values") or []) + (combo_req.get("bottom_values") or []))
        }
        count = 0
        for row in rows:
            sc = self._norm(row.get("StylingCompleteness", ""))
            category = self._norm(row.get("GarmentCategory", ""))
            if sc in incomplete_values:
                continue
            if sc in complete_values or category in complete_categories:
                count += 1
        return count

    def _policy_thresholds(self, policy: Dict[str, Any], max_results: int) -> Tuple[int, int]:
        min_results_to_enforce = int(policy.get("min_results_to_enforce", 0) or 0)
        if min_results_to_enforce <= 0:
            min_results_to_enforce = max(12, max_results * 2)
        min_complete_results = int(policy.get("min_complete_results_to_enforce", 0) or 0)
        return min_results_to_enforce, min_complete_results

    def _meets_policy_thresholds(
        self,
        *,
        rows: List[Dict[str, Any]],
        include_combos: bool,
        max_results: int,
        min_results_to_enforce: int,
        min_complete_results: int,
    ) -> bool:
        if len(rows) < min_results_to_enforce:
            return False
        if include_combos:
            return True
        required_complete = min_complete_results if min_complete_results > 0 else max(1, max_results // 2)
        return self._count_complete_candidates(rows) >= required_complete

    @staticmethod
    def _drop_required_values(policy: Dict[str, Any], attrs: List[str]) -> Dict[str, Any]:
        staged = copy.deepcopy(policy)
        hard = dict(staged.get("hard_constraints") or {})
        required = dict(hard.get("require_values") or {})
        for attr in attrs:
            required.pop(str(attr), None)
        hard["require_values"] = required
        staged["hard_constraints"] = hard
        return staged

    @staticmethod
    def _expand_required_values(policy: Dict[str, Any], expansion: Dict[str, List[str]]) -> Dict[str, Any]:
        staged = copy.deepcopy(policy)
        hard = dict(staged.get("hard_constraints") or {})
        required = dict(hard.get("require_values") or {})
        for attr, values in (expansion or {}).items():
            existing = [str(v) for v in (required.get(attr) or []) if str(v).strip()]
            merged: List[str] = []
            for value in existing + [str(v) for v in (values or []) if str(v).strip()]:
                if value not in merged:
                    merged.append(value)
            required[attr] = merged
        hard["require_values"] = required
        staged["hard_constraints"] = hard
        return staged

    def _is_smart_casual_row(self, row: Dict[str, Any]) -> bool:
        return self._norm(row.get("OccasionFit", "")) == "smart_casual" or self._norm(
            row.get("FormalityLevel", "")
        ) == "smart_casual"

    def _smart_casual_rank_key(self, row: Dict[str, Any]) -> Tuple[int, int]:
        score = 0
        if self._norm(row.get("OccasionSignal", "")) == "office":
            score += 2
        if self._norm(row.get("OccasionFit", "")) == "workwear":
            score += 2
        if self._norm(row.get("FormalityLevel", "")) in {"semi_formal", "formal"}:
            score += 2
        if self._norm(row.get("FitType", "")) == "tailored":
            score += 1
        if self._norm(row.get("GarmentCategory", "")) == "outerwear":
            score -= 2
        return score, -int(row.get("_row_idx", "0") or 0)

    def _limit_smart_casual_rows(
        self,
        *,
        rows: List[Dict[str, Any]],
        max_results: int,
        min_total_rows: int,
        limit_cfg: Dict[str, Any],
    ) -> Tuple[List[Dict[str, Any]], int]:
        smart_rows = [r for r in rows if self._is_smart_casual_row(r)]
        non_smart_rows = [r for r in rows if not self._is_smart_casual_row(r)]
        if not smart_rows:
            return rows, 0

        max_fraction = float(limit_cfg.get("max_fraction", 0.34) or 0.34)
        max_items = int(limit_cfg.get("max_items", 2) or 2)
        fraction_cap = int((max_results * max_fraction) + 0.9999)
        allowed_smart = max(0, min(max_items, fraction_cap))
        required_for_floor = max(0, min_total_rows - len(non_smart_rows))
        allowed_smart = max(allowed_smart, required_for_floor)
        allowed_smart = min(allowed_smart, len(smart_rows))

        if len(smart_rows) <= allowed_smart:
            return rows, 0

        smart_rows = sorted(smart_rows, key=self._smart_casual_rank_key, reverse=True)
        kept_smart = smart_rows[:allowed_smart]
        dropped = len(smart_rows) - len(kept_smart)
        return non_smart_rows + kept_smart, dropped

    def _filter_rows(
        self,
        *,
        rows: List[Dict[str, str]],
        ctx: UserContext,
        hard_filter_profile: str,
        relax_filters: Optional[List[str]] = None,
    ) -> Tuple[List[Dict[str, str]], List[Dict[str, Any]], List[str]]:
        return self.catalog_filter.filter_rows(
            rows=rows,
            ctx=ctx,
            hard_filter_profile=hard_filter_profile,
            relax_filters=relax_filters,
        )

    def recommend(
        self,
        *,
        context: Dict[str, str],
        profile: Dict[str, Any],
        strictness: str,
        hard_filter_profile: str,
        max_results: int,
        recommendation_mode: str = "auto",
        include_combos: bool = True,
        request_text: str = "",
    ) -> Dict[str, Any]:
        rows = read_csv_rows(self.catalog_csv_path)
        for i, row in enumerate(rows):
            row["_row_idx"] = str(i)

        ctx = UserContext(
            occasion=context["occasion"],
            archetype=context["archetype"],
            gender=context["gender"],
            age=context["age"],
        )

        passed, failed, relaxed = self._filter_rows(
            rows=rows,
            ctx=ctx,
            hard_filter_profile=hard_filter_profile,
            relax_filters=[],
        )

        policy_resolution = self.intent_policy_agent.resolve(
            request_text=request_text,
            context=context,
        )
        active_policy_id = str(policy_resolution.get("policy_id", ""))
        active_policy = dict(policy_resolution.get("policy") or {})
        policy_keyword_hits = list(policy_resolution.get("keyword_hits") or [])
        policy_hard_filter_applied = False
        policy_hard_filter_relaxed = False
        policy_relaxation_stage = "none"
        policy_smart_casual_trimmed = 0
        policy_failed: List[Dict[str, Any]] = []

        if active_policy_id and active_policy:
            min_results_to_enforce, min_complete_results = self._policy_thresholds(active_policy, max_results)
            relax_cfg = dict(active_policy.get("relaxation") or {})

            stage_policies: List[Tuple[str, Dict[str, Any]]] = [("strict", active_policy)]
            stage_1_drop = [str(x) for x in (relax_cfg.get("stage_1_drop_require_values") or []) if str(x).strip()]
            if stage_1_drop:
                stage_policies.append(("style_relaxed", self._drop_required_values(active_policy, stage_1_drop)))
            stage_2_expand = dict(relax_cfg.get("stage_2_expand_require_values") or {})
            if stage_2_expand:
                base_for_stage2 = stage_policies[-1][1]
                stage_policies.append(("formality_relaxed", self._expand_required_values(base_for_stage2, stage_2_expand)))

            final_stage_rows: List[Dict[str, Any]] = []
            final_stage_failed: List[Dict[str, Any]] = []
            final_stage_name = "strict"
            matched_stage = False
            for stage_name, stage_policy in stage_policies:
                stage_rows, stage_failed = self.intent_policy_agent.apply_filters(rows=passed, policy=stage_policy)
                final_stage_rows, final_stage_failed = stage_rows, stage_failed
                final_stage_name = stage_name
                if self._meets_policy_thresholds(
                    rows=stage_rows,
                    include_combos=include_combos,
                    max_results=max_results,
                    min_results_to_enforce=min_results_to_enforce,
                    min_complete_results=min_complete_results,
                ):
                    matched_stage = True
                    break

            if (
                not matched_stage
                and bool((relax_cfg.get("stage_3_allow_limited_smart_casual") or {}).get("enabled", False))
            ):
                stage3_base = stage_policies[-1][1]
                stage3_policy = self._expand_required_values(
                    stage3_base,
                    {"FormalityLevel": ["smart_casual"], "OccasionFit": ["smart_casual"]},
                )
                stage3_rows, stage3_failed = self.intent_policy_agent.apply_filters(rows=passed, policy=stage3_policy)
                stage3_limited, policy_smart_casual_trimmed = self._limit_smart_casual_rows(
                    rows=stage3_rows,
                    max_results=max_results,
                    min_total_rows=min_results_to_enforce,
                    limit_cfg=dict(relax_cfg.get("stage_3_allow_limited_smart_casual") or {}),
                )
                final_stage_rows, final_stage_failed = stage3_limited, stage3_failed
                final_stage_name = "smart_casual_limited"
                if self._meets_policy_thresholds(
                    rows=stage3_limited,
                    include_combos=include_combos,
                    max_results=max_results,
                    min_results_to_enforce=min_results_to_enforce,
                    min_complete_results=min_complete_results,
                ):
                    matched_stage = True

            if matched_stage:
                passed = final_stage_rows
                policy_failed = final_stage_failed
                policy_hard_filter_applied = True
                policy_relaxation_stage = final_stage_name
            else:
                policy_hard_filter_relaxed = True
                policy_failed = final_stage_failed
                policy_relaxation_stage = "policy_relaxed_off"

        ranked, recommendation_meta = self.garment_ranker.rank(
            rows=passed,
            user_profile=profile,
            strictness=strictness,
            mode=recommendation_mode,
            include_combos=include_combos,
            request_text=request_text,
            max_results=max_results,
            intent_policy_id=active_policy_id,
            intent_policy=active_policy,
        )
        total_ranked = recommendation_meta.returned_rows

        items: List[Dict[str, Any]] = []
        for idx, result in enumerate(ranked, start=1):
            row = result.row
            reasons = [x.strip() for x in str(row.get("tier2_reasons", "")).split(";") if x.strip()]
            flags = [x.strip() for x in str(row.get("tier2_flags", "")).split("|") if x.strip()]
            component_ids_raw = str(row.get("component_ids_json", "[]"))
            component_titles_raw = str(row.get("component_titles_json", "[]"))
            component_image_urls_raw = str(row.get("component_image_urls_json", "[]"))
            try:
                component_ids = list(json.loads(component_ids_raw))
            except json.JSONDecodeError:
                component_ids = []
            try:
                component_titles = list(json.loads(component_titles_raw))
            except json.JSONDecodeError:
                component_titles = []
            try:
                component_image_urls = list(json.loads(component_image_urls_raw))
            except json.JSONDecodeError:
                component_image_urls = []
            items.append(
                {
                    "rank": idx,
                    "garment_id": str(row.get("id", "")),
                    "title": str(row.get("title", "")),
                    "image_url": str(row.get("images__0__src", "")),
                    "score": float(row.get("tier2_final_score", 0.0) or 0.0),
                    "max_score": float(row.get("tier2_max_score", 0.0) or 0.0),
                    "compatibility_confidence": float(row.get("tier2_compatibility_confidence", 0.0) or 0.0),
                    "reasons": "; ".join(reasons),
                    "flags": flags,
                    "raw_reasons": reasons,
                    "recommendation_kind": str(row.get("recommendation_kind", "single_garment")),
                    "outfit_id": str(row.get("outfit_id", row.get("id", ""))),
                    "component_count": int(row.get("component_count", 1) or 1),
                    "component_ids": component_ids,
                    "component_titles": component_titles,
                    "component_image_urls": component_image_urls,
                }
            )

        return {
            "items": items,
            "meta": {
                "total_catalog_rows": len(rows),
                "filtered_rows": len(passed),
                "failed_rows": len(failed),
                "ranked_rows": total_ranked,
                "returned_rows": len(items),
                "relaxed_filters": relaxed,
                "recommendation_mode": recommendation_mode,
                "include_combos": include_combos,
                "resolved_recommendation_mode": recommendation_meta.resolved_mode,
                "requested_categories": recommendation_meta.requested_categories,
                "requested_subtypes": recommendation_meta.requested_subtypes,
                "single_candidates": recommendation_meta.single_candidates,
                "combo_candidates": recommendation_meta.combo_candidates,
                "intent_policy_id": active_policy_id,
                "intent_policy_keyword_hits": policy_keyword_hits,
                "intent_policy_hard_filter_applied": policy_hard_filter_applied,
                "intent_policy_hard_filter_relaxed": policy_hard_filter_relaxed,
                "intent_policy_failed_rows": len(policy_failed),
                "intent_policy_relaxation_stage": policy_relaxation_stage,
                "intent_policy_smart_casual_trimmed": policy_smart_casual_trimmed,
            },
        }


# ---------------------------------------------------------------------------
# Policy & Trust Guardrail Agent
# ---------------------------------------------------------------------------

class PolicyGuardrailAgent:
    """Enforces hard policy constraints. Blocks unsupported actions."""

    BLOCKED_ACTIONS = frozenset({"execute_purchase", "place_order", "confirm_order", "submit_order"})

    GUARDRAIL_EXPLANATIONS = {
        "execute_purchase": (
            "Aura is a recommendation and checkout-preparation assistant. "
            "Order placement is not supported. Please complete your purchase "
            "through the retailer's checkout flow using the prepared cart."
        ),
        "place_order": (
            "Order placement is outside Aura's scope. "
            "Use the checkout preparation to build your cart, then complete "
            "the purchase through the retailer's checkout."
        ),
    }

    DEFAULT_EXPLANATION = (
        "This action is not supported by the Aura platform. "
        "Aura assists with recommendations and checkout preparation only."
    )

    @classmethod
    def check_action(cls, action: str) -> dict:
        """Returns {"allowed": True} or {"allowed": False, "reason": "..."}."""
        normalized = action.strip().lower().replace("-", "_").replace(" ", "_")
        if normalized in cls.BLOCKED_ACTIONS:
            explanation = cls.GUARDRAIL_EXPLANATIONS.get(
                normalized, cls.DEFAULT_EXPLANATION
            )
            return {"allowed": False, "reason": explanation, "blocked_action": normalized}
        return {"allowed": True, "blocked_action": None, "reason": ""}

    @classmethod
    def blocked_actions_list(cls) -> list:
        return sorted(cls.BLOCKED_ACTIONS)


class StylistAgent:
    def build_response_message(
        self,
        items: List[Dict[str, Any]],
        context: Dict[str, str],
        user_message: str = "",
    ) -> Tuple[str, bool, str]:
        if not items:
            question = "I could not find strong matches yet. Do you want to relax constraints or upload another image?"
            return (
                "I filtered and ranked the catalog, but there are no strong matches for your current constraints.",
                True,
                question,
            )

        top = items[0]
        msg = (
            f"Top recommendations are ready for {context['occasion']} with {context['archetype']} styling. "
            f"Best match right now is '{top['title']}' with score {top['score']:.3f}."
        )

        if not user_message.strip():
            return msg, False, ""

        top_conf = float(top.get("compatibility_confidence", 0.0) or 0.0)
        text = user_message.lower()
        preference_tokens = (
            "color",
            "fit",
            "silhouette",
            "sleeve",
            "neckline",
            "length",
            "fabric",
            "budget",
            "price",
            "prefer",
            "avoid",
        )
        has_preferences = any(tok in text for tok in preference_tokens)

        if top_conf < 0.60:
            return (
                msg,
                True,
                "I can refine better if you share your preferred colors, fit (slim/regular/relaxed), and coverage level.",
            )
        if len(user_message.strip()) < 90 and not has_preferences:
            return (
                msg,
                True,
                "To personalize further, tell me your preferred colors, fit, and any no-go details.",
            )

        return msg, False, ""


class MemoryAgent:
    def merge_context(
        self,
        *,
        previous: Optional[Dict[str, Any]],
        inferred_text: Dict[str, str],
        inferred_visual: Optional[Dict[str, Any]],
    ) -> Dict[str, str]:
        base = dict(previous or {})
        if inferred_text:
            base["occasion"] = inferred_text.get("occasion", base.get("occasion", ""))
            base["archetype"] = inferred_text.get("archetype", base.get("archetype", ""))
        if inferred_visual:
            base["gender"] = inferred_visual.get("gender", base.get("gender", ""))
            base["age"] = inferred_visual.get("age", base.get("age", ""))
        return {
            "occasion": str(base.get("occasion", "")),
            "archetype": str(base.get("archetype", "")),
            "gender": str(base.get("gender", "")),
            "age": str(base.get("age", "")),
        }


class TelemetryAgent:
    def __init__(self):
        framework = load_reinforcement_framework()
        reward_map = framework.get("reward_weights") or framework.get("reward_policy") or {}
        self.reward_map = {str(k): int(v) for k, v in reward_map.items()} if reward_map else {
            "dislike": -5,
            "like": 2,
            "share": 10,
            "buy": 20,
            "no_action": -1,
            "skip": -1,
        }
        # Keep no_action and skip aligned for compatibility.
        if "no_action" in self.reward_map and "skip" not in self.reward_map:
            self.reward_map["skip"] = int(self.reward_map["no_action"])
        if "skip" in self.reward_map and "no_action" not in self.reward_map:
            self.reward_map["no_action"] = int(self.reward_map["skip"])

    def reward_for_event(self, event_type: str) -> int:
        return int(self.reward_map.get(event_type, 0))
