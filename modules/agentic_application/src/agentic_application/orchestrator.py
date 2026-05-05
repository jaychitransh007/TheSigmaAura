from __future__ import annotations

import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Thread
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import quote

from platform_core.config import AuraRuntimeConfig
from platform_core.fallback_messages import graceful_policy_message
from platform_core.restricted_categories import detect_restricted_record
from platform_core.repositories import ConversationRepository
from platform_core.request_context import (
    run_with_context,
    set_turn_id,
    set_conversation_id,
    set_external_user_id,
    snapshot as _snapshot_request_context,
)

from .agents.catalog_search_agent import CatalogSearchAgent
from .agents.copilot_planner import CopilotPlanner, build_planner_input
from .agents.outfit_architect import OutfitArchitect
from .agents.outfit_composer import OutfitComposer
from .agents.outfit_rater import OutfitRater
# Evaluator history (May 5 2026):
#   - Phase 12B (April 2026): OutfitEvaluator (text-only) replaced by
#     VisualEvaluatorAgent (vision-grounded).
#   - Phase 12E (May 2026): VisualEvaluatorAgent moved to on-demand.
#   - PR V2 (May 5 2026): VisualEvaluatorAgent + outfit_check +
#     garment_evaluation intents removed entirely. The Rater's 5
#     sub-scores power the outfit-card radar directly. tryon_render
#     still produces the image; the Rater scores from text attributes.
#
# OutfitAssembler + Reranker removed (May 3 2026) — replaced with the
# OutfitComposer + OutfitRater LLM ranker pipeline. Cosine similarity is
# now a retrieval primitive only; LLM judgment handles all reasoning
# about whether items belong together.
from .agents.response_formatter import ResponseFormatter
from .product_links import resolve_product_url
from .agents.style_advisor_agent import StyleAdvice, StyleAdvisorAgent
from .tracing import TurnTraceBuilder
from .context.conversation_memory import build_conversation_memory
from .context.user_context_builder import build_user_context, validate_minimum_profile
from .filters import build_global_hard_filters
from .intent_registry import Action, FollowUpIntent, Intent
from .onboarding_gate import evaluate as evaluate_onboarding_gate
from .recommendation_confidence import evaluate_recommendation_confidence
from .services.catalog_retrieval_gateway import ApplicationCatalogRetrievalGateway
from .services.onboarding_gateway import ApplicationUserGateway
from .services.tryon_quality_gate import TryonQualityGate
from .services.tryon_service import TryonService
from .services.outfit_decomposition import decompose_outfit_image
from .qna_messages import generate_stage_message
from .schemas import (
    CombinedContext,
    ComposedOutfit,
    CopilotPlanResult,
    EvaluatedRecommendation,
    IntentClassification,
    LiveContext,
    OutfitCandidate,
    OutfitCard,
    ProfileConfidence,
    RecommendationConfidence,
    RetrievedProduct,
    RetrievedSet,
)

_log = logging.getLogger(__name__)


_URL_RE = re.compile(r"https?://\S+")

# Per-outfit confidence threshold (0-1). Outfits below this never reach
# the user — instead we surface an honest "no confident match" message
# and offer alternative paths. Applied to wardrobe-first selection only
# (normalized item score). The catalog pipeline uses
# ``_RECOMMENDATION_FASHION_THRESHOLD`` against the LLM Rater's
# integer fashion_score (0–100).
_RECOMMENDATION_CONFIDENCE_THRESHOLD = 0.75

# Catalog-pipeline gate. After Composer + Rater, only outfits whose
# Rater fashion_score clears this floor AND were not flagged
# ``unsuitable`` by the Rater reach the user.
#
# History:
# - 75 (initial). Over-rejected palette-mid candidates that downstream
#   try-on + rater rationale showed were perfectly acceptable.
# - 60 (PR #81). More permissive on the 0–100 scale; ``unsuitable: true``
#   still hard-dropped genuinely bad outfits.
# - 50 (R7, May 5 2026). Rater moved to a 1/2/3 scale rescaled to 0–100
#   in compute_fashion_score. All-2s now lands at exactly 50, so the
#   threshold "every dim is at least neutral" maps cleanly to 50. An
#   outfit that's 2 across the board barely clears; one with even one
#   "1" on a heavily-weighted axis falls below.
_RECOMMENDATION_FASHION_THRESHOLD = 50

# Maximum raw score from `_select_wardrobe_occasion_outfit._score`:
#   +3 occasion_fit exact match
#   +1 formality_level matches occasion class
_WARDROBE_SCORE_MAX = 4.0



# Module-level no-op trace stub. Used by handlers that accept an
# optional `trace: Optional[TurnTraceBuilder]` so tests / one-off call
# sites can pass nothing and still call `add_cost(...)` etc. without
# null-checks. Keeping this a singleton (rather than redefining the
# class on every handler call) avoids the small but real cost of
# rebuilding the type each turn.
class _NoOpTrace:
    def add_cost(self, *_args, **_kwargs) -> None:
        pass

    def add_model_cost_from_row(self, *_args, **_kwargs) -> None:
        pass

    def set_evaluation(self, *_args, **_kwargs) -> None:
        pass


_NO_OP_TRACE = _NoOpTrace()


def _build_candidate_item(product: "RetrievedProduct", role: str = "") -> Dict[str, Any]:
    """Compact dict per item for an OutfitCandidate, fed to the visual
    evaluator and the response formatter.

    Matches the shape the legacy OutfitAssembler emitted (PR #30 keeps
    the contract stable so downstream consumers — try-on render path,
    response formatter, frontend renderers — don't need changes).
    Pulls image URL, title, price, product URL, and the dozen
    enrichment attributes the evaluator reads. Falls through CamelCase
    + snake_case + metadata + enriched_data to handle both catalog and
    wardrobe row shapes.
    """
    metadata = product.metadata
    enriched = product.enriched_data
    image_url = str(
        metadata.get("images__0__src")
        or metadata.get("images_0_src")
        or enriched.get("images__0__src")
        or enriched.get("images_0_src")
        or enriched.get("primary_image_url")
        or enriched.get("image_url")
        or enriched.get("image_path")
        or ""
    )
    title = str(metadata.get("title") or enriched.get("title") or product.product_id or "")
    price = str(metadata.get("price") or enriched.get("price") or "")
    product_url = resolve_product_url(
        raw_url=str(metadata.get("url") or enriched.get("url") or enriched.get("product_url") or ""),
        store=str(enriched.get("store") or metadata.get("store") or ""),
        handle=str(enriched.get("handle") or metadata.get("handle") or ""),
        image_url=image_url,
    )
    item: Dict[str, Any] = {
        "product_id": product.product_id,
        "similarity": product.similarity,
        "title": title,
        "image_url": image_url,
        "price": price,
        "product_url": product_url,
        "garment_category": str(enriched.get("garment_category") or metadata.get("GarmentCategory") or ""),
        "garment_subtype": str(enriched.get("garment_subtype") or metadata.get("GarmentSubtype") or ""),
        "styling_completeness": str(enriched.get("styling_completeness") or metadata.get("StylingCompleteness") or ""),
        "primary_color": str(enriched.get("primary_color") or metadata.get("PrimaryColor") or ""),
        "formality_level": str(enriched.get("formality_level") or metadata.get("FormalityLevel") or ""),
        "occasion_fit": str(enriched.get("occasion_fit") or metadata.get("OccasionFit") or ""),
        "pattern_type": str(enriched.get("pattern_type") or metadata.get("PatternType") or ""),
        "volume_profile": str(enriched.get("volume_profile") or metadata.get("VolumeProfile") or ""),
        "fit_type": str(enriched.get("fit_type") or metadata.get("FitType") or ""),
        "silhouette_type": str(enriched.get("silhouette_type") or metadata.get("SilhouetteType") or ""),
    }
    explicit_source = str(enriched.get("source") or "").strip().lower()
    if explicit_source in ("wardrobe", "catalog"):
        item["source"] = explicit_source
    elif enriched.get("image_path") and not (enriched.get("handle") or enriched.get("store")):
        item["source"] = "wardrobe"
    if enriched.get("is_anchor"):
        item["is_anchor"] = True
    if role:
        item["role"] = role
    return item


def _role_for_position(composed: "ComposedOutfit", items_so_far: List[Dict[str, Any]]) -> str:
    """Assign the canonical role label for the next item in a composed outfit.

    Composer outputs item_ids as a flat list. The downstream try-on
    render path expects each item dict to carry a `role` field
    (`top` / `bottom` / `outerwear` / `complete`) so it can position the
    garment correctly on the user's body image. We re-derive the role
    from the outfit's direction_type plus how many items have already
    been built — composers preserve order (top, bottom, outerwear) per
    the prompt, so position-by-index is reliable.
    """
    dt = composed.direction_type
    if dt == "complete":
        return "complete"
    idx = len(items_so_far)
    if dt == "paired":
        return ["top", "bottom"][idx] if idx < 2 else ""
    if dt == "three_piece":
        return ["top", "bottom", "outerwear"][idx] if idx < 3 else ""
    return ""


def extract_urls(message: str) -> List[str]:
    """URL detection helper inlined from the (now-deleted) shopping_decision_agent.

    Used by ``AgenticOrchestrator._uploaded_image_anchor_source`` to flag
    catalog-style image uploads when the user pastes a product link
    alongside the image.
    """
    return [match.rstrip(").,!?") for match in _URL_RE.findall(str(message or ""))]


