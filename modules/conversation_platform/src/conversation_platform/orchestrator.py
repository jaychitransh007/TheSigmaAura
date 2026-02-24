from typing import Any, Callable, Dict, List, Optional

from user_profiler.config import UserProfilerConfig
from user_profiler.schemas import BODY_ENUMS

from .agents import IntentAgent, MemoryAgent, ProfileAgent, RecommendationAgent, StylistAgent, TelemetryAgent
from .repositories import ConversationRepository


class ConversationOrchestrator:
    def __init__(self, repo: ConversationRepository, catalog_csv_path: str):
        profiler_config = UserProfilerConfig(output_dir="data/output")
        self.repo = repo
        self.profile_agent = ProfileAgent(config=profiler_config)
        self.intent_agent = IntentAgent(config=profiler_config)
        self.memory_agent = MemoryAgent()
        self.recommendation_agent = RecommendationAgent(catalog_csv_path=catalog_csv_path)
        self.stylist_agent = StylistAgent()
        self.telemetry_agent = TelemetryAgent()

    def create_conversation(self, *, external_user_id: str, initial_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        user = self.repo.get_or_create_user(external_user_id)
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
        profile = {key: visual[key] for key in BODY_ENUMS.keys()}
        profile["color_preferences"] = {}
        return profile

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

        turn = self.repo.create_turn(conversation_id=conversation_id, user_message=message)
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

        emit("tier1_tier2_recommendation", "started")
        recommendation = self.recommendation_agent.recommend(
            context=resolved_context,
            profile=profile,
            strictness=strictness,
            hard_filter_profile=hard_filter_profile,
            max_results=max_results,
        )
        emit("tier1_tier2_recommendation", "completed")

        items = recommendation["items"]
        meta = recommendation["meta"]

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

        return {
            "conversation_id": conversation_id,
            "turn_id": turn_id,
            "assistant_message": assistant_message,
            "resolved_context": resolved_context,
            "profile_snapshot_id": profile_snapshot_id,
            "recommendation_run_id": run["id"],
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
            reasons = row.get("reasons_json") or []
            reasons_text = "; ".join([str(x) for x in reasons]) if isinstance(reasons, list) else str(reasons)
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
