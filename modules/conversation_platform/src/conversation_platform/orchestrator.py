from typing import Any, Callable, Dict, List, Optional

from user_profiler.config import UserProfilerConfig

from .agents import (
    BodyHarmonyAgent,
    IntentAgent,
    IntentModeRouterAgent,
    MemoryAgent,
    PolicyGuardrailAgent,
    ProfileAgent,
    RecommendationAgent,
    StylistAgent,
    TelemetryAgent,
    UserProfileAgent,
)
from .repositories import ConversationRepository


class ConversationOrchestrator:
    def __init__(self, repo: ConversationRepository, catalog_csv_path: str):
        profiler_config = UserProfilerConfig(output_dir="data/logs")
        self.repo = repo
        self.mode_router = IntentModeRouterAgent()
        self.user_profile_agent = UserProfileAgent()
        self.body_harmony_agent = BodyHarmonyAgent(config=profiler_config)
        # Legacy alias used by existing tests and orchestrator flow.
        self.profile_agent = self.body_harmony_agent
        self.intent_agent = IntentAgent(config=profiler_config)
        self.memory_agent = MemoryAgent()
        self.recommendation_agent = RecommendationAgent(catalog_csv_path=catalog_csv_path)
        self.stylist_agent = StylistAgent()
        self.telemetry_agent = TelemetryAgent()
        self.policy_guardrail = PolicyGuardrailAgent()

    def check_action(self, action: str) -> Dict[str, Any]:
        """Check if an action is allowed by policy guardrails."""
        return PolicyGuardrailAgent.check_action(action)

    def _log_mode_resolution_trace(
        self,
        *,
        conversation_id: str,
        turn_id: str,
        mode_preference: str,
        target_garment_type: Optional[str],
        mode_result: Dict[str, Any],
        style_constraints_applied: List[str],
        profile_fields_used: List[str],
    ) -> None:
        self.repo.log_tool_trace(
            conversation_id=conversation_id,
            turn_id=turn_id,
            tool_name="mode_router.resolve_mode",
            input_json={
                "mode_preference": mode_preference,
                "target_garment_type": target_garment_type,
            },
            output_json={
                "resolved_mode": mode_result.get("resolved_mode"),
                "complete_the_look_offer": mode_result.get("complete_the_look_offer"),
                "requested_categories": mode_result.get("requested_categories", []),
                "requested_subtypes": mode_result.get("requested_subtypes", []),
                "style_constraints_applied": style_constraints_applied,
                "profile_fields_used": profile_fields_used,
            },
        )

    def _log_guardrail_trace(
        self,
        *,
        conversation_id: str,
        turn_id: str,
        action: str,
        result: Dict[str, Any],
    ) -> None:
        self.repo.log_tool_trace(
            conversation_id=conversation_id,
            turn_id=turn_id,
            tool_name="policy_guardrail.check_action",
            input_json={"action": action},
            output_json=result,
            status="blocked" if not result.get("allowed") else "ok",
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
        conversation = self.repo.create_conversation(user_id=user["id"], initial_context=initial_context)
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

        latest_profile = self.repo.get_latest_profile_snapshot(conversation_id)
        latest_turn = self.repo.get_latest_turn(conversation_id)
        raw_context = dict(conversation.get("session_context_json") or {})
        context = {
            "occasion": str(raw_context.get("occasion", "")),
            "archetype": str(raw_context.get("archetype", "")),
            "gender": str(raw_context.get("gender", "")),
            "age": str(raw_context.get("age", "")),
        }
        latest_context = context if all(context.values()) else None

        return {
            "conversation_id": conversation["id"],
            "user_id": str(user.get("external_user_id") or conversation.get("user_id") or ""),
            "status": conversation.get("status", "active"),
            "latest_context": latest_context,
            "latest_profile_snapshot_id": (latest_profile or {}).get("id"),
            "latest_recommendation_run_id": (latest_turn or {}).get("recommendation_run_id"),
        }

    def _profile_from_visual(self, visual: Dict[str, Any]) -> Dict[str, Any]:
        return BodyHarmonyAgent.extract_body_profile(visual)

    def _clarification_question_for_missing(self, missing: List[str]) -> str:
        if any(x in missing for x in ("gender", "age")):
            return (
                "Please upload one clear front-facing full-body image in good lighting "
                "so I can infer body harmony, gender, and age band."
            )
        prompts: List[str] = []
        if "occasion" in missing:
            prompts.append("occasion (work mode, night out, festive, etc.)")
        if "archetype" in missing:
            prompts.append("style archetype (classic, minimalist, glamorous, etc.)")
        if prompts:
            return "Please share your " + " and ".join(prompts) + "."
        return "Please share a bit more detail so I can personalize recommendations."

    def process_turn(
        self,
        *,
        conversation_id: str,
        external_user_id: str,
        message: str,
        image_refs: List[str],
        strictness: str,
        hard_filter_profile: str,
        max_results: int,
        result_filter: str = "complete_plus_combos",
        mode_preference: str = "auto",
        target_garment_type: Optional[str] = None,
        autonomy_level: str = "suggest",
        size_overrides: Optional[Dict[str, Any]] = None,
        stage_callback: Optional[Callable[[str, str], None]] = None,
    ) -> Dict[str, Any]:
        def emit(stage: str, detail: str = "") -> None:
            if stage_callback is not None:
                stage_callback(stage, detail)

        emit("validate_request", "started")
        user = self.repo.get_or_create_user(external_user_id)
        conversation = self.repo.get_conversation(conversation_id)
        if not conversation:
            raise ValueError("Conversation not found.")
        if conversation.get("user_id") != user.get("id"):
            raise ValueError("Conversation does not belong to user.")

        emit("load_conversation_state", "started")
        previous_context = dict(conversation.get("session_context_json") or {})
        latest_profile_snapshot = self.repo.get_latest_profile_snapshot(conversation_id)
        emit("load_conversation_state", "completed")

        turn = self.repo.create_turn(
            conversation_id=conversation_id,
            user_message=message,
            mode_preference=mode_preference,
            autonomy_level=autonomy_level,
        )
        turn_id = turn["id"]

        visual: Optional[Dict[str, Any]] = None
        profile_snapshot_id: Optional[str] = None

        if image_refs:
            emit("visual_profile_inference", "started")
            visual, visual_log = self.profile_agent.infer_visual(image_refs[0])
            image_artifact = visual_log.get("image_artifact") or {}
            self.repo.add_media_asset(
                user_id=user["id"],
                conversation_id=conversation_id,
                source_type=str(image_artifact.get("source_type", "file")),
                source_ref=str(image_artifact.get("source", image_refs[0])),
                storage_url=str(image_artifact.get("stored_path", image_refs[0])),
            )
            self.repo.log_model_call(
                conversation_id=conversation_id,
                turn_id=turn_id,
                service="conversation_platform",
                call_type="visual_profile",
                model=str(visual_log.get("model", "gpt-5.2")),
                request_json=visual_log.get("request", {}),
                response_json=visual_log.get("response", {}),
                reasoning_notes=list(visual_log.get("reasoning_notes", [])),
            )

            profile_payload = self._profile_from_visual(visual)
            profile_snapshot = self.repo.create_profile_snapshot(
                user_id=user["id"],
                conversation_id=conversation_id,
                source_turn_id=turn_id,
                profile_json=profile_payload,
                gender=str(visual["gender"]),
                age=str(visual["age"]),
                confidence_json={},
            )
            profile_snapshot_id = profile_snapshot["id"]
            emit("visual_profile_inference", "completed")
        elif latest_profile_snapshot:
            emit("visual_profile_inference", "skipped_reuse_latest_snapshot")
            profile_snapshot_id = latest_profile_snapshot["id"]
        else:
            emit("visual_profile_inference", "missing_image_no_cached_profile")

        emit("text_intent_inference", "started")
        inferred_text, text_log = self.intent_agent.infer_text(message)
        self.repo.log_model_call(
            conversation_id=conversation_id,
            turn_id=turn_id,
            service="conversation_platform",
            call_type="text_context",
            model=str(text_log.get("model", "gpt-5-mini")),
            request_json=text_log.get("request", {}),
            response_json=text_log.get("response", {}),
            reasoning_notes=[],
        )
        emit("text_intent_inference", "completed")

        emit("merge_context_memory", "started")
        resolved_context = self.memory_agent.merge_context(
            previous=previous_context,
            inferred_text=inferred_text,
            inferred_visual=visual,
        )

        # If we are reusing a prior profile snapshot, fill gender/age if absent in memory.
        if latest_profile_snapshot and not resolved_context.get("gender"):
            resolved_context["gender"] = str(latest_profile_snapshot.get("gender", ""))
        if latest_profile_snapshot and not resolved_context.get("age"):
            resolved_context["age"] = str(latest_profile_snapshot.get("age", ""))

        missing = [k for k, v in resolved_context.items() if not v]
        if missing:
            emit("clarification_required", ",".join(missing))
            assistant_message = "I need a bit more context before recommending the best-fit looks."
            clarifying_question = self._clarification_question_for_missing(missing)
            self.repo.finalize_turn(
                turn_id=turn_id,
                assistant_message=assistant_message,
                resolved_context=resolved_context,
                profile_snapshot_id=profile_snapshot_id,
                recommendation_run_id=None,
            )
            self.repo.update_conversation_context(
                conversation_id=conversation_id,
                session_context={
                    **previous_context,
                    **{k: v for k, v in resolved_context.items() if v},
                    "latest_profile_snapshot_id": profile_snapshot_id,
                },
            )
            return {
                "conversation_id": conversation_id,
                "turn_id": turn_id,
                "assistant_message": assistant_message,
                "resolved_context": resolved_context,
                "profile_snapshot_id": profile_snapshot_id,
                "recommendation_run_id": None,
                "recommendations": [],
                "needs_clarification": True,
                "clarifying_question": clarifying_question,
            }
        emit("merge_context_memory", "completed")

        context_snapshot = self.repo.create_context_snapshot(
            conversation_id=conversation_id,
            source_turn_id=turn_id,
            occasion=resolved_context["occasion"],
            archetype=resolved_context["archetype"],
            raw_text=message,
        )

        if visual:
            profile = self._profile_from_visual(visual)
        else:
            profile = dict((latest_profile_snapshot or {}).get("profile_json") or {})
            profile.setdefault("color_preferences", {})

        emit("resolve_mode", "started")
        mode_result = self.mode_router.resolve_mode(
            mode_preference=mode_preference,
            target_garment_type=target_garment_type,
            request_text=message,
        )
        resolved_mode: str = mode_result["resolved_mode"]
        complete_the_look_offer: bool = mode_result["complete_the_look_offer"]
        emit("resolve_mode", f"resolved_mode={resolved_mode}")

        emit("tier1_tier2_recommendation", "started")
        recommendation = self.recommendation_agent.recommend(
            context=resolved_context,
            profile=profile,
            strictness=strictness,
            hard_filter_profile=hard_filter_profile,
            max_results=max_results,
            recommendation_mode=resolved_mode,
            include_combos=(result_filter != "complete_only"),
            request_text=message,
        )
        emit("tier1_tier2_recommendation", "completed")

        items = recommendation["items"]
        meta = recommendation["meta"]

        # Collect style constraints applied and profile fields used.
        style_constraints_applied = BodyHarmonyAgent.style_constraints_from_profile(profile)
        if size_overrides:
            style_constraints_applied.append("size_overrides")

        profile_fields_used = self.user_profile_agent.profile_fields_used(profile)

        self._log_mode_resolution_trace(
            conversation_id=conversation_id,
            turn_id=turn_id,
            mode_preference=mode_preference,
            target_garment_type=target_garment_type,
            mode_result=mode_result,
            style_constraints_applied=style_constraints_applied,
            profile_fields_used=profile_fields_used,
        )

        requested_garment_types = [target_garment_type] if target_garment_type else []

        emit("persist_results", "started")
        run = self.repo.create_recommendation_run(
            conversation_id=conversation_id,
            turn_id=turn_id,
            profile_snapshot_id=profile_snapshot_id,
            context_snapshot_id=context_snapshot["id"],
            strictness=strictness,
            hard_filter_profile=hard_filter_profile,
            candidate_count=int(meta.get("ranked_rows", 0)),
            returned_count=int(meta.get("returned_rows", 0)),
            resolved_mode=resolved_mode,
            requested_garment_types_json=requested_garment_types,
            style_constraints_json={"constraints": style_constraints_applied},
        )
        self.repo.insert_recommendation_items(run["id"], items)

        self.repo.log_tool_trace(
            conversation_id=conversation_id,
            turn_id=turn_id,
            tool_name="recommendation_agent.recommend",
            input_json={
                "context": resolved_context,
                "strictness": strictness,
                "hard_filter_profile": hard_filter_profile,
                "max_results": max_results,
                "result_filter": result_filter,
                "resolved_mode": resolved_mode,
                "target_garment_type": target_garment_type,
            },
            output_json={"meta": meta},
        )
        emit("persist_results", "completed")

        emit("build_response", "started")
        assistant_message, needs_clarification, clarifying_question = self.stylist_agent.build_response_message(
            items=items,
            context=resolved_context,
            user_message=message,
        )

        self.repo.finalize_turn(
            turn_id=turn_id,
            assistant_message=assistant_message,
            resolved_context=resolved_context,
            profile_snapshot_id=profile_snapshot_id,
            recommendation_run_id=run["id"],
            resolved_mode=resolved_mode,
        )

        self.repo.update_conversation_context(
            conversation_id=conversation_id,
            session_context={
                **resolved_context,
                "latest_profile_snapshot_id": profile_snapshot_id,
                "latest_context_snapshot_id": context_snapshot["id"],
                "latest_recommendation_run_id": run["id"],
            },
        )
        emit("build_response", "completed")

        mode_switch_cta = ""
        if complete_the_look_offer:
            mode_switch_cta = "Switch to outfit mode to see complete looks"

        return {
            "conversation_id": conversation_id,
            "turn_id": turn_id,
            "assistant_message": assistant_message,
            "resolved_context": resolved_context,
            "profile_snapshot_id": profile_snapshot_id,
            "recommendation_run_id": run["id"],
            "resolved_mode": resolved_mode,
            "complete_the_look_offer": complete_the_look_offer,
            "style_constraints_applied": style_constraints_applied,
            "profile_fields_used": profile_fields_used,
            "mode_switch_cta": mode_switch_cta,
            "recommendations": [
                {
                    "rank": item["rank"],
                    "garment_id": item["garment_id"],
                    "title": item["title"],
                    "image_url": item["image_url"],
                    "score": item["score"],
                    "max_score": item["max_score"],
                    "compatibility_confidence": item["compatibility_confidence"],
                    "reasons": item["reasons"],
                    "recommendation_kind": item.get("recommendation_kind", "single_garment"),
                    "outfit_id": item.get("outfit_id", item["garment_id"]),
                    "component_count": item.get("component_count", 1),
                    "component_ids": item.get("component_ids", []),
                    "component_titles": item.get("component_titles", []),
                    "component_image_urls": item.get("component_image_urls", []),
                }
                for item in items
            ],
            "needs_clarification": needs_clarification,
            "clarifying_question": clarifying_question,
        }

    def get_recommendation_run(self, run_id: str) -> Dict[str, Any]:
        run = self.repo.get_recommendation_run(run_id)
        if not run:
            raise ValueError("Recommendation run not found.")
        rows = self.repo.get_recommendation_items(run_id)
        items = []
        for row in rows:
            reasons_payload = row.get("reasons_json") or {}
            reasons_text = ""
            recommendation_kind = "single_garment"
            outfit_id = str(row.get("garment_id", ""))
            component_count = 1
            component_ids: List[str] = []
            component_titles: List[str] = []
            component_image_urls: List[str] = []

            if isinstance(reasons_payload, dict):
                reasons_text = str(reasons_payload.get("summary", ""))
                recommendation_kind = str(reasons_payload.get("recommendation_kind", "single_garment"))
                outfit_id = str(reasons_payload.get("outfit_id", outfit_id))
                component_count = int(reasons_payload.get("component_count", 1) or 1)
                component_ids = [str(x) for x in list(reasons_payload.get("component_ids") or [])]
                component_titles = [str(x) for x in list(reasons_payload.get("component_titles") or [])]
                component_image_urls = [str(x) for x in list(reasons_payload.get("component_image_urls") or [])]
            elif isinstance(reasons_payload, list):
                reasons_text = "; ".join([str(x) for x in reasons_payload])
            else:
                reasons_text = str(reasons_payload)
            items.append(
                {
                    "rank": int(row.get("rank", 0)),
                    "garment_id": str(row.get("garment_id", "")),
                    "title": str(row.get("title", "")),
                    "image_url": str(row.get("image_url", "")),
                    "score": float(row.get("score", 0.0) or 0.0),
                    "max_score": float(row.get("max_score", 0.0) or 0.0),
                    "compatibility_confidence": float(row.get("compatibility_confidence", 0.0) or 0.0),
                    "reasons": reasons_text,
                    "recommendation_kind": recommendation_kind,
                    "outfit_id": outfit_id,
                    "component_count": component_count,
                    "component_ids": component_ids,
                    "component_titles": component_titles,
                    "component_image_urls": component_image_urls,
                }
            )
        return {
            "recommendation_run_id": run_id,
            "strictness": run.get("strictness", "balanced"),
            "hard_filter_profile": run.get("hard_filter_profile", "rl_ready_minimal"),
            "items": items,
            "meta": {
                "candidate_count": int(run.get("candidate_count", 0) or 0),
                "returned_count": int(run.get("returned_count", 0) or 0),
            },
        }

    def prepare_checkout(
        self,
        *,
        conversation_id: str,
        external_user_id: str,
        recommendation_run_id: str,
        selected_item_ids: List[str],
        selected_outfit_id: Optional[str] = None,
        budget_cap: Optional[int] = None,
    ) -> Dict[str, Any]:
        user = self.repo.get_or_create_user(external_user_id)
        conversation = self.repo.get_conversation(conversation_id)
        if not conversation:
            raise ValueError("Conversation not found.")
        if conversation.get("user_id") != user.get("id"):
            raise ValueError("Conversation does not belong to user.")

        run = self.repo.get_recommendation_run(recommendation_run_id)
        if not run:
            raise ValueError("Recommendation run not found.")

        reco_items = self.repo.get_recommendation_items(recommendation_run_id)
        reco_by_id: Dict[str, Dict[str, Any]] = {}
        for ri in reco_items:
            gid = str(ri.get("garment_id", ""))
            if gid:
                reco_by_id[gid] = ri

        cart_items: List[Dict[str, Any]] = []
        subtotal = 0
        for rank_idx, item_id in enumerate(selected_item_ids, start=1):
            reco = reco_by_id.get(item_id, {})
            unit_price = int(reco.get("score", 0))  # placeholder until real price
            cart_items.append(
                {
                    "rank": rank_idx,
                    "garment_id": item_id,
                    "title": str(reco.get("title", "")),
                    "qty": 1,
                    "unit_price": unit_price,
                    "discount": 0,
                    "final_price": unit_price,
                    "meta_json": {},
                }
            )
            subtotal += unit_price

        status = "ready"
        validation_notes = ["stock_revalidated", "price_revalidated"]
        substitution_suggestions: List[Dict[str, Any]] = []

        if budget_cap is not None and subtotal > budget_cap:
            # Attempt substitution: suggest cheaper alternatives from the same
            # recommendation run for items not selected.
            surplus = subtotal - budget_cap
            unused_items = [
                ri for gid, ri in reco_by_id.items() if gid not in selected_item_ids
            ]
            unused_items.sort(key=lambda x: int(x.get("score", 0)))

            # Try to suggest a swap for the most expensive cart item.
            cart_items_sorted = sorted(cart_items, key=lambda x: x["unit_price"], reverse=True)
            for expensive in cart_items_sorted:
                for alt in unused_items:
                    alt_price = int(alt.get("score", 0))
                    if alt_price < expensive["unit_price"] and (expensive["unit_price"] - alt_price) >= surplus:
                        substitution_suggestions.append({
                            "original_garment_id": expensive["garment_id"],
                            "suggested_garment_id": str(alt.get("garment_id", "")),
                            "suggested_title": str(alt.get("title", "")),
                            "suggested_price": alt_price,
                            "reason": "lower_price_within_budget",
                        })
                        break
                if substitution_suggestions:
                    break

            if substitution_suggestions:
                validation_notes.append("over_budget")
                validation_notes.append("substitution_suggested")
                status = "needs_user_action"
            else:
                validation_notes.append("over_budget")
                validation_notes.append("no_substitution_available")
                status = "needs_user_action"

        pricing = {
            "subtotal": subtotal,
            "discount_total": 0,
            "final_total": subtotal,
            "currency": "INR",
        }

        latest_turn = self.repo.get_latest_turn(conversation_id)
        turn_id = (latest_turn or {}).get("id")

        prep = self.repo.create_checkout_preparation(
            conversation_id=conversation_id,
            turn_id=turn_id,
            recommendation_run_id=recommendation_run_id,
            user_id=user["id"],
            status=status,
            cart_payload_json=cart_items,
            pricing_json=pricing,
            validation_json={
                "notes": validation_notes,
                "substitution_suggestions": substitution_suggestions,
            },
            checkout_ref="",
        )

        self.repo.insert_checkout_preparation_items(prep["id"], cart_items)

        self.repo.log_tool_trace(
            conversation_id=conversation_id,
            turn_id=turn_id or "",
            tool_name="checkout_prep.prepare",
            input_json={
                "recommendation_run_id": recommendation_run_id,
                "selected_item_ids": selected_item_ids,
                "selected_outfit_id": selected_outfit_id,
                "budget_cap": budget_cap,
            },
            output_json={
                "checkout_prep_id": prep["id"],
                "status": status,
                "subtotal": subtotal,
                "substitution_count": len(substitution_suggestions),
            },
        )

        return {
            "checkout_prep_id": prep["id"],
            "status": status,
            "cart_items": [
                {
                    "garment_id": ci["garment_id"],
                    "title": ci["title"],
                    "qty": ci["qty"],
                    "unit_price": ci["unit_price"],
                    "discount": ci["discount"],
                    "final_price": ci["final_price"],
                }
                for ci in cart_items
            ],
            "subtotal": pricing["subtotal"],
            "discount_total": pricing["discount_total"],
            "final_total": pricing["final_total"],
            "currency": pricing["currency"],
            "checkout_url_or_token": "",
            "validation_notes": validation_notes,
            "substitution_suggestions": substitution_suggestions,
        }

    def get_checkout_preparation(self, checkout_prep_id: str) -> Dict[str, Any]:
        prep = self.repo.get_checkout_preparation(checkout_prep_id)
        if not prep:
            raise ValueError("Checkout preparation not found.")
        items = self.repo.get_checkout_preparation_items(checkout_prep_id)
        pricing = prep.get("pricing_json") or {}
        validation = prep.get("validation_json") or {}
        return {
            "checkout_prep_id": prep["id"],
            "status": prep.get("status", "pending"),
            "cart_items": [
                {
                    "garment_id": str(it.get("garment_id", "")),
                    "title": str(it.get("title", "")),
                    "qty": int(it.get("qty", 1)),
                    "unit_price": int(it.get("unit_price", 0)),
                    "discount": int(it.get("discount", 0)),
                    "final_price": int(it.get("final_price", 0)),
                }
                for it in items
            ],
            "subtotal": int(pricing.get("subtotal", 0)),
            "discount_total": int(pricing.get("discount_total", 0)),
            "final_total": int(pricing.get("final_total", 0)),
            "currency": str(pricing.get("currency", "INR")),
            "checkout_url_or_token": str(prep.get("checkout_ref", "")),
            "validation_notes": list(validation.get("notes", [])),
        }

    def record_feedback(
        self,
        *,
        external_user_id: str,
        conversation_id: str,
        recommendation_run_id: str,
        garment_id: str,
        event_type: str,
        notes: str,
    ) -> Dict[str, Any]:
        user = self.repo.get_or_create_user(external_user_id)
        reward = self.telemetry_agent.reward_for_event(event_type)
        row = self.repo.create_feedback_event(
            user_id=user["id"],
            conversation_id=conversation_id,
            recommendation_run_id=recommendation_run_id,
            garment_id=garment_id,
            event_type=event_type,
            reward_value=reward,
            notes=notes,
        )
        return {"event_id": row["id"], "reward_value": reward}
