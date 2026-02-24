import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from openai import OpenAI

from catalog_enrichment.config_registry import load_reinforcement_framework
from style_engine.filters import (
    UserContext,
    filter_catalog_rows,
    filter_catalog_rows_minimal_hard,
    load_tier_a_rules,
    parse_relaxed_filters,
    read_csv_rows,
)
from style_engine.ranker import load_tier2_rules, rank_garments
from user_profiler.config import UserProfilerConfig, get_api_key
from user_profiler.service import infer_text_context, infer_visual_profile


class ProfileAgent:
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


class RecommendationAgent:
    def __init__(self, catalog_csv_path: str):
        self.catalog_csv_path = catalog_csv_path
        self.tier1_rules = load_tier_a_rules()
        self.tier2_rules = load_tier2_rules()

    def _filter_rows(
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

    def recommend(
        self,
        *,
        context: Dict[str, str],
        profile: Dict[str, Any],
        strictness: str,
        hard_filter_profile: str,
        max_results: int,
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

        ranked = rank_garments(rows=passed, user_profile=profile, rules=self.tier2_rules, strictness=strictness)
        total_ranked = len(ranked)
        ranked = ranked[:max_results]

        items: List[Dict[str, Any]] = []
        for idx, result in enumerate(ranked, start=1):
            row = result.row
            reasons_str = str(row.get("tier2_reasons", ""))
            flags_str = str(row.get("tier2_flags", ""))
            reasons = [x for x in reasons_str.split("|") if x]
            flags = [x for x in flags_str.split("|") if x]
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
            },
        }


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
        reward_map = framework.get("reward_policy") or {}
        self.reward_map = {str(k): int(v) for k, v in reward_map.items()} if reward_map else {
            "like": 5,
            "share": 10,
            "buy": 50,
            "skip": -1,
        }

    def reward_for_event(self, event_type: str) -> int:
        return int(self.reward_map.get(event_type, 0))
