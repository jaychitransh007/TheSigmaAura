from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Dict, List, Optional

from platform_core.config import AuraRuntimeConfig
from platform_core.repositories import ConversationRepository

from .agents.catalog_search_agent import CatalogSearchAgent
from .agents.outfit_architect import OutfitArchitect
from .agents.outfit_assembler import OutfitAssembler
from .agents.outfit_evaluator import OutfitEvaluator
from .agents.response_formatter import ResponseFormatter
from .context.conversation_memory import apply_conversation_memory, build_conversation_memory
from .context.occasion_resolver import resolve_occasion
from .context.user_context_builder import build_user_context, validate_minimum_profile
from .filters import build_global_hard_filters
from .services.catalog_retrieval_gateway import ApplicationCatalogRetrievalGateway
from .services.onboarding_gateway import ApplicationOnboardingGateway
from .services.tryon_service import TryonService
from .qna_messages import generate_stage_message
from .schemas import CombinedContext, LiveContext, OutfitCard

_log = logging.getLogger(__name__)


class AgenticOrchestrator:
    """Application-layer orchestrator implementing the 7-component pipeline."""

    def __init__(
        self,
        *,
        repo: ConversationRepository,
        onboarding_gateway: ApplicationOnboardingGateway,
        config: AuraRuntimeConfig,
        tryon_service: Optional[TryonService] = None,
    ) -> None:
        self.repo = repo
        self.onboarding_gateway = onboarding_gateway
        self.config = config
        self.tryon_service = tryon_service or TryonService()

        retrieval_gateway = ApplicationCatalogRetrievalGateway(repo.client)

        self.outfit_architect = OutfitArchitect()
        self.catalog_search_agent = CatalogSearchAgent(
            retrieval_gateway=retrieval_gateway,
            client=repo.client,
        )
        self.outfit_assembler = OutfitAssembler()
        self.outfit_evaluator = OutfitEvaluator()
        self.response_formatter = ResponseFormatter()

    # ------------------------------------------------------------------
    # Conversation lifecycle
    # ------------------------------------------------------------------

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

        # --- 1. User Context Builder ---
        emit("user_context", "started")
        user_context = build_user_context(
            external_user_id,
            onboarding_gateway=self.onboarding_gateway,
        )
        validate_minimum_profile(user_context)
        emit("user_context", "completed", ctx={"richness": user_context.profile_richness})

        # --- 2. Build context (occasion resolver is fallback only) ---
        emit("occasion_resolver", "started")
        previous_context = dict(conversation.get("session_context_json") or {})
        has_previous_recs = bool(previous_context.get("last_recommendations"))

        # Rule-based resolver provides fallback LiveContext + conversation memory
        fallback_live_context = resolve_occasion(message, has_previous_recommendations=has_previous_recs)
        conversation_memory = build_conversation_memory(previous_context, fallback_live_context)
        fallback_live_context = apply_conversation_memory(fallback_live_context, conversation_memory)

        # Build conversation history for the architect
        conversation_history = self._build_conversation_history(previous_context, message)

        emit("occasion_resolver", "completed", ctx={"user_need": message})

        # --- Build combined context (gender-only hard filter) ---
        hard_filters = build_global_hard_filters(user_context)

        previous_recs = previous_context.get("last_recommendations")
        combined_context = CombinedContext(
            user=user_context,
            live=fallback_live_context,
            hard_filters=hard_filters,
            previous_recommendations=previous_recs if isinstance(previous_recs, list) else None,
            conversation_memory=conversation_memory,
            conversation_history=conversation_history,
        )

        # Create turn record
        turn = self.repo.create_turn(conversation_id=conversation_id, user_message=message)
        turn_id = str(turn["id"])

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
            effective_live_context = fallback_live_context

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

        # Update combined context with effective live context from architect
        combined_context = combined_context.model_copy(update={"live": effective_live_context})

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
        emit("response_formatting", "completed", ctx={"outfit_count": min(len(evaluated), 3)})

        # --- 8. Virtual Try-On ---
        emit("virtual_tryon", "started")
        self._attach_tryon_images(response.outfits, external_user_id)
        emit("virtual_tryon", "completed")

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
            },
        )

        return {
            "conversation_id": conversation_id,
            "turn_id": turn_id,
            "assistant_message": response.message,
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
            product_url = ""
            for item in outfit.items:
                url = str(item.get("image_url") or "").strip()
                if url:
                    product_url = url
                    break
            if not product_url:
                return outfit, ""
            try:
                result = self.tryon_service.generate_tryon(
                    person_image_path=person_path,
                    product_image_url=product_url,
                )
                if result.get("success"):
                    return outfit, result["data_url"]
            except Exception:
                _log.warning("Try-on generation failed for outfit #%s", outfit.rank, exc_info=True)
            return outfit, ""

        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = {pool.submit(_generate_for_outfit, o): o for o in outfits}
            for future in as_completed(futures):
                outfit, data_url = future.result()
                if data_url:
                    outfit.tryon_image = data_url

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
            "occasion": live_context.occasion_signal or "",
            "style_goal": " ".join(live_context.specific_needs) if live_context.specific_needs else "",
            "live_context": live_context.model_dump(),
            "conversation_memory": conversation_memory,
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
                }
                for row in evaluated
            ],
            "response_metadata": response_metadata,
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