class AgenticOrchestrator:
    """Application-layer orchestrator implementing the 7-component pipeline."""

    def __init__(
        self,
        *,
        repo: ConversationRepository,
        onboarding_gateway: ApplicationUserGateway,
        config: AuraRuntimeConfig,
        tryon_service: Optional[TryonService] = None,
        tryon_quality_gate: Optional[TryonQualityGate] = None,
    ) -> None:
        self.repo = repo
        self.onboarding_gateway = onboarding_gateway
        self.config = config
        self.tryon_service = tryon_service or TryonService()
        self.tryon_quality_gate = tryon_quality_gate or TryonQualityGate()

        self._retrieval_gateway = ApplicationCatalogRetrievalGateway(repo.client)
        self._catalog_inventory: Optional[list] = None
        self._catalog_rows: Optional[list] = None

        # Architect reasoning effort flows from AuraRuntimeConfig so it
        # can be flipped per-environment (ARCHITECT_REASONING_EFFORT) for
        # the ongoing measure-and-decide work without a code change.
        # Type-check at the boundary: tests pass `config=Mock()` and
        # Mock auto-creates attribute access (so getattr-with-default
        # would still return a Mock). Coerce anything non-string to
        # the constructor default so the constructor's own validation
        # only ever sees real strings.
        _architect_effort_raw = getattr(config, "architect_reasoning_effort", "medium")
        _architect_effort = _architect_effort_raw if isinstance(_architect_effort_raw, str) else "medium"
        self.outfit_architect = OutfitArchitect(reasoning_effort=_architect_effort)
        # Evaluator history (see top of file): OutfitCheckAgent and
        # VisualEvaluatorAgent both removed; the Rater is the sole
        # scoring engine and feeds the radar UI directly.
        self.style_advisor = StyleAdvisorAgent()  # Phase 12C open-ended discovery + explanation
        self.catalog_search_agent = CatalogSearchAgent(
            retrieval_gateway=self._retrieval_gateway,
            client=repo.client,
        )
        # May 3 2026: OutfitAssembler + Reranker replaced by the Composer
        # + Rater LLM ranker pipeline. See agents/outfit_composer.py and
        # agents/outfit_rater.py.
        self.outfit_composer = OutfitComposer()
        self.outfit_rater = OutfitRater()
        # Pool / final caps live here (no longer on a Reranker instance).
        self.recommendation_final_top_n = 3
        self.recommendation_pool_top_n = 5
        self.response_formatter = ResponseFormatter()

        self._copilot_planner = CopilotPlanner()

    # ------------------------------------------------------------------
    # Conversation lifecycle
    # ------------------------------------------------------------------

    @staticmethod
    def _build_catalog_upsell(*, rationale: str, entry_intent: str) -> Dict[str, Any]:
        return {
            "available": True,
            "entry_intent": entry_intent,
            # User-facing copy: keep this in shopper vocabulary, not
            # internal-system vocabulary ("catalog"). The routing handler
            # `_message_requests_catalog_followup` matches against this
            # exact string AND the legacy phrasing for backward compat.
            "cta": "Show me options to buy",
            "rationale": rationale,
        }

    @staticmethod
    def _summarize_answer_components(outfits: List[OutfitCard]) -> Dict[str, Any]:
        breakdown: List[Dict[str, Any]] = []
        wardrobe_item_count = 0
        catalog_item_count = 0
        for outfit in outfits:
            item_sources = [str(item.get("source", "catalog") or "catalog") for item in outfit.items]
            wardrobe_count = sum(1 for source in item_sources if source == "wardrobe")
            catalog_count = sum(1 for source in item_sources if source == "catalog")
            wardrobe_item_count += wardrobe_count
            catalog_item_count += catalog_count
            source_mix = "mixed" if wardrobe_count and catalog_count else ("wardrobe" if wardrobe_count else "catalog")
            breakdown.append(
                {
                    "rank": outfit.rank,
                    "source_mix": source_mix,
                    "wardrobe_item_count": wardrobe_count,
                    "catalog_item_count": catalog_count,
                }
            )

        primary_source = "mixed"
        if wardrobe_item_count and not catalog_item_count:
            primary_source = "wardrobe"
        elif catalog_item_count and not wardrobe_item_count:
            primary_source = "catalog"

        return {
            "primary_source": primary_source,
            "wardrobe_item_count": wardrobe_item_count,
            "catalog_item_count": catalog_item_count,
            "outfit_breakdown": breakdown,
        }

    def _get_catalog_rows(self) -> List[Dict[str, Any]]:
        if self._catalog_rows is None:
            try:
                rows = self.repo.client.select_many("catalog_enriched")
            except Exception:
                rows = []
            self._catalog_rows = list(rows) if isinstance(rows, list) else []
        return list(self._catalog_rows)

    def _catalog_row_to_outfit_item(self, row: Dict[str, Any], *, role: str = "") -> Dict[str, Any]:
        return {
            "product_id": str(row.get("product_id") or ""),
            "similarity": 0.0,
            "title": str(row.get("title") or row.get("product_id") or "Catalog option"),
            "image_url": str(row.get("images__0__src") or row.get("images_0_src") or row.get("primary_image_url") or ""),
            "price": str(row.get("price") or ""),
            "product_url": str(row.get("url") or row.get("product_url") or ""),
            "garment_category": str(row.get("garment_category") or ""),
            "garment_subtype": str(row.get("garment_subtype") or ""),
            "primary_color": str(row.get("primary_color") or ""),
            "role": role,
            "formality_level": str(row.get("formality_level") or ""),
            "occasion_fit": str(row.get("occasion_fit") or ""),
            "pattern_type": str(row.get("pattern_type") or ""),
            "volume_profile": str(row.get("volume_profile") or ""),
            "fit_type": str(row.get("fit_type") or ""),
            "silhouette_type": str(row.get("silhouette_type") or ""),
            "source": "catalog",
        }

    def _select_catalog_items(
        self,
        *,
        desired_roles: List[str],
        occasion: str = "",
        preferred_colors: List[str] | None = None,
        limit: int = 3,
    ) -> List[Dict[str, Any]]:
        normalized_roles = [role for role in desired_roles if role]
        if not normalized_roles:
            return []
        normalized_occasion = self._normalize_text_token(occasion)
        color_preferences = {
            self._normalize_text_token(color)
            for color in list(preferred_colors or [])
            if self._normalize_text_token(color)
        }
        scored: List[tuple[int, Dict[str, Any], str]] = []
        seen_ids: set[str] = set()
        for row in self._get_catalog_rows():
            if detect_restricted_record(row):
                continue
            product_id = str(row.get("product_id") or "").strip()
            if not product_id or product_id in seen_ids:
                continue
            role = self._wardrobe_role_of(row)
            if role not in normalized_roles:
                continue
            score = 10 + (15 - normalized_roles.index(role))
            occasion_fit = self._normalize_text_token(row.get("occasion_fit"))
            if normalized_occasion and occasion_fit and normalized_occasion in occasion_fit:
                score += 6
            primary_color = self._normalize_text_token(row.get("primary_color"))
            if color_preferences and primary_color in color_preferences:
                score += 4
            if str(row.get("product_url") or row.get("url") or "").strip():
                score += 2
            scored.append((score, row, role))
            seen_ids.add(product_id)
        scored.sort(key=lambda item: (-item[0], str(item[1].get("title") or item[1].get("product_id") or "").lower()))
        return [self._catalog_row_to_outfit_item(row, role=role) for _, row, role in scored[:limit]]

    @staticmethod
    def _build_feedback_summary(
        *,
        event_type: str,
        item_ids: List[str],
        outfit_rank: int,
        turn_id: str | None = None,
    ) -> Dict[str, Any]:
        normalized_event = str(event_type or "").strip() or "dislike"
        cleaned_ids = [str(value).strip() for value in item_ids if str(value).strip()]
        return {
            "event_type": normalized_event,
            "item_ids": cleaned_ids,
            "item_count": len(cleaned_ids),
            "outfit_rank": int(outfit_rank or 1),
            "target_turn_id": str(turn_id or "").strip(),
        }

    @staticmethod
    def _attached_item_context(saved_item: Dict[str, Any] | None) -> str:
        item = dict(saved_item or {})
        if not item:
            return ""
        metadata = dict(item.get("metadata_json") or {})
        catalog_attrs = dict(item.get("catalog_attributes") or metadata.get("catalog_attributes") or {})
        parts = [
            str(item.get("title") or "").strip(),
            str(item.get("garment_category") or catalog_attrs.get("GarmentCategory") or "").strip(),
            str(item.get("garment_subtype") or catalog_attrs.get("GarmentSubtype") or "").strip(),
            str(item.get("primary_color") or catalog_attrs.get("PrimaryColor") or "").strip(),
            str(item.get("pattern_type") or catalog_attrs.get("PatternType") or "").strip(),
            str(item.get("occasion_fit") or catalog_attrs.get("OccasionFit") or "").strip(),
            str(item.get("formality_level") or catalog_attrs.get("FormalityLevel") or "").strip(),
        ]
        cleaned = [part for part in parts if part]
        if not cleaned:
            return ""
        return "Attached garment context: " + ", ".join(cleaned) + "."

    def _uploaded_image_anchor_source(self, *, message: str) -> str:
        source_preference = self._message_source_preference(message=message)
        if source_preference:
            return f"{source_preference}_image"
        normalized = self._normalize_text_token(message)
        if extract_urls(message):
            return "catalog_image"
        if any(token in normalized for token in ("product", "catalog", "store", "website", "buy this")):
            return "catalog_image"
        return "wardrobe_image"

    def _message_requests_pairing(self, *, message: str, has_attached_image: bool, has_previous_anchor: bool = False) -> bool:
        normalized = self._normalize_text_token(message)
        if not normalized:
            return False
        # Phrases that work with or without an image (reference "my" wardrobe)
        wardrobe_pairing_phrases = (
            "what goes with my",
            "build an outfit around",
        )
        if any(phrase in normalized for phrase in wardrobe_pairing_phrases):
            return True
        # Phrases that reference "this" — require an attached image OR previous anchor
        has_anchor = has_attached_image or has_previous_anchor
        demonstrative_pairing_phrases = (
            "pair this",
            "pairing for this",
            "what goes with this",
            "goes with this",
            "go with this",
            "complete the outfit with this",
            "outfit with this",
            "wear with this",
            "style this",
            "what shoes would work best with this",
            "what shoes work best with this",
            "which shoes would work best with this",
            "what shoes with this",
            "which shoes with this",
            "with this shirt",
            "with this piece",
            "with this garment",
            "with this blazer",
            "with this top",
        )
        if any(phrase in normalized for phrase in demonstrative_pairing_phrases):
            return has_anchor
        # Generic pairing without demonstrative
        generic_pairing_phrases = (
            "complete the outfit",
            "complete outfit",
        )
        if any(phrase in normalized for phrase in generic_pairing_phrases):
            return True
        return False

    def _message_needs_image_for_pairing(self, *, message: str, has_attached_image: bool) -> bool:
        """Returns True if the message references a specific piece ('this shirt') but no image is attached."""
        if has_attached_image:
            return False
        normalized = self._normalize_text_token(message)
        demonstrative_refs = (
            "this shirt", "this piece", "this garment", "this blazer", "this top",
            "this dress", "this jacket", "this trouser", "this skirt",
            "with this", "pair this", "style this",
        )
        return any(phrase in normalized for phrase in demonstrative_refs)

    def _message_references_prior_context(self, *, message: str) -> bool:
        normalized = self._normalize_text_token(message)
        if not normalized:
            return False
        if normalized.startswith("make it ") or normalized.startswith("make this ") or normalized.startswith("make that "):
            return True
        return any(
            phrase in normalized
            for phrase in (
                "with this",
                "with it",
                "this outfit",
                "this look",
                "that outfit",
                "that look",
                "smarter",
                "more polished",
                "more polish",
                "sharper",
                "dressier",
                "more refined",
                "more casual",
                "less dressy",
                "more relaxed",
            )
        )

    def _message_requires_richer_refinement_path(
        self,
        *,
        message: str,
        intent: IntentClassification,
        live_context: LiveContext,
    ) -> bool:
        if intent.primary_intent != Intent.OCCASION_RECOMMENDATION:
            return False
        followup_intent = str(live_context.followup_intent or "").strip()
        if followup_intent in {FollowUpIntent.INCREASE_FORMALITY, FollowUpIntent.DECREASE_FORMALITY} and self._message_references_prior_context(message=message):
            return True
        return False

    def _previous_anchor_title(self, *, previous_context: Dict[str, Any]) -> str:
        candidates = [
            str((previous_context.get("last_live_context") or {}).get("user_need") or "").strip(),
            str(previous_context.get("last_user_message") or "").strip(),
        ]
        pattern = re.compile(r"Attached garment context:\s*([^,\.]+)")
        for candidate in candidates:
            if not candidate:
                continue
            match = pattern.search(candidate)
            if match:
                title = str(match.group(1) or "").strip()
                if title:
                    return title
        return ""

    def _message_requests_catalog_followup(
        self,
        *,
        message: str,
        previous_context: Dict[str, Any],
    ) -> bool:
        normalized = self._normalize_text_token(message)
        if not normalized:
            return False
        last_response_metadata = dict(previous_context.get("last_response_metadata") or {})
        last_answer_source = self._normalize_text_token(last_response_metadata.get("answer_source"))
        catalog_upsell = dict(last_response_metadata.get("catalog_upsell") or {})
        cta = self._normalize_text_token(catalog_upsell.get("cta"))
        if cta and normalized == cta:
            return True
        # New shopper-vocabulary CTA ("Show me options to buy") + legacy
        # phrasings. The "catalog" keyword still triggers for free-form
        # asks like "show me catalog alternatives".
        shop_phrases = ("options to buy", "shop", "buy")
        if any(phrase in normalized for phrase in shop_phrases) and any(token in normalized for token in ("show me", "show", "see", "browse")):
            return True
        if "catalog" in normalized and any(token in normalized for token in ("show me", "better option", "better options", "alternative", "alternatives")):
            return True
        return bool(last_answer_source.startswith("wardrobe first")) and "catalog" in normalized

    def _message_source_preference(self, *, message: str) -> str:
        normalized = self._normalize_text_token(message)
        if not normalized:
            return ""
        wardrobe_phrases = (
            "from my wardrobe",
            "use my wardrobe",
            "using my wardrobe",
            "from my closet",
            "using what i own",
            "with what i own",
            "from what i own",
        )
        catalog_phrases = (
            "from the catalog",
            "from your catalog",
            "catalog only",
            "only from the catalog",
            "do not use my wardrobe",
            "dont use my wardrobe",
            "skip my wardrobe",
        )
        if any(phrase in normalized for phrase in wardrobe_phrases):
            return "wardrobe"
        if any(phrase in normalized for phrase in catalog_phrases):
            return "catalog"
        return ""

    def _apply_planner_overrides(
        self,
        *,
        plan_result: CopilotPlanResult,
        message: str,
        previous_context: Dict[str, Any],
        attached_item: Dict[str, Any] | None,
        has_attached_image: bool,
    ) -> tuple[CopilotPlanResult, list[str], bool, str]:
        override_reasons: list[str] = []

        # Source preference is now extracted by the planner into resolved_context.source_preference.
        # Map "auto" → "" for downstream consumers that expect an empty string for "no preference".
        planner_source_pref = str(plan_result.resolved_context.source_preference or "").strip().lower()
        source_preference = "" if planner_source_pref in ("", "auto") else planner_source_pref

        # catalog_followup is a state-conditional override (depends on the *previous* turn's
        # answer source being wardrobe-first), which the planner cannot see. Keep it.
        force_catalog_followup = self._message_requests_catalog_followup(
            message=message,
            previous_context=previous_context,
        )
        if force_catalog_followup:
            if "catalog_followup_override" not in override_reasons:
                override_reasons.append("catalog_followup_override")
            if "catalog_followup" not in plan_result.resolved_context.specific_needs:
                plan_result.resolved_context.specific_needs.append("catalog_followup")
            if not plan_result.resolved_context.followup_intent:
                plan_result.resolved_context.followup_intent = "catalog_followup"

        # When the planner classifies an INCREASE_FORMALITY follow-up but does not
        # propagate a formality_hint, default it to smart_casual so downstream search
        # has a meaningful constraint to work with.
        if (
            plan_result.resolved_context.followup_intent == FollowUpIntent.INCREASE_FORMALITY
            and not plan_result.resolved_context.formality_hint
        ):
            plan_result.resolved_context.formality_hint = "smart_casual"

        _has_prev_anchor = bool(
            str((previous_context.get("last_live_context") or {}).get("user_need") or "").find("Attached garment context:") != -1
            or str(previous_context.get("last_user_message") or "").find("Attached garment context:") != -1
        )
        if self._message_requests_pairing(message=message, has_attached_image=has_attached_image, has_previous_anchor=_has_prev_anchor):
            attached = dict(attached_item or {})
            if plan_result.intent != Intent.PAIRING_REQUEST:
                plan_result.intent = Intent.PAIRING_REQUEST
                plan_result.action = Action.RUN_RECOMMENDATION_PIPELINE
            if not str(plan_result.resolved_context.style_goal or "").strip():
                plan_result.resolved_context.style_goal = Intent.PAIRING_REQUEST
            if "pairing_request_override" not in override_reasons:
                override_reasons.append("pairing_request_override")
            if not str(plan_result.action_parameters.target_piece or "").strip():
                anchor_title = str(attached.get("title") or "").strip()
                if not anchor_title:
                    anchor_title = self._previous_anchor_title(previous_context=previous_context)
                if anchor_title:
                    plan_result.action_parameters.target_piece = anchor_title

        if source_preference == "wardrobe":
            if "wardrobe_first" not in plan_result.resolved_context.specific_needs:
                plan_result.resolved_context.specific_needs.append("wardrobe_first")
        elif source_preference == "catalog":
            if "catalog_only" not in plan_result.resolved_context.specific_needs:
                plan_result.resolved_context.specific_needs.append("catalog_only")

        return plan_result, override_reasons, force_catalog_followup, source_preference

    @staticmethod
    def _derive_answer_source_from_components(answer_components: Dict[str, Any], preferred_source: str = "") -> str:
        primary_source = str(answer_components.get("primary_source") or "").strip()
        if preferred_source == "catalog" and primary_source == "catalog":
            return "catalog_only"
        if preferred_source == "wardrobe" and primary_source == "wardrobe":
            return "wardrobe_first"
        if primary_source == "catalog":
            return "catalog_only"
        if primary_source == "wardrobe":
            return "wardrobe_first"
        if primary_source == "mixed":
            return "hybrid"
        return "copilot_planner_pipeline"

    @staticmethod
    def _build_source_selection(*, preferred_source: str = "", fulfilled_source: str = "") -> Dict[str, str]:
        return {
            "preferred_source": preferred_source or "auto",
            "fulfilled_source": fulfilled_source or "unknown",
        }

    def _build_effective_live_context(
        self,
        *,
        message: str,
        resolved_context: Any,
        previous_context: Dict[str, Any],
        force_catalog_followup: bool,
    ) -> LiveContext:
        if not force_catalog_followup:
            user_need = message.strip()
            if resolved_context.is_followup and self._message_references_prior_context(message=message):
                last_live_context = dict(previous_context.get("last_live_context") or {})
                prior_need = str(
                    last_live_context.get("user_need")
                    or previous_context.get("last_user_message")
                    or ""
                ).strip()
                if prior_need and prior_need != user_need:
                    user_need = f"{user_need} Follow-up anchor context: {prior_need}"
            return LiveContext(
                user_need=user_need,
                occasion_signal=resolved_context.occasion_signal,
                formality_hint=resolved_context.formality_hint,
                time_hint=resolved_context.time_hint,
                specific_needs=resolved_context.specific_needs,
                is_followup=resolved_context.is_followup,
                followup_intent=resolved_context.followup_intent,
                weather_context=str(getattr(resolved_context, "weather_context", "") or ""),
                time_of_day=str(getattr(resolved_context, "time_of_day", "") or ""),
                target_product_type=str(getattr(resolved_context, "target_product_type", "") or ""),
                style_goal=str(getattr(resolved_context, "style_goal", "") or ""),
            )

        last_live_context = dict(previous_context.get("last_live_context") or {})
        merged_specific_needs = _dedupe_values(
            [
                *(list(last_live_context.get("specific_needs") or [])),
                *(list(resolved_context.specific_needs or [])),
                "catalog_followup",
            ]
        )
        prior_need = str(last_live_context.get("user_need") or previous_context.get("last_user_message") or "").strip()
        user_need = prior_need or message.strip()
        if user_need and user_need != message.strip():
            user_need = f"{user_need} Catalog follow-up requested."
        else:
            user_need = message.strip()
        return LiveContext(
            user_need=user_need,
            occasion_signal=resolved_context.occasion_signal or last_live_context.get("occasion_signal"),
            formality_hint=resolved_context.formality_hint or last_live_context.get("formality_hint"),
            time_hint=resolved_context.time_hint or last_live_context.get("time_hint"),
            specific_needs=merged_specific_needs,
            is_followup=True,
            followup_intent=resolved_context.followup_intent or "catalog_followup",
            weather_context=str(getattr(resolved_context, "weather_context", "") or last_live_context.get("weather_context") or ""),
            time_of_day=str(getattr(resolved_context, "time_of_day", "") or last_live_context.get("time_of_day") or ""),
            target_product_type=str(getattr(resolved_context, "target_product_type", "") or last_live_context.get("target_product_type") or ""),
            style_goal=str(getattr(resolved_context, "style_goal", "") or last_live_context.get("style_goal") or ""),
        )

    def create_conversation(
        self,
        *,
        external_user_id: str,
        initial_context: Optional[Dict[str, Any]] = None,
        initial_profile: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        user = self.repo.get_or_create_user(external_user_id)
        if initial_profile:
            self.repo.update_user_profile(user["id"], initial_profile)
        conversation = self.repo.create_conversation(
            user_id=user["id"], initial_context=initial_context
        )
        return {
            "conversation_id": conversation["id"],
            "user_id": external_user_id,
            "status": conversation.get("status", "active"),
            "created_at": conversation.get("created_at", ""),
        }

    def resolve_active_conversation(
        self,
        *,
        external_user_id: str,
    ) -> Dict[str, Any]:
        user = self.repo.get_or_create_user(external_user_id)
        latest = self.repo.get_latest_conversation_for_user(str(user.get("id") or ""))
        if latest:
            return {
                "conversation_id": latest["id"],
                "user_id": external_user_id,
                "status": latest.get("status", "active"),
                "created_at": latest.get("created_at", ""),
                "reused_existing": True,
            }
        created = self.repo.create_conversation(user_id=user["id"], initial_context={})
        return {
            "conversation_id": created["id"],
            "user_id": external_user_id,
            "status": created.get("status", "active"),
            "created_at": created.get("created_at", ""),
            "reused_existing": False,
        }

    def get_conversation_state(self, *, conversation_id: str) -> Dict[str, Any]:
        conversation = self.repo.get_conversation(conversation_id)
        if not conversation:
            raise ValueError("Conversation not found.")
        user = self.repo.get_user_by_id(str(conversation.get("user_id", ""))) or {}
        latest_context = dict(conversation.get("session_context_json") or {})
        return {
            "conversation_id": conversation["id"],
            "user_id": str(user.get("external_user_id") or ""),
            "status": conversation.get("status", "active"),
            "latest_context": latest_context or None,
        }

    # ------------------------------------------------------------------
    # Main pipeline
    # ------------------------------------------------------------------

    def process_turn(
        self,
        *,
        conversation_id: str,
        external_user_id: str,
        message: str,
        channel: str = "web",
        image_data: str = "",
        wardrobe_item_id: str = "",
        wishlist_product_id: str = "",
        stage_callback: Optional[Callable[[str, str, str], None]] = None,
    ) -> Dict[str, Any]:
        def emit(stage: str, detail: str = "", ctx: dict | None = None) -> None:
            if stage_callback is not None:
                msg = generate_stage_message(stage, detail, ctx)
                stage_callback(stage, detail, msg)

        # ── Trace-aware emit: feeds both the SSE bubble and the trace ──
        _step_t0: dict[str, float] = {}

        # Item 6 (May 1, 2026): per-stage OTel spans. We don't open them
        # via context manager because trace_start/trace_end split across
        # callsites; instead we lazily emit a span on trace_end with the
        # measured latency. That gives the correct timing in the OTel
        # waterfall while keeping the existing call pattern.
        def trace_start(step: str, *, model: str | None = None, input_summary: str = "") -> None:
            """Mark the start of a pipeline step for latency measurement."""
            _step_t0[step] = time.monotonic()
            # Store model + input_summary so trace_end can use them.
            _step_t0[f"_model_{step}"] = model  # type: ignore[assignment]
            _step_t0[f"_input_{step}"] = input_summary  # type: ignore[assignment]

        def trace_end(step: str, *, output_summary: str = "", status: str = "ok", error: str | None = None) -> None:
            """Finalise a pipeline step: compute latency, append to trace."""
            t0 = _step_t0.pop(step, None)
            latency_ms = int((time.monotonic() - t0) * 1000) if isinstance(t0, float) else None
            model = _step_t0.pop(f"_model_{step}", None)
            input_summary = str(_step_t0.pop(f"_input_{step}", "") or "")
            trace.add_step(
                step,
                model=model,  # type: ignore[arg-type]
                input_summary=input_summary,
                output_summary=output_summary,
                latency_ms=latency_ms,
                status=status,
                error=error,
            )
            # Item 5 (May 1, 2026): mirror the latency into Prometheus
            # histogram so /metrics shows live p50/p95/p99 per stage
            # without operators needing to query Postgres.
            try:
                from platform_core.metrics import observe_turn_stage
                observe_turn_stage(step, latency_ms)
            except Exception:  # noqa: BLE001 — metrics never break the pipeline
                pass
            # Item 6 (May 1, 2026): emit a child OTel span for the stage
            # so the waterfall view reflects what we already store in
            # ``turn_traces.steps[]``. Uses start/end times derived from
            # the latency we already measured to keep the cost trivial.
            try:
                if _otel_tracer is not None and isinstance(latency_ms, int):
                    end_ns = int(time.time() * 1e9)
                    start_ns = end_ns - int(latency_ms * 1e6)
                    span = _otel_tracer.start_span(
                        f"aura.{step}",
                        start_time=start_ns,
                        attributes={
                            "aura.stage": step,
                            "aura.status": status,
                            "aura.model": model or "",
                            "aura.input_summary": input_summary[:200],
                            "aura.output_summary": output_summary[:200],
                        },
                    )
                    if status != "ok":
                        from opentelemetry.trace import Status, StatusCode
                        span.set_status(Status(StatusCode.ERROR, error or status))
                    span.end(end_time=end_ns)
            except Exception:  # noqa: BLE001
                pass

        # --- Validate request ---
        emit("validate_request", "started")
        trace_start("validate_request", input_summary=f"user={external_user_id}, conv={conversation_id}")
        user_row = self.repo.get_or_create_user(external_user_id)
        conversation = self.repo.get_conversation(conversation_id)
        if not conversation:
            raise ValueError("Conversation not found.")
        if conversation.get("user_id") != user_row.get("id"):
            raise ValueError("Conversation does not belong to user.")
        previous_context = dict(conversation.get("session_context_json") or {})
        turn = self.repo.create_turn(conversation_id=conversation_id, user_message=message)
        turn_id = str(turn["id"])

        # Item 2 (May 1, 2026): set correlation contextvars so every
        # downstream log record auto-tags with turn_id / conversation_id /
        # external_user_id via the RequestContextFilter. No explicit reset
        # — next call overwrites; empty default means stale values don't
        # leak across requests served by the same thread.
        set_turn_id(turn_id)
        set_conversation_id(conversation_id)
        set_external_user_id(external_user_id)

        # Item 6 (May 1, 2026): tag the active OTel span (created by the
        # FastAPI auto-instrumentation around the HTTP route) with our
        # turn-level identifiers. Pipeline-stage child spans are created
        # in trace_end below so the span tree mirrors the trace_traces
        # ``steps[]`` structure.
        try:
            from platform_core.otel_setup import get_tracer
            from opentelemetry import trace as _otel_trace
            _otel_tracer = get_tracer("aura.orchestrator")
            _current_span = _otel_trace.get_current_span()
            if _current_span is not None:
                _current_span.set_attribute("aura.turn_id", turn_id)
                _current_span.set_attribute("aura.conversation_id", conversation_id)
                _current_span.set_attribute("aura.external_user_id", external_user_id)
                _current_span.set_attribute("aura.has_image", bool(image_data))
        except Exception:  # noqa: BLE001
            _otel_tracer = None

        # ── Trace builder ────────────────────────────────────────────
        # Accumulates the per-turn trace incrementally. Persisted at the
        # end of every handler path via repo.insert_turn_trace.
        trace = TurnTraceBuilder(
            turn_id=turn_id,
            conversation_id=conversation_id,
            user_id=external_user_id,
            user_message=message,
            has_image=bool(image_data),
        )

        attached_item: Dict[str, Any] | None = None
        effective_message = message
        trace_end("validate_request", output_summary=f"turn={turn_id}")

        # ── Wardrobe item selection (existing item, no re-upload) ──
        # When the user picks an item from "Select from wardrobe" in the
        # chat composer, the frontend sends wardrobe_item_id (the UUID of
        # the existing row) instead of re-fetching + re-sending the image
        # as image_data. We load the row directly — no re-enrichment, no
        # duplicate wardrobe write.
        _log.warning("process_turn: wardrobe_item_id=%r, has_image_data=%s", wardrobe_item_id, bool(image_data))
        if wardrobe_item_id and not image_data:
            # ── Wardrobe selection path ──────────────────────────────
            # Functionally identical to the image-upload path below
            # EXCEPT: no re-enrichment (item is already enriched), no
            # persistence (item is already in wardrobe), no decomposition
            # (handled downstream via attachment_source check). Everything
            # else — context in effective_message, flags, trace steps,
            # anchor injection, evaluator flow — is the same.
            trace_start("wardrobe_selection", input_summary=f"wardrobe_item_id={wardrobe_item_id}")
            try:
                wardrobe_items = self.onboarding_gateway.get_wardrobe_items(external_user_id) or []
                match = next(
                    (w for w in wardrobe_items if str(w.get("id") or "") == wardrobe_item_id),
                    None,
                )
                if match:
                    attached_item = dict(match)
                    attached_item["attachment_source"] = "wardrobe_selection"
                    attached_item["is_garment_photo"] = True
                    attached_item["garment_present_confidence"] = 1.0
                    # Append the item's enriched attributes to effective_message
                    # so planner/architect/evaluator see the garment identity —
                    # same as the upload path does after enrichment.
                    attached_context = self._attached_item_context(attached_item)
                    if attached_context:
                        effective_message = f"{message.strip()} {attached_context}".strip()
                    effective_message = f"{effective_message} Image anchor source: wardrobe selection.".strip()
                    trace_end(
                        "wardrobe_selection",
                        output_summary=f"loaded: {attached_item.get('title')}, {attached_item.get('garment_category')}, {attached_item.get('primary_color')}",
                    )
                    trace.set_image_classification(
                        is_garment_photo=True,
                        garment_present_confidence=1.0,
                    )
                    _log.info(
                        "Loaded wardrobe item %s: %s",
                        wardrobe_item_id,
                        attached_context[:100] if attached_context else "no context",
                    )
                else:
                    trace_end("wardrobe_selection", output_summary="item not found", status="error")
                    _log.warning("Wardrobe item %s not found for user %s", wardrobe_item_id, external_user_id)
            except Exception:
                trace_end("wardrobe_selection", output_summary="load failed", status="error")
                _log.warning("Failed to load wardrobe item %s", wardrobe_item_id, exc_info=True)

        # ── Wishlist product selection (catalog item from wishlist) ──
        # Same pattern as wardrobe selection but sources from
        # catalog_enriched instead of user_wardrobe_items. No wardrobe
        # persistence, no decomposition.
        if wishlist_product_id and not image_data and not attached_item:
            trace_start("wishlist_selection", input_summary=f"product_id={wishlist_product_id}")
            try:
                enriched = self.repo.client.select_one(
                    "catalog_enriched",
                    filters={"product_id": f"eq.{wishlist_product_id}"},
                )
                if enriched:
                    # catalog_enriched uses PascalCase columns; fall back to
                    # snake_case for compatibility with any future migration.
                    attached_item = {
                        "id": str(enriched.get("product_id") or wishlist_product_id),
                        "title": str(enriched.get("title") or ""),
                        "image_url": str(
                            enriched.get("images_0_src")
                            or enriched.get("images__0__src")
                            or enriched.get("primary_image_url")
                            or ""
                        ),
                        "image_path": "",
                        "garment_category": str(enriched.get("GarmentCategory") or enriched.get("garment_category") or ""),
                        "garment_subtype": str(enriched.get("GarmentSubtype") or enriched.get("garment_subtype") or ""),
                        "primary_color": str(enriched.get("PrimaryColor") or enriched.get("primary_color") or ""),
                        "secondary_color": str(enriched.get("SecondaryColor") or enriched.get("secondary_color") or ""),
                        "formality_level": str(enriched.get("FormalityLevel") or enriched.get("formality_level") or ""),
                        "occasion_fit": str(enriched.get("OccasionFit") or enriched.get("occasion_fit") or ""),
                        "pattern_type": str(enriched.get("PatternType") or enriched.get("pattern_type") or ""),
                        "source": "catalog",
                        "attachment_source": "wishlist_selection",
                        "is_garment_photo": True,
                        "garment_present_confidence": 1.0,
                    }
                    attached_context = self._attached_item_context(attached_item)
                    if attached_context:
                        effective_message = f"{message.strip()} {attached_context}".strip()
                    effective_message = f"{effective_message} Image anchor source: wishlist selection.".strip()
                    trace_end(
                        "wishlist_selection",
                        output_summary=f"loaded: {attached_item.get('title')}, {attached_item.get('garment_category')}",
                    )
                    trace.set_image_classification(is_garment_photo=True, garment_present_confidence=1.0)
                    _log.info("Loaded wishlist product %s: %s", wishlist_product_id, attached_item.get("title"))
                else:
                    trace_end("wishlist_selection", output_summary="product not found", status="error")
                    _log.warning("Wishlist product %s not found in catalog_enriched", wishlist_product_id)
            except Exception:
                trace_end("wishlist_selection", output_summary="load failed", status="error")
                _log.warning("Failed to load wishlist product %s", wishlist_product_id, exc_info=True)

        if image_data:
            trace_start("wardrobe_enrichment", model="gpt-5-mini", input_summary=f"image_upload, message={message[:80]}")
            try:
                # Phase 12D follow-up (April 9 2026): enrich the uploaded
                # garment but do NOT persist it to user_wardrobe_items yet.
                # The planner needs the 46 attributes in its prompt context
                # to classify intent, but persistence should only happen
                # for intents that legitimately mean "save this to my
                # wardrobe" — pairing_request and outfit_check. For
                # garment_evaluation ("should I buy this?") and
                # style_discovery turns, the user is asking about a piece
                # they don't own, so we keep the enriched dict in memory
                # for the response and discard it after the turn.
                attached_item = self.onboarding_gateway.save_uploaded_chat_wardrobe_item(
                    user_id=external_user_id,
                    image_data=image_data,
                    description=message.strip(),
                    notes="Captured from chat image attachment.",
                    persist=False,
                )
                _log.info("Attached item enriched (pending persist): %s", {k: str(v)[:50] for k, v in (attached_item or {}).items()} if attached_item else None)
            except Exception:
                _log.exception("Failed to save attached item — attached_item will be None")
                attached_item = None
            attachment_source = self._uploaded_image_anchor_source(message=message)
            if attached_item is not None:
                attached_item = dict(attached_item)
                attached_item["attachment_source"] = attachment_source
                # Phase 12D: detect the failed-enrichment case from the
                # service layer's top-level enrichment_status marker. Also
                # treat all-empty critical fields as a failed enrichment
                # for backwards compatibility with rows saved before the
                # service layer started returning the marker.
                enrichment_status = str(attached_item.get("enrichment_status") or "").strip().lower()
                critical_fields_empty = (
                    not str(attached_item.get("garment_category") or "").strip()
                    and not str(attached_item.get("garment_subtype") or "").strip()
                    and not str(attached_item.get("title") or "").strip()
                )
                if enrichment_status == "failed" or critical_fields_empty:
                    attached_item["enrichment_failed"] = True
                    _log.warning(
                        "Wardrobe enrichment returned empty/failed for upload %s — flagging on attached_item",
                        attached_item.get("id"),
                    )
            attached_context = self._attached_item_context(attached_item)
            if attached_context:
                effective_message = f"{message.strip()} {attached_context}".strip()
            if attached_item is not None:
                effective_message = f"{effective_message} Image anchor source: {attachment_source.replace('_', ' ')}.".strip()
            # Close the wardrobe_enrichment trace step
            enriched_cat = str((attached_item or {}).get("garment_category") or "")
            enriched_color = str((attached_item or {}).get("primary_color") or "")
            is_garm = (attached_item or {}).get("is_garment_photo")
            trace_end(
                "wardrobe_enrichment",
                output_summary=f"is_garment={is_garm}, category={enriched_cat}, color={enriched_color}",
                status="ok" if attached_item else "error",
            )
            trace.set_image_classification(
                is_garment_photo=is_garm if is_garm is not None else None,
                garment_present_confidence=float((attached_item or {}).get("garment_present_confidence") or 1.0),
            )

        # ── Carry forward the previous turn's attached item ──────────
        # When the user didn't upload a new image and didn't select from
        # wardrobe, but the previous turn had an attached garment (e.g.
        # the user said "Can I wear this pant?" on Turn 1 and is now
        # saying "Show me a date-night outfit with these pants" on Turn
        # 2), use the previous turn's attached item as this turn's
        # anchor. Without this, follow-up pairing requests lose the
        # garment context and the architect searches catalog for BOTH
        # roles instead of anchoring the user's piece.
        if not attached_item:
            prev_attached = previous_context.get("last_attached_item")
            if prev_attached and isinstance(prev_attached, dict) and prev_attached.get("id"):
                attached_item = dict(prev_attached)
                attached_item.setdefault("attachment_source", "previous_turn")
                attached_item.setdefault("is_garment_photo", True)
                attached_item.setdefault("garment_present_confidence", 1.0)
                attached_context = self._attached_item_context(attached_item)
                if attached_context:
                    effective_message = f"{message.strip()} {attached_context}".strip()
                _log.info(
                    "Loaded attached item from previous turn: %s (id=%s)",
                    attached_item.get("title"),
                    attached_item.get("id"),
                )

        # --- 0.5 Onboarding Gate ---
        emit("onboarding_gate", "started")
        trace_start("onboarding_gate", input_summary=f"user={external_user_id}")
        # PR #62 (G1c): get_onboarding_status and get_analysis_status are
        # independent reads on the same user. Run them in parallel against
        # the pooled httpx client (PR #59). Saves one round-trip's worth
        # of latency on the slowest of the two — typically ~700ms-1s on
        # cold turns, less when the pool is warm.
        #
        # ContextVars (turn_id, conversation_id, etc.) don't propagate to
        # ThreadPoolExecutor workers automatically; without an explicit
        # snapshot, log lines and metrics from inside the gateway calls
        # would lose request correlation. Mirror the pattern used by the
        # tryon_render and visual_eval pools above.
        _gate_ctx_snapshot = _snapshot_request_context()
        with ThreadPoolExecutor(max_workers=2) as _gate_pool:
            _onboarding_future = _gate_pool.submit(
                run_with_context,
                _gate_ctx_snapshot,
                self.onboarding_gateway.get_onboarding_status,
                external_user_id,
            )
            _analysis_future = _gate_pool.submit(
                run_with_context,
                _gate_ctx_snapshot,
                self.onboarding_gateway.get_analysis_status,
                external_user_id,
            )
            onboarding_status = _onboarding_future.result()
            analysis_status = _analysis_future.result()
        onboarding_gate = evaluate_onboarding_gate(onboarding_status, analysis_status)
        if not onboarding_gate.allowed:
            emit("onboarding_gate", "blocked")
            trace_end("onboarding_gate", output_summary="blocked", status="blocked")
            self._persist_profile_confidence(
                external_user_id=external_user_id,
                conversation_id=conversation_id,
                turn_id=turn_id,
                channel=channel,
                profile_confidence=onboarding_gate.profile_confidence,
                primary_intent="onboarding_gate",
                status=onboarding_gate.status,
            )
            self._persist_policy_event(
                external_user_id=external_user_id,
                conversation_id=conversation_id,
                turn_id=turn_id,
                channel=channel,
                policy_event_type="onboarding_gate",
                input_class="chat_access",
                reason_code=onboarding_gate.status,
                metadata_json={
                    "missing_steps": list(onboarding_gate.missing_steps),
                    "improvement_actions": list(onboarding_gate.improvement_actions),
                },
            )
            metadata = self._build_response_metadata(
                channel=channel,
                intent=IntentClassification(primary_intent="onboarding_gate"),
                profile_confidence=onboarding_gate.profile_confidence,
                extra={
                    "onboarding_required": True,
                    "onboarding_status": onboarding_gate.status,
                },
            )
            self.repo.finalize_turn(
                turn_id=turn_id,
                assistant_message=onboarding_gate.message,
                resolved_context={
                    "request_summary": message.strip(),
                    "onboarding_gate": onboarding_gate.model_dump(),
                    "response_metadata": metadata,
                    "channel": channel,
                },
            )
            self.repo.update_conversation_context(
                conversation_id=conversation_id,
                session_context={
                    **previous_context,
                    "last_user_message": message,
                    "last_assistant_message": onboarding_gate.message,
                    "last_channel": channel,
                    "last_intent": "onboarding_gate",
                    "last_response_metadata": metadata,
                },
            )
            self._persist_dependency_turn_event(
                external_user_id=external_user_id,
                conversation_id=conversation_id,
                turn_id=turn_id,
                channel=channel,
                primary_intent="onboarding_gate",
                response_type="clarification",
                metadata_json={
                    "onboarding_status": onboarding_gate.status,
                    "missing_steps": list(onboarding_gate.missing_steps),
                    "memory_sources_written": ["confidence_history", "policy_events"],
                },
            )
            # Persist the trace before this early return — without this
            # call the onboarding-gate-blocked turn never makes it into
            # turn_traces, leaving operators blind to the most common
            # clarification path. (May 1, 2026 fix.)
            trace.set_intent(primary_intent="onboarding_gate", action="ask_clarification")
            trace.set_evaluation({"response_type": "clarification", "answer_source": "onboarding_gate"})
            self._persist_trace(trace)
            return {
                "conversation_id": conversation_id,
                "turn_id": turn_id,
                "assistant_message": onboarding_gate.message,
                "response_type": "clarification",
                "resolved_context": {
                    "request_summary": message.strip(),
                    "occasion": "",
                    "style_goal": "",
                },
                "filters_applied": {},
                "outfits": [],
                "follow_up_suggestions": onboarding_gate.improvement_actions[:4],
                "metadata": metadata,
            }
        emit("onboarding_gate", "completed")
        trace_end("onboarding_gate", output_summary="allowed")

        # --- Copilot Planner path ---
        profile_confidence = onboarding_gate.profile_confidence

        # Build user context — reuse the analysis_status fetched in the
        # onboarding-gate step above. Without this, build_user_context
        # re-fetches it (and the underlying profile + style + interpretation
        # snapshots), adding ~3 redundant Supabase round trips per turn.
        emit("user_context", "started")
        trace_start("user_context", input_summary=f"user={external_user_id}")
        user_context = build_user_context(
            external_user_id,
            onboarding_gateway=self.onboarding_gateway,
            analysis_status=analysis_status,
        )
        validate_minimum_profile(user_context)
        emit("user_context", "completed", ctx={"richness": user_context.profile_richness})
        trace_end("user_context", output_summary=f"richness={user_context.profile_richness}")

        # Build conversation history
        conversation_history = self._build_conversation_history(previous_context, message)

        # Check for person image
        has_person_image = bool(self.onboarding_gateway.get_person_image_path(external_user_id))

        # Build planner input
        planner_input = build_planner_input(
            message=effective_message,
            user_context=user_context,
            conversation_history=conversation_history,
            previous_context=previous_context,
            profile_confidence_pct=profile_confidence.analysis_confidence_pct,
            has_person_image=has_person_image,
            has_attached_image=bool(image_data),
        )

        # Run Copilot Planner
        # Model name read from the agent so the trace + log rows
        # follow the agent's _model attribute rather than a hardcoded
        # literal we'd otherwise have to keep in sync (May 5, 2026
        # gpt-5.5 → gpt-5-mini swap exposed how easy that drift is).
        # Direct attribute access (not getattr-with-default) so a future
        # rename of _model fails loud here instead of silently falling
        # back to a stale literal — see PR #44 review feedback.
        _planner_model = self._copilot_planner._model
        emit("copilot_planner", "started")
        trace_start("copilot_planner", model=_planner_model, input_summary=f"message={message[:80]}, has_image={bool(image_data)}")
        t0 = time.monotonic()
        try:
            plan_result = self._copilot_planner.plan(planner_input)
        except Exception as exc:
            planner_ms = int((time.monotonic() - t0) * 1000)
            _log.error("Copilot planner failed: %s", exc, exc_info=True)
            trace.add_model_cost_from_row(self.repo.log_model_call(
                conversation_id=conversation_id,
                turn_id=turn_id,
                service="agentic_application",
                call_type="copilot_planner",
                model=_planner_model,
                request_json={"message": effective_message},
                response_json={},
                reasoning_notes=[],
                latency_ms=planner_ms,
                status="error",
                error_message=str(exc),
            ))
            emit("copilot_planner", "error")
            trace_end("copilot_planner", status="error", error=str(exc)[:200])
            fallback_message = "I'm having trouble processing your request right now. Please try again."
            self.repo.finalize_turn(
                turn_id=turn_id,
                assistant_message=fallback_message,
                resolved_context={"error": str(exc), "request_summary": message.strip()},
            )
            # Persist the trace before this early return so the planner
            # failure shows up in turn_traces with stage_failed=copilot_planner.
            # (May 1, 2026 fix — was previously a coverage hole.)
            trace.set_intent(primary_intent="", action="error")
            trace.set_evaluation({"response_type": "error", "stage_failed": "copilot_planner", "error": str(exc)[:200]})
            self._persist_trace(trace)
            return {
                "conversation_id": conversation_id,
                "turn_id": turn_id,
                "assistant_message": fallback_message,
                "response_type": "error",
                "resolved_context": {"request_summary": message.strip()},
                "filters_applied": {},
                "outfits": [],
                "follow_up_suggestions": [],
                "metadata": {"error": True},
            }
        planner_ms = int((time.monotonic() - t0) * 1000)
        # Item 4 (May 1, 2026): pull token usage from the planner agent.
        _planner_usage = getattr(self._copilot_planner, "last_usage", {}) or {}
        trace.add_model_cost_from_row(self.repo.log_model_call(
            conversation_id=conversation_id,
            turn_id=turn_id,
            service="agentic_application",
            call_type="copilot_planner",
            model=_planner_model,
            request_json={"message": effective_message, "intent": plan_result.intent},
            response_json={
                "intent": plan_result.intent,
                "action": plan_result.action,
                "intent_confidence": plan_result.intent_confidence,
            },
            reasoning_notes=[],
            latency_ms=planner_ms,
            prompt_tokens=_planner_usage.get("prompt_tokens"),
            completion_tokens=_planner_usage.get("completion_tokens"),
            total_tokens=_planner_usage.get("total_tokens"),
        ))
        emit("copilot_planner", "completed", ctx={
            "intent": plan_result.intent,
            "action": plan_result.action,
        })
        trace_end("copilot_planner", output_summary=f"intent={plan_result.intent}, action={plan_result.action}")

        plan_result, override_reasons, force_catalog_followup, source_preference = self._apply_planner_overrides(
            plan_result=plan_result,
            message=effective_message,
            previous_context=previous_context,
            attached_item=attached_item,
            has_attached_image=bool(image_data),
        )

        # Check: pairing references a specific piece but no image attached — ask for it
        # Skip if previous context already has an attached garment (follow-up turn)
        has_previous_anchor = bool(
            str((previous_context.get("last_live_context") or {}).get("user_need") or "").find("Attached garment context:") != -1
            or str(previous_context.get("last_user_message") or "").find("Attached garment context:") != -1
        )
        if not has_previous_anchor and self._message_needs_image_for_pairing(message=effective_message, has_attached_image=bool(image_data)):
            plan_result.action = Action.ASK_CLARIFICATION
            plan_result.assistant_message = (
                "I'd love to help you pair that piece! Could you attach a photo of the garment "
                "you'd like me to build an outfit around?"
            )
            plan_result.follow_up_suggestions = [
                "Upload a photo",
                "Pick from my wardrobe",
                "Show me office outfits instead",
            ]
            if "image_required_for_pairing" not in override_reasons:
                override_reasons.append("image_required_for_pairing")

        # Phase 12D: when an upload's enrichment failed, the architect cannot
        # plan complementary items because it has no anchor attributes to work
        # with. Surface a clarification asking the user for a clearer photo,
        # rather than running the pipeline with an empty-attribute anchor.
        # PR V2 (May 5 2026): the prior garment_evaluation exemption was
        # removed alongside that intent.
        if (
            attached_item
            and attached_item.get("enrichment_failed")
        ):
            plan_result.action = Action.ASK_CLARIFICATION
            plan_result.assistant_message = (
                "I couldn't quite read the piece in that photo — could you try a clearer "
                "shot, ideally well-lit and showing the full garment? Then I can pair it "
                "properly."
            )
            plan_result.follow_up_suggestions = [
                "Upload a clearer photo",
                "Pick from my wardrobe",
                "Show me outfit ideas instead",
            ]
            if "wardrobe_enrichment_failed" not in override_reasons:
                override_reasons.append("wardrobe_enrichment_failed")

        # Phase 12D follow-up (April 9 2026): explicit non-garment guard.
        # The wardrobe enrichment now returns `is_garment_photo` and
        # `garment_present_confidence` so the model can explicitly say
        # "this image isn't a garment" instead of being forced to make
        # up attributes for every upload. Surface a clarification when
        # the model says the image isn't a garment, OR when the
        # confidence is below 0.5 (defence-in-depth: catches the case
        # where the model says yes but isn't sure).
        #
        # PR V2 (May 5 2026): the prior garment_evaluation exemption
        # was removed alongside that intent.
        #
        # This check fires BEFORE the wardrobe-persistence promotion
        # block below, so non-garment uploads never reach
        # `user_wardrobe_items`.
        if (
            attached_item
            and (
                attached_item.get("is_garment_photo") is False
                or float(attached_item.get("garment_present_confidence") or 1.0) < 0.5
            )
        ):
            plan_result.action = Action.ASK_CLARIFICATION
            plan_result.assistant_message = (
                "I couldn't see a garment in that photo — it looks like something "
                "else. Could you upload a clearer photo of the piece you'd like me "
                "to pair with?"
            )
            plan_result.follow_up_suggestions = [
                "Upload a clearer photo",
                "Pick from my wardrobe",
                "Show me outfit ideas instead",
            ]
            if "non_garment_image" not in override_reasons:
                override_reasons.append("non_garment_image")

        # ── Snapshot the intent ──
        # NOTE: trace_end("copilot_planner") fires once at line 1318
        # right after the planner LLM call returns. Calling it again
        # here used to write a second `copilot_planner` row to
        # `turn_traces.steps` (with model=None, latency=None) because
        # `_step_t0` had already been popped. Override info lives on
        # `set_intent.reason_codes` below — that's the right home.
        trace.set_intent(
            primary_intent=plan_result.intent,
            intent_confidence=plan_result.intent_confidence,
            action=plan_result.action,
            reason_codes=["copilot_planner", *override_reasons],
        )
        # Snapshot the query entities the planner extracted
        rc = plan_result.resolved_context
        trace.set_context(
            query_entities={
                "occasion_signal": rc.occasion_signal,
                "formality_hint": rc.formality_hint,
                "time_of_day": str(getattr(rc, "time_of_day", "") or ""),
                "weather_context": str(getattr(rc, "weather_context", "") or ""),
                "specific_needs": list(rc.specific_needs or []),
                "target_product_type": str(getattr(rc, "target_product_type", "") or ""),
                "followup_intent": rc.followup_intent,
                "is_followup": rc.is_followup,
            },
        )

        # Build intent classification for metadata compatibility
        intent = IntentClassification(
            primary_intent=plan_result.intent,
            confidence=plan_result.intent_confidence,
            reason_codes=["copilot_planner", *override_reasons],
        )

        # Phase 12D follow-up (April 9 2026): wardrobe persistence is
        # gated on intent. Only `pairing_request` is allowed to write the
        # uploaded garment to `user_wardrobe_items`, because that's the
        # only intent where "save this to my closet" matches the user's
        # actual ask. PR V2 (May 5 2026) folded outfit_check into
        # pairing_request and removed garment_evaluation entirely; the
        # gate is now a single-intent check.
        #
        # Also skipped when an earlier override flipped the action to
        # ASK_CLARIFICATION (non-garment image, failed enrichment, etc.)
        # — those uploads should NEVER reach the wardrobe.
        if (
            attached_item
            and attached_item.get("_pending_persist")
            and plan_result.intent == Intent.PAIRING_REQUEST
            and plan_result.action != Action.ASK_CLARIFICATION
        ):
            try:
                persisted = self.onboarding_gateway.persist_pending_wardrobe_item(
                    user_id=external_user_id,
                    pending=attached_item,
                )
                if persisted:
                    # Carry forward any flags the orchestrator already set
                    # on the pending dict (attachment_source, enrichment_failed)
                    # that the post-enrichment block above attached.
                    for key in ("attachment_source", "enrichment_failed"):
                        if key in attached_item and key not in persisted:
                            persisted[key] = attached_item[key]
                    attached_item = persisted
                    _log.info(
                        "Promoted pending wardrobe upload to row %s for intent %s",
                        attached_item.get("id"),
                        plan_result.intent,
                    )
            except Exception:
                _log.exception(
                    "Failed to promote pending wardrobe upload for intent %s",
                    plan_result.intent,
                )

        self._persist_profile_confidence(
            external_user_id=external_user_id,
            conversation_id=conversation_id,
            turn_id=turn_id,
            channel=channel,
            profile_confidence=profile_confidence,
            primary_intent=plan_result.intent,
            status=onboarding_gate.status,
        )

        # Dispatch on action — capture the return value so we can
        # persist the turn trace after the handler completes.
        handler_result: Dict[str, Any] | None = None
        if plan_result.action == Action.RESPOND_DIRECTLY:
            handler_result = self._handle_direct_response(
                plan_result=plan_result,
                intent=intent,
                conversation_id=conversation_id,
                turn_id=turn_id,
                channel=channel,
                external_user_id=external_user_id,
                message=message,
                previous_context=previous_context,
                profile_confidence=profile_confidence,

            )
        elif plan_result.action == Action.ASK_CLARIFICATION:
            handler_result = self._handle_clarification(
                plan_result=plan_result,
                intent=intent,
                conversation_id=conversation_id,
                turn_id=turn_id,
                channel=channel,
                external_user_id=external_user_id,
                message=message,
                previous_context=previous_context,
                profile_confidence=profile_confidence,

            )
        elif plan_result.action == Action.RUN_RECOMMENDATION_PIPELINE:
            handler_result = self._handle_planner_pipeline(
                plan_result=plan_result,
                intent=intent,
                conversation_id=conversation_id,
                turn_id=turn_id,
                channel=channel,
                external_user_id=external_user_id,
                message=effective_message,
                previous_context=previous_context,
                user_context=user_context,
                conversation_history=conversation_history,
                profile_confidence=profile_confidence,

                attached_item=attached_item,
                anchored_item_id=str((attached_item or {}).get("id") or ""),
                force_catalog_followup=force_catalog_followup,
                source_preference=source_preference,
                emit=emit,
                trace_start=trace_start,
                trace_end=trace_end,
                trace=trace,
            )
        elif plan_result.action == Action.SAVE_WARDROBE_ITEM:
            handler_result = self._handle_planner_wardrobe_save(
                plan_result=plan_result,
                intent=intent,
                conversation_id=conversation_id,
                turn_id=turn_id,
                channel=channel,
                external_user_id=external_user_id,
                message=message,
                previous_context=previous_context,
                profile_confidence=profile_confidence,

            )
        elif plan_result.action == Action.SAVE_FEEDBACK:
            handler_result = self._handle_planner_feedback(
                plan_result=plan_result,
                intent=intent,
                conversation_id=conversation_id,
                turn_id=turn_id,
                channel=channel,
                external_user_id=external_user_id,
                message=message,
                previous_context=previous_context,
                profile_confidence=profile_confidence,

            )
        else:
            # Unknown action — fall back to direct response
            _log.warning("Unknown planner action: %s, falling back to direct response", plan_result.action)
            handler_result = self._handle_direct_response(
                plan_result=plan_result,
                intent=intent,
                conversation_id=conversation_id,
                turn_id=turn_id,
                channel=channel,
                external_user_id=external_user_id,
                message=message,
                previous_context=previous_context,
                profile_confidence=profile_confidence,

            )

        # ── Store last_attached_item so the NEXT turn can carry it ────
        # If this turn processed an attached garment (from upload or
        # wardrobe selection), persist a summary in the session context
        # so a follow-up "pair these pants" turn can anchor on it.
        # This is a read-merge-write because the handler already wrote
        # its own session context fields — we add one more key without
        # overwriting the rest. Best-effort: failures here must not
        # block the response.
        if attached_item and str(attached_item.get("id") or "").strip():
            try:
                fresh_ctx = dict(
                    (self.repo.get_conversation(conversation_id) or {}).get("session_context_json") or {}
                )
                fresh_ctx["last_attached_item"] = {
                    "id": str(attached_item.get("id") or ""),
                    "title": str(attached_item.get("title") or ""),
                    "image_path": str(attached_item.get("image_path") or ""),
                    "image_url": str(attached_item.get("image_url") or ""),
                    "garment_category": str(attached_item.get("garment_category") or ""),
                    "garment_subtype": str(attached_item.get("garment_subtype") or ""),
                    "primary_color": str(attached_item.get("primary_color") or ""),
                    "secondary_color": str(attached_item.get("secondary_color") or ""),
                    "formality_level": str(attached_item.get("formality_level") or ""),
                    "occasion_fit": str(attached_item.get("occasion_fit") or ""),
                    "pattern_type": str(attached_item.get("pattern_type") or ""),
                    "source": str(attached_item.get("source") or "wardrobe"),
                }
                self.repo.update_conversation_context(
                    conversation_id=conversation_id,
                    session_context=fresh_ctx,
                )
            except Exception:
                _log.debug("Could not store last_attached_item in session context", exc_info=True)
        elif not attached_item:
            # Clear the previous attached item so it doesn't linger
            # across unrelated turns (e.g. user switches topic).
            try:
                fresh_ctx = dict(
                    (self.repo.get_conversation(conversation_id) or {}).get("session_context_json") or {}
                )
                if "last_attached_item" in fresh_ctx:
                    del fresh_ctx["last_attached_item"]
                    self.repo.update_conversation_context(
                        conversation_id=conversation_id,
                        session_context=fresh_ctx,
                    )
            except Exception:
                _log.debug("Could not clear last_attached_item", exc_info=True)

        # ── Persist the turn trace ────────────────────────────────────
        # Snapshot the evaluation summary from the handler result if
        # available (recommendation pipeline, garment_evaluation, outfit
        # check — each stores outfits/scores in the result dict).
        if handler_result:
            outfits = handler_result.get("outfits") or []
            metadata = handler_result.get("metadata") or {}
            trace.set_evaluation({
                "evaluator_path": metadata.get("evaluator_path") or "",
                "answer_source": metadata.get("answer_source") or "",
                "outfit_count": len(outfits),
                "response_type": handler_result.get("response_type") or "",
            })
            # Store last_turn_id in session context via the handler result
            # so the NEXT turn can correlate user_response.
            handler_result.setdefault("_trace_turn_id", turn_id)
        self._persist_trace(trace)
        # Item 5 (May 1, 2026): aura_turn_total counter — labelled by intent
        # / action / response_type. Increments on the happy-path return so
        # alerts can target real outcomes.
        try:
            from platform_core.metrics import observe_turn_outcome
            observe_turn_outcome(
                intent=str((handler_result or {}).get("metadata", {}).get("primary_intent") or plan_result.intent or ""),
                action=str(plan_result.action or ""),
                status=str((handler_result or {}).get("response_type") or "ok"),
            )
        except Exception:  # noqa: BLE001
            pass
        return handler_result or {"conversation_id": conversation_id, "turn_id": turn_id, "response_type": "error"}

    # ------------------------------------------------------------------
    # Virtual try-on
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_garment_ids(outfit: OutfitCard) -> list[str]:
        return sorted(
            str(item.get("product_id") or "").strip()
            for item in outfit.items
            if str(item.get("product_id") or "").strip()
        )

    @staticmethod
    def _detect_garment_source(outfit: OutfitCard) -> str:
        sources = set()
        for item in outfit.items:
            src = str(item.get("source") or "").strip().lower()
            if src in ("wardrobe", "catalog"):
                sources.add(src)
        if len(sources) > 1:
            return "mixed"
        return sources.pop() if sources else "catalog"

    @staticmethod
    def _tryon_image_url(file_path: str) -> str:
        return "/v1/onboarding/images/local?path=" + quote(file_path, safe="")

    def _attach_tryon_images(
        self,
        outfits: List[OutfitCard],
        external_user_id: str,
        *,
        conversation_id: str = "",
        turn_id: str = "",
    ) -> None:
        """Generate virtual try-on images for each outfit in parallel, with disk + DB persistence and cache reuse."""
        import base64
        import hashlib
        from datetime import datetime, timezone
        from pathlib import Path

        person_path = self.onboarding_gateway.get_person_image_path(external_user_id)
        if not person_path:
            return

        tryon_dir = Path("data/tryon/images")
        tryon_dir.mkdir(parents=True, exist_ok=True)

        def _generate_for_outfit(outfit: OutfitCard) -> tuple[OutfitCard, str]:
            garment_urls: list[tuple[str, str]] = []
            for item in outfit.items:
                url = str(item.get("image_url") or "").strip()
                if not url:
                    continue
                role = str(item.get("role") or "").strip()
                garment_urls.append((role or "garment", url))
            if not garment_urls:
                return outfit, ""

            garment_ids = self._extract_garment_ids(outfit)

            # Cache lookup
            if garment_ids:
                cached = self.repo.find_tryon_image_by_garments(external_user_id, garment_ids)
                if cached and cached.get("file_path"):
                    cached_path = Path(cached["file_path"])
                    if cached_path.exists():
                        _log.info("Try-on cache hit for outfit #%s", outfit.rank)
                        return outfit, self._tryon_image_url(str(cached_path))

            # Generate
            try:
                result = self.tryon_service.generate_tryon_outfit(
                    person_image_path=person_path,
                    garment_urls=garment_urls,
                )
                if not result.get("success"):
                    return outfit, ""

                quality = self.tryon_quality_gate.evaluate(
                    person_image_path=person_path,
                    tryon_result=result,
                )
                if not quality.get("passed"):
                    _log.info(
                        "Try-on quality gate blocked outfit #%s: %s",
                        outfit.rank,
                        quality.get("reason_code") or "unknown_quality_failure",
                    )
                    return outfit, ""

                # Persist to disk
                image_b64 = result.get("image_base64") or ""
                mime_type = result.get("mime_type") or "image/png"
                image_bytes = base64.b64decode(image_b64) if image_b64 else b""
                if not image_bytes:
                    return outfit, ""

                ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
                ids_key = "_".join(garment_ids) if garment_ids else ts
                encrypted = hashlib.sha256(f"{external_user_id}_tryon_{ids_key}_{ts}".encode()).hexdigest()
                ext = ".png" if "png" in mime_type else ".jpg"
                filename = f"{encrypted}{ext}"
                dest = tryon_dir / filename
                dest.write_bytes(image_bytes)

                # Persist to DB
                try:
                    self.repo.insert_tryon_image(
                        user_id=external_user_id,
                        conversation_id=conversation_id,
                        turn_id=turn_id,
                        outfit_rank=outfit.rank,
                        garment_ids=garment_ids,
                        garment_source=self._detect_garment_source(outfit),
                        person_image_path=person_path,
                        encrypted_filename=encrypted,
                        file_path=str(dest),
                        mime_type=mime_type,
                        file_size_bytes=len(image_bytes),
                        quality_score_pct=quality.get("quality_score_pct"),
                    )
                except Exception:
                    _log.warning("Failed to persist try-on metadata for outfit #%s", outfit.rank, exc_info=True)

                return outfit, self._tryon_image_url(str(dest))
            except Exception:
                _log.warning("Try-on generation failed for outfit #%s", outfit.rank, exc_info=True)
            return outfit, ""

        ctx_snapshot = _snapshot_request_context()
        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = {
                pool.submit(run_with_context, ctx_snapshot, _generate_for_outfit, o): o
                for o in outfits
            }
            for future in as_completed(futures):
                outfit, tryon_url = future.result()
                if tryon_url:
                    outfit.tryon_image = tryon_url

    def _persist_catalog_interactions(
        self,
        *,
        external_user_id: str,
        conversation_id: str,
        turn_id: str,
        channel: str,
        primary_intent: str,
        outfits: List[OutfitCard],
    ) -> None:
        seen_product_ids: set[str] = set()
        for outfit in outfits:
            for position, item in enumerate(outfit.items, start=1):
                product_id = str(item.get("product_id") or "").strip()
                if not product_id or product_id in seen_product_ids:
                    continue
                seen_product_ids.add(product_id)
                try:
                    self.repo.create_catalog_interaction(
                        user_id=external_user_id,
                        conversation_id=conversation_id,
                        turn_id=turn_id,
                        product_id=product_id,
                        interaction_type="view",
                        source_channel=channel,
                        source_surface="recommendation_outfit",
                        metadata_json={
                            "outfit_rank": outfit.rank,
                            "item_position": position,
                            "item_role": str(item.get("role") or "").strip(),
                            "primary_intent": primary_intent,
                            "title": str(item.get("title") or "").strip(),
                        },
                    )
                except Exception:
                    _log.warning(
                        "Failed to persist catalog interaction for product_id=%s",
                        product_id,
                        exc_info=True,
                    )

    def _persist_profile_confidence(
        self,
        *,
        external_user_id: str,
        conversation_id: str,
        turn_id: str,
        channel: str,
        profile_confidence: ProfileConfidence,
        primary_intent: str,
        status: str,
    ) -> None:
        try:
            self.repo.create_confidence_history(
                user_id=external_user_id,
                conversation_id=conversation_id,
                turn_id=turn_id,
                source_channel=channel,
                confidence_type="profile",
                score_pct=int(profile_confidence.analysis_confidence_pct),
                factors_json=[factor.model_dump() for factor in profile_confidence.factors],
                metadata_json={
                    "primary_intent": primary_intent,
                    "status": status,
                    "improvement_actions": list(profile_confidence.improvement_actions),
                },
            )
        except Exception:
            _log.warning("Failed to persist profile confidence history", exc_info=True)

    def _build_recommendation_confidence(
        self,
        *,
        answer_mode: str,
        profile_confidence: ProfileConfidence,
        intent: IntentClassification,
        evaluated: List[Any],
        retrieved_sets: List[Any],
        candidate_count: int,
        response_outfit_count: int,
        restricted_item_exclusion_count: int,
        wardrobe_items_used: int,
    ) -> RecommendationConfidence:
        top_match_score = max(0.0, min(1.0, float(getattr(evaluated[0], "match_score", 0.0) or 0.0))) if evaluated else 0.0
        second_match_score = max(0.0, min(1.0, float(getattr(evaluated[1], "match_score", 0.0) or 0.0))) if len(evaluated) > 1 else 0.0
        retrieved_product_count = sum(len(getattr(rs, "products", []) or []) for rs in retrieved_sets)
        return evaluate_recommendation_confidence(
            answer_mode=answer_mode,
            profile_confidence_score_pct=profile_confidence.analysis_confidence_pct,
            intent_confidence=float(intent.confidence),
            top_match_score=top_match_score,
            second_match_score=second_match_score,
            retrieved_product_count=retrieved_product_count,
            candidate_count=candidate_count,
            response_outfit_count=response_outfit_count,
            wardrobe_items_used=wardrobe_items_used,
            restricted_item_exclusion_count=restricted_item_exclusion_count,
        )

    def _persist_recommendation_confidence(
        self,
        *,
        external_user_id: str,
        conversation_id: str,
        turn_id: str,
        channel: str,
        primary_intent: str,
        recommendation_confidence: RecommendationConfidence,
        metadata_json: Dict[str, Any] | None = None,
    ) -> None:
        if recommendation_confidence.score_pct <= 0:
            return
        try:
            self.repo.create_confidence_history(
                user_id=external_user_id,
                conversation_id=conversation_id,
                turn_id=turn_id,
                source_channel=channel,
                confidence_type="recommendation",
                score_pct=max(0, min(100, int(recommendation_confidence.score_pct))),
                factors_json=[factor.model_dump() for factor in recommendation_confidence.factors],
                metadata_json={
                    "primary_intent": primary_intent,
                    "estimation_method": "runtime_evidence_v1",
                    "provisional": False,
                    "confidence_band": recommendation_confidence.confidence_band,
                    "summary": recommendation_confidence.summary,
                    "explanation": list(recommendation_confidence.explanation),
                    **dict(metadata_json or {}),
                },
            )
        except Exception:
            _log.warning("Failed to persist recommendation confidence history", exc_info=True)

    def _persist_policy_event(
        self,
        *,
        external_user_id: str,
        conversation_id: str,
        turn_id: str,
        channel: str,
        policy_event_type: str,
        input_class: str,
        reason_code: str,
        decision: str = "blocked",
        metadata_json: Dict[str, Any] | None = None,
    ) -> None:
        try:
            self.repo.create_policy_event(
                user_id=external_user_id,
                conversation_id=conversation_id,
                turn_id=turn_id,
                source_channel=channel,
                policy_event_type=policy_event_type,
                input_class=input_class,
                reason_code=reason_code,
                decision=decision,
                rule_source="rule",
                metadata_json=metadata_json or {},
            )
        except Exception:
            _log.warning("Failed to persist policy event", exc_info=True)

    def _persist_dependency_turn_event(
        self,
        *,
        external_user_id: str,
        conversation_id: str,
        turn_id: str,
        channel: str,
        primary_intent: str,
        response_type: str,
        metadata_json: Dict[str, Any] | None = None,
    ) -> None:
        try:
            self.repo.create_dependency_event(
                user_id=external_user_id,
                conversation_id=conversation_id,
                turn_id=turn_id,
                source_channel=channel,
                event_type="turn_completed",
                primary_intent=primary_intent,
                metadata_json={
                    "response_type": response_type,
                    **dict(metadata_json or {}),
                },
            )
        except Exception:
            _log.warning("Failed to persist dependency validation turn event", exc_info=True)

    def _save_chat_wardrobe_item(
        self,
        *,
        external_user_id: str,
        message: str,
    ) -> Dict[str, Any] | None:
        lowered = str(message or "").strip().lower()
        urls = re.findall(r"https?://\S+", lowered)
        garment_words = (
            "dress", "blazer", "jacket", "coat", "jeans", "trousers", "pants", "shirt",
            "top", "skirt", "heels", "sneakers", "bag", "blouse", "suit", "cardigan",
        )
        color_words = (
            "black", "white", "cream", "beige", "brown", "tan", "navy", "blue", "red",
            "burgundy", "green", "olive", "pink", "purple", "grey", "gray", "gold", "silver",
        )
        garment = next((word for word in garment_words if word in lowered), "")
        color = next((word for word in color_words if word in lowered), "")
        if not garment and not urls:
            return None
        title = " ".join(part for part in (color.title() if color else "", garment.title() if garment else "Wardrobe Item") if part).strip()
        return self.onboarding_gateway.save_chat_wardrobe_item(
            user_id=external_user_id,
            title=title or "Saved Wardrobe Item",
            description=message.strip(),
            image_url=urls[0] if urls else "",
            garment_category=garment,
            garment_subtype=garment,
            primary_color=color,
            metadata_json={
                "source_message": message.strip(),
                "capture_mode": "chat_intent",
            },
        )

    def _persist_chat_feedback(
        self,
        *,
        external_user_id: str,
        conversation_id: str,
        handler_payload: Dict[str, Any],
        notes: str,
    ) -> None:
        item_ids = [str(value) for value in (handler_payload.get("item_ids") or []) if str(value).strip()]
        if not item_ids:
            return
        event_type = str(handler_payload.get("event_type") or "dislike").strip() or "dislike"
        reward = 1 if event_type == "like" else -1
        target_turn_id = str(handler_payload.get("target_turn_id") or "").strip() or None
        outfit_rank = int(handler_payload.get("outfit_rank") or 1)
        for garment_id in item_ids:
            self.repo.create_feedback_event(
                user_id=self.repo.get_or_create_user(external_user_id)["id"],
                conversation_id=conversation_id,
                turn_id=target_turn_id,
                outfit_rank=outfit_rank,
                garment_id=garment_id,
                event_type=event_type,
                reward_value=reward,
                notes=notes,
            )
            self.repo.create_catalog_interaction(
                user_id=external_user_id,
                conversation_id=conversation_id,
                turn_id=target_turn_id,
                product_id=garment_id,
                interaction_type="save" if event_type == "like" else "dismiss",
                source_channel="web",
                source_surface="chat_feedback_intent",
                metadata_json={
                    "outfit_rank": outfit_rank,
                    "feedback_event_type": event_type,
                },
            )

    def _build_wardrobe_first_occasion_response(
        self,
        *,
        external_user_id: str,
        message: str,
        conversation_id: str,
        turn_id: str,
        channel: str,
        intent: IntentClassification,
        previous_context: Dict[str, Any],
        user_context: Any,
        live_context: LiveContext,
        conversation_memory: Dict[str, Any],
        profile_confidence: ProfileConfidence,

        anchored_item_id: str = "",
        precomputed_coverage: Optional[Tuple[bool, Dict[str, int]]] = None,
    ) -> Dict[str, Any] | None:
        if intent.primary_intent != Intent.OCCASION_RECOMMENDATION:
            return None
        occasion = str(live_context.occasion_signal or "").strip()
        wardrobe_items = list(getattr(user_context, "wardrobe_items", []) or [])
        if not occasion or not wardrobe_items:
            return None
        # Minimum-coverage gate: when the user explicitly asks for wardrobe-first,
        # require ≥2 tops AND ≥2 bottoms AND ≥2 one-pieces. If any role is below
        # the threshold, fall through so `_build_wardrobe_only_occasion_fallback`
        # can surface a clear "your wardrobe doesn't cover this yet" message
        # with the actual counts and offer catalog/hybrid alternatives.
        # The orchestrator computes coverage once and passes it via
        # `precomputed_coverage` so this function and the fallback share one
        # computation; falling back to a fresh call keeps the function safe to
        # call standalone from tests or future entry points.
        sufficient, _coverage_counts = (
            precomputed_coverage
            if precomputed_coverage is not None
            else self._wardrobe_meets_minimum_coverage(wardrobe_items)
        )
        if not sufficient:
            _log.info(
                "wardrobe-first: skipping (insufficient coverage) counts=%s",
                _coverage_counts,
            )
            return None
        wardrobe_gap_analysis = self._build_wardrobe_gap_analysis(
            wardrobe_items=wardrobe_items,
            occasion=occasion,
            required_roles=["top", "bottom", "shoe"],
        )

        outfit, wardrobe_match_confidence = self._select_wardrobe_occasion_outfit(
            wardrobe_items=wardrobe_items, occasion=occasion,
        )
        outfit, blocked_terms = self._filter_restricted_recommendation_items(outfit)
        if not outfit:
            return None
        # Confidence gate (May 1 2026): below 0.75 the wardrobe answer is
        # not honest — fall through so the caller can try
        # `_build_wardrobe_only_occasion_fallback` (which says "your wardrobe
        # doesn't fully cover this — want catalog picks?") or the full
        # catalog pipeline. The same threshold applies to hybrid mode
        # below: shipping a hybrid as a "wardrobe-first" answer demands
        # the wardrobe anchor genuinely match the occasion.
        if wardrobe_match_confidence < _RECOMMENDATION_CONFIDENCE_THRESHOLD:
            _log.info(
                "wardrobe-first: skipping (confidence %.2f below %.2f) occasion=%s",
                wardrobe_match_confidence,
                _RECOMMENDATION_CONFIDENCE_THRESHOLD,
                occasion,
            )
            return None
        outfit_roles = {self._normalize_text_token(item.get("role") or "") for item in outfit}
        has_one_piece = "one_piece" in outfit_roles or "one piece" in outfit_roles

        # ── Wardrobe-First Success Guardrails ──
        # A single non-one-piece item is not a usable outfit. Determine which
        # required outfit roles are still uncovered, then attempt a hybrid
        # pivot (wardrobe anchor + catalog gap-fill) before giving up.
        required_roles_for_complete = [] if has_one_piece else ["top", "bottom"]
        missing_required_roles = [
            role for role in required_roles_for_complete if role not in outfit_roles
        ]
        has_shoe = "shoe" in outfit_roles
        wardrobe_completeness_pct = int(wardrobe_gap_analysis.get("completeness_score_pct") or 0)
        wardrobe_is_complete = (
            (has_one_piece or not missing_required_roles)
            and wardrobe_completeness_pct >= 40
        )

        catalog_gap_fillers: List[Dict[str, Any]] = []
        hybrid_used = False
        hybrid_fill_roles: List[str] = []
        if not wardrobe_is_complete:
            # Try hybrid: pivot to catalog to fill the missing roles instead of
            # claiming a one-item wardrobe answer is the full result.
            fill_roles = list(missing_required_roles)
            if not has_shoe and "shoe" not in fill_roles:
                fill_roles.append("shoe")
            if not fill_roles:
                # Wardrobe gave us *something* but coverage is still thin —
                # fall back to filling the second core role from catalog.
                fill_roles = ["bottom" if "top" in outfit_roles else "top", "shoe"]
            catalog_gap_fillers = self._select_catalog_items(
                desired_roles=fill_roles,
                occasion=occasion,
                preferred_colors=[
                    str(item.get("primary_color") or "")
                    for item in outfit
                    if str(item.get("primary_color") or "").strip()
                ],
                limit=max(2, len(fill_roles)),
            )
            if catalog_gap_fillers:
                hybrid_used = True
                hybrid_fill_roles = fill_roles
            else:
                # No usable hybrid answer — let the main pipeline try.
                return None

        anchor_id = str(anchored_item_id or "").strip()
        selected_ids = [str(item.get("product_id") or "") for item in outfit if str(item.get("product_id") or "").strip()]
        if anchor_id and len(selected_ids) <= 1 and selected_ids == [anchor_id] and not hybrid_used:
            return None

        def _piece_label(item: Dict[str, Any]) -> str:
            title = str(item.get("title") or "").strip()
            if title:
                return title
            color = str(item.get("primary_color") or "").strip()
            cat = str(item.get("garment_subtype") or item.get("garment_category") or "piece").strip()
            return f"{color} {cat}".strip() if color else cat

        if hybrid_used:
            outfit_for_card = list(outfit) + list(catalog_gap_fillers)
            answer_source = "wardrobe_first_hybrid"
            gap_label = ", ".join(hybrid_fill_roles) if hybrid_fill_roles else "missing pieces"
            wardrobe_piece_names = [_piece_label(it) for it in outfit][:2]
            catalog_piece_names = [_piece_label(it) for it in catalog_gap_fillers][:2]
            reasoning = (
                f"Started with your "
                + " and ".join(wardrobe_piece_names)
                + f" for {occasion.replace('_', ' ')}, then added "
                + ", ".join(catalog_piece_names)
                + f" from the catalog to fill the {gap_label} you were missing."
            )
            handler_label = "occasion_recommendation_wardrobe_first_hybrid"
            outfit_card_title = f"Hybrid {occasion.replace('_', ' ').title()} look"
        else:
            outfit_for_card = outfit
            answer_source = "wardrobe_first"
            piece_names = [_piece_label(it) for it in outfit][:3]
            reasoning = (
                f"For {occasion.replace('_', ' ')}, your "
                + " and ".join(piece_names)
                + " from your saved wardrobe is the strongest fit — "
                + ("matching the occasion formality and your color story." if len(piece_names) > 1 else "anchored to the occasion formality and your color story.")
            )
            handler_label = "occasion_recommendation_wardrobe_first"
            outfit_card_title = f"Wardrobe-first {occasion.replace('_', ' ').title()} look"
        catalog_upsell = self._build_catalog_upsell(
            rationale=(
                "Your wardrobe gave us the anchor; the catalog can extend or upgrade it."
                if hybrid_used
                else "Your wardrobe covers the occasion first, but I can also show stronger catalog options if you want a more elevated or optimized version."
            ),
            entry_intent=Intent.OCCASION_RECOMMENDATION,
        )
        source_selection = self._build_source_selection(
            preferred_source="wardrobe" if "wardrobe_first" in list(live_context.specific_needs or []) else "",
            fulfilled_source="hybrid" if hybrid_used else "wardrobe",
        )
        outfit_card = OutfitCard(
            rank=1,
            title=outfit_card_title,
            reasoning=reasoning,
            occasion_note=reasoning,
            items=outfit_for_card,
        )
        answer_components = self._summarize_answer_components([outfit_card])
        recommendation_confidence = evaluate_recommendation_confidence(
            answer_mode="wardrobe_first_hybrid" if hybrid_used else "wardrobe_first",
            profile_confidence_score_pct=profile_confidence.analysis_confidence_pct,
            intent_confidence=float(intent.confidence),
            top_match_score=wardrobe_match_confidence,
            second_match_score=0.0,
            retrieved_product_count=len(catalog_gap_fillers),
            candidate_count=1,
            response_outfit_count=1,
            wardrobe_items_used=len(outfit),
            restricted_item_exclusion_count=len(blocked_terms),
        )
        routing_metadata = {
            "primary_intent": intent.primary_intent,
            "intent_confidence": intent.confidence,
            "secondary_intents": list(intent.secondary_intents or []),
            "reason_codes": list(intent.reason_codes or []),
            "memory_sources_read": [
                "user_profile",
                "wardrobe_memory",
                "conversation_memory",
            ],
            "memory_sources_written": [
                "conversation_memory",
                "confidence_history",
            ],
        }
        metadata = self._build_response_metadata(
            channel=channel,
            intent=intent,
            profile_confidence=profile_confidence,
            extra={
                "answer_source": answer_source,
                "answer_components": answer_components,
                "source_selection": source_selection,
                "catalog_upsell": catalog_upsell,
                "recommendation_confidence": recommendation_confidence.model_dump(),
                "restricted_item_exclusion_count": len(blocked_terms),
                "wardrobe_gap_analysis": wardrobe_gap_analysis,
                "routing_metadata": routing_metadata,
                "hybrid_fill_roles": hybrid_fill_roles,
                "wardrobe_completeness_pct": wardrobe_completeness_pct,
                "completion_status": "hybrid" if hybrid_used else "wardrobe_complete",
            },
        )
        resolved_context = {
            "request_summary": message.strip(),
            "occasion": occasion,
            "style_goal": "wardrobe_first",
            "live_context": live_context.model_dump(),
            "conversation_memory": conversation_memory,
            "intent_classification": intent.model_dump(),
                "profile_confidence": profile_confidence.model_dump(),

                "response_metadata": metadata,
                "handler": handler_label,
                "handler_payload": {
                    "answer_source": answer_source,
                    "selected_item_ids": [str(item.get("product_id") or "") for item in outfit_for_card],
                    "wardrobe_anchor_ids": [str(item.get("product_id") or "") for item in outfit],
                    "catalog_fill_ids": [str(item.get("product_id") or "") for item in catalog_gap_fillers],
                    "hybrid_fill_roles": hybrid_fill_roles,
                    "wardrobe_completeness_pct": wardrobe_completeness_pct,
                    "answer_components": answer_components,
                "source_selection": source_selection,
                "catalog_upsell": catalog_upsell,
                "recommendation_confidence": recommendation_confidence.model_dump(),
                "restricted_item_exclusion_count": len(blocked_terms),
                "wardrobe_gap_analysis": wardrobe_gap_analysis,
                "routing_metadata": routing_metadata,
            },
            "routing_metadata": routing_metadata,
            "recommendations": [
                {
                    "candidate_id": ("hybrid-wardrobe-first-1" if hybrid_used else "wardrobe-first-1"),
                    "rank": 1,
                    "title": outfit_card.title,
                    "item_ids": [str(item.get("product_id") or "") for item in outfit_for_card],
                    "match_score": wardrobe_match_confidence,
                    "reasoning": reasoning,
                }
            ],
            # Persist the built outfit card so historical replay in the
            # chat UI (loadConversation → renderOutfits) can re-render
            # it identically to the live response.
            "outfits": [outfit_card.model_dump()],
            "channel": channel,
        }
        if hybrid_used:
            assistant_message = (
                reasoning
                + " The pieces I added from the catalog cover what your wardrobe was missing for this occasion."
            )
        else:
            assistant_message = (
                reasoning + " If you want, I can also show better catalog options for this occasion."
            )
        self.repo.finalize_turn(
            turn_id=turn_id,
            assistant_message=assistant_message,
            resolved_context=resolved_context,
        )
        self._persist_recommendation_confidence(
            external_user_id=external_user_id,
            conversation_id=conversation_id,
            turn_id=turn_id,
            channel=channel,
            primary_intent=intent.primary_intent,
            recommendation_confidence=recommendation_confidence,
            metadata_json={"answer_mode": "wardrobe_first_hybrid" if hybrid_used else "wardrobe_first"},
        )
        session_context = {
            **previous_context,
            "memory": conversation_memory,
            "last_occasion": occasion,
            "last_live_context": live_context.model_dump(),
            "last_response_metadata": metadata,
            "last_assistant_message": assistant_message,
            "last_user_message": message,
            "last_channel": channel,
            "last_intent": intent.primary_intent,
            "consecutive_gate_blocks": 0,
            "last_recommendations": [
                {
                    "candidate_id": ("hybrid-wardrobe-first-1" if hybrid_used else "wardrobe-first-1"),
                    "rank": 1,
                    "title": outfit_card.title,
                    "item_ids": [str(item.get("product_id") or "") for item in outfit_for_card],
                    "candidate_type": "hybrid" if hybrid_used else "wardrobe",
                    "direction_id": "hybrid" if hybrid_used else "wardrobe",
                    "primary_colors": [str(item.get("primary_color") or "") for item in outfit_for_card if str(item.get("primary_color") or "").strip()],
                    "garment_categories": [str(item.get("garment_category") or "") for item in outfit_for_card if str(item.get("garment_category") or "").strip()],
                    "garment_subtypes": [str(item.get("garment_subtype") or "") for item in outfit_for_card if str(item.get("garment_subtype") or "").strip()],
                    "roles": [str(item.get("role") or "") for item in outfit_for_card if str(item.get("role") or "").strip()],
                    "occasion_fits": [occasion],
                    "formality_levels": [str(item.get("formality_level") or "") for item in outfit_for_card if str(item.get("formality_level") or "").strip()],
                    "pattern_types": [],
                    "volume_profiles": [],
                    "fit_types": [],
                    "silhouette_types": [],
                }
            ],
        }
        self.repo.update_conversation_context(
            conversation_id=conversation_id,
            session_context=session_context,
        )
        self._persist_dependency_turn_event(
            external_user_id=external_user_id,
            conversation_id=conversation_id,
            turn_id=turn_id,
            channel=channel,
            primary_intent=intent.primary_intent,
            response_type="recommendation",
            metadata_json={
                "answer_source": answer_source,
                "memory_sources_read": list(routing_metadata.get("memory_sources_read") or []),
                "memory_sources_written": list(routing_metadata.get("memory_sources_written") or []),
                "recommendation_confidence_score_pct": recommendation_confidence.score_pct,
                "wardrobe_gap_count": len(list(wardrobe_gap_analysis.get("gap_items") or [])),
                "wardrobe_completeness_pct": wardrobe_completeness_pct,
                "hybrid_fill_roles": hybrid_fill_roles,
            },
        )
        if hybrid_used:
            follow_up_suggestions = [
                "Show me more catalog options to fill the gap",
                "Save these catalog picks to my wardrobe",
                str(catalog_upsell["cta"]),
            ]
        else:
            follow_up_suggestions = [
                "Show me more from my wardrobe",
                "Show me catalog alternatives",
                str(catalog_upsell["cta"]),
            ]
        return {
            "conversation_id": conversation_id,
            "turn_id": turn_id,
            "assistant_message": assistant_message,
            "response_type": "recommendation",
            "resolved_context": {
                "request_summary": message.strip(),
                "occasion": occasion,
                "style_goal": answer_source,
                "profile_confidence_pct": profile_confidence.analysis_confidence_pct,
            },
            "filters_applied": {},
            "outfits": [outfit_card.model_dump()],
            "follow_up_suggestions": follow_up_suggestions,
            "metadata": metadata,
        }

    def _build_wardrobe_only_occasion_fallback(
        self,
        *,
        message: str,
        conversation_id: str,
        turn_id: str,
        channel: str,
        intent: IntentClassification,
        previous_context: Dict[str, Any],
        user_context: Any,
        live_context: LiveContext,
        conversation_memory: Dict[str, Any],
        profile_confidence: ProfileConfidence,

        precomputed_coverage: Optional[Tuple[bool, Dict[str, int]]] = None,
    ) -> Dict[str, Any] | None:
        if intent.primary_intent != Intent.OCCASION_RECOMMENDATION:
            return None
        if "wardrobe_first" not in list(live_context.specific_needs or []):
            return None
        occasion = str(live_context.occasion_signal or "").strip()
        wardrobe_items = list(getattr(user_context, "wardrobe_items", []) or [])
        wardrobe_gap_analysis = self._build_wardrobe_gap_analysis(
            wardrobe_items=wardrobe_items,
            occasion=occasion,
            required_roles=["top", "bottom", "shoe"],
        )
        # Coverage may have been computed by `_build_wardrobe_first_occasion_response`
        # right before this fallback fires — accept it via `precomputed_coverage`
        # to skip the redundant role-count walk over the same wardrobe.
        coverage_sufficient, coverage_counts = (
            precomputed_coverage
            if precomputed_coverage is not None
            else self._wardrobe_meets_minimum_coverage(wardrobe_items)
        )
        gap_items = [str(item).strip() for item in list(wardrobe_gap_analysis.get("gap_items") or []) if str(item).strip()]
        occasion_label = occasion.replace('_', ' ') if occasion else 'this occasion'
        if wardrobe_items:
            if not coverage_sufficient:
                # Surface the actual counts the user has so they can see what's
                # missing rather than a vague "doesn't cover this" message.
                role_labels = {"top": "tops", "bottom": "bottoms", "one_piece": "complete dresses/jumpsuits"}
                count_phrases = [
                    f"{coverage_counts[role]} {role_labels[role]}"
                    for role in self._WARDROBE_REQUIRED_ROLES
                ]
                shortage_phrases = [
                    f"{role_labels[role]} (have {coverage_counts[role]}, need {self._WARDROBE_MIN_PER_ROLE})"
                    for role in self._WARDROBE_REQUIRED_ROLES
                    if coverage_counts[role] < self._WARDROBE_MIN_PER_ROLE
                ]
                assistant_message = (
                    f"Your saved wardrobe is too thin to build {occasion_label} outfits on its own — "
                    f"you have {', '.join(count_phrases)} saved, "
                    f"but I need at least {self._WARDROBE_MIN_PER_ROLE} of each "
                    f"({', '.join(shortage_phrases)}) to compose a few options. "
                    "You can either: (1) let me show catalog picks instead, "
                    "(2) see hybrid looks that combine your wardrobe with catalog pieces, "
                    "or (3) save a few more wardrobe staples and try again."
                )
            else:
                missing_clause = (
                    f" To make this work end-to-end you're still missing {', '.join(gap_items[:2])}."
                    if gap_items
                    else ""
                )
                assistant_message = (
                    f"Your saved wardrobe doesn't fully cover {occasion_label} yet."
                    + missing_clause
                    + " You can either: (1) let me show catalog picks to fill the gap, "
                    "(2) see hybrid looks that combine your wardrobe with a couple of catalog pieces, "
                    "or (3) save more wardrobe items and try again."
                )
        else:
            assistant_message = (
                f"I don't have enough saved wardrobe pieces yet to build a {occasion_label} outfit from your wardrobe."
                " You can either save a few staples first, or I can show catalog options now."
            )
        catalog_upsell = self._build_catalog_upsell(
            rationale="Your saved wardrobe does not fully cover this occasion yet.",
            entry_intent=Intent.OCCASION_RECOMMENDATION,
        )
        source_selection = self._build_source_selection(
            preferred_source="wardrobe",
            fulfilled_source="wardrobe_unavailable",
        )
        wardrobe_coverage = {
            "min_required_per_role": self._WARDROBE_MIN_PER_ROLE,
            "counts_by_role": coverage_counts,
            "sufficient": coverage_sufficient,
        }
        metadata = self._build_response_metadata(
            channel=channel,
            intent=intent,
            profile_confidence=profile_confidence,
            extra={
                "answer_source": "wardrobe_unavailable",
                "source_selection": source_selection,
                "catalog_upsell": catalog_upsell,
                "wardrobe_gap_analysis": wardrobe_gap_analysis,
                "wardrobe_coverage": wardrobe_coverage,
            },
        )
        self.repo.finalize_turn(
            turn_id=turn_id,
            assistant_message=assistant_message,
            resolved_context={
                "request_summary": message.strip(),
                "occasion": occasion,
                "style_goal": "wardrobe_first",
                "live_context": live_context.model_dump(),
                "conversation_memory": conversation_memory,
                "intent_classification": intent.model_dump(),
                "profile_confidence": profile_confidence.model_dump(),

                "response_metadata": metadata,
                "handler": "occasion_recommendation_wardrobe_unavailable",
                "handler_payload": {
                    "answer_source": "wardrobe_unavailable",
                    "source_selection": source_selection,
                    "catalog_upsell": catalog_upsell,
                    "wardrobe_gap_analysis": wardrobe_gap_analysis,
                    "wardrobe_coverage": wardrobe_coverage,
                },
                "channel": channel,
            },
        )
        self.repo.update_conversation_context(
            conversation_id=conversation_id,
            session_context={
                **previous_context,
                "memory": conversation_memory,
                "last_occasion": occasion,
                "last_live_context": live_context.model_dump(),
                "last_response_metadata": metadata,
                "last_assistant_message": assistant_message,
                "last_user_message": message,
                "last_channel": channel,
                "last_intent": intent.primary_intent,

                "consecutive_gate_blocks": 0,
            },
        )
        return {
            "conversation_id": conversation_id,
            "turn_id": turn_id,
            "assistant_message": assistant_message,
            "response_type": "recommendation",
            "resolved_context": {
                "request_summary": message.strip(),
                "occasion": occasion,
                "style_goal": "wardrobe_first",
            },
            "filters_applied": {},
            "outfits": [],
            "follow_up_suggestions": [
                "Show me catalog picks to fill the gap",
                "Show me hybrid wardrobe + catalog looks",
                "Save more wardrobe staples",
                str(catalog_upsell["cta"]),
            ],
            "metadata": metadata,
        }

    def _build_low_confidence_catalog_response(
        self,
        *,
        external_user_id: str,
        message: str,
        conversation_id: str,
        turn_id: str,
        channel: str,
        intent: IntentClassification,
        previous_context: Dict[str, Any],
        live_context: LiveContext,
        conversation_memory: Dict[str, Any],
        profile_confidence: ProfileConfidence,
        top_match_score: float,
        candidates_seen: int,
        hard_filters: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Honest no-match response when the catalog pipeline has no
        outfit whose Rater ``fashion_score`` clears the confidence
        threshold (or when the Composer judged the pool unsuitable).

        We never ship low-confidence outfits — that's the bargain with
        the user. Instead we explain what happened, surface the best raw
        match score we saw (so they know we tried), and offer to broaden
        the request or refine it.
        """
        occasion = str(live_context.occasion_signal or "").strip()
        occasion_label = occasion.replace("_", " ") if occasion else "what you described"
        # User-facing copy never references the threshold or raw match
        # score — those are operations metrics, not user vocabulary.
        # `low_confidence_top_match_score` and `low_confidence_threshold`
        # in `metadata` carry the same data for dashboards.
        assistant_message = (
            f"I couldn't find a strong match for {occasion_label} just yet. "
            "Tell me a bit more — vibe, color, or how dressy you want to look — "
            "and I'll take another pass. Or I can show you options to buy."
        )
        catalog_upsell = self._build_catalog_upsell(
            rationale="The closest catalog matches didn't clear the confidence bar.",
            entry_intent=intent.primary_intent,
        )
        source_selection = self._build_source_selection(
            preferred_source="catalog",
            fulfilled_source="catalog_low_confidence",
        )
        recommendation_confidence = evaluate_recommendation_confidence(
            answer_mode="catalog_pipeline",
            profile_confidence_score_pct=profile_confidence.analysis_confidence_pct,
            intent_confidence=float(intent.confidence),
            top_match_score=float(top_match_score),
            second_match_score=0.0,
            retrieved_product_count=0,
            candidate_count=candidates_seen,
            response_outfit_count=0,
            wardrobe_items_used=0,
            restricted_item_exclusion_count=0,
        )
        metadata = self._build_response_metadata(
            channel=channel,
            intent=intent,
            profile_confidence=profile_confidence,
            extra={
                "answer_source": "catalog_low_confidence",
                "source_selection": source_selection,
                "catalog_upsell": catalog_upsell,
                "recommendation_confidence": recommendation_confidence.model_dump(),
                "low_confidence_top_match_score": float(top_match_score),
                "low_confidence_threshold": _RECOMMENDATION_CONFIDENCE_THRESHOLD,
                "low_confidence_candidates_seen": int(candidates_seen),
            },
        )
        self.repo.finalize_turn(
            turn_id=turn_id,
            assistant_message=assistant_message,
            resolved_context={
                "request_summary": message.strip(),
                "occasion": occasion,
                "live_context": live_context.model_dump(),
                "conversation_memory": conversation_memory,
                "intent_classification": intent.model_dump(),
                "profile_confidence": profile_confidence.model_dump(),
                "response_metadata": metadata,
                "handler": "catalog_pipeline_low_confidence",
                "handler_payload": {
                    "answer_source": "catalog_low_confidence",
                    "source_selection": source_selection,
                    "catalog_upsell": catalog_upsell,
                    "top_match_score": float(top_match_score),
                    "candidates_seen": int(candidates_seen),
                },
                "channel": channel,
            },
        )
        self.repo.update_conversation_context(
            conversation_id=conversation_id,
            session_context={
                **previous_context,
                "memory": conversation_memory,
                "last_occasion": occasion,
                "last_live_context": live_context.model_dump(),
                "last_response_metadata": metadata,
                "last_assistant_message": assistant_message,
                "last_user_message": message,
                "last_channel": channel,
                "last_intent": intent.primary_intent,
                "consecutive_gate_blocks": 0,
            },
        )
        # Emit a turn_completed dependency event so OPERATIONS Panel 16
        # ("Low-Confidence Catalog Responses") can count these turns.
        # Without this, the panel SQL filters on metadata_json->>'answer_source'
        # = 'catalog_low_confidence' but never sees rows.
        self._persist_dependency_turn_event(
            external_user_id=external_user_id,
            conversation_id=conversation_id,
            turn_id=turn_id,
            channel=channel,
            primary_intent=intent.primary_intent,
            response_type="recommendation",
            metadata_json={
                "answer_source": "catalog_low_confidence",
                "low_confidence_top_match_score": float(top_match_score),
                "low_confidence_threshold": _RECOMMENDATION_CONFIDENCE_THRESHOLD,
                "low_confidence_candidates_seen": int(candidates_seen),
            },
        )
        return {
            "conversation_id": conversation_id,
            "turn_id": turn_id,
            "assistant_message": assistant_message,
            "response_type": "recommendation",
            "resolved_context": {
                "request_summary": message.strip(),
                "occasion": occasion,
                "live_context": live_context.model_dump(),
            },
            "filters_applied": hard_filters,
            "outfits": [],
            # Every suggestion here either (a) clarifies the request or
            # (b) pivots to catalog purchase. We deliberately omit
            # "Try a different occasion" because the user already gave us
            # an occasion; firing a new turn without clarity just hides
            # the underlying mismatch.
            "follow_up_suggestions": [
                "Show me the closest matches anyway",
                "Refine the request",
                str(catalog_upsell["cta"]),
            ],
            "metadata": metadata,
        }

    def _build_wardrobe_first_pairing_response(
        self,
        *,
        external_user_id: str,
        message: str,
        conversation_id: str,
        turn_id: str,
        channel: str,
        intent: IntentClassification,
        previous_context: Dict[str, Any],
        user_context: Any,
        live_context: LiveContext,
        conversation_memory: Dict[str, Any],
        profile_confidence: ProfileConfidence,

        target_piece: str = "",
    ) -> Dict[str, Any] | None:
        if intent.primary_intent != Intent.PAIRING_REQUEST:
            return None
        wardrobe_items = list(getattr(user_context, "wardrobe_items", []) or [])
        if not wardrobe_items:
            return None
        wardrobe_gap_analysis = self._build_wardrobe_gap_analysis(
            wardrobe_items=wardrobe_items,
            occasion=str(live_context.occasion_signal or ""),
            required_roles=["top", "bottom", "shoe"],
        )

        target_text = str(target_piece or message or "").strip().lower()
        if not target_text:
            return None

        target_item = self._find_target_wardrobe_piece(wardrobe_items=wardrobe_items, target_text=target_text)
        if target_item is None:
            return None

        pairings = self._select_wardrobe_pairings(
            wardrobe_items=wardrobe_items,
            target_item=target_item,
        )
        pairings, blocked_terms = self._filter_restricted_recommendation_items(pairings)
        if not pairings:
            return None

        target_outfit_item = self._wardrobe_item_to_outfit_item(dict(target_item, _role="anchor"))
        pairing_items = [self._wardrobe_item_to_outfit_item(item) for item in pairings]
        outfit_items = [target_outfit_item, *pairing_items]
        target_role = self._wardrobe_role_of(target_item)
        desired_catalog_roles = {
            "top": ["bottom", "shoe"],
            "outerwear": ["bottom", "shoe"],
            "bottom": ["top", "shoe"],
            "one_piece": ["shoe", "outerwear"],
            "shoe": ["top", "bottom"],
        }.get(target_role, ["top", "bottom"])
        if wardrobe_gap_analysis.get("gap_items"):
            desired_catalog_roles = _dedupe_values(
                [
                    *desired_catalog_roles,
                    *[
                        role
                        for role, count in dict(wardrobe_gap_analysis.get("counts_by_role") or {}).items()
                        if int(count or 0) == 0
                    ],
                ]
            )
        catalog_items = self._select_catalog_items(
            desired_roles=desired_catalog_roles,
            occasion=str(live_context.occasion_signal or ""),
            preferred_colors=[
                str(target_item.get("primary_color") or ""),
                *[str(item.get("primary_color") or "") for item in pairings[:2]],
            ],
            limit=2,
        )
        reasoning = f"Started with your wardrobe and paired your {str(target_item.get('title') or 'piece').strip()} with saved items that work around it."
        catalog_upsell = self._build_catalog_upsell(
            rationale="Your wardrobe already gives you workable pairings. If you want, I can also suggest catalog options to expand the look.",
            entry_intent=Intent.PAIRING_REQUEST,
        )
        outfit_card = OutfitCard(
            rank=1,
            title="Wardrobe-first pairing",
            reasoning=reasoning,
            style_note=reasoning,
            items=outfit_items,
        )
        outfit_cards = [outfit_card]
        hybrid_answer_source = "wardrobe_first_pairing"
        if catalog_items:
            outfit_cards.append(
                OutfitCard(
                    rank=2,
                    title="Catalog alternatives",
                    reasoning="If you want to expand the look, these catalog pieces push the same anchor in a sharper direction.",
                    style_note="Catalog alternatives selected to extend the same anchor piece.",
                    items=[target_outfit_item, *catalog_items],
                )
            )
            hybrid_answer_source = "wardrobe_first_pairing_hybrid"
        answer_components = self._summarize_answer_components(outfit_cards)
        recommendation_confidence = evaluate_recommendation_confidence(
            answer_mode="wardrobe_first",
            profile_confidence_score_pct=profile_confidence.analysis_confidence_pct,
            intent_confidence=float(intent.confidence),
            top_match_score=0.88,
            second_match_score=0.74 if catalog_items else 0.0,
            retrieved_product_count=len(catalog_items),
            candidate_count=len(outfit_cards),
            response_outfit_count=len(outfit_cards),
            wardrobe_items_used=len(outfit_items),
            restricted_item_exclusion_count=len(blocked_terms),
        )
        routing_metadata = {
            "primary_intent": intent.primary_intent,
            "intent_confidence": intent.confidence,
            "secondary_intents": list(intent.secondary_intents or []),
            "reason_codes": list(intent.reason_codes or []),
            "memory_sources_read": [
                "user_profile",
                "wardrobe_memory",
                "conversation_memory",
            ],
            "memory_sources_written": [
                "conversation_memory",
                "confidence_history",
            ],
        }
        metadata = self._build_response_metadata(
            channel=channel,
            intent=intent,
            profile_confidence=profile_confidence,
            extra={
                "answer_source": hybrid_answer_source,
                "answer_components": answer_components,
                "catalog_upsell": catalog_upsell,
                "catalog_alternatives": catalog_items,
                "recommendation_confidence": recommendation_confidence.model_dump(),
                "restricted_item_exclusion_count": len(blocked_terms),
                "wardrobe_gap_analysis": wardrobe_gap_analysis,
                "routing_metadata": routing_metadata,
            },
        )
        assistant_message = (
            f"I'd start with your {str(target_item.get('title') or 'piece').strip()} and pair it with "
            + ", ".join(str(item.get("title") or "your saved piece").strip() for item in pairings[:2])
            + "."
        )
        if catalog_items:
            assistant_message += " For a catalog upgrade, try " + ", ".join(
                str(item.get("title") or "a catalog piece").strip() for item in catalog_items[:2]
            ) + "."
        else:
            assistant_message += " If you want, I can also show catalog alternatives for the same piece."
        resolved_context = {
            "request_summary": message.strip(),
            "occasion": live_context.occasion_signal or "",
            "style_goal": "wardrobe_first_pairing",
            "live_context": live_context.model_dump(),
            "conversation_memory": conversation_memory,
            "intent_classification": intent.model_dump(),
            "profile_confidence": profile_confidence.model_dump(),
            "response_metadata": metadata,
            "handler": "pairing_request_wardrobe_first",
            "handler_payload": {
                "answer_source": hybrid_answer_source,
                "target_item_id": str(target_item.get("id") or ""),
                "paired_item_ids": [str(item.get("id") or "") for item in pairings],
                "catalog_item_ids": [str(item.get("product_id") or "") for item in catalog_items],
                "answer_components": answer_components,
                "catalog_upsell": catalog_upsell,
                "catalog_alternatives": catalog_items,
                "recommendation_confidence": recommendation_confidence.model_dump(),
                "restricted_item_exclusion_count": len(blocked_terms),
                "wardrobe_gap_analysis": wardrobe_gap_analysis,
                "routing_metadata": routing_metadata,
            },
            "routing_metadata": routing_metadata,
            "recommendations": [
                {
                    "candidate_id": "wardrobe-pairing-1",
                    "rank": 1,
                    "title": outfit_card.title,
                    "item_ids": [str(item.get("product_id") or "") for item in outfit_items],
                    "match_score": 0.88,
                    "reasoning": reasoning,
                },
                *(
                    [
                        {
                            "candidate_id": "catalog-pairing-1",
                            "rank": 2,
                            "title": "Catalog alternatives",
                            "item_ids": [str(item.get("product_id") or "") for item in catalog_items],
                            "match_score": 0.74,
                            "reasoning": "Catalog alternatives selected around the same anchor piece.",
                        }
                    ]
                    if catalog_items else []
                ),
            ],
            # Persist outfit cards so historical replay (loadConversation →
            # renderOutfits) re-renders them identically to the live response.
            "outfits": [card.model_dump() for card in outfit_cards],
            "channel": channel,
        }
        self.repo.finalize_turn(
            turn_id=turn_id,
            assistant_message=assistant_message,
            resolved_context=resolved_context,
        )
        self._persist_recommendation_confidence(
            external_user_id=external_user_id,
            conversation_id=conversation_id,
            turn_id=turn_id,
            channel=channel,
            primary_intent=intent.primary_intent,
            recommendation_confidence=recommendation_confidence,
            metadata_json={"answer_mode": "wardrobe_first_pairing"},
        )
        self.repo.update_conversation_context(
            conversation_id=conversation_id,
            session_context={
                **previous_context,
                "memory": conversation_memory,
                "last_live_context": live_context.model_dump(),
                "last_response_metadata": metadata,
                "last_assistant_message": assistant_message,
                "last_user_message": message,
                "last_channel": channel,
                "last_intent": intent.primary_intent,

                "consecutive_gate_blocks": 0,
                "last_recommendations": [
                    {
                        "candidate_id": "wardrobe-pairing-1",
                        "rank": 1,
                        "title": outfit_card.title,
                        "item_ids": [str(item.get("product_id") or "") for item in outfit_items],
                        "candidate_type": "wardrobe",
                        "direction_id": "wardrobe",
                        "primary_colors": _dedupe_values([item.get("primary_color") for item in outfit_items]),
                        "garment_categories": _dedupe_values([item.get("garment_category") for item in outfit_items]),
                        "garment_subtypes": _dedupe_values([item.get("garment_subtype") for item in outfit_items]),
                        "roles": _dedupe_values([item.get("role") for item in outfit_items]),
                        "occasion_fits": _dedupe_values([item.get("occasion_fit") for item in outfit_items]),
                        "formality_levels": _dedupe_values([item.get("formality_level") for item in outfit_items]),
                        "pattern_types": _dedupe_values([item.get("pattern_type") for item in outfit_items]),
                        "volume_profiles": _dedupe_values([item.get("volume_profile") for item in outfit_items]),
                        "fit_types": _dedupe_values([item.get("fit_type") for item in outfit_items]),
                        "silhouette_types": _dedupe_values([item.get("silhouette_type") for item in outfit_items]),
                    },
                    *(
                        [
                            {
                                "candidate_id": "catalog-pairing-1",
                                "rank": 2,
                                "title": "Catalog alternatives",
                                "item_ids": [str(item.get("product_id") or "") for item in catalog_items],
                                "candidate_type": "catalog",
                                "direction_id": "catalog",
                                "primary_colors": _dedupe_values([item.get("primary_color") for item in catalog_items]),
                                "garment_categories": _dedupe_values([item.get("garment_category") for item in catalog_items]),
                                "garment_subtypes": _dedupe_values([item.get("garment_subtype") for item in catalog_items]),
                                "roles": _dedupe_values([item.get("role") for item in catalog_items]),
                                "occasion_fits": _dedupe_values([item.get("occasion_fit") for item in catalog_items]),
                                "formality_levels": _dedupe_values([item.get("formality_level") for item in catalog_items]),
                                "pattern_types": _dedupe_values([item.get("pattern_type") for item in catalog_items]),
                                "volume_profiles": _dedupe_values([item.get("volume_profile") for item in catalog_items]),
                                "fit_types": _dedupe_values([item.get("fit_type") for item in catalog_items]),
                                "silhouette_types": _dedupe_values([item.get("silhouette_type") for item in catalog_items]),
                            }
                        ]
                        if catalog_items else []
                    ),
                ],
            },
        )
        self._persist_dependency_turn_event(
            external_user_id=external_user_id,
            conversation_id=conversation_id,
            turn_id=turn_id,
            channel=channel,
            primary_intent=intent.primary_intent,
            response_type="recommendation",
            metadata_json={
                "answer_source": hybrid_answer_source,
                "memory_sources_read": list(routing_metadata.get("memory_sources_read") or []),
                "memory_sources_written": list(routing_metadata.get("memory_sources_written") or []),
                "recommendation_confidence_score_pct": recommendation_confidence.score_pct,
                "wardrobe_gap_count": len(list(wardrobe_gap_analysis.get("gap_items") or [])),
                "catalog_item_count": len(catalog_items),
            },
        )
        return {
            "conversation_id": conversation_id,
            "turn_id": turn_id,
            "assistant_message": assistant_message,
            "response_type": "recommendation",
            "resolved_context": {
                "request_summary": message.strip(),
                "occasion": live_context.occasion_signal or "",
                "style_goal": "wardrobe_first_pairing",
                "profile_confidence_pct": profile_confidence.analysis_confidence_pct,
            },
            "filters_applied": {},
            "outfits": [outfit.model_dump() for outfit in outfit_cards],
            "follow_up_suggestions": ["Show me more from my wardrobe", "Show me catalog alternatives", str(catalog_upsell["cta"])],
            "metadata": metadata,
        }

    def _build_catalog_anchor_pairing_response(
        self,
        *,
        message: str,
        conversation_id: str,
        turn_id: str,
        channel: str,
        intent: IntentClassification,
        previous_context: Dict[str, Any],
        live_context: LiveContext,
        conversation_memory: Dict[str, Any],
        profile_confidence: ProfileConfidence,

        attached_item: Dict[str, Any] | None,
    ) -> Dict[str, Any] | None:
        if intent.primary_intent != Intent.PAIRING_REQUEST:
            return None
        item = dict(attached_item or {})
        if self._normalize_text_token(item.get("attachment_source")) != "catalog image":
            return None

        target_role = self._wardrobe_role_of(item)
        desired_catalog_roles = {
            "top": ["bottom", "shoe"],
            "outerwear": ["bottom", "shoe"],
            "bottom": ["top", "shoe"],
            "one_piece": ["shoe", "outerwear"],
            "shoe": ["top", "bottom"],
        }.get(target_role, ["top", "bottom"])
        catalog_items = self._select_catalog_items(
            desired_roles=desired_catalog_roles,
            occasion=str(live_context.occasion_signal or ""),
            preferred_colors=[str(item.get("primary_color") or "")],
            limit=2,
        )
        catalog_items = [
            candidate
            for candidate in catalog_items
            if self._normalize_text_token(candidate.get("title")) != self._normalize_text_token(item.get("title"))
        ][:2]
        if not catalog_items:
            return None

        anchor_item = {
            "product_id": str(item.get("id") or item.get("product_id") or "catalog-anchor"),
            "similarity": 0.0,
            "title": str(item.get("title") or "Catalog anchor"),
            "image_url": str(item.get("image_url") or ""),
            "price": str(item.get("price") or ""),
            "product_url": str(item.get("product_url") or ""),
            "garment_category": str(item.get("garment_category") or ""),
            "garment_subtype": str(item.get("garment_subtype") or ""),
            "primary_color": str(item.get("primary_color") or ""),
            "role": "anchor",
            "formality_level": str(item.get("formality_level") or ""),
            "occasion_fit": str(item.get("occasion_fit") or ""),
            "pattern_type": str(item.get("pattern_type") or ""),
            "volume_profile": str(item.get("volume_profile") or ""),
            "fit_type": str(item.get("fit_type") or ""),
            "silhouette_type": str(item.get("silhouette_type") or ""),
            "source": "catalog",
        }
        reasoning = "Built a catalog pairing around the uploaded garment so the answer completes the look instead of repeating the anchor."
        outfit_card = OutfitCard(
            rank=1,
            title="Catalog pairing around your uploaded piece",
            reasoning=reasoning,
            style_note=reasoning,
            items=[anchor_item, *catalog_items],
        )
        answer_components = self._summarize_answer_components([outfit_card])
        source_selection = self._build_source_selection(
            preferred_source="catalog",
            fulfilled_source="catalog",
        )
        recommendation_confidence = evaluate_recommendation_confidence(
            answer_mode="catalog_pipeline",
            profile_confidence_score_pct=profile_confidence.analysis_confidence_pct,
            intent_confidence=float(intent.confidence),
            top_match_score=0.86,
            second_match_score=0.72 if len(catalog_items) > 1 else 0.0,
            retrieved_product_count=len(catalog_items),
            candidate_count=1,
            response_outfit_count=1,
            wardrobe_items_used=0,
            restricted_item_exclusion_count=0,
        )
        metadata = self._build_response_metadata(
            channel=channel,
            intent=intent,
            profile_confidence=profile_confidence,
            extra={
                "answer_source": "catalog_image_pairing",
                "answer_components": answer_components,
                "source_selection": source_selection,
                "recommendation_confidence": recommendation_confidence.model_dump(),
                "anchor_source": "catalog_image",
            },
        )
        assistant_message = (
            f"I'd build around the uploaded {str(item.get('title') or 'piece').strip()} with "
            + ", ".join(str(candidate.get("title") or "a catalog piece").strip() for candidate in catalog_items)
            + "."
        )
        self.repo.finalize_turn(
            turn_id=turn_id,
            assistant_message=assistant_message,
            resolved_context={
                "request_summary": message.strip(),
                "occasion": live_context.occasion_signal or "",
                "style_goal": "catalog_image_pairing",
                "live_context": live_context.model_dump(),
                "conversation_memory": conversation_memory,
                "intent_classification": intent.model_dump(),
                "profile_confidence": profile_confidence.model_dump(),
                "response_metadata": metadata,
                "handler": "pairing_request_catalog_image",
                "handler_payload": {
                    "answer_source": "catalog_image_pairing",
                    "answer_components": answer_components,
                    "source_selection": source_selection,
                    "anchor_source": "catalog_image",
                    "anchor_item_title": str(item.get("title") or ""),
                    "catalog_item_ids": [str(candidate.get("product_id") or "") for candidate in catalog_items],
                },
                # Persist the outfit card so historical replay re-renders
                # the same card the live response showed.
                "outfits": [outfit_card.model_dump()],
                "channel": channel,
            },
        )
        self.repo.update_conversation_context(
            conversation_id=conversation_id,
            session_context={
                **previous_context,
                "memory": conversation_memory,
                "last_live_context": live_context.model_dump(),
                "last_response_metadata": metadata,
                "last_assistant_message": assistant_message,
                "last_user_message": message,
                "last_channel": channel,
                "last_intent": intent.primary_intent,

                "consecutive_gate_blocks": 0,
            },
        )
        return {
            "conversation_id": conversation_id,
            "turn_id": turn_id,
            "assistant_message": assistant_message,
            "response_type": "recommendation",
            "resolved_context": {
                "request_summary": message.strip(),
                "occasion": live_context.occasion_signal or "",
                "style_goal": "catalog_image_pairing",
                "profile_confidence_pct": profile_confidence.analysis_confidence_pct,
            },
            "filters_applied": {},
            "outfits": [outfit_card.model_dump()],
            "follow_up_suggestions": ["Show me more catalog pairings", "Use my wardrobe first"],
            "metadata": metadata,
        }

    def _find_target_wardrobe_piece(
        self,
        *,
        wardrobe_items: List[Dict[str, Any]],
        target_text: str,
    ) -> Dict[str, Any] | None:
        normalized_target = self._normalize_text_token(target_text)
        best_item: Dict[str, Any] | None = None
        best_score = -1
        for item in wardrobe_items:
            haystack = " ".join(
                [
                    str(item.get("title") or ""),
                    str(item.get("garment_category") or ""),
                    str(item.get("garment_subtype") or ""),
                    str(item.get("primary_color") or ""),
                ]
            ).lower()
            score = 0
            for token in normalized_target.split():
                if token and token in haystack:
                    score += 1
            if score > best_score:
                best_score = score
                best_item = item
        return best_item if best_score > 0 else None

    def _select_wardrobe_pairings(
        self,
        *,
        wardrobe_items: List[Dict[str, Any]],
        target_item: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        target_id = str(target_item.get("id") or "")
        target_category = self._normalize_text_token(target_item.get("garment_category") or target_item.get("garment_subtype"))
        target_occasion = self._normalize_text_token(target_item.get("occasion_fit"))

        def role_of(item: Dict[str, Any]) -> str:
            category = self._normalize_text_token(item.get("garment_category") or item.get("garment_subtype"))
            if category in {"dress", "jumpsuit", "suit"}:
                return "one_piece"
            if category in {"top", "shirt", "blouse", "blazer", "jacket", "coat", "cardigan", "outerwear"}:
                return "top"
            if category in {"bottom", "trousers", "pants", "jeans", "skirt"}:
                return "bottom"
            if category in {"shoe", "shoes", "sneaker", "heels", "loafer"}:
                return "shoe"
            return "other"

        target_role = role_of(target_item)

        def score(item: Dict[str, Any]) -> int:
            if str(item.get("id") or "") == target_id:
                return -999
            item_role = role_of(item)
            item_category = self._normalize_text_token(item.get("garment_category") or item.get("garment_subtype"))
            value = 0
            if target_role == "top" and item_role == "bottom":
                value += 4
            elif target_role == "bottom" and item_role == "top":
                value += 4
            elif target_role == "one_piece" and item_role in {"shoe", "other"}:
                value += 2
            elif item_role != target_role and item_category != target_category:
                value += 1
            if target_occasion and self._normalize_text_token(item.get("occasion_fit")) == target_occasion:
                value += 2
            return value

        ranked = sorted(
            [dict(item, _role=role_of(item), _score=score(item)) for item in wardrobe_items],
            key=lambda item: (-int(item.get("_score") or 0), str(item.get("title") or "").lower()),
        )
        return [item for item in ranked if int(item.get("_score") or 0) > 0][:2]

    @staticmethod
    def _filter_restricted_recommendation_items(items: List[Dict[str, Any]]) -> tuple[List[Dict[str, Any]], List[str]]:
        allowed: List[Dict[str, Any]] = []
        blocked_terms: List[str] = []
        for item in items:
            blocked_term = detect_restricted_record(item)
            if blocked_term:
                blocked_terms.append(blocked_term)
                continue
            allowed.append(item)
        return allowed, blocked_terms

    @staticmethod
    def _select_wardrobe_occasion_outfit(
        *,
        wardrobe_items: List[Dict[str, Any]],
        occasion: str,
    ) -> Tuple[List[Dict[str, Any]], float]:
        """Return ``(items, confidence)`` for the best wardrobe outfit for the occasion.

        ``confidence`` is normalized to [0, 1] from the per-item score.
        Outfits with a single one-piece use that item's score; multi-item
        outfits use the *minimum* item score (weakest link) so a top with
        a perfect occasion match paired with a bottom that only matches
        on formality is correctly surfaced as borderline rather than
        averaging up to "looks good".

        Why drop the empty-occasion_fit reward: previously, items with no
        ``occasion_fit`` tag scored +1 (read: "not disqualified"). That
        let untagged or differently-tagged items (e.g., festive ethnic
        wear with empty/festive tag) win for unrelated occasions like
        ``date_night``. Empty now scores 0 — the gate must be earned.
        """
        def role_of(item: Dict[str, Any]) -> str:
            category = str(item.get("garment_category") or item.get("garment_subtype") or "").strip().lower()
            if category in {"dress", "jumpsuit", "suit"}:
                return "one_piece"
            if category in {"top", "shirt", "blouse", "blazer", "jacket", "coat", "cardigan", "outerwear"}:
                return "top"
            if category in {"bottom", "trousers", "pants", "jeans", "skirt"}:
                return "bottom"
            return "other"

        def score(item: Dict[str, Any]) -> int:
            value = 0
            item_occasion = str(item.get("occasion_fit") or "").strip().lower().replace(" ", "_")
            if item_occasion == occasion:
                value += 3
            # Empty occasion_fit no longer earns a participation point —
            # it's evidence we don't have, not evidence the item fits.
            formality = str(item.get("formality_level") or "").strip().lower()
            if occasion in {"office", "work", "work_meeting"} and formality in {"business_casual", "smart_casual", "semi_formal"}:
                value += 1
            if occasion in {"wedding", "cocktail_party", "date_night"} and formality in {"smart_casual", "semi_formal", "formal"}:
                value += 1
            return value

        def _norm(raw: int) -> float:
            return max(0.0, min(float(raw) / _WARDROBE_SCORE_MAX, 1.0))

        ranked = sorted(
            [dict(item, _role=role_of(item), _score=score(item)) for item in wardrobe_items],
            key=lambda item: (-int(item.get("_score") or 0), str(item.get("title") or "").lower()),
        )
        one_piece = next((item for item in ranked if item.get("_role") == "one_piece" and int(item.get("_score") or 0) > 0), None)
        if one_piece is not None:
            return (
                [AgenticOrchestrator._wardrobe_item_to_outfit_item(one_piece)],
                _norm(int(one_piece.get("_score") or 0)),
            )

        top = next((item for item in ranked if item.get("_role") == "top" and int(item.get("_score") or 0) > 0), None)
        bottom = next(
            (item for item in ranked if item.get("_role") == "bottom" and int(item.get("_score") or 0) > 0 and item.get("id") != (top or {}).get("id")),
            None,
        )
        items: List[Dict[str, Any]] = []
        item_scores: List[int] = []
        if top is not None:
            items.append(AgenticOrchestrator._wardrobe_item_to_outfit_item(top))
            item_scores.append(int(top.get("_score") or 0))
        if bottom is not None:
            items.append(AgenticOrchestrator._wardrobe_item_to_outfit_item(bottom))
            item_scores.append(int(bottom.get("_score") or 0))
        if items:
            return items, _norm(min(item_scores))
        fallback = [item for item in ranked if int(item.get("_score") or 0) > 0][:2]
        if not fallback:
            return [], 0.0
        fallback_scores = [int(it.get("_score") or 0) for it in fallback]
        return (
            [AgenticOrchestrator._wardrobe_item_to_outfit_item(item) for item in fallback],
            _norm(min(fallback_scores)),
        )

    @staticmethod
    def _browser_safe_image_url(value: Any) -> str:
        raw = str(value or "").strip()
        if not raw:
            return ""
        normalized = raw.lower()
        if normalized.startswith(("http://", "https://", "data:", "/v1/")):
            return raw
        if raw.startswith("data/") or "/data/onboarding/images/" in raw or "onboarding/images/" in raw:
            return "/v1/onboarding/images/local?path=" + quote(raw, safe="/._-")
        return raw

    @staticmethod
    def _wardrobe_item_to_outfit_item(item: Dict[str, Any]) -> Dict[str, Any]:
        role = str(item.get("_role") or "").strip()
        metadata = dict(item.get("metadata_json") or {})
        catalog_attrs = dict(item.get("catalog_attributes") or metadata.get("catalog_attributes") or {})
        return {
            "product_id": str(item.get("id") or ""),
            "title": str(item.get("title") or ""),
            "image_url": AgenticOrchestrator._browser_safe_image_url(item.get("image_url") or item.get("image_path") or ""),
            "price": "",
            "product_url": "",
            "garment_category": str(item.get("garment_category") or ""),
            "garment_subtype": str(item.get("garment_subtype") or ""),
            "primary_color": str(item.get("primary_color") or ""),
            "role": role,
            "formality_level": str(item.get("formality_level") or ""),
            "occasion_fit": str(item.get("occasion_fit") or ""),
            "pattern_type": str(item.get("pattern_type") or ""),
            "volume_profile": str(item.get("volume_profile") or catalog_attrs.get("VolumeProfile") or ""),
            "fit_type": str(item.get("fit_type") or catalog_attrs.get("FitType") or ""),
            "silhouette_type": str(item.get("silhouette_type") or catalog_attrs.get("SilhouetteType") or ""),
            "source": "wardrobe",
        }

    _WARDROBE_MIN_PER_ROLE = 2
    _WARDROBE_REQUIRED_ROLES = ("top", "bottom", "one_piece")

    def _wardrobe_role_counts(
        self, wardrobe_items: List[Dict[str, Any]]
    ) -> Dict[str, int]:
        counts: Dict[str, int] = {role: 0 for role in self._WARDROBE_REQUIRED_ROLES}
        for item in wardrobe_items or []:
            role = self._wardrobe_role_of(item)
            if role in counts:
                counts[role] += 1
        return counts

    def _wardrobe_meets_minimum_coverage(
        self, wardrobe_items: List[Dict[str, Any]]
    ) -> tuple[bool, Dict[str, int]]:
        counts = self._wardrobe_role_counts(wardrobe_items)
        sufficient = all(
            counts[role] >= self._WARDROBE_MIN_PER_ROLE
            for role in self._WARDROBE_REQUIRED_ROLES
        )
        return sufficient, counts

    def _wardrobe_role_of(self, item: Dict[str, Any]) -> str:
        category = self._normalize_text_token(item.get("garment_category") or item.get("garment_subtype"))
        if category in {"dress", "jumpsuit", "suit"}:
            return "one_piece"
        if category in {"top", "shirt", "blouse", "tee", "t shirt", "tshirt", "sweater", "knitwear"}:
            return "top"
        if category in {"blazer", "jacket", "coat", "cardigan", "outerwear", "overshirt"}:
            return "outerwear"
        if category in {"bottom", "trousers", "pants", "jeans", "skirt", "shorts"}:
            return "bottom"
        if category in {"shoe", "shoes", "sneaker", "heels", "loafer", "boot", "sandal"}:
            return "shoe"
        return "other"

    def _build_wardrobe_gap_analysis(
        self,
        *,
        wardrobe_items: List[Dict[str, Any]],
        occasion: str = "",
        required_roles: List[str] | None = None,
    ) -> Dict[str, Any]:
        role_counts = {"top": 0, "bottom": 0, "shoe": 0, "outerwear": 0, "one_piece": 0}
        occasion_matches = 0
        normalized_occasion = self._normalize_text_token(occasion)
        for item in wardrobe_items:
            role = self._wardrobe_role_of(item)
            if role in role_counts:
                role_counts[role] += 1
            occasion_fit = self._normalize_text_token(item.get("occasion_fit"))
            if normalized_occasion and occasion_fit and normalized_occasion in occasion_fit:
                occasion_matches += 1

        required = [role for role in list(required_roles or []) if role in role_counts]
        role_labels = {
            "top": "an easy top",
            "bottom": "a versatile bottom",
            "shoe": "a flexible shoe option",
            "outerwear": "a layering piece",
            "one_piece": "a one-piece look",
        }
        gap_items = [role_labels[role] for role in required if role_counts.get(role, 0) == 0]
        if normalized_occasion and occasion_matches == 0:
            gap_items.append(f"a stronger {normalized_occasion.replace('_', ' ')} option")

        completeness_pct = min(
            100,
            role_counts["top"] * 22
            + role_counts["bottom"] * 22
            + role_counts["shoe"] * 18
            + role_counts["outerwear"] * 14
            + role_counts["one_piece"] * 12,
        )
        summary = "Wardrobe coverage is strong."
        if gap_items:
            summary = "Main gaps: " + ", ".join(gap_items[:3]) + "."
        return {
            "completeness_score_pct": int(completeness_pct),
            "occasion": normalized_occasion,
            "occasion_item_count": occasion_matches,
            "counts_by_role": role_counts,
            "gap_items": gap_items[:4],
            "summary": summary,
        }

    @staticmethod
    def _build_conversation_history(
        previous_context: Dict[str, Any],
        current_message: str,
    ) -> List[Dict[str, str]]:
        """Build conversation history from prior turns for the architect."""
        history: List[Dict[str, str]] = []
        prev_user = str(previous_context.get("last_user_message") or "").strip()
        prev_assistant = str(previous_context.get("last_assistant_message") or "").strip()
        if prev_user:
            history.append({"role": "user", "content": prev_user})
        if prev_assistant:
            history.append({"role": "assistant", "content": prev_assistant})
        return history

    @staticmethod
    def _flatten_applied_filters(retrieved_sets: List[Any]) -> Dict[str, str]:
        merged: Dict[str, str] = {}
        for retrieved_set in retrieved_sets:
            for key, value in dict(retrieved_set.applied_filters or {}).items():
                merged[key] = value
        return merged

    @staticmethod
    def _build_turn_artifacts(
        *,
        message: str,
        live_context: Any,
        conversation_memory: Dict[str, Any],
        plan: Dict[str, Any],
        retrieved_sets: List[Any],
        evaluated: List[Any],
        candidates: List[Any],
        response_metadata: Dict[str, Any],
        intent_classification: Dict[str, Any] | None = None,
        profile_confidence: Dict[str, Any] | None = None,

        channel: str = "web",
        outfits: List[Any] | None = None,
    ) -> Dict[str, Any]:
        retrieval = []
        for retrieved_set in retrieved_sets:
            retrieval.append(
                {
                    "direction_id": retrieved_set.direction_id,
                    "query_id": retrieved_set.query_id,
                    "role": retrieved_set.role,
                    "applied_filters": retrieved_set.applied_filters,
                    "product_ids": [product.product_id for product in retrieved_set.products],
                }
            )
        candidate_summaries = []
        for candidate in candidates[:20]:
            candidate_summaries.append(
                {
                    "candidate_id": candidate.candidate_id,
                    "direction_id": candidate.direction_id,
                    "candidate_type": candidate.candidate_type,
                    "fashion_score": candidate.fashion_score,
                    # R7 (May 5 2026): six 1/2/3 sub-scores. Pairing
                    # is None for complete (single-item) outfits.
                    "occasion_fit": candidate.occasion_fit,
                    "body_harmony": candidate.body_harmony,
                    "color_harmony": candidate.color_harmony,
                    "pairing": candidate.pairing,
                    "formality": candidate.formality,
                    "statement": candidate.statement,
                    "composer_rationale": candidate.composer_rationale,
                    "rater_rationale": candidate.rater_rationale,
                    "unsuitable": candidate.unsuitable,
                    "item_ids": [str(item.get("product_id") or "") for item in candidate.items],
                }
            )
        return {
            "request_summary": message.strip(),
            "channel": channel,
            "occasion": live_context.occasion_signal or "",
            "style_goal": " ".join(live_context.specific_needs) if live_context.specific_needs else "",
            "live_context": live_context.model_dump(),
            "conversation_memory": conversation_memory,
            "intent_classification": intent_classification or {},
            "profile_confidence": profile_confidence or {},
            "plan": plan,
            "retrieval": retrieval,
            "assembled_candidates": candidate_summaries,
            "recommendations": [
                {
                    "candidate_id": row.candidate_id,
                    "rank": row.rank,
                    "title": row.title,
                    "item_ids": row.item_ids,
                    "match_score": row.match_score,
                    "reasoning": row.reasoning,
                    "body_harmony_pct": row.body_harmony_pct,
                    "color_suitability_pct": row.color_suitability_pct,
                    "occasion_pct": row.occasion_pct,
                    # R7 (May 5 2026): renamed from inter_item_coherence_pct;
                    # plus new formality_pct and statement_pct axes.
                    "pairing_pct": row.pairing_pct,
                    "formality_pct": row.formality_pct,
                    "statement_pct": row.statement_pct,
                    "fashion_score_pct": row.fashion_score_pct,
                }
                for row in evaluated
            ],
            "response_metadata": response_metadata,
            "profile_confidence_pct": int(profile_confidence.get("score_pct", 0)) if isinstance(profile_confidence, dict) else int(getattr(profile_confidence, "score_pct", 0)),
            "outfits": [o.model_dump() if hasattr(o, "model_dump") else dict(o) for o in (outfits or [])],
        }

    @staticmethod
    def _build_response_metadata(
        *,
        channel: str,
        intent: IntentClassification,
        profile_confidence: ProfileConfidence,
        extra: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "channel": channel,
            "primary_intent": intent.primary_intent,
            "intent_confidence": intent.confidence,
            "secondary_intents": list(intent.secondary_intents or []),
            "intent_reason_codes": list(intent.reason_codes or []),
            "profile_confidence": profile_confidence.model_dump(),
        }
        if extra:
            payload.update(extra)
        return payload

    # ------------------------------------------------------------------
    # Turn trace persistence
    # ------------------------------------------------------------------

    def _persist_trace(self, trace: TurnTraceBuilder) -> None:
        """Persist the accumulated per-turn trace. Best-effort: failures
        here must never block the response to the user. Idempotent —
        callable multiple times (e.g. once on the happy path and again
        from a finally block) without producing duplicate rows."""
        if getattr(trace, "_persisted", False):
            return
        try:
            self.repo.insert_turn_trace(**trace.build())
            trace._persisted = True  # type: ignore[attr-defined]
        except Exception:
            _log.warning("Failed to persist turn trace", exc_info=True)

    # ------------------------------------------------------------------
    # Copilot Planner action handlers
    # ------------------------------------------------------------------

    def _handle_direct_response(
        self,
        *,
        plan_result: CopilotPlanResult,
        intent: IntentClassification,
        conversation_id: str,
        turn_id: str,
        channel: str,
        external_user_id: str,
        message: str,
        previous_context: Dict[str, Any],
        profile_confidence: ProfileConfidence,

    ) -> Dict[str, Any]:
        if intent.primary_intent == Intent.STYLE_DISCOVERY:
            return self._handle_style_discovery(
                plan_result=plan_result,
                intent=intent,
                conversation_id=conversation_id,
                turn_id=turn_id,
                channel=channel,
                external_user_id=external_user_id,
                message=message,
                previous_context=previous_context,
                profile_confidence=profile_confidence,

            )
        if intent.primary_intent == Intent.EXPLANATION_REQUEST:
            return self._handle_explanation_request(
                plan_result=plan_result,
                intent=intent,
                conversation_id=conversation_id,
                turn_id=turn_id,
                channel=channel,
                external_user_id=external_user_id,
                message=message,
                previous_context=previous_context,
                profile_confidence=profile_confidence,

            )
        metadata = self._build_response_metadata(
            channel=channel,
            intent=intent,
            profile_confidence=profile_confidence,
            extra={"answer_source": "copilot_planner"},
        )
        self.repo.finalize_turn(
            turn_id=turn_id,
            assistant_message=plan_result.assistant_message,
            resolved_context={
                "request_summary": message.strip(),
                "intent_classification": intent.model_dump(),
                "profile_confidence": profile_confidence.model_dump(),
                "response_metadata": metadata,
                "handler": "copilot_planner_direct",
                "channel": channel,
            },
        )
        self.repo.update_conversation_context(
            conversation_id=conversation_id,
            session_context={
                **previous_context,
                "last_user_message": message,
                "last_assistant_message": plan_result.assistant_message,
                "last_channel": channel,
                "last_intent": plan_result.intent,

                "last_response_metadata": metadata,
            },
        )
        self._persist_dependency_turn_event(
            external_user_id=external_user_id,
            conversation_id=conversation_id,
            turn_id=turn_id,
            channel=channel,
            primary_intent=plan_result.intent,
            response_type="recommendation",
            metadata_json={"answer_source": "copilot_planner"},
        )
        return {
            "conversation_id": conversation_id,
            "turn_id": turn_id,
            "assistant_message": plan_result.assistant_message,
            "response_type": "recommendation",
            "resolved_context": {
                "request_summary": message.strip(),
                "occasion": str(plan_result.resolved_context.occasion_signal or ""),
                "style_goal": plan_result.resolved_context.style_goal,
            },
            "filters_applied": {},
            "outfits": [],
            "follow_up_suggestions": plan_result.follow_up_suggestions[:5],
            "metadata": metadata,
        }

    @staticmethod
    def _profile_value(payload: Dict[str, Any], key: str) -> str:
        value = payload.get(key)
        if isinstance(value, dict):
            return str(value.get("value") or "").strip()
        return str(value or "").strip()

    _COLOR_KEYWORDS = frozenset((
        "color", "colour", "colors", "colours", "palette", "hue", "shade", "tone",
        "black", "white", "navy", "red", "blue", "green", "olive", "rust",
        "cream", "beige", "brown", "burgundy", "maroon", "camel", "tan",
        "grey", "gray", "pink", "orange", "yellow", "purple", "teal",
        "autumn", "spring", "summer", "winter",
    ))

    def _detect_style_advice_topic(self, *, message: str, style_goal: str) -> str:
        normalized = self._normalize_text_token(message)
        goal = self._normalize_text_token(style_goal)
        if "collar" in normalized:
            return "collar"
        if "neckline" in normalized or "neck line" in normalized:
            return "neckline"
        if "pattern" in normalized or "print" in normalized:
            return "pattern"
        if "silhouette" in normalized or "cut" in normalized or "shape" in normalized:
            return "silhouette"
        if "archetype" in normalized or "style type" in normalized:
            return "archetype"
        if "color" in normalized or "colour" in normalized or goal == "color direction":
            return "color"
        if any(kw in normalized for kw in self._COLOR_KEYWORDS):
            return "color"
        if "neckline" in goal:
            return "neckline"
        return "general"

    _COOL_NEUTRAL_COLORS = frozenset(("black", "white", "grey", "gray", "charcoal", "silver"))
    _WARM_NEUTRAL_COLORS = frozenset(("cream", "beige", "camel", "tan", "ivory", "khaki", "brown"))

    def _build_style_advice_response(
        self,
        *,
        topic: str,
        user_message: str = "",
        seasonal: str,
        contrast: str,
        frame: str,
        height: str,
        body_shape: str,
        primary: str,
        secondary: str,
        profile_confidence: ProfileConfidence,
    ) -> tuple[str, List[str]]:
        evidence: List[str] = []
        if seasonal:
            evidence.append(f"seasonal:{seasonal}")
        if contrast:
            evidence.append(f"contrast:{contrast}")
        if frame:
            evidence.append(f"frame:{frame}")
        if height:
            evidence.append(f"height:{height}")
        if body_shape:
            evidence.append(f"body_shape:{body_shape}")
        if primary:
            evidence.append(f"primary_archetype:{primary}")
        if secondary:
            evidence.append(f"secondary_archetype:{secondary}")

        season_lower = seasonal.lower()
        contrast_lower = contrast.lower()
        frame_lower = frame.lower()
        height_lower = height.lower()
        body_lower = body_shape.lower()
        primary_lower = primary.lower()
        secondary_lower = secondary.lower()

        msg_lower = self._normalize_text_token(user_message)
        mentioned_colors = [kw for kw in self._COLOR_KEYWORDS if kw in msg_lower and kw not in {
            "color", "colour", "colors", "colours", "palette", "hue", "shade", "tone",
            "autumn", "spring", "summer", "winter",
        }]

        parts: List[str] = []
        if topic == "color":
            is_warm_season = season_lower in {"spring", "autumn"}
            if mentioned_colors:
                mc = mentioned_colors[0]
                is_cool_neutral = mc in self._COOL_NEUTRAL_COLORS
                if seasonal and is_warm_season and is_cool_neutral:
                    parts.append(
                        f"{mc.title()} isn't a natural first choice for your {seasonal} palette, but you can absolutely make it work."
                        f" Ground it with warm companions — pair {mc} with olive, rust, warm brown, deep camel, or forest green"
                        f" so the overall outfit still reads warm."
                    )
                    parts.append(
                        f"Keep {mc} to one anchor piece (like a trouser or jacket) rather than head-to-toe,"
                        f" and let your {seasonal} warmth come through in the other layers, accessories, or shoes."
                    )
                elif seasonal and not is_warm_season and mc in self._WARM_NEUTRAL_COLORS:
                    parts.append(
                        f"{mc.title()} runs warm for your {seasonal} palette."
                        f" If you love it, pair it with cool anchors like charcoal, navy, or icy blue"
                        f" to keep the overall balance in your zone."
                    )
                else:
                    if seasonal:
                        parts.append(
                            f"{mc.title()} can work within your {seasonal} palette."
                            f" Lean into your strongest companion shades to build the outfit around it."
                        )
            elif seasonal:
                if is_warm_season:
                    parts.append(f"For your {seasonal} palette, rich warm shades like olive, camel, rust, cream, and warm navy will usually look strongest.")
                else:
                    parts.append(f"For your {seasonal} palette, cooler tones like charcoal, true navy, berry, icy blue, and crisp white will usually look strongest.")
            if contrast:
                if "high" in contrast_lower:
                    parts.append("Because your contrast is high, keep some clear light-dark separation rather than washing everything into one mid-tone blend.")
                elif "low" in contrast_lower:
                    parts.append("Because your contrast is lower, tonal dressing and blended palettes will usually look more polished than sharp oppositions.")
            if not mentioned_colors:
                parts.append("Avoid colors that fight that direction, especially muddy cools on a warm palette or harsh neon brights that overpower your natural coloring.")
        elif topic == "collar":
            parts.append("The safest collar direction for you is an open, elongated shape rather than a tight closed neck.")
            if body_lower:
                parts.append(f"Your {body_lower} shape benefits from keeping the neckline and collar line clean instead of visually crowding the bust or shoulder area.")
            if body_lower == "hourglass" or "balanced" in frame_lower:
                parts.append("With your balanced proportions, soft point collars, open camp collars, and slightly extended shirt collars keep the line clean without making the top half look crowded.")
            if "tall" in height_lower:
                parts.append("Your taller vertical line can also handle a slightly deeper opening, so avoid collars that sit too high and boxy unless the rest of the outfit is very streamlined.")
            parts.append("I would avoid very tiny collars or overly stiff short collars because they can look fussy against your profile.")
        elif topic == "neckline":
            parts.append("Necklines that open the chest a little will usually work better for you than very high, closed necklines.")
            if body_lower == "hourglass":
                parts.append("For your hourglass balance, soft V-necks, open square necklines, and gentle scoop shapes usually keep the waist-to-shoulder balance elegant.")
            if primary_lower == "classic":
                parts.append("Keep the neckline clean and structured rather than overly dramatic, because your classic side reads best with polished, deliberate lines.")
            parts.append("I would be more careful with very tight crew necks or bulky mock necks if the rest of the silhouette is also heavy.")
        elif topic == "pattern":
            if "high" in contrast_lower:
                parts.append("Patterns with clear definition will usually suit you better than blurry or washed-out motifs.")
            else:
                parts.append("Patterns with softer contrast and cleaner spacing will usually suit you better than aggressive high-contrast prints.")
            if "balanced" in frame_lower:
                parts.append("Because your frame reads balanced, medium-scale patterns are the safest place to start rather than tiny busy prints or oversized graphics.")
            if primary_lower == "classic" and secondary_lower == "romantic":
                parts.append("Because your style blend is classic with romantic softness, the strongest pattern lane is refined structure with softness: clean stripes, restrained geometrics, subtle florals, or elegant tonal motifs.")
            parts.append("I would avoid chaotic mixed prints unless you deliberately want the outfit to lead before you do.")
        elif topic == "silhouette":
            parts.append("Your best silhouette direction is shape with control rather than boxiness.")
            if body_lower == "hourglass":
                parts.append("Because you have an hourglass base, waist definition, clean shoulder lines, and gently elongated shapes will usually do more for you than straight blocky cuts.")
            if "tall" in height_lower:
                parts.append("Your height can carry long lines well, so columns, long blazers, and tailored wide-leg shapes can work if the waist or torso still feels intentional.")
            parts.append("I would be careful with oversized boxy silhouettes that hide structure everywhere at once.")
        elif topic == "archetype":
            # May 2026: archetype dropped as a stored field. The user
            # might still ask "which archetype fits me?" — ground the
            # answer in the deterministic body+palette+frame signals
            # that ACTUALLY drive what suits them, plus a note that
            # sharper direction comes from chat ("tell me 'something
            # edgy' or 'old-money classic' and I'll bias accordingly").
            if seasonal:
                parts.append(f"Your {seasonal} palette and {body_shape or 'frame'} are your strongest signals — the most flattering directions sit where those line up.")
            elif body_shape:
                parts.append(f"Your {body_shape} frame is the strongest signal for what reads well — silhouette and proportion drive the directions that suit you.")
            else:
                # Both seasonal + body_shape empty (incomplete profile)
                # — drop the possessive ("Your" → bare statement) so we
                # don't promise per-user analysis we haven't done. Reads
                # as a generic theory line until the profile fills in.
                parts.append("Body proportions and coloring are the strongest signals for what direction reads well on you.")
            parts.append("If you have a specific direction in mind — minimalist, edgy, romantic, old-money classic — tell me in chat and I will tune the recommendations to that.")
        else:
            parts.append("Your profile points toward polished structure, controlled contrast, and intentional lines rather than random trend-driven choices.")
            if seasonal:
                parts.append(f"Color-wise, keep working with your {seasonal} direction.")

        if profile_confidence.analysis_confidence_pct >= 85:
            parts.append("I’m fairly confident in this because your profile evidence is strong.")
        elif profile_confidence.analysis_confidence_pct >= 65:
            parts.append("This is a solid read, but it would sharpen further with a bit more profile evidence.")
        else:
            parts.append("This is a directional read for now, and it may sharpen as I learn more about your profile.")
        return " ".join(parts).strip(), evidence

    def _handle_style_discovery(
        self,
        *,
        plan_result: CopilotPlanResult,
        intent: IntentClassification,
        conversation_id: str,
        turn_id: str,
        channel: str,
        external_user_id: str,
        message: str,
        previous_context: Dict[str, Any],
        profile_confidence: ProfileConfidence,

    ) -> Dict[str, Any]:
        analysis_status = self.onboarding_gateway.get_analysis_status(external_user_id) or {}
        profile = dict(analysis_status.get("profile") or {})
        attributes = dict(analysis_status.get("attributes") or {})
        derived = dict(analysis_status.get("derived_interpretations") or {})
        style_preference = dict(profile.get("style_preference") or {})

        seasonal = self._profile_value(derived, "SeasonalColorGroup")
        contrast = self._profile_value(derived, "ContrastLevel")
        frame = self._profile_value(derived, "FrameStructure")
        height = self._profile_value(derived, "HeightCategory")
        body_shape = self._profile_value(attributes, "BodyShape")
        # archetype dropped May 2026; advisor grounds in body+palette+chat
        primary = ""
        secondary = ""
        advice_topic = self._detect_style_advice_topic(
            message=message,
            style_goal=plan_result.resolved_context.style_goal,
        )

        # Phase 12C: layered routing.
        # - Topical questions (collar, neckline, pattern, silhouette,
        #   archetype, color) use the deterministic, evidence-backed
        #   profile-grounded helper from Phase 11.
        # - Open-ended discovery ("general") delegates to the new
        #   StyleAdvisorAgent which generates LLM-backed advice using the
        #   four thinking directions.
        advisor_used = False
        advisor_payload: Dict[str, Any] | None = None
        if advice_topic == "general":
            try:
                # Build a duck-typed advisor context from the data the
                # handler already loaded. The advisor reads via getattr on
                # derived_interpretations / style_preference / analysis_attributes.
                from types import SimpleNamespace
                advisor_ctx = SimpleNamespace(
                    gender=str(profile.get("gender") or ""),
                    derived_interpretations=derived,
                    style_preference=style_preference,
                    analysis_attributes=attributes,
                )
                style_advice = self.style_advisor.advise(
                    mode="discovery",
                    query=message,
                    user_context=advisor_ctx,
                    plan_resolved_context=plan_result.resolved_context,
                    plan_action_parameters=plan_result.action_parameters,
                    conversation_memory=dict(previous_context.get("memory") or {}),
                    profile_confidence_pct=int(profile_confidence.analysis_confidence_pct),
                )
                assistant_message = style_advice.render_assistant_message()
                advisor_used = True
                advisor_payload = style_advice.to_dict()
                evidence: List[str] = list(style_advice.cited_attributes)
            except Exception as exc:
                _log.warning("StyleAdvisorAgent failed; falling back to deterministic helper: %s", exc, exc_info=True)
                assistant_message, evidence = self._build_style_advice_response(
                    topic=advice_topic,
                    user_message=message,
                    seasonal=seasonal,
                    contrast=contrast,
                    frame=frame,
                    height=height,
                    body_shape=body_shape,
                    primary=primary,
                    secondary=secondary,
                    profile_confidence=profile_confidence,
                )
        else:
            assistant_message, evidence = self._build_style_advice_response(
                topic=advice_topic,
                user_message=message,
                seasonal=seasonal,
                contrast=contrast,
                frame=frame,
                height=height,
                body_shape=body_shape,
                primary=primary,
                secondary=secondary,
                profile_confidence=profile_confidence,
            )
        assistant_message = assistant_message or plan_result.assistant_message
        metadata = self._build_response_metadata(
            channel=channel,
            intent=intent,
            profile_confidence=profile_confidence,
            extra={
                "answer_source": (
                    "style_advisor_agent" if advisor_used else "style_discovery_handler"
                ),
                "style_discovery": {
                    "advice_topic": advice_topic,
                    "evidence": evidence,
                    "seasonal_color_group": seasonal,
                    "contrast_level": contrast,
                    "frame_structure": frame,
                    "height_category": height,
                    "body_shape": body_shape,
                    "advisor_used": advisor_used,
                    "advisor_payload": advisor_payload,
                },
            },
        )
        self.repo.finalize_turn(
            turn_id=turn_id,
            assistant_message=assistant_message,
            resolved_context={
                "request_summary": message.strip(),
                "intent_classification": intent.model_dump(),
                "profile_confidence": profile_confidence.model_dump(),

                "response_metadata": metadata,
                "handler": Intent.STYLE_DISCOVERY,
                "channel": channel,
            },
        )
        self.repo.update_conversation_context(
            conversation_id=conversation_id,
            session_context={
                **previous_context,
                "last_user_message": message,
                "last_assistant_message": assistant_message,
                "last_channel": channel,
                "last_intent": plan_result.intent,

                "last_response_metadata": metadata,
            },
        )
        self._persist_dependency_turn_event(
            external_user_id=external_user_id,
            conversation_id=conversation_id,
            turn_id=turn_id,
            channel=channel,
            primary_intent=plan_result.intent,
            response_type="recommendation",
            metadata_json={"answer_source": "style_discovery_handler"},
        )
        return {
            "conversation_id": conversation_id,
            "turn_id": turn_id,
            "assistant_message": assistant_message,
            "response_type": "recommendation",
            "resolved_context": {
                "request_summary": message.strip(),
                "occasion": str(plan_result.resolved_context.occasion_signal or ""),
                "style_goal": plan_result.resolved_context.style_goal or "style_discovery",
            },
            "filters_applied": {},
            "outfits": [],
            "follow_up_suggestions": plan_result.follow_up_suggestions[:5],
            "metadata": metadata,
        }

    def _handle_explanation_request(
        self,
        *,
        plan_result: CopilotPlanResult,
        intent: IntentClassification,
        conversation_id: str,
        turn_id: str,
        channel: str,
        external_user_id: str,
        message: str,
        previous_context: Dict[str, Any],
        profile_confidence: ProfileConfidence,

    ) -> Dict[str, Any]:
        previous_recommendations = list(previous_context.get("last_recommendations") or [])
        response_metadata = dict(previous_context.get("last_response_metadata") or {})
        target = dict(previous_recommendations[0] if previous_recommendations else {})
        title = str(target.get("title") or "that recommendation").strip()
        colors = [str(v).strip() for v in list(target.get("primary_colors") or []) if str(v).strip()]
        categories = [str(v).strip() for v in list(target.get("garment_categories") or []) if str(v).strip()]
        occasion_fits = [str(v).strip().replace("_", " ") for v in list(target.get("occasion_fits") or []) if str(v).strip()]
        # R2 (PR #65): the rater_rationale and composer_rationale are now
        # persisted on each rec summary by _build_recommendation_summaries.
        # If they're missing (older session pre-R2), fall back to empty —
        # the advisor then leans on the legacy attribute fields.
        rater_rationale = str(target.get("rater_rationale") or "").strip()
        composer_rationale = str(target.get("composer_rationale") or "").strip()
        # PR #71 review feedback: pass the four-dim archetype_scores
        # through so the advisor can ground explanations in the actual
        # numbers ("body harmony scored 88, color was the weak axis at
        # 64"). Defaults to {} on pre-R2 sessions; the advisor handles
        # an empty dict gracefully.
        archetype_scores = target.get("archetype_scores") or {}
        confidence_payload = dict(response_metadata.get("recommendation_confidence") or {})
        confidence_explanation = [str(v).strip() for v in list(confidence_payload.get("explanation") or []) if str(v).strip()]
        confidence_band = str(confidence_payload.get("confidence_band") or "").strip()

        # Phase 12C: build the deterministic explanation as a baseline, then
        # try the StyleAdvisorAgent for a richer response. The advisor
        # receives the actual prior-turn recommendation summary so it can
        # reason against real data, not invented context. If the advisor
        # fails or has nothing to work with (no previous recommendation),
        # fall back to the deterministic summary.
        explanation_parts: List[str] = []
        if title and title != "that recommendation":
            explanation_parts.append(f"I picked {title} because it matched the strongest signals in your profile and request.")
        if colors or categories:
            detail_bits = []
            if colors:
                detail_bits.append("the color direction " + ", ".join(colors[:2]))
            if categories:
                detail_bits.append("the garment mix " + ", ".join(categories[:2]))
            explanation_parts.append("The fit came from " + " and ".join(detail_bits) + ".")
        if occasion_fits:
            explanation_parts.append(f"It also lined up with the occasion signal around {occasion_fits[0]}.")
        if confidence_explanation:
            explanation_parts.append("Confidence-wise, " + " ".join(confidence_explanation[:2]))
        elif confidence_band:
            explanation_parts.append(f"My confidence on that answer was {confidence_band.lower()}.")
        deterministic_message = " ".join(part for part in explanation_parts if part).strip()

        advisor_used = False
        advisor_payload: Dict[str, Any] | None = None
        assistant_message = deterministic_message
        if previous_recommendations:
            try:
                analysis_status = self.onboarding_gateway.get_analysis_status(external_user_id) or {}
                profile = dict(analysis_status.get("profile") or {})
                from types import SimpleNamespace
                advisor_ctx = SimpleNamespace(
                    gender=str(profile.get("gender") or ""),
                    derived_interpretations=dict(analysis_status.get("derived_interpretations") or {}),
                    style_preference=dict(profile.get("style_preference") or {}),
                    analysis_attributes=dict(analysis_status.get("attributes") or {}),
                )
                style_advice = self.style_advisor.advise(
                    mode="explanation",
                    query=message,
                    user_context=advisor_ctx,
                    plan_resolved_context=plan_result.resolved_context,
                    plan_action_parameters=plan_result.action_parameters,
                    conversation_memory=dict(previous_context.get("memory") or {}),
                    previous_recommendation_focus={
                        "title": title,
                        "primary_colors": colors,
                        "garment_categories": categories,
                        "occasion_fits": occasion_fits,
                        "recommendation_confidence_band": confidence_band,
                        "recommendation_confidence_explanation": confidence_explanation,
                        # R2 (PR #65): real stylist rationales — when
                        # populated, the advisor should quote / paraphrase
                        # rather than fabricate. archetype_scores added
                        # in PR #71 review feedback so the advisor can
                        # cite specific dimension numbers.
                        "archetype_scores": archetype_scores,
                        "rater_rationale": rater_rationale,
                        "composer_rationale": composer_rationale,
                    },
                    profile_confidence_pct=int(profile_confidence.analysis_confidence_pct),
                )
                rendered = style_advice.render_assistant_message()
                if rendered:
                    assistant_message = rendered
                    advisor_used = True
                    advisor_payload = style_advice.to_dict()
            except Exception as exc:
                _log.warning(
                    "StyleAdvisorAgent failed for explanation_request; using deterministic summary: %s",
                    exc,
                    exc_info=True,
                )

        if not assistant_message:
            assistant_message = (
                "It was the strongest match among the options available at the time."
                if not previous_recommendations
                else plan_result.assistant_message
            )

        metadata = self._build_response_metadata(
            channel=channel,
            intent=intent,
            profile_confidence=profile_confidence,
            extra={
                "answer_source": (
                    "style_advisor_agent" if advisor_used else "explanation_handler"
                ),
                "explanation": {
                    "target_title": title,
                    "target_colors": colors,
                    "target_categories": categories,
                    "target_occasions": occasion_fits,
                    "recommendation_confidence_band": confidence_band,
                    "advisor_used": advisor_used,
                    "advisor_payload": advisor_payload,
                },
            },
        )
        self.repo.finalize_turn(
            turn_id=turn_id,
            assistant_message=assistant_message,
            resolved_context={
                "request_summary": message.strip(),
                "intent_classification": intent.model_dump(),
                "profile_confidence": profile_confidence.model_dump(),
                "response_metadata": metadata,
                "handler": Intent.EXPLANATION_REQUEST,
                "channel": channel,
            },
        )
        self.repo.update_conversation_context(
            conversation_id=conversation_id,
            session_context={
                **previous_context,
                "last_user_message": message,
                "last_assistant_message": assistant_message,
                "last_channel": channel,
                "last_intent": plan_result.intent,

                "last_response_metadata": metadata,
            },
        )
        self._persist_dependency_turn_event(
            external_user_id=external_user_id,
            conversation_id=conversation_id,
            turn_id=turn_id,
            channel=channel,
            primary_intent=plan_result.intent,
            response_type="recommendation",
            metadata_json={"answer_source": "explanation_handler"},
        )
        return {
            "conversation_id": conversation_id,
            "turn_id": turn_id,
            "assistant_message": assistant_message,
            "response_type": "recommendation",
            "resolved_context": {
                "request_summary": message.strip(),
                "occasion": str(plan_result.resolved_context.occasion_signal or ""),
                "style_goal": plan_result.resolved_context.style_goal or "explanation",
            },
            "filters_applied": {},
            "outfits": [],
            "follow_up_suggestions": plan_result.follow_up_suggestions[:5],
            "metadata": metadata,
        }

    def _handle_clarification(
        self,
        *,
        plan_result: CopilotPlanResult,
        intent: IntentClassification,
        conversation_id: str,
        turn_id: str,
        channel: str,
        external_user_id: str,
        message: str,
        previous_context: Dict[str, Any],
        profile_confidence: ProfileConfidence,

    ) -> Dict[str, Any]:
        consecutive_blocks = int(previous_context.get("consecutive_gate_blocks", 0))
        metadata = self._build_response_metadata(
            channel=channel,
            intent=intent,
            profile_confidence=profile_confidence,
            extra={"gate_blocked": True, "answer_source": "copilot_planner"},
        )
        self.repo.finalize_turn(
            turn_id=turn_id,
            assistant_message=plan_result.assistant_message,
            resolved_context={
                "request_summary": message.strip(),
                "gate_blocked": True,
                "intent_classification": intent.model_dump(),
                "profile_confidence": profile_confidence.model_dump(),
                "response_metadata": metadata,
                "channel": channel,
            },
        )
        self.repo.update_conversation_context(
            conversation_id=conversation_id,
            session_context={
                **previous_context,
                "consecutive_gate_blocks": consecutive_blocks + 1,
                "last_user_message": message,
                "last_assistant_message": plan_result.assistant_message,
                "last_channel": channel,
                "last_intent": plan_result.intent,

            },
        )
        self._persist_dependency_turn_event(
            external_user_id=external_user_id,
            conversation_id=conversation_id,
            turn_id=turn_id,
            channel=channel,
            primary_intent=plan_result.intent,
            response_type="clarification",
            metadata_json={"gate_blocked": True, "answer_source": "copilot_planner"},
        )
        return {
            "conversation_id": conversation_id,
            "turn_id": turn_id,
            "assistant_message": plan_result.assistant_message,
            "response_type": "clarification",
            "resolved_context": {
                "request_summary": message.strip(),
            },
            "filters_applied": {},
            "outfits": [],
            "follow_up_suggestions": plan_result.follow_up_suggestions[:5],
            "metadata": metadata,
        }

    def _handle_planner_pipeline(
        self,
        *,
        plan_result: CopilotPlanResult,
        intent: IntentClassification,
        conversation_id: str,
        turn_id: str,
        channel: str,
        external_user_id: str,
        message: str,
        previous_context: Dict[str, Any],
        user_context: Any,
        conversation_history: List[Dict[str, str]],
        profile_confidence: ProfileConfidence,

        attached_item: Dict[str, Any] | None = None,
        anchored_item_id: str = "",
        force_catalog_followup: bool = False,
        source_preference: str = "",
        emit: Any,
        trace_start: Any = None,
        trace_end: Any = None,
        trace: Optional[TurnTraceBuilder] = None,
    ) -> Dict[str, Any]:
        # Default trace functions to no-ops if not passed (e.g. in tests).
        if trace_start is None:
            trace_start = lambda *a, **kw: None
        if trace_end is None:
            trace_end = lambda *a, **kw: None
        # Tests that exercise the handler without the full process_turn
        # shell can pass trace=None — the module-level _NO_OP_TRACE
        # singleton absorbs the cost / evaluation calls cleanly.
        if trace is None:
            trace = _NO_OP_TRACE

        # Build live context from planner's resolved context
        rc = plan_result.resolved_context
        initial_live_context = self._build_effective_live_context(
            message=message,
            resolved_context=rc,
            previous_context=previous_context,
            force_catalog_followup=force_catalog_followup,
        )
        # Set anchor garment for pairing requests so the architect knows what NOT to search for.
        # Pass all available attributes (enrichment fields, colors, formality, etc.) so the
        # architect can plan complementary pieces with full context.
        _log.info("Anchor check: intent=%s attached_item=%s", intent.primary_intent, bool(attached_item))
        if intent.primary_intent == Intent.PAIRING_REQUEST and attached_item:
            anchor = {k: v for k, v in dict(attached_item).items() if v and str(v).strip()}
            anchor["source"] = anchor.get("source") or "wardrobe"
            initial_live_context.anchor_garment = anchor
            _log.info("Anchor garment set: title=%s cat=%s", anchor.get("title"), anchor.get("garment_category"))
        conversation_memory = build_conversation_memory(
            previous_context,
            initial_live_context,
            current_intent=plan_result.intent,
            channel=channel,
            wardrobe_item_count=len(user_context.wardrobe_items),
        )

        hard_filters = build_global_hard_filters(user_context)

        # Load catalog inventory
        if self._catalog_inventory is None:
            try:
                self._catalog_inventory = self._retrieval_gateway.get_catalog_inventory()
            except Exception:
                _log.warning("Failed to load catalog inventory", exc_info=True)
                self._catalog_inventory = []

        # Local environment guardrail: if catalog data / embeddings are not
        # loaded (e.g. running locally without a synced staging DB), the
        # recommendation pipeline will silently produce zero results. Detect
        # that state up front and return a clear, actionable message instead
        # of running an empty pipeline. The wardrobe-first short-circuit above
        # will already have returned by this point if the user has wardrobe
        # items, so this only fires when we *need* the catalog and it isn't
        # there.
        if not self._catalog_inventory:
            _log.error(
                "Catalog/embeddings missing — pipeline cannot run. "
                "Run catalog enrichment + embedding sync, or point at a "
                "staging Supabase instance with seeded catalog data."
            )
            guardrail_message = (
                "I can't put together catalog recommendations right now — the "
                "catalog and embeddings aren't loaded in this environment. "
                "Run the catalog enrichment + embedding sync, or switch to a "
                "staging database with seeded catalog data, and try again."
            )
            self.repo.finalize_turn(
                turn_id=turn_id,
                assistant_message=guardrail_message,
                resolved_context={
                    "request_summary": message.strip(),
                    "error": "catalog_unavailable",
                    "stage": "planner_pipeline_preflight",
                    "channel": channel,
                },
            )
            emit("catalog_search", "blocked")
            return {
                "conversation_id": conversation_id,
                "turn_id": turn_id,
                "assistant_message": guardrail_message,
                "response_type": "error",
                "resolved_context": {
                    "request_summary": message.strip(),
                    "error": "catalog_unavailable",
                },
                "filters_applied": hard_filters,
                "outfits": [],
                "follow_up_suggestions": [],
                "metadata": {
                    "error": True,
                    "error_stage": "catalog_unavailable",
                    "guardrail": "local_environment_catalog_missing",
                    "primary_intent": intent.primary_intent,
                },
            }

        previous_recs = previous_context.get("last_recommendations")

        # Load disliked product_ids from feedback_events so retrieval can
        # suppress items the user already rejected. Merge with anything we
        # persisted in session_context for cross-turn continuity (the
        # session_context copy is what survives between turns even if the
        # feedback_events query is slow or fails).
        disliked_from_session = [
            str(pid).strip()
            for pid in list(previous_context.get("disliked_product_ids") or [])
            if str(pid or "").strip()
        ]
        try:
            internal_user_id = str(self.repo.get_or_create_user(external_user_id).get("id") or external_user_id)
        except Exception:
            internal_user_id = external_user_id
        try:
            raw_disliked = self.repo.list_disliked_product_ids_for_user(
                user_id=internal_user_id,
                conversation_id=conversation_id,
                limit=200,
            )
            disliked_from_db = list(raw_disliked) if isinstance(raw_disliked, (list, tuple)) else []
        except Exception:
            _log.warning("Failed to load disliked product_ids — proceeding without exclusion", exc_info=True)
            disliked_from_db = []
        disliked_product_ids: List[str] = []
        seen_disliked: set[str] = set()
        for pid in (disliked_from_db + disliked_from_session):
            if pid and pid not in seen_disliked:
                seen_disliked.add(pid)
                disliked_product_ids.append(pid)
        if disliked_product_ids:
            _log.info(
                "Loaded %d disliked product_ids for suppression (db=%d, session=%d)",
                len(disliked_product_ids), len(disliked_from_db), len(disliked_from_session),
            )

        # R4 (PR #67, May 5 2026): aggregate the user's recent
        # like/dislike feedback into archetypal axes (color_temperature,
        # pattern_type, fit_type, silhouette_type, embellishment_level)
        # so the Composer can soft-bias item selection. The Rater no
        # longer consumes this (PR #89, May 5 2026) — its veto rule was
        # producing systematic empty responses.
        try:
            _raw_prefs = self.repo.aggregate_archetypal_feedback(internal_user_id)
            archetypal_preferences = dict(_raw_prefs) if isinstance(_raw_prefs, dict) else {}
        except Exception:
            _log.warning("Failed to aggregate archetypal feedback — proceeding without it", exc_info=True)
            archetypal_preferences = {}

        # PR 2 (May 5 2026): episodic memory for the architect. Raw
        # last-30-days timeline of like/dislike events with the user_query
        # that produced each outfit. The architect reads this to find
        # context-dependent patterns and bias retrieval queries — the
        # aggregate-veto failure mode (T12) replaced with LLM pattern
        # recognition over richer evidence.
        # Same defensive pattern as `aggregate_archetypal_feedback` above:
        # tolerate exceptions AND non-list returns (test mocks default to
        # Mock objects, not lists) so the pipeline still ships on cold
        # paths and during legacy test wiring.
        try:
            _raw_actions = self.repo.list_recent_user_actions(internal_user_id)
            recent_user_actions = list(_raw_actions) if isinstance(_raw_actions, list) else []
        except Exception:
            _log.warning("Failed to load recent user actions — proceeding without episodic memory", exc_info=True)
            recent_user_actions = []

        combined_context = CombinedContext(
            user=user_context,
            live=initial_live_context,
            hard_filters=hard_filters,
            previous_recommendations=previous_recs if isinstance(previous_recs, list) else None,
            conversation_memory=conversation_memory,
            conversation_history=conversation_history,
            catalog_inventory=self._catalog_inventory or None,
            disliked_product_ids=disliked_product_ids,
            archetypal_preferences=archetypal_preferences,
            recent_user_actions=recent_user_actions,
        )

        richer_refinement_path = self._message_requires_richer_refinement_path(
            message=message,
            intent=intent,
            live_context=initial_live_context,
        )

        # Wardrobe-first check (occasion only — pairing always runs full pipeline).
        # Default is catalog (shop-the-look). Wardrobe-first runs only when the
        # user explicitly asks for it; auto/empty/catalog all skip this branch
        # and fall through to the catalog pipeline.
        if not force_catalog_followup and source_preference == "wardrobe":
            if not richer_refinement_path:
                # Compute wardrobe coverage once and thread it through both
                # the wardrobe-first builder (for the gate) and the fallback
                # (for the message + metadata). Without this, the role-count
                # walk runs twice on the insufficient-coverage path.
                precomputed_coverage = self._wardrobe_meets_minimum_coverage(
                    user_context.wardrobe_items
                )

                wardrobe_first_response = self._build_wardrobe_first_occasion_response(
                    external_user_id=external_user_id,
                    message=message,
                    conversation_id=conversation_id,
                    turn_id=turn_id,
                    channel=channel,
                    intent=intent,
                    previous_context=previous_context,
                    user_context=user_context,
                    live_context=initial_live_context,
                    conversation_memory=conversation_memory.model_dump(),
                    profile_confidence=profile_confidence,

                    anchored_item_id=anchored_item_id,
                    precomputed_coverage=precomputed_coverage,
                )
                if wardrobe_first_response is not None:
                    return wardrobe_first_response

                wardrobe_only_fallback = self._build_wardrobe_only_occasion_fallback(
                    message=message,
                    conversation_id=conversation_id,
                    turn_id=turn_id,
                    channel=channel,
                    intent=intent,
                    previous_context=previous_context,
                    user_context=user_context,
                    live_context=initial_live_context,
                    conversation_memory=conversation_memory.model_dump(),
                    profile_confidence=profile_confidence,

                    precomputed_coverage=precomputed_coverage,
                )
                if wardrobe_only_fallback is not None:
                    return wardrobe_only_fallback

        # Run Outfit Architect
        # Read model + reasoning effort from the agent so the trace +
        # log rows always reflect what was actually called (May 5, 2026
        # gpt-5.5 → gpt-5.4 + medium-effort swap exposed how easy
        # hardcoded-literal drift is here). Direct attribute access
        # rather than getattr-with-default so a future rename fails loud
        # here instead of silently falling back to a stale literal.
        _architect_model = self.outfit_architect._model
        _architect_effort_used = self.outfit_architect._reasoning_effort
        emit("outfit_architect", "started")
        trace_start("outfit_architect", model=_architect_model, input_summary=f"message={message[:80]}")
        t0 = time.monotonic()
        try:
            plan = self.outfit_architect.plan(combined_context)
        except Exception as exc:
            architect_ms = int((time.monotonic() - t0) * 1000)
            trace_end("outfit_architect", status="error", error=str(exc)[:200])
            _log.error("Outfit architect failed: %s", exc, exc_info=True)
            trace.add_model_cost_from_row(self.repo.log_model_call(
                conversation_id=conversation_id,
                turn_id=turn_id,
                service="agentic_application",
                call_type="outfit_architect",
                model=_architect_model,
                request_json={
                    # Same shape as the success-path log below — the
                    # error case used to drop occasion + is_followup,
                    # which made model_call_logs harder to slice on
                    # failures by occasion mix. initial_live_context is
                    # in scope and is what the architect actually saw.
                    "combined_context_summary": {
                        "gender": user_context.gender,
                        "occasion": initial_live_context.occasion_signal,
                        "message": message,
                        "is_followup": initial_live_context.is_followup,
                    },
                    "reasoning_effort": _architect_effort_used,
                },
                response_json={},
                reasoning_notes=[],
                latency_ms=architect_ms,
                status="error",
                error_message=str(exc),
            ))
            emit("outfit_architect", "error")
            self.repo.finalize_turn(
                turn_id=turn_id,
                assistant_message="I'm having trouble processing your request right now. Please try again.",
                resolved_context={"error": str(exc), "request_summary": message.strip()},
            )
            return {
                "conversation_id": conversation_id,
                "turn_id": turn_id,
                "assistant_message": "I'm having trouble processing your request right now. Please try again.",
                "resolved_context": {"request_summary": message.strip()},
                "filters_applied": hard_filters,
                "outfits": [],
                "follow_up_suggestions": [],
                "metadata": {"error": True},
            }
        architect_ms = int((time.monotonic() - t0) * 1000)

        resolved = plan.resolved_context
        if resolved:
            effective_live_context = LiveContext(
                user_need=message.strip(),
                occasion_signal=resolved.occasion_signal,
                formality_hint=resolved.formality_hint,
                time_hint=resolved.time_hint,
                specific_needs=resolved.specific_needs,
                is_followup=resolved.is_followup,
                followup_intent=resolved.followup_intent,
                anchor_garment=initial_live_context.anchor_garment,
                weather_context=initial_live_context.weather_context,
                time_of_day=initial_live_context.time_of_day,
                target_product_type=initial_live_context.target_product_type,
            )
        else:
            effective_live_context = initial_live_context

        _arch_usage = getattr(self.outfit_architect, "last_usage", {}) or {}
        trace.add_model_cost_from_row(self.repo.log_model_call(
            conversation_id=conversation_id,
            turn_id=turn_id,
            service="agentic_application",
            call_type="outfit_architect",
            model=_architect_model,
            request_json={
                "combined_context_summary": {
                    "gender": user_context.gender,
                    "occasion": effective_live_context.occasion_signal,
                    "message": message,
                    "is_followup": effective_live_context.is_followup,
                },
                "reasoning_effort": _architect_effort_used,
            },
            response_json=plan.model_dump(),
            reasoning_notes=[],
            latency_ms=architect_ms,
            prompt_tokens=_arch_usage.get("prompt_tokens"),
            completion_tokens=_arch_usage.get("completion_tokens"),
            total_tokens=_arch_usage.get("total_tokens"),
        ))
        emit("outfit_architect", "completed", ctx={
            "direction_types": sorted({d.direction_type for d in plan.directions}),
            "direction_count": len(plan.directions),
        })
        trace_end("outfit_architect", output_summary=f"{len(plan.directions)} directions, retrieval_count={plan.retrieval_count}")

        conversation_memory = build_conversation_memory(
            previous_context,
            effective_live_context,
            current_intent=plan_result.intent,
            channel=channel,
            wardrobe_item_count=len(user_context.wardrobe_items),
        )
        combined_context = combined_context.model_copy(update={
            "live": effective_live_context,
            "conversation_memory": conversation_memory,
        })

        # When anchor garment exists, strip queries for the anchor's role from the plan
        # BEFORE search — don't waste embedding calls on a role the user already fills.
        # Then inject the anchor as the sole item for that role after search.
        anchor = combined_context.live.anchor_garment
        anchor_role = ""
        has_paired = any(d.direction_type in ("paired", "three_piece") for d in plan.directions)
        if anchor and has_paired:
            anchor_category = str(anchor.get("garment_category") or "").lower()
            anchor_role = "top" if anchor_category in ("top", "shirt", "blouse") else "bottom" if anchor_category in ("bottom", "trouser", "pant") else "complete"
            for direction in plan.directions:
                direction.queries = [q for q in direction.queries if q.role != anchor_role]
            plan.directions = [d for d in plan.directions if d.queries]
            _log.info("Stripped %s queries from plan — anchor fills this role", anchor_role)

        # Stages 4-8: Search → Assemble → Evaluate → Format → TryOn
        # Wrap the entire mid-pipeline in a guard so any unhandled failure
        # surfaces as a graceful user-facing message instead of an empty turn.
        try:
            emit("catalog_search", "started")
            trace_start("catalog_search", input_summary=f"{len(plan.directions)} directions, retrieval_count={plan.retrieval_count}")
            t0 = time.monotonic()
            retrieved_sets = self.catalog_search_agent.search(plan, combined_context)
            search_ms = int((time.monotonic() - t0) * 1000)
            for rs in retrieved_sets:
                self.repo.log_tool_trace(
                    conversation_id=conversation_id,
                    turn_id=turn_id,
                    tool_name="catalog_search_agent",
                    input_json={"direction_id": rs.direction_id, "query_id": rs.query_id, "role": rs.role, "applied_filters": rs.applied_filters},
                    output_json={"result_count": len(rs.products)},
                    latency_ms=search_ms,
                )
            # Capture the embedding API cost for the per-turn rollup.
            # The retrieval gateway exposes `last_usage` after the
            # batched embed call; tokens × text-embedding-3-small
            # pricing folds into total_cost_usd. Without this row, the
            # embedding bill (~$0.0001-0.0003/turn) was invisible to
            # turn-level cost dashboards.
            _embed_usage = getattr(self._retrieval_gateway, "last_usage", {}) or {}
            if _embed_usage.get("total_tokens"):
                trace.add_model_cost_from_row(self.repo.log_model_call(
                    conversation_id=conversation_id,
                    turn_id=turn_id,
                    service="agentic_application",
                    call_type="catalog_embedding",
                    model="text-embedding-3-small",
                    request_json={"query_count": len(plan.directions)},
                    response_json={"embedding_count": sum(len(d.queries) for d in plan.directions)},
                    reasoning_notes=[],
                    latency_ms=search_ms,
                    prompt_tokens=_embed_usage.get("prompt_tokens"),
                    total_tokens=_embed_usage.get("total_tokens"),
                ))
            total_products = sum(len(rs.products) for rs in retrieved_sets)
            emit("catalog_search", "completed", ctx={
                "product_count": total_products,
                "set_count": len(retrieved_sets),
            })
            trace_end("catalog_search", output_summary=f"{len(retrieved_sets)} sets, {total_products} products, {search_ms}ms")

            # Inject anchor as the sole item for its role.
            # Phase 12D: mark with is_anchor=True so the assembler's
            # cross-outfit diversity pass exempts this product from the
            # "no repeats" rule. Pairing requests intentionally include
            # the anchor in every candidate by definition.
            if anchor and anchor_role:
                anchor_with_flag = dict(anchor)
                anchor_with_flag["is_anchor"] = True
                anchor_product = RetrievedProduct(
                    product_id=str(anchor.get("id") or anchor.get("product_id") or "anchor_wardrobe"),
                    similarity=1.0,
                    metadata={},
                    enriched_data=anchor_with_flag,
                )
                retrieved_sets.append(
                    RetrievedSet(
                        direction_id=plan.directions[0].direction_id if plan.directions else "anchor",
                        query_id="anchor",
                        role=anchor_role,
                        products=[anchor_product],
                        applied_filters={"source": "wardrobe_anchor"},
                    )
                )
                _log.info("Injected anchor as sole %s — assembler will pair with %d complementary items",
                           anchor_role, sum(len(rs.products) for rs in retrieved_sets if rs.role != anchor_role))

            # === LLM ranker (Composer + Rater) — May 3 2026 ===========
            # Replaces the deterministic OutfitAssembler + Reranker pair.
            # The Composer constructs up to 10 outfits from the retrieved
            # pool; the Rater scores them on a 4-dim rubric and emits a
            # fashion_score 0–100. Cosine similarity remains a retrieval
            # primitive only — all reasoning about whether items belong
            # together is now LLM judgment.
            # Same drift-protection pattern as the architect above: read the
            # model literal off the agent instance so trace + log rows always
            # reflect what was actually called.
            _composer_model = self.outfit_composer._model
            emit("outfit_composer", "started")
            trace_start(
                "outfit_composer",
                model=_composer_model,
                input_summary=f"{total_products} products across {len(retrieved_sets)} sets",
            )
            t_compose = time.monotonic()
            # PR #80 (May 5 2026): per-attempt logging. The composer's
            # retry-on-hallucination path used to roll up into one
            # model_call_logs row that summed prompt_tokens across
            # both attempts (T6 turn appeared to have a 24K-token
            # prompt because it was actually 12K + 12K). Each attempt
            # now persists its own row, distinguished by call_type
            # suffix and an `attempt_no` field in request_json.
            _attempt_logs: List[Dict[str, Any]] = []

            def _record_attempt(payload: Dict[str, Any]) -> None:
                _attempt_logs.append(payload)
                attempt_no = int(payload.get("attempt_no") or 1)
                call_type = "outfit_composer" if attempt_no == 1 else f"outfit_composer_retry{attempt_no - 1}"
                try:
                    trace.add_model_cost_from_row(self.repo.log_model_call(
                        conversation_id=conversation_id,
                        turn_id=turn_id,
                        service="agentic_application",
                        call_type=call_type,
                        model=_composer_model,
                        request_json={
                            "pool_size": total_products,
                            "directions": len({rs.direction_id for rs in retrieved_sets}),
                            "attempt_no": attempt_no,
                        },
                        response_json={
                            "raw": str(payload.get("raw_text") or "")[:8000],
                            "outfit_count_emitted": payload.get("outfit_count_emitted"),
                            "outfit_count_kept": payload.get("outfit_count_kept"),
                            "drop_reasons": (payload.get("drop_reasons") or [])[:10],
                        },
                        reasoning_notes=[],
                        prompt_tokens=int(payload.get("prompt_tokens") or 0),
                        completion_tokens=int(payload.get("completion_tokens") or 0),
                        total_tokens=int(payload.get("total_tokens") or 0),
                        # PR #95: composer now reports per-attempt wall-clock
                        # latency through the on_attempt payload. Without
                        # this, model_call_logs.latency_ms was 0 for every
                        # composer row — turn_traces had the real ~14s but
                        # any p50/p95 panel computed off model_call_logs was
                        # blind. None-coercion mirrors the other token fields
                        # so an older composer that doesn't supply latency
                        # still logs cleanly.
                        latency_ms=(
                            int(payload["latency_ms"])
                            if payload.get("latency_ms") is not None
                            else None
                        ),
                    ))
                except Exception:  # noqa: BLE001 — telemetry must never break pipeline
                    _log.exception("composer per-attempt log failed; ignoring")

            composer_result = self.outfit_composer.compose(
                combined_context, retrieved_sets, on_attempt=_record_attempt,
            )
            compose_ms = int((time.monotonic() - t_compose) * 1000)
            emit(
                "outfit_composer", "completed",
                ctx={
                    "outfit_count": len(composer_result.outfits),
                    "attempt_count": composer_result.attempt_count,
                },
            )
            trace_end(
                "outfit_composer",
                output_summary=(
                    f"{len(composer_result.outfits)} outfits "
                    f"(attempts={composer_result.attempt_count})"
                ),
            )
            try:
                self.repo.log_tool_trace(
                    conversation_id=conversation_id,
                    turn_id=turn_id,
                    tool_name="composer_decision",
                    input_json={"pool_size": total_products},
                    output_json={
                        "outfit_count": len(composer_result.outfits),
                        "overall_assessment": composer_result.overall_assessment,
                        "pool_unsuitable": composer_result.pool_unsuitable,
                        "attempt_count": composer_result.attempt_count,
                        "outfits": [
                            {
                                "composer_id": o.composer_id,
                                "direction_id": o.direction_id,
                                "direction_type": o.direction_type,
                                "item_ids": o.item_ids,
                                "rationale": o.rationale,
                            }
                            for o in composer_result.outfits
                        ],
                    },
                )
            except Exception:  # noqa: BLE001 — telemetry must never break pipeline
                _log.exception("composer decision log failed; ignoring")

            if not composer_result.outfits:
                # Composer either short-circuited the empty pool, judged
                # the pool unsuitable, or hallucinated everything twice.
                # Surface "no confident match" rather than press on.
                emit("confidence_gate", "blocked", ctx={
                    "top_match_score": 0.0,
                    "candidates_seen": 0,
                    "stage": "composer_empty",
                })
                return self._build_low_confidence_catalog_response(
                    external_user_id=external_user_id,
                    message=message,
                    conversation_id=conversation_id,
                    turn_id=turn_id,
                    channel=channel,
                    intent=intent,
                    previous_context=previous_context,
                    live_context=effective_live_context,
                    conversation_memory=conversation_memory.model_dump(),
                    profile_confidence=profile_confidence,
                    top_match_score=0.0,
                    candidates_seen=0,
                    hard_filters=hard_filters,
                )

            # --- Rater pass ------------------------------------------
            emit("outfit_rater", "started")
            trace_start(
                "outfit_rater",
                model="gpt-5-mini",
                input_summary=f"{len(composer_result.outfits)} composed outfits",
            )
            t_rate = time.monotonic()
            rater_result = self.outfit_rater.rate(
                combined_context, composer_result.outfits, retrieved_sets,
            )
            rate_ms = int((time.monotonic() - t_rate) * 1000)
            emit(
                "outfit_rater", "completed",
                ctx={
                    "rated_count": len(rater_result.ranked_outfits),
                    "overall_assessment": rater_result.overall_assessment,
                },
            )
            trace_end(
                "outfit_rater",
                output_summary=(
                    f"{len(rater_result.ranked_outfits)} rated "
                    f"(profile={rater_result.fashion_score_weight_profile})"
                ),
            )
            _rate_usage = rater_result.usage or {}
            trace.add_model_cost_from_row(self.repo.log_model_call(
                conversation_id=conversation_id,
                turn_id=turn_id,
                service="agentic_application",
                call_type="outfit_rater",
                model="gpt-5-mini",
                request_json={
                    "composed_count": len(composer_result.outfits),
                    # R3 (PR #66): which weight profile picked the
                    # final fashion_score blend. SQL-grep with
                    # request_json->>'fashion_score_weight_profile'.
                    "fashion_score_weight_profile": rater_result.fashion_score_weight_profile,
                },
                response_json={"raw": rater_result.raw_response[:8000]},
                reasoning_notes=[r.rationale for r in rater_result.ranked_outfits],
                latency_ms=rate_ms,
                prompt_tokens=_rate_usage.get("prompt_tokens"),
                completion_tokens=_rate_usage.get("completion_tokens"),
                total_tokens=_rate_usage.get("total_tokens"),
            ))
            try:
                self.repo.log_tool_trace(
                    conversation_id=conversation_id,
                    turn_id=turn_id,
                    tool_name="rater_decision",
                    input_json={"composed_count": len(composer_result.outfits)},
                    output_json={
                        "overall_assessment": rater_result.overall_assessment,
                        "ranked_outfits": [
                            {
                                "composer_id": r.composer_id,
                                "rank": r.rank,
                                "fashion_score": r.fashion_score,
                                # R7 (May 5 2026): six 1/2/3 sub-scores.
                                # Pairing replaces inter_item_coherence
                                # (now scoped to fit + fabric only).
                                "occasion_fit": r.occasion_fit,
                                "body_harmony": r.body_harmony,
                                "color_harmony": r.color_harmony,
                                "pairing": r.pairing,
                                "formality": r.formality,
                                "statement": r.statement,
                                "rationale": r.rationale,
                                "unsuitable": r.unsuitable,
                            }
                            for r in rater_result.ranked_outfits
                        ],
                    },
                )
            except Exception:  # noqa: BLE001
                _log.exception("rater decision log failed; ignoring")

            # --- Build OutfitCandidate objects from the rated slate ---
            # Look up the per-item product attrs from the retrieval pool
            # so the candidate's `items` field matches the legacy shape
            # the visual evaluator + try-on render expect.
            products_by_id: Dict[str, RetrievedProduct] = {}
            for rs in retrieved_sets:
                for p in rs.products:
                    products_by_id[p.product_id] = p
            composed_by_id = {o.composer_id: o for o in composer_result.outfits}

            candidates: List[OutfitCandidate] = []
            for rated in rater_result.ranked_outfits:
                composed = composed_by_id.get(rated.composer_id)
                if composed is None:
                    continue
                items: List[Dict[str, Any]] = []
                for iid in composed.item_ids:
                    product = products_by_id.get(iid)
                    if product is None:
                        continue
                    items.append(
                        _build_candidate_item(product, role=_role_for_position(composed, items)),
                    )
                if not items:
                    continue
                candidates.append(
                    OutfitCandidate(
                        candidate_id=composed.composer_id,
                        direction_id=composed.direction_id,
                        candidate_type=composed.direction_type,
                        items=items,
                        fashion_score=rated.fashion_score,
                        # R7 (May 5 2026): six 1/2/3 sub-scores. Pairing
                        # is Optional and stays None for complete outfits.
                        occasion_fit=rated.occasion_fit,
                        body_harmony=rated.body_harmony,
                        color_harmony=rated.color_harmony,
                        pairing=rated.pairing,
                        formality=rated.formality,
                        statement=rated.statement,
                        composer_id=composed.composer_id,
                        composer_rationale=composed.rationale,
                        rater_rationale=rated.rationale,
                        unsuitable=rated.unsuitable,
                        name=composed.name,
                    )
                )

            # Apply Rater veto + threshold gate BEFORE try-on render so
            # we don't burn Gemini calls on outfits the gate would drop.
            ranked_pool = [
                c for c in candidates
                if not c.unsuitable and c.fashion_score >= _RECOMMENDATION_FASHION_THRESHOLD
            ][: self.recommendation_pool_top_n]

            if not ranked_pool:
                top_score = max((c.fashion_score for c in candidates), default=0)
                emit("confidence_gate", "blocked", ctx={
                    "top_match_score": top_score / 100.0,
                    "candidates_seen": len(candidates),
                    "stage": "rater_below_threshold",
                })
                return self._build_low_confidence_catalog_response(
                    external_user_id=external_user_id,
                    message=message,
                    conversation_id=conversation_id,
                    turn_id=turn_id,
                    channel=channel,
                    intent=intent,
                    previous_context=previous_context,
                    live_context=effective_live_context,
                    conversation_memory=conversation_memory.model_dump(),
                    profile_confidence=profile_confidence,
                    top_match_score=top_score / 100.0,
                    candidates_seen=len(candidates),
                    hard_filters=hard_filters,
                )

            person_image_path = self.onboarding_gateway.get_person_image_path(external_user_id)
            visual_path_attempted = False
            evaluator_path = "legacy_text"
            t0 = time.monotonic()
            evaluated: List[EvaluatedRecommendation] = []
            tryon_stats: Dict[str, int] = {
                "tryon_attempted_count": 0,
                "tryon_succeeded_count": 0,
                "tryon_quality_gate_failures": 0,
                "tryon_overgeneration_used": 0,
                "rendered_with_image_count": 0,
                "rendered_without_image_count": 0,
            }
            # May 5, 2026: visual_evaluation moved to an on-demand action.
            # The default flow ships Rater-only dims; the user can request
            # the full visual evaluator read via POST /v1/turns/{turn_id}/
            # outfits/{rank}/visual-eval. We still render top-N via Gemini
            # so every shipped card has a try-on image and the user can
            # scrutinise any one of them with a click.
            if person_image_path and ranked_pool:
                visual_path_attempted = True
                rendered: List[tuple[OutfitCandidate, str]] = []
                try:
                    emit("tryon_render", "started", ctx={"target_count": self.recommendation_final_top_n})
                    trace_start(
                        "tryon_render",
                        model="gemini-3.1-flash-image-preview",
                        input_summary=f"pool={len(ranked_pool)}, target={self.recommendation_final_top_n}",
                    )
                    rendered, tryon_stats = self._render_candidates_for_visual_eval(
                        candidates=ranked_pool,
                        person_image_path=str(person_image_path),
                        external_user_id=external_user_id,
                        conversation_id=conversation_id,
                        turn_id=turn_id,
                        target_count=self.recommendation_final_top_n,
                        trace=trace,
                    )
                    emit("tryon_render", "completed", ctx={
                        "rendered_count": sum(1 for _, p in rendered if p),
                        "attempted_count": tryon_stats.get("tryon_attempted_count", 0),
                    })
                    trace_end(
                        "tryon_render",
                        output_summary=f"{sum(1 for _, p in rendered if p)}/{len(rendered)} rendered",
                    )
                except Exception as _tryon_exc:
                    _log.warning(
                        "Try-on render failed; cards will ship without a render",
                        exc_info=True,
                    )
                    emit("tryon_render", "error")
                    trace_end("tryon_render", status="error", error=str(_tryon_exc)[:200])
                    rendered = []

            evaluator_path = "rater_only"
            top_n = self.recommendation_final_top_n
            promoted_candidates = sorted(
                ranked_pool,
                key=lambda c: c.fashion_score,
                reverse=True,
            )[:top_n]
            # R7 (May 5 2026): the rater emits 1/2/3 sub-scores. The UI
            # radar reads percentages, so rescale per axis: 1→0, 2→50,
            # 3→100 via _r7_pct. The center fashion_score is already
            # 0–100 from compute_fashion_score's blended math.
            for rank, candidate in enumerate(promoted_candidates, 1):
                is_complete = (candidate.candidate_type or "").strip().lower() == "complete"
                # _r7_pct returns Optional[int]; the always-on dims
                # default to 0 if somehow None reaches us here, which
                # is more honest than the prior unconditional `or 0`
                # against 0–100 inputs.
                def _required(v: Any) -> int:
                    return _r7_pct(v) or 0
                evaluated.append(
                    EvaluatedRecommendation(
                        candidate_id=candidate.candidate_id,
                        rank=rank,
                        match_score=candidate.fashion_score / 100.0,
                        # Composer emits a stylist-flavored per-outfit name
                        # (see prompt/outfit_composer.md "Naming"); fall back
                        # to "Outfit N" only if the LLM somehow returns blank.
                        title=candidate.name or f"Outfit {rank}",
                        reasoning=candidate.rater_rationale or "Rated by stylist.",
                        # Map the Rater's 1/2/3 sub-scores onto the 0/50/100
                        # axis percentages the radar UI reads.
                        occasion_pct=_required(candidate.occasion_fit),
                        body_harmony_pct=_required(candidate.body_harmony),
                        color_suitability_pct=_required(candidate.color_harmony),
                        formality_pct=_required(candidate.formality),
                        statement_pct=_required(candidate.statement),
                        # Pairing drops out for complete (single-item)
                        # outfits — None signals the radar to hide the
                        # axis (5-axis pentagon instead of 6-axis hexagon).
                        # Otherwise rescale the 1/2/3 sub-score same as
                        # the always-on dims.
                        pairing_pct=(
                            None if is_complete
                            else _r7_pct(candidate.pairing)
                        ),
                        fashion_score_pct=int(candidate.fashion_score or 0),
                        item_ids=sorted(
                            str(item.get("product_id", ""))
                            for item in (candidate.items or [])
                            if item.get("product_id")
                        ),
                    )
                )

            evaluator_ms = int((time.monotonic() - t0) * 1000)
            _log.info(
                "rater_only promotion: %d candidates promoted in %dms",
                len(evaluated),
                evaluator_ms,
            )

            # Confidence gate (May 3 2026): The Rater + threshold have
            # already filtered the pre-render pool. This second pass is
            # belt-and-suspenders — if the visual evaluator surfaces a
            # candidate whose fashion_score somehow regressed (shouldn't
            # happen since we built `candidates` from the rated slate),
            # drop it. Also caps the kept set at the configured top_n.
            fashion_score_by_cid: Dict[str, int] = {
                str(c.candidate_id): c.fashion_score for c in candidates
            }
            top_match_score_seen = max(
                (fashion_score_by_cid.get(str(e.candidate_id), 0) for e in evaluated),
                default=0,
            ) / 100.0
            confident_evaluated = [
                e for e in evaluated
                if fashion_score_by_cid.get(str(e.candidate_id), 0) >= _RECOMMENDATION_FASHION_THRESHOLD
            ][: self.recommendation_final_top_n]
            dropped_low_confidence = len(evaluated) - len(confident_evaluated)
            if dropped_low_confidence:
                _log.info(
                    "confidence gate: dropped %d/%d outfits below fashion_score=%d (top seen=%.2f)",
                    dropped_low_confidence,
                    len(evaluated),
                    _RECOMMENDATION_FASHION_THRESHOLD,
                    top_match_score_seen,
                )
            if not confident_evaluated:
                emit("confidence_gate", "blocked", ctx={
                    "top_match_score": top_match_score_seen,
                    "candidates_seen": len(candidates),
                })
                return self._build_low_confidence_catalog_response(
                    external_user_id=external_user_id,
                    message=message,
                    conversation_id=conversation_id,
                    turn_id=turn_id,
                    channel=channel,
                    intent=intent,
                    previous_context=previous_context,
                    live_context=effective_live_context,
                    conversation_memory=conversation_memory.model_dump(),
                    profile_confidence=profile_confidence,
                    top_match_score=top_match_score_seen,
                    candidates_seen=len(candidates),
                    hard_filters=hard_filters,
                )
            evaluated = confident_evaluated

            emit("response_formatting", "started")
            trace_start("response_formatting", input_summary=f"{len(evaluated)} evaluated")
            response = self.response_formatter.format(
                evaluated,
                combined_context,
                plan,
                candidates,
                planner_message=plan_result.assistant_message or None,
                planner_suggestions=plan_result.follow_up_suggestions[:5] if plan_result.follow_up_suggestions else None,
            )

            restricted_item_exclusion_count = int(response.metadata.get("restricted_item_exclusion_count") or 0)
            recommendation_confidence = self._build_recommendation_confidence(
                answer_mode="catalog_pipeline",
                profile_confidence=profile_confidence,
                intent=intent,
                evaluated=evaluated,
                retrieved_sets=retrieved_sets,
                candidate_count=len(candidates),
                response_outfit_count=len(response.outfits),
                restricted_item_exclusion_count=restricted_item_exclusion_count,
                wardrobe_items_used=0,
            )
            answer_components = dict(response.metadata.get("answer_components") or {})
            derived_answer_source = self._derive_answer_source_from_components(
                answer_components,
                preferred_source=source_preference,
            )
            response.metadata.update(
                self._build_response_metadata(
                    channel=channel,
                    intent=intent,
                    profile_confidence=profile_confidence,
                    extra={
                        "recommendation_confidence": recommendation_confidence.model_dump(),
                        "answer_source": derived_answer_source,
                        "source_selection": self._build_source_selection(
                            preferred_source=source_preference,
                            fulfilled_source=str(answer_components.get("primary_source") or ""),
                        ),
                        # Phase 12E: surface visual-eval pipeline operational
                        # signals so the operations dashboard can track
                        # quality-gate failure rate, over-generation usage,
                        # and the visual-vs-legacy evaluator path mix.
                        "evaluator_path": evaluator_path,
                        "visual_path_attempted": visual_path_attempted,
                        "tryon_stats": tryon_stats,
                    },
                )
            )
            response.metadata["turn_id"] = turn_id
            outfit_count = min(len(evaluated), 3)
            emit("response_formatting", "completed", ctx={"outfit_count": outfit_count})
            trace_end("response_formatting", output_summary=f"{outfit_count} outfits")
        except Exception as exc:
            stage_ms = int((time.monotonic() - t0) * 1000)
            _log.error("Pipeline stage failed between architect and formatter: %s", exc, exc_info=True)
            self.repo.log_tool_trace(
                conversation_id=conversation_id,
                turn_id=turn_id,
                tool_name="planner_pipeline",
                input_json={"stage": "search_to_format"},
                output_json={"error": str(exc)},
                latency_ms=stage_ms,
            )
            emit("response_formatting", "error")
            fallback_message = (
                "I wasn't able to put together recommendations this time — "
                "try rephrasing or adjusting your request."
            )
            self.repo.finalize_turn(
                turn_id=turn_id,
                assistant_message=fallback_message,
                resolved_context={
                    "error": str(exc),
                    "request_summary": message.strip(),
                    "stage": "planner_pipeline",
                },
            )
            # Mirror the failure into turn_traces.evaluation so dashboards
            # querying turn_traces alone (without joining tool_traces) can
            # surface the error stage + message. Matches the pattern used
            # for the planner failure path at line ~1280.
            trace.set_evaluation({
                "response_type": "error",
                "stage_failed": "planner_pipeline",
                "error": str(exc)[:200],
                "answer_source": "pipeline_error",
            })
            self._persist_trace(trace)
            return {
                "conversation_id": conversation_id,
                "turn_id": turn_id,
                "assistant_message": fallback_message,
                "response_type": "error",
                "resolved_context": {"request_summary": message.strip()},
                "filters_applied": hard_filters,
                "outfits": [],
                "follow_up_suggestions": [],
                "metadata": {"error": True, "error_stage": "planner_pipeline"},
            }

        # Post-pipeline guard: an empty assistant_message means a downstream
        # stage silently produced nothing — surface a graceful fallback so the
        # user never sees a blank turn.
        if not str(getattr(response, "message", "") or "").strip():
            _log.warning(
                "Empty assistant_message after pipeline (turn_id=%s, outfits=%d) — using fallback copy",
                turn_id,
                len(response.outfits),
            )
            response.message = (
                "I wasn't able to put together recommendations this time — "
                "try rephrasing or adjusting your request."
            )

        # Post-format cache lookup; actual Gemini renders ran earlier under tryon_render.
        emit("attach_tryon_images", "started")
        trace_start("attach_tryon_images", input_summary=f"{len(response.outfits)} outfits")
        self._attach_tryon_images(response.outfits, external_user_id, conversation_id=conversation_id, turn_id=turn_id)
        emit("attach_tryon_images", "completed")
        trace_end("attach_tryon_images", output_summary=f"{len(response.outfits)} outfits attached")

        self._persist_catalog_interactions(
            external_user_id=external_user_id,
            conversation_id=conversation_id,
            turn_id=turn_id,
            channel=channel,
            primary_intent=plan_result.intent,
            outfits=response.outfits,
        )
        self._persist_recommendation_confidence(
            external_user_id=external_user_id,
            conversation_id=conversation_id,
            turn_id=turn_id,
            channel=channel,
            primary_intent=plan_result.intent,
            recommendation_confidence=recommendation_confidence,
            metadata_json={"answer_mode": "catalog_pipeline"},
        )

        self.repo.finalize_turn(
            turn_id=turn_id,
            assistant_message=response.message,
            resolved_context=self._build_turn_artifacts(
                message=message,
                live_context=effective_live_context,
                conversation_memory=conversation_memory.model_dump(),
                plan=plan.model_dump(),
                retrieved_sets=retrieved_sets,
                evaluated=evaluated,
                candidates=candidates,
                response_metadata=response.metadata,
                intent_classification=intent.model_dump(),
                profile_confidence=profile_confidence.model_dump(),

                channel=channel,
                outfits=response.outfits,
            ),
        )

        rec_summary = self._build_recommendation_summaries(evaluated, candidates)
        self.repo.update_conversation_context(
            conversation_id=conversation_id,
            session_context={
                **previous_context,
                "memory": conversation_memory.model_dump(),
                "last_direction_types": sorted({d.direction_type for d in plan.directions}),
                "last_recommendations": rec_summary,
                "last_occasion": effective_live_context.occasion_signal or "",
                "last_live_context": effective_live_context.model_dump(),
                "last_response_metadata": response.metadata,
                "last_assistant_message": response.message,
                "last_user_message": message,
                "last_channel": channel,
                "last_intent": plan_result.intent,
                "disliked_product_ids": disliked_product_ids,
                "consecutive_gate_blocks": 0,
            },
        )
        self._persist_dependency_turn_event(
            external_user_id=external_user_id,
            conversation_id=conversation_id,
            turn_id=turn_id,
            channel=channel,
            primary_intent=plan_result.intent,
            response_type="recommendation",
            metadata_json={
                "answer_source": derived_answer_source,
                "outfit_count": len(response.outfits),
                "recommendation_confidence_score_pct": recommendation_confidence.score_pct,
                "restricted_item_exclusion_count": restricted_item_exclusion_count,
                # Phase 12E: dashboard signals for evaluator path mix and
                # try-on quality gate health.
                "evaluator_path": evaluator_path,
                "tryon_stats": tryon_stats,
            },
        )

        return {
            "conversation_id": conversation_id,
            "turn_id": turn_id,
            "assistant_message": response.message,
            "response_type": "recommendation",
            "resolved_context": {
                "request_summary": message.strip(),
                "occasion": effective_live_context.occasion_signal or "",
                "style_goal": (
                    " ".join(effective_live_context.specific_needs)
                    if effective_live_context.specific_needs
                    else ""
                ),
                "profile_confidence_pct": profile_confidence.analysis_confidence_pct,
            },
            "filters_applied": self._flatten_applied_filters(retrieved_sets) or hard_filters,
            "outfits": [card.model_dump() for card in response.outfits],
            "follow_up_suggestions": response.follow_up_suggestions,
            "metadata": response.metadata,
        }

    # ------------------------------------------------------------------
    # Phase 12B: visual evaluator pipeline (rerank → tryon → vision eval)
    # ------------------------------------------------------------------

    def _render_candidates_for_visual_eval(
        self,
        *,
        candidates: List[OutfitCandidate],
        person_image_path: str,
        external_user_id: str,
        conversation_id: str,
        turn_id: str,
        target_count: int,
        trace: Optional[TurnTraceBuilder] = None,
    ) -> tuple[List[tuple[OutfitCandidate, str]], Dict[str, int]]:
        """Render try-on for the top candidates with quality-gate over-generation.

        Walks ``candidates`` (already reranked, top-N to top-pool) and
        renders try-on for the first ``target_count`` whose quality gate
        passes. If a render fails the quality gate (or generation
        errors), pulls from the next position in the over-generation
        pool. Persists each successful render to disk + DB so the
        post-format ``_attach_tryon_images`` cache lookup hits.

        Returns:
            ``(rendered, stats)`` tuple.
            - ``rendered`` is a list of ``(candidate, tryon_path_or_empty)``
              tuples in rank order. The tuple's path is empty if every
              attempt for that slot failed; the orchestrator will still
              ship the candidate as a text-only outfit in that case
              rather than dropping it.
            - ``stats`` is a small dict surfaced to ``response.metadata``
              for the operations dashboard:
                ``{
                    "tryon_attempted_count": int,
                    "tryon_succeeded_count": int,
                    "tryon_quality_gate_failures": int,
                    "tryon_overgeneration_used": bool,
                    "rendered_with_image_count": int,
                    "rendered_without_image_count": int,
                }``
        """
        import base64
        import hashlib
        from datetime import datetime, timezone
        from pathlib import Path

        # Match the contract _handle_planner_pipeline already uses:
        # callers may pass trace=None (e.g. tests), and the singleton
        # absorbs cost-tracking calls without per-callsite null checks.
        if trace is None:
            trace = _NO_OP_TRACE

        empty_stats: Dict[str, int] = {
            "tryon_attempted_count": 0,
            "tryon_succeeded_count": 0,
            "tryon_quality_gate_failures": 0,
            "tryon_overgeneration_used": 0,
            "rendered_with_image_count": 0,
            "rendered_without_image_count": 0,
        }
        if not candidates or not person_image_path:
            return [], empty_stats
        tryon_dir = Path("data/tryon/images")
        tryon_dir.mkdir(parents=True, exist_ok=True)

        stats: Dict[str, int] = dict(empty_stats)

        def _render_one(candidate: OutfitCandidate) -> Dict[str, Any]:
            """Render one candidate via try-on; return a result dict.

            May 3, 2026 — refactored to be thread-safe: returns a pure
            result dict instead of mutating closure-captured counters or
            shared state. The caller reconciles `stats` after each
            parallel batch completes. tool_traces writes happen here
            (each row is independent so HTTP-via-Supabase-REST is fine
            from multiple threads).

            Result keys:
              path: str — saved file path on success, '' otherwise
              attempted: bool — True if we issued a Gemini call (vs cache hit / skipped)
              quality_passed: bool|None — None if no QG ran
              quality_gate_failed: bool — True iff QG ran and rejected
              status: str — short category for telemetry
              error: str|None — short error message
            """
            _candidate_started = time.monotonic()
            _candidate_status = "ok"
            _candidate_error: str | None = None
            _quality_passed: bool | None = None

            def _log_candidate_trace(garment_ids_local: List[str]) -> None:
                latency = int((time.monotonic() - _candidate_started) * 1000)
                try:
                    self.repo.log_tool_trace(
                        conversation_id=conversation_id,
                        turn_id=turn_id,
                        tool_name="tryon_render",
                        input_json={
                            "candidate_id": str(getattr(candidate, "candidate_id", "")),
                            "garment_ids": list(garment_ids_local),
                            "parent_step": "visual_evaluation",
                        },
                        output_json={
                            "status": _candidate_status,
                            "quality_passed": _quality_passed,
                            "error": _candidate_error,
                        },
                        latency_ms=latency,
                        status=_candidate_status,
                        error_message=_candidate_error or "",
                    )
                except Exception:  # noqa: BLE001
                    _log.warning("Failed to persist per-candidate tryon trace", exc_info=True)

            def _result(path: str, *, attempted: bool, qg_failed: bool = False) -> Dict[str, Any]:
                return {
                    "path": path,
                    "attempted": attempted,
                    "quality_passed": _quality_passed,
                    "quality_gate_failed": qg_failed,
                    "status": _candidate_status,
                    "error": _candidate_error,
                }

            garment_urls: list[tuple[str, str]] = []
            for item in candidate.items or []:
                url = str(item.get("image_url") or "").strip()
                if not url:
                    continue
                role = str(item.get("role") or "").strip()
                garment_urls.append((role or "garment", url))
            garment_ids = sorted(
                str(item.get("product_id", "")).strip()
                for item in (candidate.items or [])
                if str(item.get("product_id", "")).strip()
            )
            if not garment_urls:
                _candidate_status = "skipped_no_urls"
                _log_candidate_trace(garment_ids)
                return _result("", attempted=False)
            if garment_ids:
                _cache_t0 = time.monotonic()
                cached = self.repo.find_tryon_image_by_garments(external_user_id, garment_ids)
                if cached and cached.get("file_path"):
                    cached_path = Path(cached["file_path"])
                    if cached_path.exists():
                        _cache_ms = int((time.monotonic() - _cache_t0) * 1000)
                        _candidate_status = "cache_hit"
                        # May 5, 2026: log cache hits to model_call_logs so the
                        # `tryon_render` row count in the trace matches the
                        # `virtual_tryon*` row count in model_call_logs.
                        # Without this, "3/3 rendered" can map to only 2 rows
                        # (the cold renders) and leaves the third unaccounted
                        # for in cost/latency rollups.
                        # Distinct call_type so per-model rollups still group
                        # under gemini-3.1-flash-image-preview while cost queries
                        # can opt to exclude cache hits when measuring net spend.
                        try:
                            _cache_hit_row = self.repo.log_model_call(
                                conversation_id=conversation_id,
                                turn_id=turn_id,
                                service="agentic_application",
                                call_type="virtual_tryon_cache_hit",
                                model="gemini-3.1-flash-image-preview",
                                request_json={
                                    "candidate_id": str(getattr(candidate, "candidate_id", "")),
                                    "garment_ids": list(garment_ids),
                                    "garment_count": len(garment_urls),
                                },
                                response_json={
                                    "success": True,
                                    "cache_hit": True,
                                    "file_path": str(cached_path),
                                },
                                reasoning_notes=[],
                                latency_ms=_cache_ms,
                                status="ok",
                                estimated_cost_usd=0.0,
                            )
                            # Mirror the cold-render path's trace.add_model_cost_from_row
                            # call (line 5628). Cost is 0 so this is a no-op for the
                            # rollup math, but it keeps the cache-hit and cold-render
                            # paths structurally identical so a future cost-tracking
                            # change doesn't silently skip cache hits.
                            trace.add_model_cost_from_row(_cache_hit_row)
                        except Exception:  # noqa: BLE001 — telemetry never breaks pipeline
                            _log.warning("Failed to persist tryon cache_hit model_call_log", exc_info=True)
                        _log_candidate_trace(garment_ids)
                        return _result(str(cached_path), attempted=False)
            try:
                _tryon_t0 = time.monotonic()
                result = self.tryon_service.generate_tryon_outfit(
                    person_image_path=person_image_path,
                    garment_urls=garment_urls,
                )
                _tryon_ms = int((time.monotonic() - _tryon_t0) * 1000)
                # Cost capture (May 3, 2026 doc-cleanup item): every Gemini
                # call is one billable image. We emit a `model_call_logs`
                # row per cold render so per-turn cost rolls up correctly
                # alongside the LLM rows. Cache hits and skipped-no-urls
                # paths return earlier and don't reach this row.
                _tryon_succeeded = bool(result.get("success"))
                try:
                    _tryon_row = self.repo.log_model_call(
                        conversation_id=conversation_id,
                        turn_id=turn_id,
                        service="agentic_application",
                        call_type="virtual_tryon",
                        model="gemini-3.1-flash-image-preview",
                        request_json={
                            "candidate_id": str(getattr(candidate, "candidate_id", "")),
                            "garment_ids": list(garment_ids),
                            "garment_count": len(garment_urls),
                        },
                        response_json={
                            "success": _tryon_succeeded,
                            "mime_type": result.get("mime_type"),
                        },
                        reasoning_notes=[],
                        latency_ms=_tryon_ms,
                        status="ok" if _tryon_succeeded else "error",
                        error_message=str(result.get("error") or "") if not _tryon_succeeded else "",
                        image_count=1 if _tryon_succeeded else 0,
                    )
                    trace.add_model_cost_from_row(_tryon_row)
                except Exception:  # noqa: BLE001 — telemetry never breaks pipeline
                    _log.warning("Failed to persist tryon model_call_log", exc_info=True)
                if not _tryon_succeeded:
                    _candidate_status = "tryon_failed"
                    _candidate_error = str(result.get("error") or "tryon returned success=False")
                    _log_candidate_trace(garment_ids)
                    return _result("", attempted=True)
                quality = self.tryon_quality_gate.evaluate(
                    person_image_path=person_image_path,
                    tryon_result=result,
                )
                _quality_passed = bool(quality.get("passed"))
                try:
                    from platform_core.metrics import observe_tryon_quality_gate
                    observe_tryon_quality_gate(passed=_quality_passed)
                except Exception:  # noqa: BLE001
                    pass
                if not quality.get("passed"):
                    _log.info(
                        "Visual eval try-on failed quality gate for candidate %s: %s",
                        candidate.candidate_id,
                        quality.get("reason_code") or "unknown",
                    )
                    _candidate_status = "quality_gate_failed"
                    _candidate_error = str(quality.get("reason_code") or "unknown")
                    _log_candidate_trace(garment_ids)
                    return _result("", attempted=True, qg_failed=True)
                image_b64 = result.get("image_base64") or ""
                if not image_b64:
                    _candidate_status = "tryon_no_image"
                    _log_candidate_trace(garment_ids)
                    return _result("", attempted=True)
                try:
                    image_bytes = base64.b64decode(image_b64)
                except Exception:
                    _candidate_status = "decode_failed"
                    _log_candidate_trace(garment_ids)
                    return _result("", attempted=True)
                if not image_bytes:
                    _candidate_status = "decode_empty"
                    _log_candidate_trace(garment_ids)
                    return _result("", attempted=True)
                mime_type = result.get("mime_type") or "image/png"
                ext = ".png" if "png" in mime_type else ".jpg"
                ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
                ids_key = "_".join(garment_ids) if garment_ids else ts
                encrypted = hashlib.sha256(
                    f"{external_user_id}_visualeval_{ids_key}_{ts}".encode()
                ).hexdigest()
                dest = tryon_dir / f"{encrypted}{ext}"
                dest.write_bytes(image_bytes)
                try:
                    self.repo.insert_tryon_image(
                        user_id=external_user_id,
                        conversation_id=conversation_id,
                        turn_id=turn_id,
                        outfit_rank=0,
                        garment_ids=garment_ids,
                        garment_source=self._detect_garment_source(candidate),
                        person_image_path=person_image_path,
                        encrypted_filename=encrypted,
                        file_path=str(dest),
                        mime_type=mime_type,
                        file_size_bytes=len(image_bytes),
                        quality_score_pct=quality.get("quality_score_pct"),
                    )
                except Exception:
                    _log.warning("Failed to persist visual-eval tryon metadata", exc_info=True)
                _candidate_status = "ok"
                _log_candidate_trace(garment_ids)
                return _result(str(dest), attempted=True)
            except Exception as exc:
                _log.warning(
                    "Visual eval try-on raised for candidate %s",
                    candidate.candidate_id,
                    exc_info=True,
                )
                _candidate_status = "error"
                _candidate_error = str(exc)[:200]
                _log_candidate_trace(garment_ids)
                return _result("", attempted=True)

        # Batched-parallel rendering (May 3, 2026 — Lever 1 of the
        # performance plan). Each batch fans out up to
        # `(target_count - len(rendered))` candidates to a thread pool;
        # the next batch only fires if the prior one's quality-gate
        # failures left slots empty. Compared with the prior sequential
        # walk this preserves the same total Gemini call count on every
        # outcome while collapsing 3 sequential 20-second renders into a
        # single ~20-second wallclock for the happy path.
        pool = list(candidates)
        rendered: List[tuple[OutfitCandidate, str]] = []
        pool_idx = 0
        attempted_ids: set[str] = set()
        # Map candidate_id → (rank in pool) so we can sort the rendered
        # list back into rank order at the end.
        rank_by_id: Dict[str, int] = {
            str(c.candidate_id): i for i, c in enumerate(pool)
        }
        while len(rendered) < target_count and pool_idx < len(pool):
            batch: List[OutfitCandidate] = []
            slots_remaining = target_count - len(rendered)
            while pool_idx < len(pool) and len(batch) < slots_remaining:
                cand = pool[pool_idx]
                pool_idx += 1
                if cand.candidate_id in attempted_ids:
                    continue
                attempted_ids.add(cand.candidate_id)
                batch.append(cand)
                if pool_idx > target_count:
                    stats["tryon_overgeneration_used"] = 1
            if not batch:
                break
            # Visible-in-stdout observability so the parallel-render
            # behaviour is provable from server logs without re-querying
            # tool_traces. Every cold render in this batch fires before
            # any .result() blocks.
            batch_t0 = time.monotonic()
            _log.info(
                "tryon parallel batch: submitting %d candidate(s) [%s]",
                len(batch),
                ", ".join(str(c.candidate_id) for c in batch),
            )
            # ContextVar propagation: snapshot the parent thread's
            # request_id / turn_id / etc. once and re-set them inside
            # each worker via run_with_context. Without this, model_call_logs
            # rows written from threadpool workers have empty request_id
            # and break cross-stage correlation in observability.
            # We can't share a `contextvars.copy_context()` across workers
            # — the same Context object can't be entered concurrently.
            ctx_snapshot = _snapshot_request_context()
            with ThreadPoolExecutor(max_workers=len(batch)) as exec_pool:
                future_to_cand = [
                    (c, exec_pool.submit(run_with_context, ctx_snapshot, _render_one, c))
                    for c in batch
                ]
                results = [(c, fut.result()) for c, fut in future_to_cand]
            batch_wall_ms = int((time.monotonic() - batch_t0) * 1000)
            # Each candidate's outcome is one of:
            #   - cold success (attempted=True, path set)         → counted in cold_success + succeeded
            #   - cache hit (attempted=False, path set)           → counted in cache_hit + succeeded
            #   - cold failure (attempted=True, path empty)       → not counted in succeeded
            n_succeeded = sum(1 for _c, r in results if r.get("path"))
            n_cache_hit = sum(1 for _c, r in results if not r.get("attempted") and r.get("path"))
            n_cold_attempts = sum(1 for _c, r in results if r.get("attempted"))
            n_cold_success = n_succeeded - n_cache_hit
            _log.info(
                "tryon parallel batch: %d/%d succeeded (cold_success=%d, cache_hit=%d, cold_attempts=%d) in %dms wallclock",
                n_succeeded, len(batch), n_cold_success, n_cache_hit, n_cold_attempts, batch_wall_ms,
            )
            for cand, result in results:
                if result.get("attempted"):
                    stats["tryon_attempted_count"] += 1
                if result.get("quality_gate_failed"):
                    stats["tryon_quality_gate_failures"] += 1
                if result.get("path"):
                    stats["tryon_succeeded_count"] += 1
                    rendered.append((cand, result["path"]))
        # Pool exhausted with empty slots remaining — accept candidates
        # without a tryon image rather than dropping them. The visual
        # evaluator can still score the bare items via attribute fallback.
        if len(rendered) < target_count:
            for cand in pool:
                already_rendered = any(rc.candidate_id == cand.candidate_id for rc, _ in rendered)
                if not already_rendered:
                    rendered.append((cand, ""))
                if len(rendered) >= target_count:
                    break
        # Restore rank order — parallel completion order doesn't preserve
        # it. Stable sort keeps unrendered candidates after rendered ones
        # at the same rank (which can happen during pool exhaustion).
        rendered.sort(key=lambda rc: rank_by_id.get(str(rc[0].candidate_id), 1_000_000))
        rendered = rendered[:target_count]
        stats["rendered_with_image_count"] = sum(1 for _c, p in rendered if p)
        stats["rendered_without_image_count"] = sum(1 for _c, p in rendered if not p)
        return rendered, stats

    @staticmethod
    def _detect_garment_source(candidate: OutfitCandidate) -> str:
        sources = set()
        for item in candidate.items or []:
            src = str(item.get("source") or "").strip().lower()
            if src in ("wardrobe", "catalog"):
                sources.add(src)
        if len(sources) > 1:
            return "mixed"
        return sources.pop() if sources else "catalog"

    def _compute_wardrobe_overlap(
        *,
        attached_item: Dict[str, Any] | None,
        wardrobe_items: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Deterministic check: does the user already own a similar piece?

        Phase 12D follow-up (April 9 2026): excludes any wardrobe row
        whose `id` matches `attached_item["id"]`. Even though the
        orchestrator no longer persists garment_evaluation uploads, this
        is belt-and-braces in case any future code path persists the
        upload before this check runs — without it, the loop will match
        the just-saved row against itself and produce a false-positive
        "your wardrobe already has X" message.

        Strong overlap: same garment_category + similar primary_color.
        Moderate overlap: same garment_category + different color.
        None: different category, no overlap.

        Returns the same shape the legacy ShoppingDecisionAgent prompt
        produced so downstream metadata + UI consumers see a consistent
        contract:
            { has_duplicate, duplicate_detail, overlap_level }
        """
        item = dict(attached_item or {})
        target_category = str(item.get("garment_category") or "").strip().lower()
        target_subtype = str(item.get("garment_subtype") or "").strip().lower()
        target_color = str(item.get("primary_color") or "").strip().lower()
        if not target_category and not target_subtype:
            return {"has_duplicate": False, "duplicate_detail": None, "overlap_level": "none"}

        attached_id = str(item.get("id") or "").strip()
        strong_match: Optional[Dict[str, Any]] = None
        moderate_match: Optional[Dict[str, Any]] = None
        for w_item in wardrobe_items:
            # Skip the attached item itself if it has somehow already been
            # persisted — without this guard the loop matches the just-saved
            # upload against itself and reports it as a duplicate.
            if attached_id and str(w_item.get("id") or "").strip() == attached_id:
                continue
            w_category = str(w_item.get("garment_category") or "").strip().lower()
            w_subtype = str(w_item.get("garment_subtype") or "").strip().lower()
            w_color = str(w_item.get("primary_color") or "").strip().lower()
            category_match = bool(target_category) and w_category == target_category
            subtype_match = bool(target_subtype) and w_subtype == target_subtype
            if not (category_match or subtype_match):
                continue
            if target_color and w_color and target_color == w_color:
                strong_match = w_item
                break
            if moderate_match is None:
                moderate_match = w_item

        if strong_match is not None:
            title = str(strong_match.get("title") or "a similar piece").strip()
            return {
                "has_duplicate": True,
                "duplicate_detail": f"your {title}",
                "overlap_level": "strong",
            }
        if moderate_match is not None:
            title = str(moderate_match.get("title") or "a similar piece").strip()
            return {
                "has_duplicate": True,
                "duplicate_detail": f"your {title} (different color)",
                "overlap_level": "moderate",
            }
        return {"has_duplicate": False, "duplicate_detail": None, "overlap_level": "none"}

    @staticmethod
    def _compute_wardrobe_versatility(
        *,
        attached_item: Dict[str, Any] | None,
        wardrobe_items: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Deterministic check: how easily can the user pair this with their wardrobe?

        Counts compatible wardrobe items by complementary category and
        formality level. The signal is intentionally coarse:
            - tops pair with bottoms and shoes
            - bottoms pair with tops and shoes
            - dresses / one-pieces pair with shoes and outerwear
            - outerwear pairs with everything

        Returns:
            {
                "compatible_count": int,
                "complement_categories": [str, ...],
                "rating": "high" | "medium" | "low" | "none",
            }
        """
        item = dict(attached_item or {})
        category = str(item.get("garment_category") or "").strip().lower()
        formality = str(item.get("formality_level") or "").strip().lower()

        complement_map: Dict[str, List[str]] = {
            "top": ["bottom", "shoe"],
            "shirt": ["bottom", "shoe"],
            "blouse": ["bottom", "shoe"],
            "bottom": ["top", "shoe"],
            "trouser": ["top", "shoe"],
            "skirt": ["top", "shoe"],
            "dress": ["shoe", "outerwear"],
            "one_piece": ["shoe", "outerwear"],
            "outerwear": ["top", "bottom", "dress"],
            "shoe": ["top", "bottom", "dress"],
        }
        complement_categories = complement_map.get(category, [])
        if not complement_categories:
            return {"compatible_count": 0, "complement_categories": [], "rating": "none"}

        compatible: List[Dict[str, Any]] = []
        for w_item in wardrobe_items:
            w_category = str(w_item.get("garment_category") or "").strip().lower()
            w_formality = str(w_item.get("formality_level") or "").strip().lower()
            if w_category not in complement_categories:
                continue
            # Soft formality compatibility — same level or one step apart
            if formality and w_formality and formality != w_formality:
                # Use the assembler's same compatibility table indirectly
                compat_table = {
                    "casual": {"casual", "smart_casual"},
                    "smart_casual": {"casual", "smart_casual", "business_casual"},
                    "business_casual": {"smart_casual", "business_casual", "semi_formal"},
                    "semi_formal": {"business_casual", "semi_formal", "formal"},
                    "formal": {"semi_formal", "formal", "ultra_formal"},
                    "ultra_formal": {"formal", "ultra_formal"},
                }
                if w_formality not in compat_table.get(formality, {formality}):
                    continue
            compatible.append(w_item)

        count = len(compatible)
        if count >= 5:
            rating = "high"
        elif count >= 2:
            rating = "medium"
        elif count >= 1:
            rating = "low"
        else:
            rating = "none"
        return {
            "compatible_count": count,
            "complement_categories": complement_categories,
            "rating": rating,
        }

    def _attached_item_to_outfit_item(attached_item: Dict[str, Any] | None) -> Dict[str, Any]:
        item = dict(attached_item or {})
        # Phase 12D follow-up (April 9 2026): wardrobe rows store the
        # uploaded image at `image_path` (relative repo path) and leave
        # `image_url` empty. The browser can't fetch a relative path
        # directly — `_browser_safe_image_url` rewrites it to
        # `/v1/onboarding/images/local?path=...` which the FastAPI route
        # serves. Without this, the PDP card thumbnail of the uploaded
        # garment fails to load and only the try-on render is visible.
        # `_wardrobe_item_to_outfit_item` already does this; this method
        # was missing the wrapper, which is why the bug only surfaced
        # for chat-uploaded garments shown via the garment_evaluation
        # card.
        raw_image = item.get("image_url") or item.get("image_path") or ""
        return {
            "product_id": str(item.get("id") or item.get("product_id") or ""),
            "title": str(item.get("title") or "Uploaded garment"),
            "image_url": AgenticOrchestrator._browser_safe_image_url(raw_image),
            "garment_category": str(item.get("garment_category") or ""),
            "garment_subtype": str(item.get("garment_subtype") or ""),
            "primary_color": str(item.get("primary_color") or ""),
            "formality_level": str(item.get("formality_level") or ""),
            "occasion_fit": str(item.get("occasion_fit") or ""),
            "pattern_type": str(item.get("pattern_type") or ""),
            "fit_type": str(item.get("fit_type") or ""),
            "volume_profile": str(item.get("volume_profile") or ""),
            "silhouette_type": str(item.get("silhouette_type") or ""),
            "source": "wardrobe",
            "role": "garment",
        }

    def _persist_tryon_render(
        self,
        *,
        external_user_id: str,
        conversation_id: str,
        turn_id: str,
        garment_image_path: str,
        tryon_result: Dict[str, Any],
        quality: Dict[str, Any],
    ) -> str:
        """Persist a successful single-garment try-on to disk + DB; return the file path."""
        import base64
        import hashlib
        from datetime import datetime, timezone
        from pathlib import Path

        image_b64 = tryon_result.get("image_base64") or ""
        if not image_b64:
            return ""
        try:
            image_bytes = base64.b64decode(image_b64)
        except Exception:
            return ""
        if not image_bytes:
            return ""
        mime_type = tryon_result.get("mime_type") or "image/png"
        ext = ".png" if "png" in mime_type else ".jpg"
        ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
        encrypted = hashlib.sha256(
            f"{external_user_id}_garment_eval_{garment_image_path}_{ts}".encode()
        ).hexdigest()
        tryon_dir = Path("data/tryon/images")
        tryon_dir.mkdir(parents=True, exist_ok=True)
        dest = tryon_dir / f"{encrypted}{ext}"
        try:
            dest.write_bytes(image_bytes)
        except Exception:
            _log.warning("Failed to persist garment_evaluation tryon image", exc_info=True)
            return ""
        try:
            self.repo.insert_tryon_image(
                user_id=external_user_id,
                conversation_id=conversation_id,
                turn_id=turn_id,
                outfit_rank=1,
                garment_ids=[garment_image_path],
                garment_source="wardrobe",
                person_image_path=str(self.onboarding_gateway.get_person_image_path(external_user_id) or ""),
                encrypted_filename=encrypted,
                file_path=str(dest),
                mime_type=mime_type,
                file_size_bytes=len(image_bytes),
                quality_score_pct=quality.get("quality_score_pct"),
            )
        except Exception:
            _log.warning("Failed to persist garment_evaluation tryon metadata", exc_info=True)
        return str(dest)

    def _garment_evaluation_error_response(
        self,
        *,
        conversation_id: str,
        turn_id: str,
        message: str,
        error: str,
    ) -> Dict[str, Any]:
        fallback = "I'm having trouble evaluating this piece right now. Please try again."
        self.repo.finalize_turn(
            turn_id=turn_id,
            assistant_message=fallback,
            resolved_context={"error": error, "request_summary": message.strip()},
        )
        return {
            "conversation_id": conversation_id,
            "turn_id": turn_id,
            "assistant_message": fallback,
            "response_type": "error",
            "resolved_context": {"request_summary": message.strip()},
            "filters_applied": {},
            "outfits": [],
            "follow_up_suggestions": [],
            "metadata": {"error": True},
        }

    def _decompose_and_save_garments(
        self,
        image_path: str,
        message: str,
        user_id: str,
        turn_id: str,
        conversation_id: str,
    ) -> None:
        """Process 2 (async): decompose outfit image → crop → enrich 46 attributes → save to wardrobe."""
        try:
            garments = decompose_outfit_image(image_path, user_hints=message.strip())
            if garments:
                self.onboarding_gateway.save_decomposed_garments(
                    user_id=user_id,
                    garments=garments,
                    turn_id=turn_id,
                    conversation_id=conversation_id,
                )
                _log.info("Background decomposition saved %d garments for turn %s", len(garments), turn_id)
        except Exception:
            _log.warning("Background outfit decomposition failed for turn %s", turn_id, exc_info=True)

    @staticmethod
    def _normalize_text_token(value: Any) -> str:
        return str(value or "").strip().lower().replace("-", " ").replace("_", " ")

    def _handle_planner_wardrobe_save(
        self,
        *,
        plan_result: CopilotPlanResult,
        intent: IntentClassification,
        conversation_id: str,
        turn_id: str,
        channel: str,
        external_user_id: str,
        message: str,
        previous_context: Dict[str, Any],
        profile_confidence: ProfileConfidence,

    ) -> Dict[str, Any]:
        saved_item = self._save_chat_wardrobe_item(
            external_user_id=external_user_id,
            message=message,
        )
        metadata = self._build_response_metadata(
            channel=channel,
            intent=intent,
            profile_confidence=profile_confidence,
            extra={"answer_source": "copilot_planner"},
        )
        self.repo.finalize_turn(
            turn_id=turn_id,
            assistant_message=plan_result.assistant_message,
            resolved_context={
                "request_summary": message.strip(),
                "intent_classification": intent.model_dump(),
                "response_metadata": metadata,
                "handler": "copilot_planner_wardrobe_save",
                "saved_item_id": str((saved_item or {}).get("id") or ""),
                "channel": channel,
            },
        )
        self.repo.update_conversation_context(
            conversation_id=conversation_id,
            session_context={
                **previous_context,
                "last_user_message": message,
                "last_assistant_message": plan_result.assistant_message,
                "last_channel": channel,
                "last_intent": plan_result.intent,

                "last_response_metadata": metadata,
            },
        )
        self._persist_dependency_turn_event(
            external_user_id=external_user_id,
            conversation_id=conversation_id,
            turn_id=turn_id,
            channel=channel,
            primary_intent=plan_result.intent,
            response_type="recommendation",
            metadata_json={"answer_source": "copilot_planner"},
        )
        return {
            "conversation_id": conversation_id,
            "turn_id": turn_id,
            "assistant_message": plan_result.assistant_message,
            "response_type": "recommendation",
            "resolved_context": {"request_summary": message.strip()},
            "filters_applied": {},
            "outfits": [],
            "follow_up_suggestions": plan_result.follow_up_suggestions[:5],
            "metadata": metadata,
        }

    def _handle_planner_feedback(
        self,
        *,
        plan_result: CopilotPlanResult,
        intent: IntentClassification,
        conversation_id: str,
        turn_id: str,
        channel: str,
        external_user_id: str,
        message: str,
        previous_context: Dict[str, Any],
        profile_confidence: ProfileConfidence,

    ) -> Dict[str, Any]:
        event_type = str(plan_result.action_parameters.feedback_event_type or "dislike")
        recommendations = list(previous_context.get("last_recommendations") or [])
        top = recommendations[0] if recommendations else {}
        item_ids = [str(v) for v in (top.get("item_ids") or []) if str(v).strip()]
        outfit_rank = int(top.get("rank") or 1) if str(top.get("rank") or "").strip() else 1
        target_turn_id = str((previous_context.get("last_response_metadata") or {}).get("turn_id") or "")

        handler_payload = {
            "event_type": event_type,
            "item_ids": item_ids,
            "outfit_rank": outfit_rank,
            "target_turn_id": target_turn_id,
        }
        self._persist_chat_feedback(
            external_user_id=external_user_id,
            conversation_id=conversation_id,
            handler_payload=handler_payload,
            notes=message.strip(),
        )
        feedback_summary = self._build_feedback_summary(
            event_type=event_type,
            item_ids=item_ids,
            outfit_rank=outfit_rank,
            turn_id=target_turn_id,
        )

        metadata = self._build_response_metadata(
            channel=channel,
            intent=intent,
            profile_confidence=profile_confidence,
            extra={"answer_source": "copilot_planner"},
        )
        self.repo.finalize_turn(
            turn_id=turn_id,
            assistant_message=plan_result.assistant_message,
            resolved_context={
                "request_summary": message.strip(),
                "intent_classification": intent.model_dump(),
                "response_metadata": metadata,
                "handler": "copilot_planner_feedback",
                "handler_payload": handler_payload,
                "feedback_summary": feedback_summary,
                "channel": channel,
            },
        )
        self.repo.update_conversation_context(
            conversation_id=conversation_id,
            session_context={
                **previous_context,
                "last_user_message": message,
                "last_assistant_message": plan_result.assistant_message,
                "last_channel": channel,
                "last_intent": plan_result.intent,

                "last_response_metadata": metadata,
                "last_feedback_summary": feedback_summary,
            },
        )
        self._persist_dependency_turn_event(
            external_user_id=external_user_id,
            conversation_id=conversation_id,
            turn_id=turn_id,
            channel=channel,
            primary_intent=plan_result.intent,
            response_type="recommendation",
            metadata_json={"answer_source": "copilot_planner"},
        )
        return {
            "conversation_id": conversation_id,
            "turn_id": turn_id,
            "assistant_message": plan_result.assistant_message,
            "response_type": "recommendation",
            "resolved_context": {"request_summary": message.strip()},
            "filters_applied": {},
            "outfits": [],
            "follow_up_suggestions": plan_result.follow_up_suggestions[:5],
            "metadata": metadata,
        }

    @staticmethod
    def _build_recommendation_summaries(
        evaluated: List[Any],
        candidates: List[Any],
    ) -> List[Dict[str, Any]]:
        candidate_lookup = {
            str(candidate.candidate_id): candidate
            for candidate in candidates
        }
        summaries: List[Dict[str, Any]] = []
        for row in evaluated:
            candidate = candidate_lookup.get(str(row.candidate_id))
            items = list(getattr(candidate, "items", []) or [])
            primary_colors = []
            garment_categories = []
            garment_subtypes = []
            roles = []
            for item in items:
                color = str(item.get("primary_color") or "").strip()
                if color and color not in primary_colors:
                    primary_colors.append(color)
                category = str(item.get("garment_category") or "").strip()
                if category and category not in garment_categories:
                    garment_categories.append(category)
                subtype = str(item.get("garment_subtype") or "").strip()
                if subtype and subtype not in garment_subtypes:
                    garment_subtypes.append(subtype)
                role = str(item.get("role") or "").strip()
                if role and role not in roles:
                    roles.append(role)
            summaries.append(
                {
                    "candidate_id": row.candidate_id,
                    "rank": row.rank,
                    "title": row.title,
                    "item_ids": row.item_ids,
                    "candidate_type": getattr(candidate, "candidate_type", ""),
                    "direction_id": getattr(candidate, "direction_id", ""),
                    "primary_colors": primary_colors,
                    "garment_categories": garment_categories,
                    "garment_subtypes": garment_subtypes,
                    "roles": roles,
                    "occasion_fits": _dedupe_values(
                        str(item.get("occasion_fit") or "").strip() for item in items
                    ),
                    "formality_levels": _dedupe_values(
                        str(item.get("formality_level") or "").strip() for item in items
                    ),
                    "pattern_types": _dedupe_values(
                        str(item.get("pattern_type") or "").strip() for item in items
                    ),
                    "volume_profiles": _dedupe_values(
                        str(item.get("volume_profile") or "").strip() for item in items
                    ),
                    "fit_types": _dedupe_values(
                        str(item.get("fit_type") or "").strip() for item in items
                    ),
                    "silhouette_types": _dedupe_values(
                        str(item.get("silhouette_type") or "").strip() for item in items
                    ),
                    # R2 (PR #65, May 5 2026): persist the Rater +
                    # Composer rationales so the explanation_request
                    # handler can quote the actual stylist-to-stylist
                    # reasoning instead of regenerating it from raw
                    # attributes. PR #71 review feedback: also persist
                    # the Rater dimension scores so the advisor has
                    # the quantitative evidence behind the rank.
                    # R7 (May 5 2026): scores are now 1/2/3 — rescale
                    # to 0/50/100 to keep the ``_pct`` keys honest.
                    # Pairing, formality, statement added; pairing is
                    # None for complete (single-item) outfits.
                    "archetype_scores": {
                        "occasion_pct": _r7_pct(getattr(candidate, "occasion_fit", None)),
                        "body_harmony_pct": _r7_pct(getattr(candidate, "body_harmony", None)),
                        "color_suitability_pct": _r7_pct(getattr(candidate, "color_harmony", None)),
                        "pairing_pct": _r7_pct(getattr(candidate, "pairing", None)),
                        "formality_pct": _r7_pct(getattr(candidate, "formality", None)),
                        "statement_pct": _r7_pct(getattr(candidate, "statement", None)),
                    },
                    "rater_rationale": str(getattr(candidate, "rater_rationale", "") or "").strip(),
                    "composer_rationale": str(getattr(candidate, "composer_rationale", "") or "").strip(),
                }
            )
        return summaries


def _r7_pct(value: Any) -> Optional[int]:
    """Rescale a Rater 1/2/3 sub-score to a 0/50/100 percent for UI /
    advisor consumption. R7 (May 5 2026) moved from 0–100 sub-scores
    to a 1/2/3 scale; consumers read ``_pct`` so this helper keeps the
    contract consistent.

    None / missing → None (lets the radar drop the axis or the advisor
    skip the dim, instead of pretending a phantom 0).
    """
    if value is None:
        return None
    try:
        v = max(1, min(3, int(value)))
    except (TypeError, ValueError):
        return None
    return (v - 1) * 50


def _dedupe_values(values: Any) -> List[str]:
    ordered: List[str] = []
    seen: set[str] = set()
    for raw in values:
        value = str(raw or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered
