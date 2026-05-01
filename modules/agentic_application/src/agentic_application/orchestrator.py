from __future__ import annotations

import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Thread
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import quote

from platform_core.config import AuraRuntimeConfig
from platform_core.fallback_messages import graceful_policy_message
from platform_core.restricted_categories import detect_restricted_record
from platform_core.repositories import ConversationRepository
from platform_core.request_context import (
    set_turn_id,
    set_conversation_id,
    set_external_user_id,
)

from .agents.catalog_search_agent import CatalogSearchAgent
from .agents.copilot_planner import CopilotPlanner, build_planner_input
from .agents.outfit_architect import OutfitArchitect
from .agents.outfit_assembler import OutfitAssembler
# OutfitEvaluator removed (Phase 12B cleanup, April 9 2026) — the
# VisualEvaluatorAgent is now the sole evaluator. The legacy text-only
# fallback has been replaced with a graceful empty-response path that
# lets the response formatter handle transient visual-evaluator failures.
from .agents.reranker import Reranker
from .agents.response_formatter import ResponseFormatter
from .agents.style_advisor_agent import StyleAdvice, StyleAdvisorAgent
from .agents.visual_evaluator_agent import VisualEvaluatorAgent
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

        self.outfit_architect = OutfitArchitect()
        # OutfitCheckAgent removed (Phase 12B cleanup, April 9 2026) — the
        # VisualEvaluatorAgent replaced all of its call sites. The legacy
        # text-only OutfitEvaluator below is still the fallback for the
        # recommendation pipeline when the visual evaluator returns zero
        # results; it stays until Phase 12E.
        self.visual_evaluator = VisualEvaluatorAgent()  # Phase 12B vision-grounded evaluator
        self.style_advisor = StyleAdvisorAgent()  # Phase 12C open-ended discovery + explanation
        self.catalog_search_agent = CatalogSearchAgent(
            retrieval_gateway=self._retrieval_gateway,
            client=repo.client,
        )
        self.outfit_assembler = OutfitAssembler()
        self.reranker = Reranker()  # Phase 12B explicit pruning step
        # OutfitEvaluator removed — see import block comment above.
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
            "cta": "Show me better options from the catalog",
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
        onboarding_status = self.onboarding_gateway.get_onboarding_status(external_user_id)
        analysis_status = self.onboarding_gateway.get_analysis_status(external_user_id)
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

        # Build user context
        emit("user_context", "started")
        trace_start("user_context", input_summary=f"user={external_user_id}")
        user_context = build_user_context(
            external_user_id,
            onboarding_gateway=self.onboarding_gateway,
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
        emit("copilot_planner", "started")
        trace_start("copilot_planner", model="gpt-5.5", input_summary=f"message={message[:80]}, has_image={bool(image_data)}")
        t0 = time.monotonic()
        try:
            plan_result = self._copilot_planner.plan(planner_input)
        except Exception as exc:
            planner_ms = int((time.monotonic() - t0) * 1000)
            _log.error("Copilot planner failed: %s", exc, exc_info=True)
            self.repo.log_model_call(
                conversation_id=conversation_id,
                turn_id=turn_id,
                service="agentic_application",
                call_type="copilot_planner",
                model="gpt-5.5",
                request_json={"message": effective_message},
                response_json={},
                reasoning_notes=[],
                latency_ms=planner_ms,
                status="error",
                error_message=str(exc),
            )
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
        self.repo.log_model_call(
            conversation_id=conversation_id,
            turn_id=turn_id,
            service="agentic_application",
            call_type="copilot_planner",
            model="gpt-5.5",
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
        )
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
        # garment_evaluation is exempt because the visual evaluator works on
        # the image bytes directly and doesn't need attribute enrichment.
        if (
            attached_item
            and attached_item.get("enrichment_failed")
            and plan_result.intent != Intent.GARMENT_EVALUATION
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
        # garment_evaluation is exempt because the visual evaluator
        # works on image bytes directly and might handle edge cases
        # the enrichment can't (same exemption as the wardrobe_enrichment_failed
        # guard above).
        #
        # This check fires BEFORE the wardrobe-persistence promotion
        # block below, so non-garment uploads never reach
        # `user_wardrobe_items`.
        if (
            attached_item
            and plan_result.intent != Intent.GARMENT_EVALUATION
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

        # ── Close the planner trace step and snapshot the intent ──
        trace_end(
            "copilot_planner",
            output_summary=f"intent={plan_result.intent}, action={plan_result.action}, overrides={override_reasons}",
        )
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
        # gated on intent. Only `pairing_request` and `outfit_check` are
        # allowed to write the uploaded garment to `user_wardrobe_items`,
        # because those are the only intents where "save this to my
        # closet" matches the user's actual ask. `garment_evaluation`
        # ("should I buy this?") asks about a piece the user does NOT
        # own; persisting it produces a false-positive duplicate hit
        # downstream and pollutes the user's wardrobe with items they
        # only considered. The pending dict from the enrichment step is
        # promoted to a real row here.
        #
        # Also skipped when an earlier override flipped the action to
        # ASK_CLARIFICATION (non-garment image, failed enrichment, etc.)
        # — those uploads should NEVER reach the wardrobe.
        if (
            attached_item
            and attached_item.get("_pending_persist")
            and plan_result.intent in (Intent.PAIRING_REQUEST, Intent.OUTFIT_CHECK)
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
            )
        elif plan_result.action == Action.RUN_OUTFIT_CHECK:
            handler_result = self._handle_outfit_check(
                plan_result=plan_result,
                intent=intent,
                conversation_id=conversation_id,
                turn_id=turn_id,
                channel=channel,
                external_user_id=external_user_id,
                message=effective_message,
                previous_context=previous_context,
                user_context=user_context,
                profile_confidence=profile_confidence,
                attached_item=attached_item,
                raw_image_data=image_data,
            )
        elif plan_result.action == Action.RUN_GARMENT_EVALUATION:
            handler_result = self._handle_garment_evaluation(
                plan_result=plan_result,
                intent=intent,
                conversation_id=conversation_id,
                turn_id=turn_id,
                channel=channel,
                external_user_id=external_user_id,
                message=effective_message,
                previous_context=previous_context,
                user_context=user_context,
                profile_confidence=profile_confidence,
                attached_item=attached_item,
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

        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = {pool.submit(_generate_for_outfit, o): o for o in outfits}
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
    ) -> Dict[str, Any] | None:
        if intent.primary_intent != Intent.OCCASION_RECOMMENDATION:
            return None
        occasion = str(live_context.occasion_signal or "").strip()
        wardrobe_items = list(getattr(user_context, "wardrobe_items", []) or [])
        if not occasion or not wardrobe_items:
            return None
        wardrobe_gap_analysis = self._build_wardrobe_gap_analysis(
            wardrobe_items=wardrobe_items,
            occasion=occasion,
            required_roles=["top", "bottom", "shoe"],
        )

        outfit = self._select_wardrobe_occasion_outfit(wardrobe_items=wardrobe_items, occasion=occasion)
        outfit, blocked_terms = self._filter_restricted_recommendation_items(outfit)
        if not outfit:
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
            top_match_score=0.88 if hybrid_used else 0.9,
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
                    "match_score": 0.88 if hybrid_used else 0.9,
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
        gap_items = [str(item).strip() for item in list(wardrobe_gap_analysis.get("gap_items") or []) if str(item).strip()]
        occasion_label = occasion.replace('_', ' ') if occasion else 'this occasion'
        if wardrobe_items:
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
        metadata = self._build_response_metadata(
            channel=channel,
            intent=intent,
            profile_confidence=profile_confidence,
            extra={
                "answer_source": "wardrobe_unavailable",
                "source_selection": source_selection,
                "catalog_upsell": catalog_upsell,
                "wardrobe_gap_analysis": wardrobe_gap_analysis,
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
    ) -> List[Dict[str, Any]]:
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
            elif not item_occasion:
                value += 1
            formality = str(item.get("formality_level") or "").strip().lower()
            if occasion in {"office", "work", "work_meeting"} and formality in {"business_casual", "smart_casual", "semi_formal"}:
                value += 1
            if occasion in {"wedding", "cocktail_party", "date_night"} and formality in {"smart_casual", "semi_formal", "formal"}:
                value += 1
            return value

        ranked = sorted(
            [dict(item, _role=role_of(item), _score=score(item)) for item in wardrobe_items],
            key=lambda item: (-int(item.get("_score") or 0), str(item.get("title") or "").lower()),
        )
        one_piece = next((item for item in ranked if item.get("_role") == "one_piece" and int(item.get("_score") or 0) > 0), None)
        if one_piece is not None:
            return [AgenticOrchestrator._wardrobe_item_to_outfit_item(one_piece)]

        top = next((item for item in ranked if item.get("_role") == "top" and int(item.get("_score") or 0) > 0), None)
        bottom = next(
            (item for item in ranked if item.get("_role") == "bottom" and int(item.get("_score") or 0) > 0 and item.get("id") != (top or {}).get("id")),
            None,
        )
        items: List[Dict[str, Any]] = []
        if top is not None:
            items.append(AgenticOrchestrator._wardrobe_item_to_outfit_item(top))
        if bottom is not None:
            items.append(AgenticOrchestrator._wardrobe_item_to_outfit_item(bottom))
        if items:
            return items
        fallback = [item for item in ranked if int(item.get("_score") or 0) > 0][:2]
        return [AgenticOrchestrator._wardrobe_item_to_outfit_item(item) for item in fallback]

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
                    "assembly_score": candidate.assembly_score,
                    "assembly_notes": candidate.assembly_notes,
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
                    "body_note": row.body_note,
                    "color_note": row.color_note,
                    "style_note": row.style_note,
                    "occasion_note": row.occasion_note,
                    "body_harmony_pct": row.body_harmony_pct,
                    "color_suitability_pct": row.color_suitability_pct,
                    "style_fit_pct": row.style_fit_pct,
                    "risk_tolerance_pct": row.risk_tolerance_pct,
                    "occasion_pct": row.occasion_pct,
                    "comfort_boundary_pct": row.comfort_boundary_pct,
                    "specific_needs_pct": row.specific_needs_pct,
                    "pairing_coherence_pct": row.pairing_coherence_pct,
                    "classic_pct": row.classic_pct,
                    "dramatic_pct": row.dramatic_pct,
                    "romantic_pct": row.romantic_pct,
                    "natural_pct": row.natural_pct,
                    "minimalist_pct": row.minimalist_pct,
                    "creative_pct": row.creative_pct,
                    "sporty_pct": row.sporty_pct,
                    "edgy_pct": row.edgy_pct,
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
            if primary and secondary:
                parts.append(f"Your strongest archetype blend reads as {primary} with a secondary {secondary} influence.")
            elif primary:
                parts.append(f"Your clearest archetype is {primary}.")
            if primary_lower == "classic":
                parts.append("That means polished structure, symmetry, and restraint should stay at the core of your outfits.")
            if secondary_lower == "romantic":
                parts.append("The romantic layer is best used as softness in texture, drape, curve, or detail rather than turning the whole look ornate.")
            parts.append("When you are choosing between options, keep the base classic and add the secondary archetype as the accent.")
        else:
            parts.append("Your profile points toward polished structure, controlled contrast, and intentional lines rather than random trend-driven choices.")
            if seasonal:
                parts.append(f"Color-wise, keep working with your {seasonal} direction.")
            if primary:
                parts.append(f"Style-wise, stay anchored in your {primary}{f' + {secondary}' if secondary else ''} blend.")

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
        primary = str(style_preference.get("primaryArchetype") or "").strip()
        secondary = str(style_preference.get("secondaryArchetype") or "").strip()
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
                    "primary_archetype": primary,
                    "secondary_archetype": secondary,
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
    ) -> Dict[str, Any]:
        # Default trace functions to no-ops if not passed (e.g. in tests).
        if trace_start is None:
            trace_start = lambda *a, **kw: None
        if trace_end is None:
            trace_end = lambda *a, **kw: None

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

        combined_context = CombinedContext(
            user=user_context,
            live=initial_live_context,
            hard_filters=hard_filters,
            previous_recommendations=previous_recs if isinstance(previous_recs, list) else None,
            conversation_memory=conversation_memory,
            conversation_history=conversation_history,
            catalog_inventory=self._catalog_inventory or None,
            disliked_product_ids=disliked_product_ids,
        )

        richer_refinement_path = self._message_requires_richer_refinement_path(
            message=message,
            intent=intent,
            live_context=initial_live_context,
        )

        # Wardrobe-first check (occasion only — pairing always runs full pipeline)
        if not force_catalog_followup and source_preference != "catalog":
            if not richer_refinement_path:
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
    
                )
                if wardrobe_only_fallback is not None:
                    return wardrobe_only_fallback

        # Run Outfit Architect
        emit("outfit_architect", "started")
        trace_start("outfit_architect", model="gpt-5.5", input_summary=f"message={message[:80]}")
        t0 = time.monotonic()
        try:
            plan = self.outfit_architect.plan(combined_context)
        except Exception as exc:
            architect_ms = int((time.monotonic() - t0) * 1000)
            trace_end("outfit_architect", status="error", error=str(exc)[:200])
            _log.error("Outfit architect failed: %s", exc, exc_info=True)
            self.repo.log_model_call(
                conversation_id=conversation_id,
                turn_id=turn_id,
                service="agentic_application",
                call_type="outfit_architect",
                model="gpt-5.5",
                request_json={"combined_context_summary": {"gender": user_context.gender, "message": message}},
                response_json={},
                reasoning_notes=[],
                latency_ms=architect_ms,
                status="error",
                error_message=str(exc),
            )
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
                ranking_bias=resolved.ranking_bias or "balanced",
            )
        else:
            effective_live_context = initial_live_context

        # Item 4 (May 1, 2026): pull token usage from architect agent.
        _arch_usage = getattr(self.outfit_architect, "last_usage", {}) or {}
        self.repo.log_model_call(
            conversation_id=conversation_id,
            turn_id=turn_id,
            service="agentic_application",
            call_type="outfit_architect",
            model="gpt-5.5",
            request_json={
                "combined_context_summary": {
                    "gender": user_context.gender,
                    "occasion": effective_live_context.occasion_signal,
                    "message": message,
                    "is_followup": effective_live_context.is_followup,
                }
            },
            response_json=plan.model_dump(),
            reasoning_notes=[],
            latency_ms=architect_ms,
            prompt_tokens=_arch_usage.get("prompt_tokens"),
            completion_tokens=_arch_usage.get("completion_tokens"),
            total_tokens=_arch_usage.get("total_tokens"),
        )
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

            emit("outfit_assembly", "started")
            trace_start("outfit_assembly", input_summary=f"{total_products} products")
            candidates = self.outfit_assembler.assemble(retrieved_sets, plan, combined_context)
            emit("outfit_assembly", "completed", ctx={"candidate_count": len(candidates)})
            trace_end("outfit_assembly", output_summary=f"{len(candidates)} candidates")

            # Phase 12B: rerank → render top-N try-ons → visual evaluator
            # (per-candidate, parallel) with legacy text evaluator as the
            # fallback when no person photo is on file or the visual path
            # raises. Stage emission distinguishes the two paths so the
            # operator dashboard can track which one ran.
            emit("reranker", "started")
            trace_start("reranker", input_summary=f"{len(candidates)} candidates")
            # Phase 13B+: ranking_bias from architect modulates the
            # tie-break ordering inside the reranker. The decision_log
            # callback persists kept/dropped candidate ids into
            # tool_traces (tool_name="reranker_decision") so offline
            # calibration can correlate reranker output with downstream
            # feedback events.
            reranker_bias = (combined_context.live.ranking_bias or "balanced") if combined_context else "balanced"

            def _persist_reranker_decision(payload: Dict[str, Any]) -> None:
                try:
                    self.repo.log_tool_trace(
                        conversation_id=conversation_id,
                        turn_id=turn_id,
                        tool_name="reranker_decision",
                        input_json={
                            "bias": payload.get("bias"),
                            "input_count": payload.get("input_count"),
                            "weights": payload.get("weights"),
                        },
                        output_json={
                            "kept_count": payload.get("kept_count"),
                            "kept": payload.get("kept"),
                            "dropped": payload.get("dropped"),
                        },
                    )
                except Exception:  # noqa: BLE001 — telemetry must never break pipeline
                    _log.exception("reranker decision log failed; ignoring")

            ranked_pool = self.reranker.rerank(
                candidates,
                bias=reranker_bias,
                turn_id=turn_id,
                decision_log=_persist_reranker_decision,
            )
            emit("reranker", "completed", ctx={"pool_size": len(ranked_pool), "bias": reranker_bias})
            trace_end("reranker", output_summary=f"pool={len(ranked_pool)}, bias={reranker_bias}")

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
            if person_image_path and ranked_pool:
                visual_path_attempted = True
                try:
                    emit("visual_evaluation", "started", ctx={"target_count": self.reranker.final_top_n})
                    trace_start("visual_evaluation", model="gpt-5-mini", input_summary=f"pool={len(ranked_pool)}, target={self.reranker.final_top_n}")
                    rendered, tryon_stats = self._render_candidates_for_visual_eval(
                        candidates=ranked_pool,
                        person_image_path=str(person_image_path),
                        external_user_id=external_user_id,
                        conversation_id=conversation_id,
                        turn_id=turn_id,
                        target_count=self.reranker.final_top_n,
                    )
                    if rendered:
                        evaluated = self._evaluate_candidates_visually(
                            rendered=rendered,
                            user_context=user_context,
                            live_context=combined_context.live,
                            intent=intent.primary_intent,
                            profile_confidence_pct=int(profile_confidence.analysis_confidence_pct),
                        )
                        evaluator_path = "visual"
                    emit("visual_evaluation", "completed", ctx={"evaluated_count": len(evaluated)})
                    trace_end("visual_evaluation", output_summary=f"{len(evaluated)} evaluated, path=visual")
                except Exception as _ve_exc:
                    _log.warning(
                        "Visual evaluator path failed; will fall back to assembly_score promotion",
                        exc_info=True,
                    )
                    emit("visual_evaluation", "error")
                    trace_end("visual_evaluation", status="error", error=str(_ve_exc)[:200])
                    evaluated = []

            if not evaluated:
                # The visual evaluator either wasn't attempted or failed.
                # Rather than returning zero outfits (which the user sees
                # as a broken response), promote the top candidates by
                # assembly_score with neutral evaluation scores. This is a
                # lightweight inline fallback — NOT the deleted 540-line
                # legacy OutfitEvaluator. The candidates already have
                # catalog attributes; we just don't have vision-grounded
                # dimension scores for them. The response will look
                # reasonable (real products, real images) but won't have
                # the per-candidate body/color/style analysis.
                _log.warning(
                    "Visual evaluator produced zero results for turn %s; "
                    "promoting top candidates by assembly_score (inline fallback)",
                    turn_id,
                )
                evaluator_path = "assembly_score_fallback"
                top_n = self.reranker.final_top_n
                fallback_candidates = sorted(
                    ranked_pool,
                    key=lambda c: float(getattr(c, "assembly_score", 0.0) or 0.0),
                    reverse=True,
                )[:top_n]
                fallback_pct = 65  # neutral score — better than 0, not as good as visual
                for rank, candidate in enumerate(fallback_candidates, 1):
                    evaluated.append(
                        EvaluatedRecommendation(
                            candidate_id=candidate.candidate_id,
                            rank=rank,
                            match_score=float(getattr(candidate, "assembly_score", 0.5) or 0.5),
                            title=f"Outfit {rank}",
                            reasoning="Scored by catalog compatibility (visual evaluator unavailable this turn).",
                            body_harmony_pct=fallback_pct,
                            color_suitability_pct=fallback_pct,
                            style_fit_pct=fallback_pct,
                            risk_tolerance_pct=fallback_pct,
                            comfort_boundary_pct=fallback_pct,
                            item_ids=sorted(
                                str(item.get("product_id", ""))
                                for item in (candidate.items or [])
                                if item.get("product_id")
                            ),
                        )
                    )

            evaluator_ms = int((time.monotonic() - t0) * 1000)
            # Item 4 (May 1, 2026): pull token usage from the visual
            # evaluator. last_usage reflects the most recent candidate
            # eval, which is the appropriate denominator since the
            # parallel pool calls its agent per-candidate.
            _eval_usage = getattr(self.visual_evaluator, "last_usage", {}) or {}
            self.repo.log_model_call(
                conversation_id=conversation_id,
                turn_id=turn_id,
                service="agentic_application",
                call_type="outfit_evaluator",
                model="gpt-5-mini",
                request_json={
                    "candidate_count": len(candidates),
                    "evaluator_path": evaluator_path,
                    "visual_path_attempted": visual_path_attempted,
                },
                response_json={"evaluation_count": len(evaluated)},
                reasoning_notes=[],
                latency_ms=evaluator_ms,
                prompt_tokens=_eval_usage.get("prompt_tokens"),
                completion_tokens=_eval_usage.get("completion_tokens"),
                total_tokens=_eval_usage.get("total_tokens"),
            )

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

        emit("virtual_tryon", "started")
        trace_start("virtual_tryon", model="gemini-3.1-flash", input_summary=f"{len(response.outfits)} outfits")
        self._attach_tryon_images(response.outfits, external_user_id, conversation_id=conversation_id, turn_id=turn_id)
        emit("virtual_tryon", "completed")
        trace_end("virtual_tryon", output_summary=f"{len(response.outfits)} outfits attached")

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

        # Mutable counters captured by the inner closure so we can track
        # quality-gate failures vs generation errors separately.
        stats: Dict[str, int] = dict(empty_stats)

        def _render_one(candidate: OutfitCandidate) -> str:
            """Render a single candidate via try-on; return file path or ''.

            Item 10 (May 1, 2026): emits a per-candidate ``tool_traces``
            row with ``tool_name="tryon_render"`` so a slow turn can be
            traced down to which specific candidate dragged the
            wallclock without rerunning the pipeline.
            """
            _candidate_started = time.monotonic()
            _candidate_status = "ok"
            _candidate_error: str | None = None
            _quality_passed: bool | None = None

            def _log_candidate_trace() -> None:
                latency = int((time.monotonic() - _candidate_started) * 1000)
                try:
                    self.repo.log_tool_trace(
                        conversation_id=conversation_id,
                        turn_id=turn_id,
                        tool_name="tryon_render",
                        input_json={
                            "candidate_id": str(getattr(candidate, "candidate_id", "")),
                            "garment_ids": list(garment_ids) if "garment_ids" in dir() else [],
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
                _log_candidate_trace()
                return ""
            # Cache lookup — reuse a previously rendered image for the
            # same garment combination so repeat turns don't re-pay
            # Gemini latency.
            if garment_ids:
                cached = self.repo.find_tryon_image_by_garments(external_user_id, garment_ids)
                if cached and cached.get("file_path"):
                    cached_path = Path(cached["file_path"])
                    if cached_path.exists():
                        _candidate_status = "cache_hit"
                        _log_candidate_trace()
                        return str(cached_path)
            stats["tryon_attempted_count"] += 1
            try:
                result = self.tryon_service.generate_tryon_outfit(
                    person_image_path=person_image_path,
                    garment_urls=garment_urls,
                )
                if not result.get("success"):
                    _candidate_status = "tryon_failed"
                    _candidate_error = str(result.get("error") or "tryon returned success=False")
                    _log_candidate_trace()
                    return ""
                quality = self.tryon_quality_gate.evaluate(
                    person_image_path=person_image_path,
                    tryon_result=result,
                )
                _quality_passed = bool(quality.get("passed"))
                # Item 5: mirror to Prometheus.
                try:
                    from platform_core.metrics import observe_tryon_quality_gate
                    observe_tryon_quality_gate(passed=_quality_passed)
                except Exception:  # noqa: BLE001
                    pass
                if not quality.get("passed"):
                    stats["tryon_quality_gate_failures"] += 1
                    _log.info(
                        "Visual eval try-on failed quality gate for candidate %s: %s",
                        candidate.candidate_id,
                        quality.get("reason_code") or "unknown",
                    )
                    _candidate_status = "quality_gate_failed"
                    _candidate_error = str(quality.get("reason_code") or "unknown")
                    _log_candidate_trace()
                    return ""
                image_b64 = result.get("image_base64") or ""
                if not image_b64:
                    _candidate_status = "tryon_no_image"
                    _log_candidate_trace()
                    return ""
                try:
                    image_bytes = base64.b64decode(image_b64)
                except Exception:
                    _candidate_status = "decode_failed"
                    _log_candidate_trace()
                    return ""
                if not image_bytes:
                    _candidate_status = "decode_empty"
                    _log_candidate_trace()
                    return ""
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
                        outfit_rank=0,  # rank set by formatter later
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
                stats["tryon_succeeded_count"] += 1
                _candidate_status = "ok"
                _log_candidate_trace()
                return str(dest)
            except Exception as exc:
                _log.warning(
                    "Visual eval try-on raised for candidate %s",
                    candidate.candidate_id,
                    exc_info=True,
                )
                _candidate_status = "error"
                _candidate_error = str(exc)[:200]
                _log_candidate_trace()
                return ""

        # Walk the pool greedily — render the first `target_count` whose
        # try-on passes the quality gate. Pull from positions beyond
        # `target_count` (the over-generation pool) when earlier slots fail.
        pool = list(candidates)
        rendered: List[tuple[OutfitCandidate, str]] = []
        pool_idx = 0
        attempted_ids: set[str] = set()
        while len(rendered) < target_count and pool_idx < len(pool):
            candidate = pool[pool_idx]
            pool_idx += 1
            if candidate.candidate_id in attempted_ids:
                continue
            attempted_ids.add(candidate.candidate_id)
            # Phase 12E: detect when we've started pulling from the
            # over-generation pool (positions beyond target_count). This
            # is the operational signal that the quality gate forced us
            # to dig deeper than the natural top-N.
            if pool_idx > target_count:
                stats["tryon_overgeneration_used"] = 1
            tryon_path = _render_one(candidate)
            if tryon_path:
                rendered.append((candidate, tryon_path))
            elif len(rendered) + (len(pool) - pool_idx) < target_count:
                # Pool exhausted — accept the candidate without a tryon
                # rather than dropping it. The visual evaluator can still
                # score the bare items via attribute fallback.
                rendered.append((candidate, ""))
        if len(rendered) < target_count and pool_idx >= len(pool):
            for candidate in pool:
                if candidate.candidate_id not in attempted_ids:
                    rendered.append((candidate, ""))
                if len(rendered) >= target_count:
                    break
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

    def _evaluate_candidates_visually(
        self,
        *,
        rendered: List[tuple[OutfitCandidate, str]],
        user_context: Any,
        live_context: Any,
        intent: str,
        profile_confidence_pct: int,
    ) -> List[EvaluatedRecommendation]:
        """Run VisualEvaluatorAgent for each rendered candidate in parallel.

        Returns the list of ``EvaluatedRecommendation`` in the same
        order as ``rendered`` (which is rank order). Each result has its
        ``rank`` field set to its 1-indexed position in the list.

        Failures fall back to a low-fidelity ``EvaluatedRecommendation``
        constructed from the candidate's assembly_score so the response
        still ships rather than dropping the slot.
        """
        if not rendered:
            return []

        def _eval_one(payload: tuple[int, OutfitCandidate, str]) -> EvaluatedRecommendation:
            rank, candidate, image_path = payload
            try:
                result = self.visual_evaluator.evaluate_candidate(
                    candidate=candidate,
                    image_path=image_path,
                    user_context=user_context,
                    live_context=live_context,
                    intent=intent,
                    mode="recommendation",
                    profile_confidence_pct=profile_confidence_pct,
                )
                return result.model_copy(update={"rank": rank})
            except Exception:
                _log.warning(
                    "Visual evaluator failed for candidate %s; using assembly_score fallback",
                    candidate.candidate_id,
                    exc_info=True,
                )
                fallback_pct = max(0, min(100, int(getattr(candidate, "assembly_score", 0.0) * 100)))
                fallback_item_ids = [
                    str(item.get("product_id", ""))
                    for item in (candidate.items or [])
                    if str(item.get("product_id", ""))
                ]
                return EvaluatedRecommendation(
                    candidate_id=candidate.candidate_id,
                    rank=rank,
                    match_score=float(getattr(candidate, "assembly_score", 0.0) or 0.0),
                    title="",
                    reasoning="Ranked by retrieval similarity (visual evaluator unavailable).",
                    body_harmony_pct=fallback_pct,
                    color_suitability_pct=fallback_pct,
                    style_fit_pct=fallback_pct,
                    risk_tolerance_pct=fallback_pct,
                    occasion_pct=fallback_pct,
                    comfort_boundary_pct=fallback_pct,
                    specific_needs_pct=fallback_pct,
                    pairing_coherence_pct=fallback_pct,
                    weather_time_pct=fallback_pct,
                    item_ids=fallback_item_ids,
                )

        payloads = [(idx + 1, c, p) for idx, (c, p) in enumerate(rendered)]
        results: List[EvaluatedRecommendation] = [
            EvaluatedRecommendation(candidate_id="") for _ in payloads
        ]
        with ThreadPoolExecutor(max_workers=min(len(payloads), 3)) as pool:
            futures = {pool.submit(_eval_one, payload): idx for idx, payload in enumerate(payloads)}
            for future in as_completed(futures):
                idx = futures[future]
                results[idx] = future.result()
        return results

    def _handle_outfit_check(
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
        profile_confidence: ProfileConfidence,
        attached_item: Dict[str, Any] | None = None,
        raw_image_data: str = "",
    ) -> Dict[str, Any]:
        occasion_signal = str(plan_result.resolved_context.occasion_signal or "").strip() or None
        image_path = str((attached_item or {}).get("image_path") or "").strip()

        # Fallback: if the upload/enrichment pipeline failed but we still
        # have the raw image data URL, save it to disk so the evaluator
        # can see the actual outfit photo and we can set tryon_image.
        if not image_path and raw_image_data:
            try:
                import base64, hashlib
                from pathlib import Path
                from datetime import datetime, timezone
                raw = str(raw_image_data).strip()
                if raw.startswith("data:") and ";base64," in raw:
                    encoded = raw.split(",", 1)[1]
                    file_bytes = base64.b64decode(encoded)
                    ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
                    name = hashlib.sha256(f"{external_user_id}_outfit_check_{ts}".encode()).hexdigest()
                    img_dir = Path("data/onboarding/images/wardrobe")
                    img_dir.mkdir(parents=True, exist_ok=True)
                    dest = img_dir / f"{name}.jpg"
                    with open(dest, "wb") as f:
                        f.write(file_bytes)
                    image_path = str(dest)
                    _log.info("Outfit check fallback: saved raw image to %s", image_path)
            except Exception:
                _log.warning("Outfit check fallback image save failed", exc_info=True)

        # Phase 12B: outfit check uses VisualEvaluatorAgent on the user's photo
        # directly. No try-on (the user is already wearing the outfit in the
        # image). No architect call (rating what they're wearing, not picking
        # what to recommend).
        synthetic_candidate = OutfitCandidate(
            candidate_id="outfit-check-1",
            direction_id="outfit_check",
            candidate_type="user_outfit",
            items=[],
            assembly_score=1.0,
        )
        live_context_for_eval = LiveContext(
            user_need=message.strip(),
            occasion_signal=occasion_signal,
            formality_hint=plan_result.resolved_context.formality_hint,
            time_hint=plan_result.resolved_context.time_hint,
            time_of_day=str(getattr(plan_result.resolved_context, "time_of_day", "") or ""),
            weather_context=str(getattr(plan_result.resolved_context, "weather_context", "") or ""),
            specific_needs=list(plan_result.resolved_context.specific_needs or []),
            is_followup=bool(plan_result.resolved_context.is_followup),
            followup_intent=plan_result.resolved_context.followup_intent,
        )

        try:
            check = self.visual_evaluator.evaluate_candidate(
                candidate=synthetic_candidate,
                image_path=image_path,
                user_context=user_context,
                live_context=live_context_for_eval,
                intent=Intent.OUTFIT_CHECK,
                mode="outfit_check",
                profile_confidence_pct=int(profile_confidence.analysis_confidence_pct),
            )
        except Exception as exc:
            _log.error("Outfit check evaluation failed: %s", exc, exc_info=True)
            self.repo.finalize_turn(
                turn_id=turn_id,
                assistant_message="I'm having trouble reviewing this outfit right now. Please try again.",
                resolved_context={"error": str(exc), "request_summary": message.strip()},
            )
            return {
                "conversation_id": conversation_id,
                "turn_id": turn_id,
                "assistant_message": "I'm having trouble reviewing this outfit right now. Please try again.",
                "response_type": "error",
                "resolved_context": {"request_summary": message.strip()},
                "filters_applied": {},
                "outfits": [],
                "follow_up_suggestions": [],
                "metadata": {"error": True},
            }

        # Compute overall_score_pct from the outfit-relevant dimensions for
        # backwards compatibility with the old OutfitCheckResult.overall_score_pct
        # property used by downstream metadata + UI.
        #
        # Phase 12B follow-ups (April 9 2026): pairing_coherence_pct and
        # occasion_pct are now context-gated (Optional[int]). For
        # outfit_check turns pairing should always be present (the user IS
        # wearing a multi-piece outfit), but occasion may be null when the
        # user didn't name one. Average only the dimensions that were
        # actually scored — coercing None to 0 here would re-introduce the
        # phantom-default bug we fixed for the radar chart and verdict.
        outfit_check_scores = [
            check.body_harmony_pct,
            check.color_suitability_pct,
            check.style_fit_pct,
        ]
        if check.pairing_coherence_pct is not None:
            outfit_check_scores.append(check.pairing_coherence_pct)
        if check.occasion_pct is not None:
            outfit_check_scores.append(check.occasion_pct)
        overall_score_pct = int(sum(outfit_check_scores) / len(outfit_check_scores))

        # Item 4 (May 1, 2026): pull token usage from visual evaluator.
        _check_usage = getattr(self.visual_evaluator, "last_usage", {}) or {}
        self.repo.log_model_call(
            conversation_id=conversation_id,
            turn_id=turn_id,
            service="agentic_application",
            call_type=Intent.OUTFIT_CHECK,
            model="gpt-5-mini",
            request_json={
                "message": message,
                "occasion_signal": occasion_signal,
                "profile_confidence_pct": profile_confidence.analysis_confidence_pct,
                "evaluator": "visual_evaluator",
            },
            response_json=check.model_dump(),
            reasoning_notes=[],
            prompt_tokens=_check_usage.get("prompt_tokens"),
            completion_tokens=_check_usage.get("completion_tokens"),
            total_tokens=_check_usage.get("total_tokens"),
        )

        wardrobe_items = list(getattr(user_context, "wardrobe_items", []) or [])

        # Outfit card items are empty for the live response — decomposed garments
        # with cropped images are saved to wardrobe asynchronously.  The outfit
        # photo itself is shown via tryon_image as the hero image.
        outfit_card_items: List[Dict[str, Any]] = []
        if not attached_item:
            anchor_item = self._find_target_wardrobe_piece(
                wardrobe_items=wardrobe_items,
                target_text=message,
            )
            if anchor_item is not None:
                outfit_card_items = [self._wardrobe_item_to_outfit_item(dict(anchor_item, _role="anchor"))]

        # Remove the initial full-photo wardrobe item and decompose into
        # individual garments — but ONLY for new uploads. When the item
        # was selected from wardrobe (attachment_source == "wardrobe_selection"),
        # skip both: the item is already properly saved in the user's
        # wardrobe and doesn't need re-decomposition.
        is_wardrobe_selection = str((attached_item or {}).get("attachment_source") or "") == "wardrobe_selection"
        attached_item_id = str((attached_item or {}).get("id") or "").strip()
        if attached_item_id and not is_wardrobe_selection:
            try:
                self.onboarding_gateway.delete_wardrobe_item(
                    user_id=external_user_id,
                    wardrobe_item_id=attached_item_id,
                )
            except Exception:
                _log.warning("Failed to delete initial outfit wardrobe item %s", attached_item_id, exc_info=True)

        # Process 2 (async): decompose outfit → crop → enrich → save to wardrobe
        # Skipped for wardrobe selections — the item is already in wardrobe.
        if image_path and not is_wardrobe_selection:
            Thread(
                target=self._decompose_and_save_garments,
                args=(image_path, message, external_user_id, turn_id, conversation_id),
                daemon=True,
            ).start()

        # Use the already-resolved image_path (which includes the fallback)
        tryon_image = self._tryon_image_url(image_path) if image_path else None
        outfit_card = OutfitCard(
            rank=1,
            title=str(check.title or "").strip() or "Outfit Check",
            reasoning=check.overall_note,
            body_note=(check.strengths[0] if check.strengths else check.body_note),
            color_note=(check.strengths[1] if len(check.strengths) > 1 else check.color_note),
            style_note=(check.strengths[2] if len(check.strengths) > 2 else check.style_note),
            occasion_note=(check.strengths[3] if len(check.strengths) > 3 else check.occasion_note),
            body_harmony_pct=check.body_harmony_pct,
            color_suitability_pct=check.color_suitability_pct,
            style_fit_pct=check.style_fit_pct,
            pairing_coherence_pct=check.pairing_coherence_pct,
            occasion_pct=check.occasion_pct,
            weather_time_pct=check.weather_time_pct,
            classic_pct=check.classic_pct,
            dramatic_pct=check.dramatic_pct,
            romantic_pct=check.romantic_pct,
            natural_pct=check.natural_pct,
            minimalist_pct=check.minimalist_pct,
            creative_pct=check.creative_pct,
            sporty_pct=check.sporty_pct,
            edgy_pct=check.edgy_pct,
            items=outfit_card_items,
            tryon_image=tryon_image,
        )
        wardrobe_gap_analysis = self._build_wardrobe_gap_analysis(
            wardrobe_items=wardrobe_items,
            occasion=occasion_signal or "",
            required_roles=["top", "bottom", "shoe"],
        )

        strengths = [str(item).strip() for item in check.strengths if str(item).strip()][:2]
        improvements = [dict(item) for item in check.improvements[:2]]
        wardrobe_suggestions = self._build_outfit_check_wardrobe_suggestions(
            wardrobe_items=wardrobe_items,
            improvements=improvements,
            occasion_signal=occasion_signal,
        )
        assistant_parts: List[str] = [check.overall_note.strip()]
        if profile_confidence.analysis_confidence_pct < 70:
            assistant_parts.append(
                f"My confidence is moderate here because your profile confidence is {profile_confidence.analysis_confidence_pct}%."
            )
        if strengths:
            assistant_parts.append("What works: " + " ".join(strengths))
        referenced_swap_details: set[str] = set()
        if improvements:
            improvement_lines = []
            for item in improvements:
                suggestion = str(item.get("suggestion") or "").strip()
                swap_detail = str(item.get("swap_detail") or "").strip()
                swap_source = str(item.get("swap_source") or "").strip()
                if swap_detail:
                    normalized_detail = self._normalize_text_token(swap_detail)
                    if normalized_detail.startswith("your "):
                        normalized_detail = normalized_detail[5:]
                    referenced_swap_details.add(normalized_detail)
                if suggestion and swap_detail:
                    improvement_lines.append(f"{suggestion} Try {swap_detail} ({swap_source}).")
                elif suggestion:
                    improvement_lines.append(suggestion)
            if improvement_lines:
                assistant_parts.append("Tweaks: " + " ".join(improvement_lines))
        fresh_wardrobe_suggestions = [
            item
            for item in wardrobe_suggestions
            if str(item.get("title") or "").strip()
            and (
                self._normalize_text_token(str(item.get("title") or "").strip())[5:]
                if self._normalize_text_token(str(item.get("title") or "").strip()).startswith("your ")
                else self._normalize_text_token(str(item.get("title") or "").strip())
            ) not in referenced_swap_details
        ]
        if fresh_wardrobe_suggestions:
            assistant_parts.append(
                "From your wardrobe, try: "
                + "; ".join(
                    f"{item['title']} ({item['reason']})"
                    for item in fresh_wardrobe_suggestions[:2]
                    if str(item.get("title") or "").strip()
                )
                + "."
            )
        assistant_message = " ".join(part for part in assistant_parts if part).strip()
        gap_items = [str(item).strip() for item in list(wardrobe_gap_analysis.get("gap_items") or []) if str(item).strip()]
        catalog_upsell = self._build_catalog_upsell(
            rationale=(
                "I can also show catalog options to close the gaps in this look."
                if gap_items
                else "I can also show catalog options that solve the same styling tweak."
            ),
            entry_intent=Intent.OUTFIT_CHECK,
        )
        live_context = LiveContext(
            user_need=message.strip(),
            occasion_signal=occasion_signal,
            formality_hint=plan_result.resolved_context.formality_hint,
            time_hint=plan_result.resolved_context.time_hint,
            specific_needs=_dedupe_values(
                [
                    *(list(plan_result.resolved_context.specific_needs or [])),
                    Intent.OUTFIT_CHECK,
                ]
            ),
            is_followup=bool(plan_result.resolved_context.is_followup),
            followup_intent=plan_result.resolved_context.followup_intent,
        )
        follow_up_suggestions = list(plan_result.follow_up_suggestions[:5] if plan_result.follow_up_suggestions else [])
        if not follow_up_suggestions:
            follow_up_suggestions = ["What would improve this look?", "Show me wardrobe swap options"]
        if str(catalog_upsell["cta"]) not in follow_up_suggestions:
            follow_up_suggestions.append(str(catalog_upsell["cta"]))
        follow_up_suggestions = follow_up_suggestions[:5]

        handler_payload = {
            "overall_verdict": check.overall_verdict,
            "overall_score_pct": overall_score_pct,
            "scores": {
                "body_harmony_pct": check.body_harmony_pct,
                "color_suitability_pct": check.color_suitability_pct,
                "style_fit_pct": check.style_fit_pct,
                "pairing_coherence_pct": check.pairing_coherence_pct,
                "occasion_pct": check.occasion_pct,
                "weather_time_pct": check.weather_time_pct,
            },
            "strengths": strengths,
            "improvements": improvements,
            "wardrobe_suggestions": wardrobe_suggestions,
            "style_archetype_read": {
                "classic_pct": check.classic_pct,
                "dramatic_pct": check.dramatic_pct,
                "romantic_pct": check.romantic_pct,
                "natural_pct": check.natural_pct,
                "minimalist_pct": check.minimalist_pct,
                "creative_pct": check.creative_pct,
                "sporty_pct": check.sporty_pct,
                "edgy_pct": check.edgy_pct,
            },
            "occasion_signal": occasion_signal or "",
            "wardrobe_gap_analysis": wardrobe_gap_analysis,
            "catalog_upsell": catalog_upsell,
        }
        metadata = self._build_response_metadata(
            channel=channel,
            intent=intent,
            profile_confidence=profile_confidence,
            extra={
                "answer_source": "outfit_check_handler",
                "outfit_check": handler_payload,
                "catalog_upsell": catalog_upsell,
            },
        )
        outfit_item_ids = [str(item.get("product_id") or "") for item in outfit_card_items if str(item.get("product_id") or "")]
        outfit_card_data = outfit_card.model_dump()
        self.repo.finalize_turn(
            turn_id=turn_id,
            assistant_message=assistant_message,
            resolved_context={
                "request_summary": message.strip(),
                "occasion": occasion_signal or "",
                "style_goal": "outfit_check",
                "live_context": live_context.model_dump(),
                "intent_classification": intent.model_dump(),
                "profile_confidence": profile_confidence.model_dump(),
                "response_metadata": metadata,
                "handler": Intent.OUTFIT_CHECK,
                "handler_payload": handler_payload,
                "channel": channel,
                "outfits": [outfit_card_data],
                "recommendations": [
                    {
                        "candidate_id": "outfit-check-1",
                        "rank": 1,
                        "title": "Outfit Check",
                        "item_ids": outfit_item_ids,
                        "match_score": overall_score_pct / 100.0,
                        "reasoning": check.overall_note,
                    }
                ],
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
                "last_live_context": live_context.model_dump(),

                "last_response_metadata": metadata,
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
                "answer_source": "outfit_check_handler",
                "overall_score_pct": overall_score_pct,
            },
        )
        return {
            "conversation_id": conversation_id,
            "turn_id": turn_id,
            "assistant_message": assistant_message,
            "response_type": "recommendation",
            "resolved_context": {
                "request_summary": message.strip(),
                "occasion": occasion_signal or "",
                "style_goal": "outfit_check",
                "profile_confidence_pct": profile_confidence.analysis_confidence_pct,
            },
            "filters_applied": {},
            "outfits": [outfit_card.model_dump()],
            "follow_up_suggestions": follow_up_suggestions,
            "metadata": metadata,
        }

    def _handle_garment_evaluation(
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
        profile_confidence: ProfileConfidence,
        attached_item: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        """Phase 12B garment_evaluation pipeline:

            try-on → VisualEvaluatorAgent → formatter (with optional verdict)

        Inputs: an uploaded garment image (`attached_item.image_path`).
        The handler renders a try-on of the garment on the user's body,
        then runs the VisualEvaluatorAgent on the rendered image to
        score body harmony, color suitability, style fit, occasion,
        weather/time, and 8 archetype dimensions.

        ``purchase_intent`` (extracted by the planner) controls whether
        the response formatter renders a buy/skip verdict block. The
        wardrobe overlap + versatility checks below run regardless of
        framing because they're useful information for both shopping and
        suitability questions.

        Graceful fallbacks:
            - no attached image → ask_clarification
            - no person photo → degraded response (attribute-only via
              direct evaluator call without image)
            - try-on quality gate failure → degraded response with the
              evaluator scoring the bare garment image
        """
        garment_image_path = str((attached_item or {}).get("image_path") or "").strip()
        if not garment_image_path:
            assistant_message = (
                "Upload a photo of the piece you'd like me to evaluate and I'll "
                "render it on you for a clear take."
            )
            metadata = self._build_response_metadata(
                channel=channel,
                intent=intent,
                profile_confidence=profile_confidence,
                extra={"answer_source": "garment_evaluation_no_image"},
            )
            self.repo.finalize_turn(
                turn_id=turn_id,
                assistant_message=assistant_message,
                resolved_context={
                    "request_summary": message.strip(),
                    "intent_classification": intent.model_dump(),
                    "profile_confidence": profile_confidence.model_dump(),
                    "response_metadata": metadata,
                    "handler": Intent.GARMENT_EVALUATION,
                    "channel": channel,
                },
            )
            return {
                "conversation_id": conversation_id,
                "turn_id": turn_id,
                "assistant_message": assistant_message,
                "response_type": "clarification",
                "resolved_context": {"request_summary": message.strip()},
                "filters_applied": {},
                "outfits": [],
                "follow_up_suggestions": ["Upload a garment photo", "Rate my outfit instead"],
                "metadata": metadata,
            }

        # Stage 1: Try-on render
        emit = lambda *_args, **_kwargs: None  # noqa: E731 — no progress callback at this layer
        person_image_path = self.onboarding_gateway.get_person_image_path(external_user_id)
        tryon_render_path = ""
        tryon_image_url = ""
        tryon_quality_passed = False
        tryon_failure_reason = ""
        if person_image_path:
            try:
                tryon_result = self.tryon_service.generate_tryon(
                    person_image_path=person_image_path,
                    product_image_url=garment_image_path,
                )
                if tryon_result.get("success"):
                    quality = self.tryon_quality_gate.evaluate(
                        person_image_path=person_image_path,
                        tryon_result=tryon_result,
                    )
                    if quality.get("passed"):
                        tryon_quality_passed = True
                        tryon_render_path = self._persist_tryon_render(
                            external_user_id=external_user_id,
                            conversation_id=conversation_id,
                            turn_id=turn_id,
                            garment_image_path=garment_image_path,
                            tryon_result=tryon_result,
                            quality=quality,
                        )
                        if tryon_render_path:
                            tryon_image_url = self._tryon_image_url(tryon_render_path)
                    else:
                        tryon_failure_reason = str(quality.get("reason_code") or "quality_gate_failed")
                        _log.info("garment_evaluation tryon failed quality gate: %s", tryon_failure_reason)
                else:
                    tryon_failure_reason = "tryon_generation_failed"
            except Exception as exc:
                tryon_failure_reason = "tryon_exception"
                _log.warning("garment_evaluation tryon raised: %s", exc, exc_info=True)
        else:
            tryon_failure_reason = "missing_person_image"

        # Stage 2: VisualEvaluatorAgent — score the rendered try-on if we have
        # one, otherwise fall back to scoring the bare garment image so the
        # user still gets a meaningful evaluation.
        evaluation_image_path = tryon_render_path or garment_image_path
        synthetic_candidate = OutfitCandidate(
            candidate_id="garment-eval-1",
            direction_id="garment_evaluation",
            candidate_type="single_garment",
            items=[self._attached_item_to_outfit_item(attached_item)],
            assembly_score=1.0,
        )
        live_context_for_eval = LiveContext(
            user_need=message.strip(),
            occasion_signal=plan_result.resolved_context.occasion_signal,
            formality_hint=plan_result.resolved_context.formality_hint,
            time_hint=plan_result.resolved_context.time_hint,
            time_of_day=str(getattr(plan_result.resolved_context, "time_of_day", "") or ""),
            weather_context=str(getattr(plan_result.resolved_context, "weather_context", "") or ""),
            specific_needs=list(plan_result.resolved_context.specific_needs or []),
            is_followup=bool(plan_result.resolved_context.is_followup),
            followup_intent=plan_result.resolved_context.followup_intent,
        )
        try:
            evaluation = self.visual_evaluator.evaluate_candidate(
                candidate=synthetic_candidate,
                image_path=evaluation_image_path,
                user_context=user_context,
                live_context=live_context_for_eval,
                intent=Intent.GARMENT_EVALUATION,
                mode="single_garment",
                profile_confidence_pct=int(profile_confidence.analysis_confidence_pct),
            )
        except Exception as exc:
            _log.error("Garment evaluation failed: %s", exc, exc_info=True)
            return self._garment_evaluation_error_response(
                conversation_id=conversation_id,
                turn_id=turn_id,
                message=message,
                error=str(exc),
            )

        # Item 4 (May 1, 2026): pull token usage from visual evaluator.
        _ge_usage = getattr(self.visual_evaluator, "last_usage", {}) or {}
        self.repo.log_model_call(
            conversation_id=conversation_id,
            turn_id=turn_id,
            service="agentic_application",
            call_type=Intent.GARMENT_EVALUATION,
            model="gpt-5-mini",
            request_json={
                "message": message,
                "tryon_quality_passed": tryon_quality_passed,
                "tryon_failure_reason": tryon_failure_reason or None,
                "purchase_intent": bool(plan_result.action_parameters.purchase_intent),
            },
            response_json=evaluation.model_dump(),
            reasoning_notes=[],
            prompt_tokens=_ge_usage.get("prompt_tokens"),
            completion_tokens=_ge_usage.get("completion_tokens"),
            total_tokens=_ge_usage.get("total_tokens"),
        )

        # Stage 3: Deterministic wardrobe overlap + versatility (no LLM)
        wardrobe_items = list(getattr(user_context, "wardrobe_items", []) or [])
        wardrobe_overlap = self._compute_wardrobe_overlap(
            attached_item=attached_item,
            wardrobe_items=wardrobe_items,
        )
        versatility = self._compute_wardrobe_versatility(
            attached_item=attached_item,
            wardrobe_items=wardrobe_items,
        )

        # Stage 4: Optional buy/skip verdict (only if purchase_intent)
        purchase_intent = bool(plan_result.action_parameters.purchase_intent)
        verdict = ""
        if purchase_intent:
            verdict = self._compute_purchase_verdict(
                evaluation=evaluation,
                wardrobe_overlap=wardrobe_overlap,
            )

        # Stage 5: Build the response card + assistant message
        outfit_card = OutfitCard(
            rank=1,
            title="Garment Evaluation",
            reasoning=evaluation.overall_note or evaluation.reasoning,
            body_note=evaluation.body_note,
            color_note=evaluation.color_note,
            style_note=evaluation.style_note,
            occasion_note=evaluation.occasion_note,
            # 5 always-evaluated dimensions — risk_tolerance + comfort_boundary
            # were missing from this card construction prior to the
            # April 9 2026 follow-up (only 5 of the 9 dimensions were
            # being plumbed through to the garment_evaluation PDP card).
            body_harmony_pct=evaluation.body_harmony_pct,
            color_suitability_pct=evaluation.color_suitability_pct,
            style_fit_pct=evaluation.style_fit_pct,
            risk_tolerance_pct=evaluation.risk_tolerance_pct,
            comfort_boundary_pct=evaluation.comfort_boundary_pct,
            # 4 context-gated dimensions — None when their gating condition
            # is not met. pairing_coherence_pct is null for garment_evaluation
            # (this handler) because we're judging a single piece in
            # isolation, not pairing anything. The other 3 are null when
            # their live_context inputs are absent. The frontend drops these
            # from the radar chart when null.
            pairing_coherence_pct=evaluation.pairing_coherence_pct,
            occasion_pct=evaluation.occasion_pct,
            specific_needs_pct=evaluation.specific_needs_pct,
            weather_time_pct=evaluation.weather_time_pct,
            classic_pct=evaluation.classic_pct,
            dramatic_pct=evaluation.dramatic_pct,
            romantic_pct=evaluation.romantic_pct,
            natural_pct=evaluation.natural_pct,
            minimalist_pct=evaluation.minimalist_pct,
            creative_pct=evaluation.creative_pct,
            sporty_pct=evaluation.sporty_pct,
            edgy_pct=evaluation.edgy_pct,
            items=[self._attached_item_to_outfit_item(attached_item)],
            tryon_image=tryon_image_url or None,
        )

        assistant_parts: List[str] = []
        if purchase_intent and verdict:
            verdict_label = {
                "buy": "Buy it.",
                "skip": "I'd skip it.",
                "conditional": "Buy it with one caveat.",
            }.get(verdict, "")
            if verdict_label:
                assistant_parts.append(verdict_label)
        if evaluation.overall_note:
            assistant_parts.append(evaluation.overall_note.strip())
        if wardrobe_overlap.get("has_duplicate"):
            duplicate = str(wardrobe_overlap.get("duplicate_detail") or "").strip()
            if duplicate:
                assistant_parts.append(f"Heads up — your wardrobe already has {duplicate}.")
        if not tryon_quality_passed and tryon_failure_reason:
            if tryon_failure_reason == "missing_person_image":
                assistant_parts.append(
                    "I scored this from your profile — upload a full-body photo of yourself "
                    "and I can render it on you for a richer take next time."
                )
            else:
                assistant_parts.append(
                    "I couldn't render a clean try-on this round, so I scored the piece "
                    "from the photo and your profile."
                )
        assistant_message = " ".join(part for part in assistant_parts if part).strip()
        if not assistant_message:
            assistant_message = "I evaluated this piece against your profile."

        follow_up_suggestions = list(plan_result.follow_up_suggestions[:5] or [])
        if not follow_up_suggestions:
            if purchase_intent:
                follow_up_suggestions = [
                    "What goes with this?",
                    "Show me alternatives",
                    "Save to wardrobe",
                ]
            else:
                follow_up_suggestions = [
                    "What goes with this?",
                    "Try on something else",
                    "Save to wardrobe",
                ]

        handler_payload = {
            "evaluator": "visual_evaluator",
            "tryon_quality_passed": tryon_quality_passed,
            "tryon_failure_reason": tryon_failure_reason or None,
            "purchase_intent": purchase_intent,
            "verdict": verdict or None,
            "wardrobe_overlap": wardrobe_overlap,
            "wardrobe_versatility": versatility,
            "scores": {
                "body_harmony_pct": evaluation.body_harmony_pct,
                "color_suitability_pct": evaluation.color_suitability_pct,
                "style_fit_pct": evaluation.style_fit_pct,
                "occasion_pct": evaluation.occasion_pct,
                "weather_time_pct": evaluation.weather_time_pct,
                "pairing_coherence_pct": evaluation.pairing_coherence_pct,
            },
            "strengths": list(evaluation.strengths or []),
            "improvements": list(evaluation.improvements or []),
        }
        metadata = self._build_response_metadata(
            channel=channel,
            intent=intent,
            profile_confidence=profile_confidence,
            extra={
                "answer_source": "garment_evaluation_handler",
                "garment_evaluation": handler_payload,
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
                "handler": Intent.GARMENT_EVALUATION,
                "handler_payload": handler_payload,
                "channel": channel,
                "outfits": [outfit_card.model_dump()],
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
                "answer_source": "garment_evaluation_handler",
                "purchase_intent": purchase_intent,
                "verdict": verdict or None,
                "tryon_quality_passed": tryon_quality_passed,
            },
        )
        return {
            "conversation_id": conversation_id,
            "turn_id": turn_id,
            "assistant_message": assistant_message,
            "response_type": "recommendation",
            "resolved_context": {
                "request_summary": message.strip(),
                "occasion": str(plan_result.resolved_context.occasion_signal or ""),
                "style_goal": Intent.GARMENT_EVALUATION,
                "purchase_intent": purchase_intent,
            },
            "filters_applied": {},
            "outfits": [outfit_card.model_dump()],
            "follow_up_suggestions": follow_up_suggestions,
            "metadata": metadata,
        }

    @staticmethod
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

    @staticmethod
    def _compute_purchase_verdict(
        *,
        evaluation: EvaluatedRecommendation,
        wardrobe_overlap: Dict[str, Any],
    ) -> str:
        """Deterministic buy/skip/conditional verdict from evaluator scores.

        Phase 12B follow-up (April 9 2026): the average is computed over
        only the dimensions that were actually evaluated. The 3
        always-evaluated dimensions (body / color / style) are always in
        the average; occasion_pct and weather_time_pct are added only
        when the model returned a non-null score for them. Previously
        the average was a fixed 5-dimension mean — when the user didn't
        name an occasion or weather, two of those five contributed
        synthetic neutral defaults and the buy/skip recommendation was
        partially built on fake data.

        Phase 12B initial thresholds (calibrate from staging telemetry
        in Phase 12E):
            - strong wardrobe duplicate → skip (overrides scores)
            - average score >= 78 AND no strong duplicate → buy
            - average score >= 60 → conditional
            - else → skip
        """
        if str(wardrobe_overlap.get("overlap_level") or "").lower() == "strong":
            return "skip"
        # Always-evaluated dimensions for the verdict — body, color, style.
        # We deliberately exclude risk_tolerance, comfort_boundary, and
        # pairing_coherence from the verdict average even though they are
        # always evaluated, because the verdict is about "is this piece a
        # good buy on its objective merits?", not about how risky it is or
        # how easy it pairs. (Those are surfaced separately on the card.)
        scores: List[int] = [
            evaluation.body_harmony_pct,
            evaluation.color_suitability_pct,
            evaluation.style_fit_pct,
        ]
        if evaluation.occasion_pct is not None:
            scores.append(evaluation.occasion_pct)
        if evaluation.weather_time_pct is not None:
            scores.append(evaluation.weather_time_pct)
        avg = sum(scores) / len(scores)
        if avg >= 78:
            return "buy"
        if avg >= 60:
            return "conditional"
        return "skip"

    @staticmethod
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

    def _build_outfit_check_wardrobe_suggestions(
        self,
        *,
        wardrobe_items: List[Dict[str, Any]],
        improvements: List[Dict[str, Any]],
        occasion_signal: str | None,
    ) -> List[Dict[str, str]]:
        suggestions: List[Dict[str, str]] = []
        seen_titles: set[str] = set()
        for item in improvements:
            if self._normalize_text_token(item.get("swap_source")) != "wardrobe":
                continue
            swap_detail = str(item.get("swap_detail") or "").strip()
            if not swap_detail:
                continue
            normalized_title = self._normalize_text_token(swap_detail)
            if not normalized_title or normalized_title in seen_titles:
                continue
            suggestions.append(
                {
                    "title": swap_detail,
                    "reason": str(item.get("suggestion") or "").strip(),
                    "source": "improvement_swap",
                }
            )
            seen_titles.add(normalized_title)

        normalized_occasion = self._normalize_text_token(occasion_signal)
        for row in wardrobe_items:
            title = str(row.get("title") or "").strip()
            if not title:
                continue
            normalized_title = self._normalize_text_token(title)
            if not normalized_title or normalized_title in seen_titles:
                continue
            occasion_fit = self._normalize_text_token(row.get("occasion_fit"))
            formality_level = self._normalize_text_token(row.get("formality_level"))
            if normalized_occasion and normalized_occasion not in {occasion_fit, formality_level}:
                continue
            role = str(row.get("garment_category") or row.get("garment_subtype") or "piece").strip()
            color = str(row.get("primary_color") or "").strip()
            detail = re.sub(r"\s+", " ", f"{color} {role}".strip())
            if detail and occasion_signal:
                reason = f"A {detail} from your wardrobe can tighten the look for {occasion_signal}."
            else:
                reason = "This could strengthen the outfit using pieces you already own."
            suggestions.append(
                {
                    "title": title,
                    "reason": reason,
                    "source": "occasion_match",
                }
            )
            seen_titles.add(normalized_title)
            if len(suggestions) >= 3:
                break
        return suggestions[:3]

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
                }
            )
        return summaries


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
