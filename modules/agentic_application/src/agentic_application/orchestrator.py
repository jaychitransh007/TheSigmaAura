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

from .agents.catalog_search_agent import CatalogSearchAgent
from .agents.copilot_planner import CopilotPlanner, build_planner_input
from .agents.outfit_check_agent import OutfitCheckAgent
from .agents.shopping_decision_agent import ShoppingDecisionAgent, extract_urls
from .agents.outfit_architect import OutfitArchitect
from .agents.outfit_assembler import OutfitAssembler
from .agents.outfit_evaluator import OutfitEvaluator
from .agents.response_formatter import ResponseFormatter
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
    IntentClassification,
    LiveContext,
    OutfitCard,
    ProfileConfidence,
    RecommendationConfidence,
    RetrievedProduct,
    RetrievedSet,
)

_log = logging.getLogger(__name__)


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
        self.outfit_check_agent = OutfitCheckAgent()
        self.shopping_decision_agent = ShoppingDecisionAgent()
        self.catalog_search_agent = CatalogSearchAgent(
            retrieval_gateway=self._retrieval_gateway,
            client=repo.client,
        )
        self.outfit_assembler = OutfitAssembler()
        self.outfit_evaluator = OutfitEvaluator()
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

    def _infer_followup_intent_override(self, *, message: str) -> str:
        normalized = self._normalize_text_token(message)
        if not normalized:
            return ""
        if any(token in normalized for token in ("smarter", "more polished", "more polish", "sharper", "dressier", "more refined")):
            return FollowUpIntent.INCREASE_FORMALITY
        if any(token in normalized for token in ("more casual", "less dressy", "more relaxed")):
            return FollowUpIntent.DECREASE_FORMALITY
        return ""

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

    def _message_requests_outfit_check(self, *, message: str) -> bool:
        normalized = self._normalize_text_token(message)
        if not normalized:
            return False
        direct_phrases = (
            "rate my outfit",
            "rate this outfit",
            "how does this look",
            "outfit check",
            "review this outfit",
            "judge my outfit",
        )
        if any(phrase in normalized for phrase in direct_phrases):
            return True
        return normalized.startswith("is this outfit")

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
        source_preference = self._message_source_preference(message=message)
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

        followup_override = self._infer_followup_intent_override(message=message)
        if followup_override:
            plan_result.resolved_context.followup_intent = followup_override
            if followup_override == FollowUpIntent.INCREASE_FORMALITY:
                plan_result.resolved_context.formality_hint = (
                    plan_result.resolved_context.formality_hint or "smart_casual"
                )
            if "followup_phrase_override" not in override_reasons:
                override_reasons.append("followup_phrase_override")

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

        if self._message_requests_outfit_check(message=message):
            if plan_result.intent != Intent.OUTFIT_CHECK:
                plan_result.intent = Intent.OUTFIT_CHECK
                plan_result.action = Action.RUN_OUTFIT_CHECK
            if not str(plan_result.resolved_context.style_goal or "").strip():
                plan_result.resolved_context.style_goal = Intent.OUTFIT_CHECK
            if "outfit_check_override" not in override_reasons:
                override_reasons.append("outfit_check_override")

        if source_preference == "wardrobe":
            if "wardrobe_first" not in plan_result.resolved_context.specific_needs:
                plan_result.resolved_context.specific_needs.append("wardrobe_first")
            if "wardrobe_source_override" not in override_reasons:
                override_reasons.append("wardrobe_source_override")
        elif source_preference == "catalog":
            if "catalog_only" not in plan_result.resolved_context.specific_needs:
                plan_result.resolved_context.specific_needs.append("catalog_only")
            if "catalog_source_override" not in override_reasons:
                override_reasons.append("catalog_source_override")

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
        stage_callback: Optional[Callable[[str, str, str], None]] = None,
    ) -> Dict[str, Any]:
        def emit(stage: str, detail: str = "", ctx: dict | None = None) -> None:
            if stage_callback is not None:
                msg = generate_stage_message(stage, detail, ctx)
                stage_callback(stage, detail, msg)

        # --- Validate request ---
        emit("validate_request", "started")
        user_row = self.repo.get_or_create_user(external_user_id)
        conversation = self.repo.get_conversation(conversation_id)
        if not conversation:
            raise ValueError("Conversation not found.")
        if conversation.get("user_id") != user_row.get("id"):
            raise ValueError("Conversation does not belong to user.")
        previous_context = dict(conversation.get("session_context_json") or {})
        turn = self.repo.create_turn(conversation_id=conversation_id, user_message=message)
        turn_id = str(turn["id"])
        attached_item: Dict[str, Any] | None = None
        effective_message = message
        if image_data:
            try:
                attached_item = self.onboarding_gateway.save_uploaded_chat_wardrobe_item(
                    user_id=external_user_id,
                    image_data=image_data,
                    description=message.strip(),
                    notes="Captured from chat image attachment.",
                )
                _log.info("Attached item saved: %s", {k: str(v)[:50] for k, v in (attached_item or {}).items()} if attached_item else None)
            except Exception:
                _log.exception("Failed to save attached item — attached_item will be None")
                attached_item = None
            attachment_source = self._uploaded_image_anchor_source(message=message)
            if attached_item is not None:
                attached_item = dict(attached_item)
                attached_item["attachment_source"] = attachment_source
            attached_context = self._attached_item_context(attached_item)
            if attached_context:
                effective_message = f"{message.strip()} {attached_context}".strip()
            if attached_item is not None:
                effective_message = f"{effective_message} Image anchor source: {attachment_source.replace('_', ' ')}.".strip()
        # --- 0.5 Onboarding Gate ---
        emit("onboarding_gate", "started")
        onboarding_status = self.onboarding_gateway.get_onboarding_status(external_user_id)
        analysis_status = self.onboarding_gateway.get_analysis_status(external_user_id)
        onboarding_gate = evaluate_onboarding_gate(onboarding_status, analysis_status)
        if not onboarding_gate.allowed:
            emit("onboarding_gate", "blocked")
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

        # --- Copilot Planner path ---
        profile_confidence = onboarding_gate.profile_confidence

        # Build user context
        emit("user_context", "started")
        user_context = build_user_context(
            external_user_id,
            onboarding_gateway=self.onboarding_gateway,
        )
        validate_minimum_profile(user_context)
        emit("user_context", "completed", ctx={"richness": user_context.profile_richness})

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
                model="gpt-5.4",
                request_json={"message": effective_message},
                response_json={},
                reasoning_notes=[],
                latency_ms=planner_ms,
                status="error",
                error_message=str(exc),
            )
            emit("copilot_planner", "error")
            fallback_message = "I'm having trouble processing your request right now. Please try again."
            self.repo.finalize_turn(
                turn_id=turn_id,
                assistant_message=fallback_message,
                resolved_context={"error": str(exc), "request_summary": message.strip()},
            )
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
        self.repo.log_model_call(
            conversation_id=conversation_id,
            turn_id=turn_id,
            service="agentic_application",
            call_type="copilot_planner",
            model="gpt-5.4",
            request_json={"message": effective_message, "intent": plan_result.intent},
            response_json={
                "intent": plan_result.intent,
                "action": plan_result.action,
                "intent_confidence": plan_result.intent_confidence,
            },
            reasoning_notes=[],
            latency_ms=planner_ms,
        )
        emit("copilot_planner", "completed", ctx={
            "intent": plan_result.intent,
            "action": plan_result.action,
        })

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

        # Build intent classification for metadata compatibility
        intent = IntentClassification(
            primary_intent=plan_result.intent,
            confidence=plan_result.intent_confidence,
            reason_codes=["copilot_planner", *override_reasons],
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

        # Dispatch on action
        if plan_result.action == Action.RESPOND_DIRECTLY:
            return self._handle_direct_response(
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
            return self._handle_clarification(
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
            return self._handle_planner_pipeline(
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
            )
        elif plan_result.action == Action.RUN_OUTFIT_CHECK:
            return self._handle_outfit_check(
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
        elif plan_result.action == Action.RUN_SHOPPING_DECISION:
            return self._handle_shopping_decision(
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

            )
        elif plan_result.action == Action.RUN_VIRTUAL_TRYON:
            return self._handle_planner_virtual_tryon(
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
        elif plan_result.action == Action.SAVE_WARDROBE_ITEM:
            return self._handle_planner_wardrobe_save(
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
            return self._handle_planner_feedback(
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
        elif plan_result.action == Action.RUN_PRODUCT_BROWSE:
            return self._handle_product_browse(
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
                emit=emit,
            )
        else:
            # Unknown action — fall back to direct response
            _log.warning("Unknown planner action: %s, falling back to direct response", plan_result.action)
            return self._handle_direct_response(
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
        if len(outfit) <= 1 and "one piece" not in outfit_roles and "one_piece" not in outfit_roles:
            return None
        anchor_id = str(anchored_item_id or "").strip()
        selected_ids = [str(item.get("product_id") or "") for item in outfit if str(item.get("product_id") or "").strip()]
        if anchor_id and len(selected_ids) <= 1 and selected_ids == [anchor_id]:
            return None

        reasoning = f"Built from your saved wardrobe for {occasion.replace('_', ' ')}."
        catalog_upsell = self._build_catalog_upsell(
            rationale="Your wardrobe covers the occasion first, but I can also show stronger catalog options if you want a more elevated or optimized version.",
            entry_intent=Intent.OCCASION_RECOMMENDATION,
        )
        source_selection = self._build_source_selection(
            preferred_source="wardrobe" if "wardrobe_first" in list(live_context.specific_needs or []) else "",
            fulfilled_source="wardrobe",
        )
        outfit_card = OutfitCard(
            rank=1,
            title=f"Wardrobe-first {occasion.replace('_', ' ').title()} look",
            reasoning=reasoning,
            occasion_note=reasoning,
            items=outfit,
        )
        answer_components = self._summarize_answer_components([outfit_card])
        recommendation_confidence = evaluate_recommendation_confidence(
            answer_mode="wardrobe_first",
            profile_confidence_score_pct=profile_confidence.analysis_confidence_pct,
            intent_confidence=float(intent.confidence),
            top_match_score=0.9,
            second_match_score=0.0,
            retrieved_product_count=0,
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
                "answer_source": "wardrobe_first",
                "answer_components": answer_components,
                "source_selection": source_selection,
                "catalog_upsell": catalog_upsell,
                "recommendation_confidence": recommendation_confidence.model_dump(),
                "restricted_item_exclusion_count": len(blocked_terms),
                "wardrobe_gap_analysis": wardrobe_gap_analysis,
                "routing_metadata": routing_metadata,
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
                "handler": "occasion_recommendation_wardrobe_first",
                "handler_payload": {
                    "answer_source": "wardrobe_first",
                    "selected_item_ids": [str(item.get("product_id") or "") for item in outfit],
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
                    "candidate_id": "wardrobe-first-1",
                    "rank": 1,
                    "title": outfit_card.title,
                    "item_ids": [str(item.get("product_id") or "") for item in outfit],
                    "match_score": 0.9,
                    "reasoning": reasoning,
                }
            ],
            "channel": channel,
        }
        self.repo.finalize_turn(
            turn_id=turn_id,
            assistant_message=reasoning + " If you want, I can also show better catalog options for this occasion.",
            resolved_context=resolved_context,
        )
        self._persist_recommendation_confidence(
            external_user_id=external_user_id,
            conversation_id=conversation_id,
            turn_id=turn_id,
            channel=channel,
            primary_intent=intent.primary_intent,
            recommendation_confidence=recommendation_confidence,
            metadata_json={"answer_mode": "wardrobe_first"},
        )
        session_context = {
            **previous_context,
            "memory": conversation_memory,
            "last_occasion": occasion,
            "last_live_context": live_context.model_dump(),
            "last_response_metadata": metadata,
            "last_assistant_message": reasoning + " If you want, I can also show better catalog options for this occasion.",
            "last_user_message": message,
            "last_channel": channel,
            "last_intent": intent.primary_intent,
            "consecutive_gate_blocks": 0,
            "last_recommendations": [
                {
                    "candidate_id": "wardrobe-first-1",
                    "rank": 1,
                    "title": outfit_card.title,
                    "item_ids": [str(item.get("product_id") or "") for item in outfit],
                    "candidate_type": "wardrobe",
                    "direction_id": "wardrobe",
                    "primary_colors": [str(item.get("primary_color") or "") for item in outfit if str(item.get("primary_color") or "").strip()],
                    "garment_categories": [str(item.get("garment_category") or "") for item in outfit if str(item.get("garment_category") or "").strip()],
                    "garment_subtypes": [str(item.get("garment_subtype") or "") for item in outfit if str(item.get("garment_subtype") or "").strip()],
                    "roles": [str(item.get("role") or "") for item in outfit if str(item.get("role") or "").strip()],
                    "occasion_fits": [occasion],
                    "formality_levels": [str(item.get("formality_level") or "") for item in outfit if str(item.get("formality_level") or "").strip()],
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
                "answer_source": "wardrobe_first",
                "memory_sources_read": list(routing_metadata.get("memory_sources_read") or []),
                "memory_sources_written": list(routing_metadata.get("memory_sources_written") or []),
                "recommendation_confidence_score_pct": recommendation_confidence.score_pct,
                "wardrobe_gap_count": len(list(wardrobe_gap_analysis.get("gap_items") or [])),
            },
        )
        return {
            "conversation_id": conversation_id,
            "turn_id": turn_id,
            "assistant_message": reasoning + " If you want, I can also show better catalog options for this occasion.",
            "response_type": "recommendation",
            "resolved_context": {
                "request_summary": message.strip(),
                "occasion": occasion,
                "style_goal": "wardrobe_first",
                "profile_confidence_pct": profile_confidence.analysis_confidence_pct,
            },
            "filters_applied": {},
            "outfits": [outfit_card.model_dump()],
            "follow_up_suggestions": ["Show me more from my wardrobe", "Show me catalog alternatives", str(catalog_upsell["cta"])],
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
        if wardrobe_items:
            assistant_message = (
                f"I can't build a complete {occasion.replace('_', ' ') if occasion else 'occasion'} outfit purely from your saved wardrobe yet."
                + (f" You're still missing {', '.join(gap_items[:2])}." if gap_items else "")
                + " If you want, I can show catalog options to fill those gaps."
            )
        else:
            assistant_message = (
                "I don't have enough saved wardrobe pieces yet to build this outfit from your wardrobe."
                " Add a few staples first, or I can show catalog options for the occasion."
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
            "follow_up_suggestions": ["Save wardrobe staples", str(catalog_upsell["cta"])],
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

                "handler": "pairing_request_catalog_image",
                "handler_payload": {
                    "answer_source": "catalog_image_pairing",
                    "answer_components": answer_components,
                    "source_selection": source_selection,
                    "anchor_source": "catalog_image",
                    "anchor_item_title": str(item.get("title") or ""),
                    "catalog_item_ids": [str(candidate.get("product_id") or "") for candidate in catalog_items],
                },
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

    def _run_virtual_tryon_request(
        self,
        *,
        external_user_id: str,
        message: str,
    ) -> Dict[str, Any]:
        urls = re.findall(r"https?://\S+", str(message or "").strip())
        product_url = urls[0] if urls else ""
        person_image_path = self.onboarding_gateway.get_person_image_path(external_user_id)
        if not person_image_path:
            return {
                "success": False,
                "reason_code": "missing_person_image",
                "error": graceful_policy_message("missing_person_image"),
                "product_url": product_url,
            }
        if not product_url:
            return {
                "success": False,
                "error": "No product image or link found in the request.",
                "product_url": "",
            }
        try:
            result = self.tryon_service.generate_tryon(
                person_image_path=person_image_path,
                product_image_url=product_url,
            )
            result["product_url"] = product_url
            if result.get("success"):
                quality = self.tryon_quality_gate.evaluate(
                    person_image_path=person_image_path,
                    tryon_result=result,
                )
                result["quality_gate"] = quality
                if not quality.get("passed"):
                    reason_code = str(quality.get("reason_code") or "quality_gate_failed")
                    result["success"] = False
                    result["reason_code"] = reason_code
                    result["error"] = graceful_policy_message(
                        reason_code,
                        default=str(quality.get("message") or "Generated try-on output failed quality checks."),
                    )
            return result
        except Exception as exc:
            return {
                "success": False,
                "reason_code": "tryon_request_failed",
                "error": str(exc),
                "product_url": product_url,
            }

    # ------------------------------------------------------------------
    # Conversation history
    # ------------------------------------------------------------------

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
        if intent.primary_intent == Intent.CAPSULE_OR_TRIP_PLANNING:
            return self._handle_capsule_or_trip_planning(
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
                "answer_source": "style_discovery_handler",
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

        explanation_parts: List[str] = []
        if title:
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
        else:
            explanation_parts.append("It was the strongest match among the options available at the time.")

        assistant_message = " ".join(part for part in explanation_parts if part).strip() or plan_result.assistant_message
        metadata = self._build_response_metadata(
            channel=channel,
            intent=intent,
            profile_confidence=profile_confidence,
            extra={
                "answer_source": "explanation_handler",
                "explanation": {
                    "target_title": title,
                    "target_colors": colors,
                    "target_categories": categories,
                    "target_occasions": occasion_fits,
                    "recommendation_confidence_band": confidence_band,
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

    def _infer_capsule_target(self, *, message: str, style_goal: str) -> tuple[int, int, list[str]]:
        normalized_message = self._normalize_text_token(message)
        normalized_goal = self._normalize_text_token(style_goal)
        combined = f"{normalized_message} {normalized_goal}".strip()
        days = 0
        match = re.search(r"\b(\d+)\s*day\b", combined)
        if match:
            days = max(1, int(match.group(1)))
        elif "workweek" in combined:
            days = 5
        elif "weekend" in combined:
            days = 2
        elif "trip" in combined or "travel" in combined:
            days = 3

        if days <= 0:
            days = 3
        target = min(10, max(3, days * 2))
        context_labels = [
            "travel day",
            "daytime",
            "meeting",
            "dinner",
            "off duty",
            "evening",
            "city walk",
            "smart casual",
            "dinner out",
            "travel return",
        ]
        contexts = [context_labels[index % len(context_labels)] for index in range(target)]
        return days, target, contexts

    def _handle_capsule_or_trip_planning(
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
        wardrobe_items = list(self.onboarding_gateway.get_wardrobe_items(external_user_id) or [])
        wardrobe_gap_analysis = self._build_wardrobe_gap_analysis(
            wardrobe_items=wardrobe_items,
            occasion=str(plan_result.resolved_context.occasion_signal or ""),
            required_roles=["top", "bottom", "shoe"],
        )
        if not wardrobe_items:
            assistant_message = (
                "I can plan this, but I need a bit more wardrobe depth first. "
                "Add a few staples and I can turn them into a tighter trip or workweek capsule."
            )
            metadata = self._build_response_metadata(
                channel=channel,
                intent=intent,
                profile_confidence=profile_confidence,
                extra={
                    "answer_source": "capsule_planning_handler",
                    "capsule_plan": {"outfit_count": 0, "packing_list": [], "gap_items": []},
                    "wardrobe_gap_analysis": wardrobe_gap_analysis,
                },
            )
            self.repo.finalize_turn(
                turn_id=turn_id,
                assistant_message=assistant_message,
                resolved_context={
                    "request_summary": message.strip(),
                    "intent_classification": intent.model_dump(),
                    "profile_confidence": profile_confidence.model_dump(),
    
                    "handler": Intent.CAPSULE_OR_TRIP_PLANNING,
                    "channel": channel,
                },
            )
            return {
                "conversation_id": conversation_id,
                "turn_id": turn_id,
                "assistant_message": assistant_message,
                "response_type": "recommendation",
                "resolved_context": {
                    "request_summary": message.strip(),
                    "occasion": "",
                    "style_goal": "capsule_or_trip_planning",
                },
                "filters_applied": {},
                "outfits": [],
                "follow_up_suggestions": ["Save wardrobe staples", "Show me catalog essentials", "Use my wardrobe first"],
                "metadata": metadata,
            }

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

        trip_days, target_outfit_count, context_labels = self._infer_capsule_target(
            message=message,
            style_goal=plan_result.resolved_context.style_goal or "",
        )
        tops = [dict(item, _role="top") for item in wardrobe_items if role_of(item) == "top"]
        bottoms = [dict(item, _role="bottom") for item in wardrobe_items if role_of(item) == "bottom"]
        one_pieces = [dict(item, _role="one_piece") for item in wardrobe_items if role_of(item) == "one_piece"]
        shoes = [dict(item, _role="shoe") for item in wardrobe_items if role_of(item) == "shoe"]

        outfits: List[OutfitCard] = []
        candidate_sets: List[List[Dict[str, Any]]] = []
        seen_signatures: set[tuple[str, ...]] = set()

        def add_candidate(items: List[Dict[str, Any]]) -> None:
            signature = tuple(sorted(str(item.get("id") or item.get("product_id") or "") for item in items if str(item.get("id") or item.get("product_id") or "").strip()))
            if not signature or signature in seen_signatures:
                return
            seen_signatures.add(signature)
            candidate_sets.append(items)

        for index, item in enumerate(one_pieces):
            items = [item]
            if shoes:
                items.append(shoes[index % len(shoes)])
            add_candidate(items)

        for top_index, top in enumerate(tops):
            for bottom_index, bottom in enumerate(bottoms):
                items = [top, bottom]
                if shoes:
                    items.append(shoes[(top_index + bottom_index) % len(shoes)])
                add_candidate(items)

        usage_count: Dict[str, int] = {}
        selected_sets: List[List[Dict[str, Any]]] = []
        remaining_candidates = list(candidate_sets)
        while remaining_candidates and len(selected_sets) < min(target_outfit_count, len(candidate_sets)):
            best_index = 0
            best_score = -999
            for index, items in enumerate(remaining_candidates):
                novelty = sum(max(0, 3 - usage_count.get(str(item.get("id") or item.get("product_id") or ""), 0)) for item in items)
                role_variety = len({role_of(item) for item in items})
                score = novelty + role_variety
                if score > best_score:
                    best_score = score
                    best_index = index
            chosen = remaining_candidates.pop(best_index)
            selected_sets.append(chosen)
            for item in chosen:
                item_id = str(item.get("id") or item.get("product_id") or "")
                usage_count[item_id] = usage_count.get(item_id, 0) + 1

        for rank, items in enumerate(selected_sets, start=1):
            context_label = context_labels[rank - 1]
            outfit_items = [self._wardrobe_item_to_outfit_item(item) for item in items]
            outfits.append(
                OutfitCard(
                    rank=rank,
                    title=f"{context_label.title()} look",
                    reasoning=f"Built from your wardrobe for the {context_label} part of the plan while keeping the capsule reusable.",
                    items=outfit_items,
                )
            )

        packing_map: Dict[str, Dict[str, Any]] = {}
        for outfit in outfits:
            for item in outfit.items:
                product_id = str(item.get("product_id") or "")
                if product_id and product_id not in packing_map:
                    packing_map[product_id] = item
        packing_list = list(packing_map.values())

        gap_items: List[str] = []
        if not bottoms:
            gap_items.append("a versatile trouser or skirt")
        if not tops:
            gap_items.append("an easy top layer")
        if not shoes:
            gap_items.append("a flexible shoe option")
        if len(outfits) < target_outfit_count:
            gap_items.append("one more mix-and-match staple to make the capsule more reusable")
        desired_gap_roles = [
            role
            for role, count in dict(wardrobe_gap_analysis.get("counts_by_role") or {}).items()
            if role in {"top", "bottom", "shoe", "outerwear"} and int(count or 0) == 0
        ]
        if len(outfits) < target_outfit_count:
            desired_gap_roles.extend(["top", "bottom"])
        catalog_gap_fillers = self._select_catalog_items(
            desired_roles=_dedupe_values(desired_gap_roles or ["top", "bottom", "shoe"]),
            occasion=str(plan_result.resolved_context.occasion_signal or ""),
            preferred_colors=[
                str(item.get("primary_color") or "")
                for outfit in outfits
                for item in outfit.items
                if str(item.get("primary_color") or "").strip()
            ],
            limit=3,
        )
        hybrid_index = len(outfits)
        while len(outfits) < target_outfit_count and catalog_gap_fillers:
            filler = catalog_gap_fillers[(len(outfits) - hybrid_index) % len(catalog_gap_fillers)]
            filler_role = self._wardrobe_role_of(filler)
            hybrid_items: List[Dict[str, Any]] = []
            if filler_role != "top" and tops:
                hybrid_items.append(self._wardrobe_item_to_outfit_item(tops[len(outfits) % len(tops)]))
            if filler_role != "bottom" and bottoms:
                hybrid_items.append(self._wardrobe_item_to_outfit_item(bottoms[len(outfits) % len(bottoms)]))
            if filler_role != "shoe" and shoes:
                hybrid_items.append(self._wardrobe_item_to_outfit_item(shoes[len(outfits) % len(shoes)]))
            hybrid_items.append(filler)
            deduped_hybrid: List[Dict[str, Any]] = []
            seen_hybrid_ids: set[str] = set()
            for item in hybrid_items:
                item_id = str(item.get("product_id") or "")
                if item_id and item_id in seen_hybrid_ids:
                    continue
                seen_hybrid_ids.add(item_id)
                deduped_hybrid.append(item)
            if len(deduped_hybrid) < 2:
                break
            context_label = context_labels[len(outfits)]
            outfits.append(
                OutfitCard(
                    rank=len(outfits) + 1,
                    title=f"{context_label.title()} hybrid look",
                    reasoning="Extended the capsule with one catalog-supported piece so the trip can cover more moments without overpacking.",
                    items=deduped_hybrid,
                )
            )
            for item in deduped_hybrid:
                product_id = str(item.get("product_id") or "")
                if product_id and product_id not in packing_map:
                    packing_map[product_id] = item
        if outfits and len(outfits) < target_outfit_count:
            repeat_seed = [outfit.model_copy() for outfit in outfits]
            while len(outfits) < target_outfit_count:
                base = repeat_seed[len(outfits) % len(repeat_seed)]
                context_label = context_labels[len(outfits)]
                repeated_items = [dict(item) for item in base.items]
                outfits.append(
                    OutfitCard(
                        rank=len(outfits) + 1,
                        title=f"{context_label.title()} repeated capsule look",
                        reasoning="Reused your strongest capsule base for another part of the trip so you can cover more moments without overpacking.",
                        items=repeated_items,
                    )
                )
                for item in repeated_items:
                    product_id = str(item.get("product_id") or "")
                    if product_id and product_id not in packing_map:
                        packing_map[product_id] = item
        packing_list = list(packing_map.values())

        style_preference = dict((analysis_status.get("profile") or {}).get("style_preference") or {})
        primary = str(style_preference.get("primaryArchetype") or "").strip()
        assistant_parts = []
        if outfits:
            assistant_parts.append(
                f"I mapped out {len(outfits)} looks across {trip_days} days so the capsule can cover multiple moments of the trip."
            )
        if primary:
            assistant_parts.append(f"I kept the capsule aligned with your {primary} style direction.")
        if gap_items:
            assistant_parts.append("The main gaps are " + ", ".join(gap_items[:2]) + ".")
        if catalog_gap_fillers:
            assistant_parts.append(
                "To close them fast, start with "
                + ", ".join(str(item.get("title") or "a catalog piece").strip() for item in catalog_gap_fillers[:2])
                + "."
            )
        assistant_parts.append(
            "If you want, I can turn the gaps into a short shopping list next."
        )
        assistant_message = " ".join(assistant_parts).strip()

        metadata = self._build_response_metadata(
            channel=channel,
            intent=intent,
            profile_confidence=profile_confidence,
            extra={
                "answer_source": "capsule_planning_handler",
                "capsule_plan": {
                    "trip_days": trip_days,
                    "target_outfit_count": target_outfit_count,
                    "outfit_count": len(outfits),
                    "contexts": context_labels[:len(outfits)],
                    "packing_list": [
                        {
                            "product_id": str(item.get("product_id") or ""),
                            "title": str(item.get("title") or ""),
                            "source": str(item.get("source") or "wardrobe"),
                        }
                        for item in packing_list
                    ],
                    "gap_items": gap_items,
                    "catalog_gap_fillers": [
                        {
                            "product_id": str(item.get("product_id") or ""),
                            "title": str(item.get("title") or ""),
                            "product_url": str(item.get("product_url") or ""),
                            "source": str(item.get("source") or "catalog"),
                        }
                        for item in catalog_gap_fillers
                    ],
                },
                "wardrobe_gap_analysis": wardrobe_gap_analysis,
            },
        )
        self.repo.finalize_turn(
            turn_id=turn_id,
            assistant_message=assistant_message,
            resolved_context={
                "request_summary": message.strip(),
                "intent_classification": intent.model_dump(),
                "profile_confidence": profile_confidence.model_dump(),

                "handler": Intent.CAPSULE_OR_TRIP_PLANNING,
                "handler_payload": dict(metadata.get("capsule_plan") or {}),
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
            metadata_json={
                "answer_source": "capsule_planning_handler",
                "trip_days": trip_days,
                "target_outfit_count": target_outfit_count,
                "outfit_count": len(outfits),
                "gap_item_count": len(gap_items),
                "catalog_gap_filler_count": len(catalog_gap_fillers),
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
                "style_goal": plan_result.resolved_context.style_goal or "capsule_or_trip_planning",
                "profile_confidence_pct": profile_confidence.analysis_confidence_pct,
            },
            "filters_applied": {},
            "outfits": [outfit.model_dump() for outfit in outfits],
            "follow_up_suggestions": plan_result.follow_up_suggestions[:5] or ["Build a shopping list", "Show me catalog gap fillers", "Use my wardrobe first"],
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
    ) -> Dict[str, Any]:
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

        previous_recs = previous_context.get("last_recommendations")
        combined_context = CombinedContext(
            user=user_context,
            live=initial_live_context,
            hard_filters=hard_filters,
            previous_recommendations=previous_recs if isinstance(previous_recs, list) else None,
            conversation_memory=conversation_memory,
            conversation_history=conversation_history,
            catalog_inventory=self._catalog_inventory or None,
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
        t0 = time.monotonic()
        try:
            plan = self.outfit_architect.plan(combined_context)
        except Exception as exc:
            architect_ms = int((time.monotonic() - t0) * 1000)
            _log.error("Outfit architect failed: %s", exc, exc_info=True)
            self.repo.log_model_call(
                conversation_id=conversation_id,
                turn_id=turn_id,
                service="agentic_application",
                call_type="outfit_architect",
                model="gpt-5.4",
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
            )
        else:
            effective_live_context = initial_live_context

        self.repo.log_model_call(
            conversation_id=conversation_id,
            turn_id=turn_id,
            service="agentic_application",
            call_type="outfit_architect",
            model="gpt-5.4",
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
        )
        emit("outfit_architect", "completed", ctx={
            "plan_type": plan.plan_type,
            "direction_count": len(plan.directions),
        })

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

        # Stages 4-8: Search → Assemble → Evaluate → Format → TryOn
        emit("catalog_search", "started")
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
        emit("catalog_search", "completed", ctx={
            "product_count": sum(len(rs.products) for rs in retrieved_sets),
            "set_count": len(retrieved_sets),
        })

        # Inject anchor garment as a synthetic retrieved product for paired assembly
        anchor = combined_context.live.anchor_garment
        if anchor and plan.plan_type == "paired_only":
            anchor_category = str(anchor.get("garment_category") or "").lower()
            anchor_role = "top" if anchor_category in ("top", "shirt", "blouse") else "bottom" if anchor_category in ("bottom", "trouser", "pant") else "complete"
            anchor_product = RetrievedProduct(
                product_id=str(anchor.get("id") or anchor.get("product_id") or "anchor_wardrobe"),
                similarity=1.0,
                metadata={},
                enriched_data=anchor,
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
            _log.info("Injected anchor garment as role=%s for paired assembly", anchor_role)

        emit("outfit_assembly", "started")
        candidates = self.outfit_assembler.assemble(retrieved_sets, plan, combined_context)
        emit("outfit_assembly", "completed", ctx={"candidate_count": len(candidates)})

        emit("outfit_evaluation", "started")
        t0 = time.monotonic()
        evaluated = self.outfit_evaluator.evaluate(candidates, combined_context, plan)
        evaluator_ms = int((time.monotonic() - t0) * 1000)
        self.repo.log_model_call(
            conversation_id=conversation_id,
            turn_id=turn_id,
            service="agentic_application",
            call_type="outfit_evaluator",
            model="gpt-5.4",
            request_json={"candidate_count": len(candidates)},
            response_json={"evaluation_count": len(evaluated)},
            reasoning_notes=[],
            latency_ms=evaluator_ms,
        )
        emit("outfit_evaluation", "completed")

        emit("response_formatting", "started")
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
                },
            )
        )
        response.metadata["turn_id"] = turn_id
        emit("response_formatting", "completed", ctx={"outfit_count": min(len(evaluated), 3)})

        emit("virtual_tryon", "started")
        self._attach_tryon_images(response.outfits, external_user_id, conversation_id=conversation_id, turn_id=turn_id)
        emit("virtual_tryon", "completed")

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
                "last_plan_type": plan.plan_type,
                "last_recommendations": rec_summary,
                "last_occasion": effective_live_context.occasion_signal or "",
                "last_live_context": effective_live_context.model_dump(),
                "last_response_metadata": response.metadata,
                "last_assistant_message": response.message,
                "last_user_message": message,
                "last_channel": channel,
                "last_intent": plan_result.intent,

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
    ) -> Dict[str, Any]:
        occasion_signal = str(plan_result.resolved_context.occasion_signal or "").strip() or None
        image_path = str((attached_item or {}).get("image_path") or "").strip()

        # Process 1 (blocking): Vision-based outfit check — agent sees the image directly
        try:
            check = self.outfit_check_agent.evaluate(
                user_context=user_context,
                outfit_description=message,
                occasion_signal=occasion_signal,
                profile_confidence_pct=int(profile_confidence.analysis_confidence_pct),
                image_path=image_path,
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

        self.repo.log_model_call(
            conversation_id=conversation_id,
            turn_id=turn_id,
            service="agentic_application",
            call_type=Intent.OUTFIT_CHECK,
            model="gpt-5.4",
            request_json={
                "message": message,
                "occasion_signal": occasion_signal,
                "profile_confidence_pct": profile_confidence.analysis_confidence_pct,
            },
            response_json=check.to_dict(),
            reasoning_notes=[],
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

        # Remove the initial full-photo wardrobe item — decomposition will
        # create proper individual garment items to replace it.
        attached_item_id = str((attached_item or {}).get("id") or "").strip()
        if attached_item_id:
            try:
                self.onboarding_gateway.delete_wardrobe_item(
                    user_id=external_user_id,
                    wardrobe_item_id=attached_item_id,
                )
            except Exception:
                _log.warning("Failed to delete initial outfit wardrobe item %s", attached_item_id, exc_info=True)

        # Process 2 (async): decompose outfit → crop → enrich → save to wardrobe
        if image_path:
            Thread(
                target=self._decompose_and_save_garments,
                args=(image_path, message, external_user_id, turn_id, conversation_id),
                daemon=True,
            ).start()

        attached_image_path = str((attached_item or {}).get("image_path") or "").strip()
        tryon_image = self._tryon_image_url(attached_image_path) if attached_image_path else None
        outfit_card = OutfitCard(
            rank=1,
            title="Outfit Check",
            reasoning=check.overall_note,
            body_note=(check.strengths[0] if check.strengths else ""),
            color_note=(check.strengths[1] if len(check.strengths) > 1 else ""),
            style_note=(check.strengths[2] if len(check.strengths) > 2 else ""),
            occasion_note=(check.strengths[3] if len(check.strengths) > 3 else ""),
            body_harmony_pct=check.body_harmony_pct,
            color_suitability_pct=check.color_suitability_pct,
            style_fit_pct=check.style_fit_pct,
            pairing_coherence_pct=check.pairing_coherence_pct,
            occasion_pct=check.occasion_pct,
            classic_pct=check.style_archetype_read.get("classic_pct", 0),
            dramatic_pct=check.style_archetype_read.get("dramatic_pct", 0),
            romantic_pct=check.style_archetype_read.get("romantic_pct", 0),
            natural_pct=check.style_archetype_read.get("natural_pct", 0),
            minimalist_pct=check.style_archetype_read.get("minimalist_pct", 0),
            creative_pct=check.style_archetype_read.get("creative_pct", 0),
            sporty_pct=check.style_archetype_read.get("sporty_pct", 0),
            edgy_pct=check.style_archetype_read.get("edgy_pct", 0),
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
            "overall_score_pct": check.overall_score_pct,
            "scores": {
                "body_harmony_pct": check.body_harmony_pct,
                "color_suitability_pct": check.color_suitability_pct,
                "style_fit_pct": check.style_fit_pct,
                "pairing_coherence_pct": check.pairing_coherence_pct,
                "occasion_pct": check.occasion_pct,
            },
            "strengths": strengths,
            "improvements": improvements,
            "wardrobe_suggestions": wardrobe_suggestions,
            "style_archetype_read": dict(check.style_archetype_read),
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
                        "match_score": check.overall_score_pct / 100.0,
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
                "overall_score_pct": check.overall_score_pct,
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

    def _compute_wardrobe_overlap(
        self,
        *,
        wardrobe_items: List[Dict[str, Any]],
        detected_garments: List[str],
        detected_colors: List[str],
    ) -> Dict[str, Any]:
        normalized_garments = {
            self._normalize_text_token(value)
            for value in detected_garments
            if self._normalize_text_token(value)
        }
        normalized_colors = {
            self._normalize_text_token(value)
            for value in detected_colors
            if self._normalize_text_token(value)
        }
        best_match: Dict[str, Any] | None = None
        best_score = -1
        for item in wardrobe_items:
            item_garments = {
                self._normalize_text_token(item.get("garment_category")),
                self._normalize_text_token(item.get("garment_subtype")),
            }
            item_colors = {self._normalize_text_token(item.get("primary_color"))}
            garment_match = bool(normalized_garments and item_garments.intersection(normalized_garments))
            color_match = bool(normalized_colors and item_colors.intersection(normalized_colors))
            score = 0
            if garment_match:
                score += 2
            if color_match:
                score += 1
            if score > best_score:
                best_score = score
                best_match = item
        if not best_match or best_score <= 0:
            return {"has_duplicate": False, "duplicate_detail": None, "overlap_level": "none"}
        if best_score >= 3:
            level = "strong"
        else:
            level = "moderate"
        return {
            "has_duplicate": True,
            "duplicate_detail": str(best_match.get("title") or "").strip() or None,
            "overlap_level": level,
        }

    def _build_shopping_pairing_suggestions(
        self,
        *,
        wardrobe_items: List[Dict[str, Any]],
        detected_garments: List[str],
        detected_colors: List[str],
    ) -> List[Dict[str, str]]:
        target_garments = {self._normalize_text_token(value) for value in detected_garments if self._normalize_text_token(value)}
        target_colors = {self._normalize_text_token(value) for value in detected_colors if self._normalize_text_token(value)}

        def is_same_category(item: Dict[str, Any]) -> bool:
            categories = {
                self._normalize_text_token(item.get("garment_category")),
                self._normalize_text_token(item.get("garment_subtype")),
            }
            return bool(target_garments and categories.intersection(target_garments))

        suggestions: List[Dict[str, str]] = []
        for item in wardrobe_items:
            if is_same_category(item):
                continue
            title = str(item.get("title") or "").strip()
            if not title:
                continue
            color = str(item.get("primary_color") or "").strip()
            occasion = str(item.get("occasion_fit") or "").strip().replace("_", " ")
            note_parts = []
            if color and target_colors and self._normalize_text_token(color) not in target_colors:
                note_parts.append(f"The {color} tone adds contrast.")
            if occasion:
                note_parts.append(f"It already works for {occasion}.")
            if not note_parts:
                note_parts.append("It broadens how often you could wear the piece.")
            suggestions.append(
                {
                    "wardrobe_item": title,
                    "pairing_note": " ".join(note_parts).strip(),
                }
            )
            if len(suggestions) >= 3:
                break
        return suggestions

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

    def _handle_shopping_decision(
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

    ) -> Dict[str, Any]:
        params = plan_result.action_parameters
        product_urls = list(params.product_urls or []) or extract_urls(message)
        detected_garments = [str(v).strip() for v in list(params.detected_garments or []) if str(v).strip()]
        detected_colors = [str(v).strip() for v in list(params.detected_colors or []) if str(v).strip()]
        wardrobe_items = list(getattr(user_context, "wardrobe_items", []) or [])
        overlap = self._compute_wardrobe_overlap(
            wardrobe_items=wardrobe_items,
            detected_garments=detected_garments,
            detected_colors=detected_colors,
        )
        pairing_suggestions = self._build_shopping_pairing_suggestions(
            wardrobe_items=wardrobe_items,
            detected_garments=detected_garments,
            detected_colors=detected_colors,
        )
        occasion_signal = str(plan_result.resolved_context.occasion_signal or "").strip() or None
        wardrobe_gap_analysis = self._build_wardrobe_gap_analysis(
            wardrobe_items=wardrobe_items,
            occasion=occasion_signal or "",
            required_roles=detected_garments or ["top", "bottom", "shoe"],
        )
        try:
            decision = self.shopping_decision_agent.evaluate(
                user_context=user_context,
                product_description=message,
                product_urls=product_urls,
                detected_garments=detected_garments,
                detected_colors=detected_colors,
                occasion_signal=occasion_signal,
                profile_confidence_pct=int(profile_confidence.analysis_confidence_pct),
                wardrobe_overlap=overlap,
                pairing_suggestions=pairing_suggestions,
            )
        except Exception as exc:
            _log.error("Shopping decision evaluation failed: %s", exc, exc_info=True)
            self.repo.finalize_turn(
                turn_id=turn_id,
                assistant_message="I'm having trouble evaluating this item right now. Please try again.",
                resolved_context={"error": str(exc), "request_summary": message.strip()},
            )
            return {
                "conversation_id": conversation_id,
                "turn_id": turn_id,
                "assistant_message": "I'm having trouble evaluating this item right now. Please try again.",
                "response_type": "error",
                "resolved_context": {"request_summary": message.strip()},
                "filters_applied": {},
                "outfits": [],
                "follow_up_suggestions": [],
                "metadata": {"error": True},
            }

        self.repo.log_model_call(
            conversation_id=conversation_id,
            turn_id=turn_id,
            service="agentic_application",
            call_type=Intent.SHOPPING_DECISION,
            model="gpt-5.4",
            request_json={
                "message": message,
                "product_urls": product_urls,
                "detected_garments": detected_garments,
                "detected_colors": detected_colors,
                "occasion_signal": occasion_signal,
            },
            response_json=decision.to_dict(),
            reasoning_notes=[],
        )

        verdict_label = decision.verdict.upper()
        assistant_parts: List[str] = [f"My verdict: {verdict_label}.", decision.verdict_note]
        if overlap.get("has_duplicate") and overlap.get("duplicate_detail"):
            assistant_parts.append(
                f"You already own something similar: {overlap['duplicate_detail']}."
            )
        if decision.concerns:
            assistant_parts.append("Watchouts: " + "; ".join(decision.concerns[:2]) + ".")
        if decision.pairing_suggestions:
            pairing_text = " ".join(
                f"{item['wardrobe_item']}: {item['pairing_note']}"
                for item in decision.pairing_suggestions[:2]
                if str(item.get("wardrobe_item") or "").strip()
            ).strip()
            if pairing_text:
                assistant_parts.append("If you buy it: " + pairing_text)
        if decision.verdict == "skip" and decision.instead_consider:
            assistant_parts.append(f"Instead, consider {decision.instead_consider}.")
        elif decision.if_you_buy:
            assistant_parts.append(decision.if_you_buy)
        if wardrobe_gap_analysis.get("gap_items"):
            assistant_parts.append(
                "The bigger wardrobe gap is " + ", ".join(list(wardrobe_gap_analysis.get("gap_items") or [])[:2]) + "."
            )
        if profile_confidence.analysis_confidence_pct < 70:
            assistant_parts.append(
                f"My confidence is moderated by your profile confidence being {profile_confidence.analysis_confidence_pct}%."
            )
        assistant_message = " ".join(part for part in assistant_parts if str(part).strip()).strip()

        handler_payload = {
            **decision.to_dict(),
            "product_urls": product_urls,
            "detected_garments": detected_garments,
            "detected_colors": detected_colors,
            "occasion_signal": occasion_signal or "",
            "wardrobe_gap_analysis": wardrobe_gap_analysis,
        }
        metadata = self._build_response_metadata(
            channel=channel,
            intent=intent,
            profile_confidence=profile_confidence,
            extra={
                "answer_source": "shopping_decision_handler",
                "shopping_decision": handler_payload,
            },
        )
        self.repo.finalize_turn(
            turn_id=turn_id,
            assistant_message=assistant_message,
            resolved_context={
                "request_summary": message.strip(),
                "occasion": occasion_signal or "",
                "style_goal": "shopping_decision",
                "intent_classification": intent.model_dump(),
                "profile_confidence": profile_confidence.model_dump(),

                "handler": Intent.SHOPPING_DECISION,
                "handler_payload": handler_payload,
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
                "answer_source": "shopping_decision_handler",
                "verdict": decision.verdict,
                "verdict_confidence": decision.verdict_confidence,
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
                "style_goal": "shopping_decision",
            },
            "filters_applied": {},
            "outfits": [],
            "follow_up_suggestions": (
                plan_result.follow_up_suggestions[:5]
                if plan_result.follow_up_suggestions
                else ["What goes with this?", "Show me better options", "Use my wardrobe first"]
            ),
            "metadata": metadata,
        }

    def _handle_planner_virtual_tryon(
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
        tryon_result = self._run_virtual_tryon_request(
            external_user_id=external_user_id,
            message=message,
        )
        assistant_message = plan_result.assistant_message
        if not tryon_result.get("success"):
            error_msg = str(tryon_result.get("error") or "")
            if error_msg:
                assistant_message = error_msg

        handler_payload: Dict[str, Any] = {
            "success": tryon_result.get("success"),
            "product_url": tryon_result.get("product_url", ""),
        }
        if tryon_result.get("quality_gate"):
            handler_payload["quality_gate"] = dict(tryon_result.get("quality_gate") or {})
        if tryon_result.get("success") and tryon_result.get("data_url"):
            handler_payload["tryon_image"] = str(tryon_result.get("data_url") or "")
            self._persist_policy_event(
                external_user_id=external_user_id,
                conversation_id=conversation_id,
                turn_id=turn_id,
                channel=channel,
                policy_event_type="virtual_tryon_guardrail",
                input_class=Intent.VIRTUAL_TRYON_REQUEST,
                reason_code="quality_gate_passed",
                decision="allowed",
                metadata_json={
                    "quality_gate": dict(tryon_result.get("quality_gate") or {}),
                    "product_url": str(tryon_result.get("product_url") or ""),
                },
            )
        elif tryon_result.get("quality_gate") and not tryon_result["quality_gate"].get("passed"):
            self._persist_policy_event(
                external_user_id=external_user_id,
                conversation_id=conversation_id,
                turn_id=turn_id,
                channel=channel,
                policy_event_type="virtual_tryon_guardrail",
                input_class=Intent.VIRTUAL_TRYON_REQUEST,
                reason_code=str(tryon_result["quality_gate"].get("reason_code") or "quality_gate_failed"),
                metadata_json={
                    "quality_gate": dict(tryon_result.get("quality_gate") or {}),
                    "product_url": str(tryon_result.get("product_url") or ""),
                },
            )

        metadata = self._build_response_metadata(
            channel=channel,
            intent=intent,
            profile_confidence=profile_confidence,
            extra={"answer_source": "copilot_planner"},
        )
        self.repo.finalize_turn(
            turn_id=turn_id,
            assistant_message=assistant_message,
            resolved_context={
                "request_summary": message.strip(),
                "intent_classification": intent.model_dump(),
                "handler": "copilot_planner_tryon",
                "handler_payload": handler_payload,
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
            metadata_json={"answer_source": "copilot_planner"},
        )
        return {
            "conversation_id": conversation_id,
            "turn_id": turn_id,
            "assistant_message": assistant_message,
            "response_type": "recommendation",
            "resolved_context": {"request_summary": message.strip()},
            "filters_applied": {},
            "outfits": [],
            "follow_up_suggestions": plan_result.follow_up_suggestions[:5],
            "metadata": metadata,
        }

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

    def _handle_product_browse(
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
        profile_confidence: Any,
        emit: Any,
    ) -> Dict[str, Any]:
        """Handle product_browse intent — direct catalog search by category/color/attribute."""
        from .filters import build_global_hard_filters, merge_filters, resolve_garment_filters
        from .schemas import (
            CombinedContext,
            DirectionSpec,
            LiveContext,
            QuerySpec,
            RecommendationPlan,
        )

        detected_garments = list(plan_result.action_parameters.detected_garments or [])
        detected_colors = list(plan_result.action_parameters.detected_colors or [])
        formality = str(plan_result.resolved_context.formality_hint or "").strip()

        # Build query document from constraints
        garment_label = detected_garments[0] if detected_garments else "item"
        color_label = " ".join(detected_colors) if detected_colors else ""
        profile_hint = ""
        if hasattr(user_context, "color_palette") and user_context.color_palette:
            palette = user_context.color_palette
            if hasattr(palette, "base_colors") and palette.base_colors:
                profile_hint = f" Profile palette includes {', '.join(palette.base_colors[:3])}."
        query_parts = ["A"]
        if color_label:
            query_parts.append(color_label)
        query_parts.append(garment_label)
        if formality:
            query_parts.append(f"for {formality} wear")
        query_doc = " ".join(query_parts) + "." + profile_hint

        # Build filters
        garment_filters = resolve_garment_filters(detected_garments)
        hard_filters = merge_filters(
            build_global_hard_filters(user_context),
            garment_filters,
        )

        # Build minimal single-direction plan
        browse_plan = RecommendationPlan(
            plan_type="complete_only",
            retrieval_count=12,
            directions=[
                DirectionSpec(
                    direction_id="browse",
                    direction_type="complete",
                    label=f"Browse: {garment_label}",
                    queries=[
                        QuerySpec(
                            query_id="browse_q1",
                            role="complete",
                            hard_filters=garment_filters,
                            query_document=query_doc,
                        ),
                    ],
                ),
            ],
        )

        live_context = LiveContext(
            user_need=message,
            occasion_signal=plan_result.resolved_context.occasion_signal or "",
            formality_hint=formality,
            time_hint=plan_result.resolved_context.time_hint or "",
            specific_needs=list(plan_result.resolved_context.specific_needs or []),
        )

        combined_context = CombinedContext(
            user=user_context,
            live=live_context,
            hard_filters=hard_filters,
        )

        # Search catalog via existing agent
        if emit:
            emit("search", "catalog_browse", "Searching catalog...")
        retrieved_sets = self.catalog_search_agent.search(browse_plan, combined_context)

        # Collect all products across sets
        all_products = []
        for rs in retrieved_sets:
            all_products.extend(rs.products)

        # Build individual product cards (1 item per OutfitCard)
        from .schemas import OutfitCard, OutfitItem
        outfits = []
        for i, product in enumerate(all_products[:12]):
            enriched = dict(product.enriched_data or {})
            metadata = dict(product.metadata or {})
            item = OutfitItem(
                product_id=product.product_id,
                similarity=product.similarity,
                title=str(enriched.get("title") or metadata.get("title") or ""),
                image_url=str(enriched.get("image_urls") or metadata.get("image_url") or ""),
                price=str(enriched.get("price") or metadata.get("price") or ""),
                product_url=str(enriched.get("url") or enriched.get("product_url") or ""),
                garment_category=str(enriched.get("garment_category") or metadata.get("garment_category") or ""),
                garment_subtype=str(enriched.get("garment_subtype") or metadata.get("garment_subtype") or ""),
                primary_color=str(enriched.get("primary_color") or metadata.get("primary_color") or ""),
                role="complete",
                formality_level=str(enriched.get("formality_level") or metadata.get("formality_level") or ""),
                occasion_fit=str(enriched.get("occasion_fit") or metadata.get("occasion_fit") or ""),
                pattern_type=str(enriched.get("pattern_type") or ""),
                source="catalog",
            )
            outfits.append(
                OutfitCard(
                    rank=i + 1,
                    title=item.title or f"{garment_label.title()} Option {i + 1}",
                    items=[item.model_dump()],
                )
            )

        # Follow-up suggestions
        follow_ups = list(plan_result.follow_up_suggestions or [])
        if not follow_ups:
            follow_ups = [
                "Style this piece",
                "Show me more like this",
                "Try this on me",
                "Show me a different color",
                "Build an outfit around one of these",
            ]

        # Response message
        product_count = len(outfits)
        if product_count:
            assistant_message = plan_result.assistant_message or f"Here are {product_count} {garment_label} options from the catalog that suit your profile."
        else:
            assistant_message = plan_result.assistant_message or f"I couldn't find {garment_label} options matching those filters right now. Try broadening your search."

        # Build metadata
        response_metadata = self._build_response_metadata(
            channel=channel,
            intent=intent,
            profile_confidence=profile_confidence,
            extra={
                "answer_source": "product_browse_handler",
                "product_count": product_count,
                "browse_constraints": {
                    "garment_label": garment_label,
                    "colors": detected_colors,
                    "formality": formality,
                    "hard_filters": hard_filters,
                },
            },
        )

        # Persist
        resolved_context_dict = {
            "request_summary": message,
            "occasion": "",
            "style_goal": "product_browse",
            "handler": Intent.PRODUCT_BROWSE,
            "profile_confidence_pct": profile_confidence.analysis_confidence_pct,
        }

        self.repo.finalize_turn(
            turn_id=turn_id,
            assistant_message=assistant_message,
            resolved_context=resolved_context_dict,
        )

        session_update = {
            **previous_context,
            "last_intent": plan_result.intent,
            "last_live_context": {
                "occasion_signal": "",
                "formality_hint": formality,
                "style_goal": "product_browse",
            },
        }
        self.repo.update_conversation_context(
            conversation_id=conversation_id,
            session_context=session_update,
        )

        self._persist_dependency_turn_event(
            conversation_id=conversation_id,
            turn_id=turn_id,
            external_user_id=external_user_id,
            channel=channel,
            primary_intent=plan_result.intent,
            response_type="product_browse",
            metadata_json={
                "product_count": product_count,
                "garment_label": garment_label,
            },
        )

        return {
            "conversation_id": conversation_id,
            "turn_id": turn_id,
            "assistant_message": assistant_message,
            "response_type": "product_browse",
            "resolved_context": resolved_context_dict,
            "filters_applied": hard_filters,
            "outfits": [o.model_dump() if hasattr(o, "model_dump") else dict(o) for o in outfits],
            "follow_up_suggestions": follow_ups[:5],
            "metadata": response_metadata,
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
