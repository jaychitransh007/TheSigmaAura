from __future__ import annotations

import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Dict, List, Optional

from platform_core.config import AuraRuntimeConfig
from platform_core.fallback_messages import graceful_policy_message
from platform_core.restricted_categories import detect_restricted_record
from platform_core.repositories import ConversationRepository

from .agents.catalog_search_agent import CatalogSearchAgent
from .agents.outfit_architect import OutfitArchitect
from .agents.outfit_assembler import OutfitAssembler
from .agents.outfit_evaluator import OutfitEvaluator
from .agents.response_formatter import ResponseFormatter
from .context.conversation_memory import build_conversation_memory
from .context.occasion_resolver import resolve_occasion
from .context.user_context_builder import build_user_context, validate_minimum_profile
from .filters import build_global_hard_filters
from .intent_handlers import (
    build_capsule_or_trip_planning_response,
    build_explanation_response,
    build_feedback_submission_response,
    build_garment_on_me_response,
    build_outfit_check_response,
    build_pairing_request_response,
    build_shopping_decision_response,
    build_style_discovery_response,
    build_virtual_tryon_response,
    build_wardrobe_ingestion_response,
)
from .intent_router import classify as classify_intent
from .onboarding_gate import evaluate as evaluate_onboarding_gate
from .recommendation_confidence import evaluate_recommendation_confidence
from .services.catalog_retrieval_gateway import ApplicationCatalogRetrievalGateway
from .services.onboarding_gateway import ApplicationUserGateway
from .services.tryon_quality_gate import TryonQualityGate
from .services.tryon_service import TryonService
from .sentiment import extract_sentiment
from .context_gate import evaluate as evaluate_context_gate
from .qna_messages import generate_stage_message
from .schemas import CombinedContext, IntentClassification, LiveContext, OutfitCard, ProfileConfidence, RecommendationConfidence

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

        self.outfit_architect = OutfitArchitect()
        self.catalog_search_agent = CatalogSearchAgent(
            retrieval_gateway=self._retrieval_gateway,
            client=repo.client,
        )
        self.outfit_assembler = OutfitAssembler()
        self.outfit_evaluator = OutfitEvaluator()
        self.response_formatter = ResponseFormatter()

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
        sentiment_trace = extract_sentiment(message)
        self._persist_sentiment_trace(
            external_user_id=external_user_id,
            conversation_id=conversation_id,
            turn_id=turn_id,
            channel=channel,
            message=message,
            sentiment_trace=sentiment_trace,
        )

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
                    "sentiment_trace": sentiment_trace,
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
                    "last_sentiment_trace": sentiment_trace,
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

        # --- 0.75 Intent Router ---
        emit("intent_router", "started")
        intent = classify_intent(message, previous_context=previous_context)
        emit("intent_router", "completed", ctx={"primary_intent": intent.primary_intent})
        profile_confidence = onboarding_gate.profile_confidence
        self._persist_profile_confidence(
            external_user_id=external_user_id,
            conversation_id=conversation_id,
            turn_id=turn_id,
            channel=channel,
            profile_confidence=profile_confidence,
            primary_intent=intent.primary_intent,
            status=onboarding_gate.status,
        )

        if intent.primary_intent in {
            "style_discovery",
            "explanation_request",
            "shopping_decision",
            "pairing_request",
            "outfit_check",
            "garment_on_me_request",
            "capsule_or_trip_planning",
            "wardrobe_ingestion",
            "feedback_submission",
            "virtual_tryon_request",
        }:
            emit("user_context", "started")
            user_context = build_user_context(
                external_user_id,
                onboarding_gateway=self.onboarding_gateway,
            )
            validate_minimum_profile(user_context)
            emit("user_context", "completed", ctx={"richness": user_context.profile_richness})

            if intent.primary_intent == "style_discovery":
                assistant_message, suggestions = build_style_discovery_response(
                    user_context=user_context,
                    profile_confidence=profile_confidence,
                )
                style_goal = str((user_context.style_preference or {}).get("primaryArchetype") or "").strip()
                handler_payload: Dict[str, Any] = {}
            elif intent.primary_intent == "shopping_decision":
                assistant_message, suggestions, handler_payload = build_shopping_decision_response(
                    message=message,
                    user_context=user_context,
                    previous_context=previous_context,
                    profile_confidence=profile_confidence,
                )
                style_goal = "buy_or_skip"
            elif intent.primary_intent == "pairing_request":
                assistant_message, suggestions, handler_payload = build_pairing_request_response(
                    message=message,
                    user_context=user_context,
                    previous_context=previous_context,
                    profile_confidence=profile_confidence,
                )
                style_goal = "pairing"
            elif intent.primary_intent == "outfit_check":
                assistant_message, suggestions, handler_payload = build_outfit_check_response(
                    message=message,
                    user_context=user_context,
                    previous_context=previous_context,
                    profile_confidence=profile_confidence,
                )
                style_goal = "outfit_check"
            elif intent.primary_intent == "garment_on_me_request":
                assistant_message, suggestions, handler_payload = build_garment_on_me_response(
                    message=message,
                    user_context=user_context,
                    previous_context=previous_context,
                    profile_confidence=profile_confidence,
                )
                style_goal = "garment_on_me"
            elif intent.primary_intent == "capsule_or_trip_planning":
                assistant_message, suggestions, handler_payload = build_capsule_or_trip_planning_response(
                    message=message,
                    user_context=user_context,
                    previous_context=previous_context,
                    profile_confidence=profile_confidence,
                )
                wardrobe_plan_cards = self._build_wardrobe_first_capsule_plan(
                    message=message,
                    wardrobe_items=list(user_context.wardrobe_items or []),
                )
                if wardrobe_plan_cards:
                    style_goal = "capsule_or_trip"
                    catalog_upsell = self._build_catalog_upsell(
                        rationale="Your saved wardrobe can cover the first pass, but I can also show stronger catalog options to fill gaps or elevate the plan.",
                        entry_intent="capsule_or_trip_planning",
                    )
                    answer_components = self._summarize_answer_components(wardrobe_plan_cards)
                    recommendation_confidence = evaluate_recommendation_confidence(
                        answer_mode="wardrobe_first",
                        profile_confidence_score_pct=profile_confidence.score_pct,
                        intent_confidence=float(intent.confidence),
                        top_match_score=0.88,
                        second_match_score=0.82 if len(wardrobe_plan_cards) > 1 else 0.0,
                        retrieved_product_count=0,
                        candidate_count=len(wardrobe_plan_cards),
                        response_outfit_count=len(wardrobe_plan_cards),
                        wardrobe_items_used=sum(len(card.items) for card in wardrobe_plan_cards),
                        restricted_item_exclusion_count=0,
                    )
                    routing_metadata = self._build_intent_routing_metadata(
                        intent=intent,
                        handler_payload=handler_payload,
                    )
                    handler_payload = {
                        **handler_payload,
                        "answer_source": "wardrobe_first",
                        "wardrobe_plan_count": len(wardrobe_plan_cards),
                        "answer_components": answer_components,
                        "catalog_upsell": catalog_upsell,
                        "recommendation_confidence": recommendation_confidence.model_dump(),
                        "routing_metadata": routing_metadata,
                    }
                    metadata = self._build_response_metadata(
                        channel=channel,
                        intent=intent,
                        profile_confidence=profile_confidence,
                        extra={
                            "routing_metadata": routing_metadata,
                            "answer_source": "wardrobe_first",
                            "answer_components": answer_components,
                            "catalog_upsell": catalog_upsell,
                            "recommendation_confidence": recommendation_confidence.model_dump(),
                        },
                    )
                    resolved_context = {
                        "request_summary": message.strip(),
                        "intent_classification": intent.model_dump(),
                        "profile_confidence": profile_confidence.model_dump(),
                        "sentiment_trace": sentiment_trace,
                        "handler": intent.primary_intent,
                        "handler_payload": handler_payload,
                        "routing_metadata": routing_metadata,
                        "channel": channel,
                        "recommendations": [
                            {
                                "candidate_id": f"wardrobe-plan-{card.rank}",
                                "rank": card.rank,
                                "title": card.title,
                                "item_ids": [str(item.get("product_id") or "") for item in card.items],
                                "match_score": 0.88,
                                "reasoning": card.reasoning,
                            }
                            for card in wardrobe_plan_cards
                        ],
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
                        metadata_json={"answer_mode": "wardrobe_first"},
                    )
                    self.repo.update_conversation_context(
                        conversation_id=conversation_id,
                        session_context={
                            **previous_context,
                            "last_user_message": message,
                            "last_assistant_message": assistant_message,
                            "last_channel": channel,
                            "last_intent": intent.primary_intent,
                            "last_sentiment_trace": sentiment_trace,
                            "last_response_metadata": metadata,
                            "last_recommendations": [
                                {
                                    "candidate_id": f"wardrobe-plan-{card.rank}",
                                    "rank": card.rank,
                                    "title": card.title,
                                    "item_ids": [str(item.get("product_id") or "") for item in card.items],
                                    "candidate_type": "wardrobe",
                                    "direction_id": "wardrobe_plan",
                                    "primary_colors": [str(item.get("primary_color") or "") for item in card.items if str(item.get("primary_color") or "").strip()],
                                    "garment_categories": [str(item.get("garment_category") or "") for item in card.items if str(item.get("garment_category") or "").strip()],
                                    "garment_subtypes": [str(item.get("garment_subtype") or "") for item in card.items if str(item.get("garment_subtype") or "").strip()],
                                    "roles": [str(item.get("role") or "") for item in card.items if str(item.get("role") or "").strip()],
                                    "occasion_fits": [],
                                    "formality_levels": [str(item.get("formality_level") or "") for item in card.items if str(item.get("formality_level") or "").strip()],
                                    "pattern_types": [],
                                    "volume_profiles": [],
                                    "fit_types": [],
                                    "silhouette_types": [],
                                }
                                for card in wardrobe_plan_cards
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
                            "answer_source": "wardrobe_first",
                            "memory_sources_read": list(routing_metadata.get("memory_sources_read") or []),
                            "memory_sources_written": list(routing_metadata.get("memory_sources_written") or []),
                            "recommendation_confidence_score_pct": recommendation_confidence.score_pct,
                            "outfit_count": len(wardrobe_plan_cards),
                        },
                    )
                    return {
                        "conversation_id": conversation_id,
                        "turn_id": turn_id,
                        "assistant_message": assistant_message + " If you want, I can also show better catalog options for the same plan.",
                        "response_type": "recommendation",
                        "resolved_context": {
                            "request_summary": message.strip(),
                            "occasion": str(previous_context.get("last_occasion") or ""),
                            "style_goal": "capsule_or_trip",
                        },
                        "filters_applied": {},
                        "outfits": [card.model_dump() for card in wardrobe_plan_cards],
                        "follow_up_suggestions": suggestions + [str(catalog_upsell["cta"])],
                        "metadata": metadata,
                    }
                style_goal = "capsule_or_trip"
            elif intent.primary_intent == "wardrobe_ingestion":
                saved_item = self._save_chat_wardrobe_item(
                    external_user_id=external_user_id,
                    message=message,
                )
                assistant_message, suggestions, handler_payload = build_wardrobe_ingestion_response(
                    message=message,
                    user_context=user_context,
                    profile_confidence=profile_confidence,
                    saved_item=saved_item,
                )
                style_goal = "wardrobe_ingestion"
            elif intent.primary_intent == "feedback_submission":
                assistant_message, suggestions, handler_payload = build_feedback_submission_response(
                    message=message,
                    previous_context=previous_context,
                )
                self._persist_chat_feedback(
                    external_user_id=external_user_id,
                    conversation_id=conversation_id,
                    handler_payload=handler_payload,
                    notes=message.strip(),
                )
                handler_payload["feedback_summary"] = self._build_feedback_summary(
                    event_type=str(handler_payload.get("event_type") or "dislike"),
                    item_ids=list(handler_payload.get("item_ids") or []),
                    outfit_rank=int(handler_payload.get("outfit_rank") or 1),
                    turn_id=str(handler_payload.get("target_turn_id") or ""),
                )
                style_goal = "feedback_submission"
            elif intent.primary_intent == "virtual_tryon_request":
                tryon_result = self._run_virtual_tryon_request(
                    external_user_id=external_user_id,
                    message=message,
                )
                assistant_message, suggestions, handler_payload = build_virtual_tryon_response(
                    message=message,
                    success=bool(tryon_result.get("success")),
                    product_url=str(tryon_result.get("product_url") or ""),
                    error_message=str(tryon_result.get("error") or ""),
                )
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
                        input_class="virtual_tryon_request",
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
                        input_class="virtual_tryon_request",
                        reason_code=str(tryon_result["quality_gate"].get("reason_code") or "quality_gate_failed"),
                        metadata_json={
                            "quality_gate": dict(tryon_result.get("quality_gate") or {}),
                            "product_url": str(tryon_result.get("product_url") or ""),
                        },
                    )
                style_goal = "virtual_tryon"
            else:
                assistant_message, suggestions = build_explanation_response(
                    user_context=user_context,
                    previous_context=previous_context,
                    profile_confidence=profile_confidence,
                )
                style_goal = "explanation"
                handler_payload = {}

            routing_metadata = self._build_intent_routing_metadata(
                intent=intent,
                handler_payload=handler_payload,
            )
            handler_payload = {
                **handler_payload,
                "routing_metadata": routing_metadata,
            }

            metadata = self._build_response_metadata(
                channel=channel,
                intent=intent,
                profile_confidence=profile_confidence,
                extra={
                    "routing_metadata": routing_metadata,
                    **(
                        {"catalog_upsell": handler_payload.get("catalog_upsell")}
                        if handler_payload.get("catalog_upsell")
                        else {}
                    ),
                },
            )
            self.repo.finalize_turn(
                turn_id=turn_id,
                assistant_message=assistant_message,
                resolved_context={
                    "request_summary": message.strip(),
                    "intent_classification": intent.model_dump(),
                    "profile_confidence": profile_confidence.model_dump(),
                    "sentiment_trace": sentiment_trace,
                    "handler": intent.primary_intent,
                    "handler_payload": handler_payload,
                    "routing_metadata": routing_metadata,
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
                    "last_intent": intent.primary_intent,
                    "last_sentiment_trace": sentiment_trace,
                    "last_response_metadata": metadata,
                    **(
                        {"last_feedback_summary": handler_payload.get("feedback_summary")}
                        if handler_payload.get("feedback_summary")
                        else {}
                    ),
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
                    "answer_source": str(handler_payload.get("answer_source") or "intent_handler"),
                    "memory_sources_read": list(routing_metadata.get("memory_sources_read") or []),
                    "memory_sources_written": list(routing_metadata.get("memory_sources_written") or []),
                    "catalog_upsell_available": bool(handler_payload.get("catalog_upsell")),
                },
            )
            return {
                "conversation_id": conversation_id,
                "turn_id": turn_id,
                "assistant_message": assistant_message,
                "response_type": "recommendation",
                "resolved_context": {
                    "request_summary": message.strip(),
                    "occasion": str(previous_context.get("last_occasion") or ""),
                    "style_goal": style_goal,
                },
                "filters_applied": {},
                "outfits": [],
                "follow_up_suggestions": suggestions,
                "metadata": metadata,
            }

        # --- 1. User Context Builder ---
        emit("user_context", "started")
        user_context = build_user_context(
            external_user_id,
            onboarding_gateway=self.onboarding_gateway,
        )
        validate_minimum_profile(user_context)
        emit("user_context", "completed", ctx={"richness": user_context.profile_richness})

        # --- 2. Build context for the architect ---
        emit("context_builder", "started")

        # Quick rule-based signal extraction so the context gate and
        # conversation memory see structured signals (occasion, formality, …)
        # before the expensive Architect LLM call.
        has_previous_recs = bool(previous_context.get("last_recommendations"))
        pre_resolved = resolve_occasion(message.strip(), has_previous_recommendations=has_previous_recs)

        initial_live_context = pre_resolved
        conversation_memory = build_conversation_memory(
            previous_context,
            initial_live_context,
            current_intent=intent.primary_intent,
            channel=channel,
            sentiment_trace=sentiment_trace,
            wardrobe_item_count=len(user_context.wardrobe_items),
        )

        # Build conversation history for the architect
        conversation_history = self._build_conversation_history(previous_context, message)

        emit("context_builder", "completed", ctx={"user_need": message})

        # --- Build combined context (gender-only hard filter) ---
        hard_filters = build_global_hard_filters(user_context)

        # Load catalog inventory (cached for the lifetime of this orchestrator)
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

        # --- 3.5 Context Gate ---
        emit("context_gate", "started")
        consecutive_blocks = int(previous_context.get("consecutive_gate_blocks", 0))
        gate_result = evaluate_context_gate(combined_context, consecutive_blocks)

        if not gate_result.sufficient:
            emit("context_gate", "insufficient")
            _log.info(
                "Context gate blocked (score=%.1f, missing=%s, consecutive=%d)",
                gate_result.score, gate_result.missing_signal, consecutive_blocks,
            )
            self.repo.finalize_turn(
                turn_id=turn_id,
                assistant_message=gate_result.question,
                resolved_context={
                    "request_summary": message.strip(),
                    "gate_blocked": True,
                    "gate_score": gate_result.score,
                    "gate_missing_signal": gate_result.missing_signal,
                    "intent_classification": intent.model_dump(),
                    "profile_confidence": profile_confidence.model_dump(),
                    "sentiment_trace": sentiment_trace,
                    "channel": channel,
                },
            )
            self.repo.update_conversation_context(
                conversation_id=conversation_id,
                session_context={
                    **previous_context,
                    "memory": conversation_memory.model_dump(),
                    "consecutive_gate_blocks": consecutive_blocks + 1,
                    "last_user_message": message,
                    "last_assistant_message": gate_result.question,
                    "last_channel": channel,
                    "last_intent": intent.primary_intent,
                    "last_sentiment_trace": sentiment_trace,
                },
            )
            self._persist_dependency_turn_event(
                external_user_id=external_user_id,
                conversation_id=conversation_id,
                turn_id=turn_id,
                channel=channel,
                primary_intent=intent.primary_intent,
                response_type="clarification",
                metadata_json={
                    "gate_blocked": True,
                    "gate_score": gate_result.score,
                    "gate_missing_signal": gate_result.missing_signal,
                    "memory_sources_read": ["conversation_memory", "user_profile"],
                    "memory_sources_written": ["conversation_memory"],
                },
            )
            return {
                "conversation_id": conversation_id,
                "turn_id": turn_id,
                "assistant_message": gate_result.question,
                "response_type": "clarification",
                "resolved_context": {
                    "request_summary": message.strip(),
                    "gate_score": gate_result.score,
                    "gate_missing_signal": gate_result.missing_signal,
                },
                "filters_applied": {},
                "outfits": [],
                "follow_up_suggestions": gate_result.quick_replies,
                "metadata": self._build_response_metadata(
                    channel=channel,
                    intent=intent,
                    profile_confidence=profile_confidence,
                    extra={"gate_blocked": True},
                ),
            }

        # Gate passed — reset consecutive counter
        emit("context_gate", "sufficient")
        if gate_result.bypass_reason:
            _log.info("Context gate bypassed: %s", gate_result.bypass_reason)

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
            sentiment_trace=sentiment_trace,
        )
        if wardrobe_first_response is not None:
            return wardrobe_first_response

        # --- 3. Outfit Architect (now also resolves occasion/context) ---
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
                request_json={
                    "combined_context_summary": {
                        "gender": user_context.gender,
                        "message": message,
                    }
                },
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
            self._persist_dependency_turn_event(
                external_user_id=external_user_id,
                conversation_id=conversation_id,
                turn_id=turn_id,
                channel=channel,
                primary_intent=intent.primary_intent,
                response_type="error",
                metadata_json={
                    "error": True,
                    "error_stage": "outfit_architect",
                },
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

        # Apply the architect's resolved context back to live context
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

        # Rebuild conversation memory now that the Architect has resolved context
        # (follow-up detection and formality shifts depend on the resolved live context)
        conversation_memory = build_conversation_memory(
            previous_context,
            effective_live_context,
            current_intent=intent.primary_intent,
            channel=channel,
            sentiment_trace=sentiment_trace,
            wardrobe_item_count=len(user_context.wardrobe_items),
        )

        # Update combined context with effective live context from architect
        combined_context = combined_context.model_copy(update={
            "live": effective_live_context,
            "conversation_memory": conversation_memory,
        })

        # --- 4. Catalog Search Agent (single search, no relaxation) ---
        emit("catalog_search", "started")
        t0 = time.monotonic()
        retrieved_sets = self.catalog_search_agent.search(plan, combined_context)
        search_ms = int((time.monotonic() - t0) * 1000)

        for rs in retrieved_sets:
            self.repo.log_tool_trace(
                conversation_id=conversation_id,
                turn_id=turn_id,
                tool_name="catalog_search_agent",
                input_json={
                    "direction_id": rs.direction_id,
                    "query_id": rs.query_id,
                    "role": rs.role,
                    "applied_filters": rs.applied_filters,
                },
                output_json={
                    "result_count": len(rs.products),
                },
                latency_ms=search_ms,
            )
        emit("catalog_search", "completed", ctx={
            "product_count": sum(len(rs.products) for rs in retrieved_sets),
            "set_count": len(retrieved_sets),
        })

        # --- 5. Outfit Assembler ---
        emit("outfit_assembly", "started")
        candidates = self.outfit_assembler.assemble(retrieved_sets, plan, combined_context)
        emit("outfit_assembly", "completed", ctx={"candidate_count": len(candidates)})

        # --- 6. Outfit Evaluator ---
        emit("outfit_evaluation", "started", ctx={
            "has_body_data": bool(user_context.height_cm or user_context.waist_cm),
            "has_color_season": bool(user_context.derived_interpretations.get("seasonal_color_group")),
            "has_style_pref": bool(user_context.style_preference),
        })
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

        # --- 7. Response Formatter ---
        emit("response_formatting", "started")
        response = self.response_formatter.format(evaluated, combined_context, plan, candidates)
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
        response.metadata.update(
            self._build_response_metadata(
                channel=channel,
                intent=intent,
                profile_confidence=profile_confidence,
                extra={
                    "recommendation_confidence": recommendation_confidence.model_dump(),
                },
            )
        )
        response.metadata["turn_id"] = turn_id
        emit("response_formatting", "completed", ctx={"outfit_count": min(len(evaluated), 3)})

        # --- 8. Virtual Try-On ---
        emit("virtual_tryon", "started")
        self._attach_tryon_images(response.outfits, external_user_id)
        emit("virtual_tryon", "completed")

        self._persist_catalog_interactions(
            external_user_id=external_user_id,
            conversation_id=conversation_id,
            turn_id=turn_id,
            channel=channel,
            primary_intent=intent.primary_intent,
            outfits=response.outfits,
        )
        self._persist_recommendation_confidence(
            external_user_id=external_user_id,
            conversation_id=conversation_id,
            turn_id=turn_id,
            channel=channel,
            primary_intent=intent.primary_intent,
            recommendation_confidence=recommendation_confidence,
            metadata_json={"answer_mode": "catalog_pipeline"},
        )

        # --- Persist ---
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
                sentiment_trace=sentiment_trace,
                channel=channel,
            ),
        )

        # Store plan + recommendations for follow-up turns
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
                "last_intent": intent.primary_intent,
                "last_sentiment_trace": sentiment_trace,
                "consecutive_gate_blocks": 0,
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
                "answer_source": "catalog_pipeline",
                "outfit_count": len(response.outfits),
                "memory_sources_read": list(
                    ((response.metadata.get("routing_metadata") or {}).get("memory_sources_read") or [])
                ),
                "memory_sources_written": [
                    "conversation_memory",
                    "catalog_interaction_history",
                    "confidence_history",
                    "sentiment_history",
                ],
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
            },
            "filters_applied": self._flatten_applied_filters(retrieved_sets) or hard_filters,
            "outfits": [card.model_dump() for card in response.outfits],
            "follow_up_suggestions": response.follow_up_suggestions,
            "metadata": response.metadata,
        }

    # ------------------------------------------------------------------
    # Virtual try-on
    # ------------------------------------------------------------------

    def _attach_tryon_images(
        self,
        outfits: List[OutfitCard],
        external_user_id: str,
    ) -> None:
        """Generate virtual try-on images for each outfit in parallel."""
        person_path = self.onboarding_gateway.get_person_image_path(external_user_id)
        if not person_path:
            return

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
            try:
                result = self.tryon_service.generate_tryon_outfit(
                    person_image_path=person_path,
                    garment_urls=garment_urls,
                )
                if result.get("success"):
                    quality = self.tryon_quality_gate.evaluate(
                        person_image_path=person_path,
                        tryon_result=result,
                    )
                    if quality.get("passed"):
                        return outfit, result["data_url"]
                    _log.info(
                        "Try-on quality gate blocked outfit #%s: %s",
                        outfit.rank,
                        quality.get("reason_code") or "unknown_quality_failure",
                    )
                    return outfit, ""
            except Exception:
                _log.warning("Try-on generation failed for outfit #%s", outfit.rank, exc_info=True)
            return outfit, ""

        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = {pool.submit(_generate_for_outfit, o): o for o in outfits}
            for future in as_completed(futures):
                outfit, data_url = future.result()
                if data_url:
                    outfit.tryon_image = data_url

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

    def _persist_sentiment_trace(
        self,
        *,
        external_user_id: str,
        conversation_id: str,
        turn_id: str,
        channel: str,
        message: str,
        sentiment_trace: Dict[str, object],
    ) -> None:
        try:
            self.repo.create_sentiment_trace(
                user_id=external_user_id,
                conversation_id=conversation_id,
                turn_id=turn_id,
                source_channel=channel,
                sentiment_source="user_message",
                sentiment_label=str(sentiment_trace.get("sentiment_label") or "neutral"),
                sentiment_score=float(sentiment_trace.get("sentiment_score") or 0.0),
                intensity=float(sentiment_trace.get("intensity") or 0.0),
                cues_json=list(sentiment_trace.get("cues") or []),
                metadata_json={
                    "message_length": len(message.strip()),
                    "has_question": "?" in message,
                },
            )
        except Exception:
            _log.warning("Failed to persist sentiment trace", exc_info=True)

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
                score_pct=int(profile_confidence.score_pct),
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
            profile_confidence_score_pct=profile_confidence.score_pct,
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
        sentiment_trace: Dict[str, Any],
    ) -> Dict[str, Any] | None:
        if intent.primary_intent != "occasion_recommendation":
            return None
        occasion = str(live_context.occasion_signal or "").strip()
        wardrobe_items = list(getattr(user_context, "wardrobe_items", []) or [])
        if not occasion or not wardrobe_items:
            return None

        outfit = self._select_wardrobe_occasion_outfit(wardrobe_items=wardrobe_items, occasion=occasion)
        outfit, blocked_terms = self._filter_restricted_recommendation_items(outfit)
        if not outfit:
            return None

        reasoning = f"Built from your saved wardrobe for {occasion.replace('_', ' ')}."
        catalog_upsell = self._build_catalog_upsell(
            rationale="Your wardrobe covers the occasion first, but I can also show stronger catalog options if you want a more elevated or optimized version.",
            entry_intent="occasion_recommendation",
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
            profile_confidence_score_pct=profile_confidence.score_pct,
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
                "catalog_upsell": catalog_upsell,
                "recommendation_confidence": recommendation_confidence.model_dump(),
                "restricted_item_exclusion_count": len(blocked_terms),
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
            "sentiment_trace": sentiment_trace,
            "handler": "occasion_recommendation_wardrobe_first",
            "handler_payload": {
                "answer_source": "wardrobe_first",
                "selected_item_ids": [str(item.get("product_id") or "") for item in outfit],
                "answer_components": answer_components,
                "catalog_upsell": catalog_upsell,
                "recommendation_confidence": recommendation_confidence.model_dump(),
                "restricted_item_exclusion_count": len(blocked_terms),
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
            "last_sentiment_trace": sentiment_trace,
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
            },
            "filters_applied": {},
            "outfits": [outfit_card.model_dump()],
            "follow_up_suggestions": ["Show me more from my wardrobe", "Show me catalog alternatives", str(catalog_upsell["cta"])],
            "metadata": metadata,
        }

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
    def _wardrobe_item_to_outfit_item(item: Dict[str, Any]) -> Dict[str, Any]:
        role = str(item.get("_role") or "").strip()
        return {
            "product_id": str(item.get("id") or ""),
            "title": str(item.get("title") or ""),
            "image_url": str(item.get("image_url") or item.get("image_path") or ""),
            "price": "",
            "product_url": "",
            "garment_category": str(item.get("garment_category") or ""),
            "garment_subtype": str(item.get("garment_subtype") or ""),
            "primary_color": str(item.get("primary_color") or ""),
            "role": role,
            "formality_level": str(item.get("formality_level") or ""),
            "occasion_fit": str(item.get("occasion_fit") or ""),
            "pattern_type": str(item.get("pattern_type") or ""),
            "volume_profile": "",
            "fit_type": "",
            "silhouette_type": "",
            "source": "wardrobe",
        }

    def _build_wardrobe_first_capsule_plan(
        self,
        *,
        message: str,
        wardrobe_items: List[Dict[str, Any]],
    ) -> List[OutfitCard]:
        if not wardrobe_items:
            return []

        planning_type = "trip" if any(token in str(message or "").lower() for token in ("trip", "travel", "vacation", "pack")) else "capsule"
        look_note = "Wardrobe-first trip look." if planning_type == "trip" else "Wardrobe-first capsule look."
        ranked = sorted(
            [dict(item, _role=self._capsule_role(item)) for item in wardrobe_items],
            key=lambda item: str(item.get("title") or "").lower(),
        )
        one_pieces = [item for item in ranked if item.get("_role") == "one_piece"]
        tops = [item for item in ranked if item.get("_role") == "top"]
        bottoms = [item for item in ranked if item.get("_role") == "bottom"]

        cards: List[OutfitCard] = []
        rank = 1
        if one_pieces:
            for item in one_pieces[:2]:
                cards.append(
                    OutfitCard(
                        rank=rank,
                        title=f"Wardrobe Plan {rank}",
                        reasoning="Built from a saved one-piece anchor in your wardrobe.",
                        occasion_note=look_note,
                        items=[self._wardrobe_item_to_outfit_item(dict(item, _role="one_piece"))],
                    )
                )
                rank += 1

        for top in tops[:2]:
            if not bottoms:
                break
            bottom = next((candidate for candidate in bottoms if candidate.get("id") != top.get("id")), None)
            if bottom is None:
                continue
            cards.append(
                OutfitCard(
                    rank=rank,
                    title=f"Wardrobe Plan {rank}",
                    reasoning="Built from saved top and bottom anchors in your wardrobe.",
                    occasion_note=look_note,
                    items=[
                        self._wardrobe_item_to_outfit_item(dict(top, _role="top")),
                        self._wardrobe_item_to_outfit_item(dict(bottom, _role="bottom")),
                    ],
                )
            )
            rank += 1
            if rank > 3:
                break

        if not cards and ranked:
            cards.append(
                OutfitCard(
                    rank=1,
                    title="Wardrobe Plan 1",
                    reasoning="Built from the strongest saved wardrobe anchor available.",
                    occasion_note=look_note,
                    items=[self._wardrobe_item_to_outfit_item(dict(ranked[0], _role=ranked[0].get("_role") or "other"))],
                )
            )
        sanitized_cards: List[OutfitCard] = []
        for card in cards[:3]:
            allowed_items, _blocked_terms = self._filter_restricted_recommendation_items(list(card.items))
            if not allowed_items:
                continue
            card.items = allowed_items
            card.rank = len(sanitized_cards) + 1
            sanitized_cards.append(card)
        return sanitized_cards

    @staticmethod
    def _capsule_role(item: Dict[str, Any]) -> str:
        category = str(item.get("garment_category") or item.get("garment_subtype") or "").strip().lower()
        title = str(item.get("title") or "").strip().lower()
        corpus = f"{category} {title}".strip()
        if any(token in corpus for token in ("dress", "jumpsuit", "suit")):
            return "one_piece"
        if any(token in corpus for token in ("top", "shirt", "blouse", "blazer", "jacket", "coat", "cardigan", "outerwear", "tee", "sweater")):
            return "top"
        if any(token in corpus for token in ("bottom", "trousers", "pants", "jeans", "skirt", "shorts")):
            return "bottom"
        return "other"

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
        sentiment_trace: Dict[str, Any] | None = None,
        channel: str = "web",
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
            "sentiment_trace": sentiment_trace or {},
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

    @staticmethod
    def _build_intent_routing_metadata(
        *,
        intent: IntentClassification,
        handler_payload: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        payload = dict(handler_payload or {})
        default_read_map = {
            "style_discovery": ["user_profile", "style_preference", "derived_interpretations"],
            "explanation_request": ["recommendation_history", "conversation_memory", "profile_confidence"],
        }
        default_write_map = {
            "style_discovery": ["conversation_memory", "confidence_history"],
            "explanation_request": ["conversation_memory"],
        }
        memory_sources_read = [
            str(value).strip()
            for value in (
                list(payload.get("memory_sources_read") or [])
                or default_read_map.get(intent.primary_intent, [])
            )
            if str(value).strip()
        ]
        memory_sources_written = [
            str(value).strip()
            for value in (
                list(payload.get("memory_sources_written") or [])
                or default_write_map.get(intent.primary_intent, [])
            )
            if str(value).strip()
        ]
        return {
            "primary_intent": intent.primary_intent,
            "intent_confidence": intent.confidence,
            "secondary_intents": list(intent.secondary_intents or []),
            "reason_codes": list(intent.reason_codes or []),
            "memory_sources_read": memory_sources_read,
            "memory_sources_written": memory_sources_written,
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
