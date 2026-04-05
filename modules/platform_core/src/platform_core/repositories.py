from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .supabase_rest import SupabaseRestClient


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ConversationRepository:
    def __init__(self, client: SupabaseRestClient):
        self.client = client

    def get_or_create_user(self, external_user_id: str) -> Dict[str, Any]:
        row = self.client.select_one("users", filters={"external_user_id": f"eq.{external_user_id}"})
        if row:
            return row
        return self.client.insert_one("users", {"external_user_id": external_user_id})

    def get_user_by_external_user_id(self, external_user_id: str) -> Optional[Dict[str, Any]]:
        return self.client.select_one("users", filters={"external_user_id": f"eq.{external_user_id}"})

    def get_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        return self.client.select_one("users", filters={"id": f"eq.{user_id}"})

    def create_conversation(self, user_id: str, initial_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        payload = {
            "user_id": user_id,
            "status": "active",
            "session_context_json": initial_context or {},
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
        }
        return self.client.insert_one("conversations", payload)

    def get_conversation(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        return self.client.select_one("conversations", filters={"id": f"eq.{conversation_id}"})

    def get_latest_conversation_for_user(
        self,
        user_id: str,
        *,
        status: str = "active",
    ) -> Optional[Dict[str, Any]]:
        rows = self.client.select_many(
            "conversations",
            filters={
                "user_id": f"eq.{user_id}",
                "status": f"eq.{status}",
            },
            order="updated_at.desc",
            limit=1,
        )
        return rows[0] if rows else None

    def merge_external_user_identity(
        self,
        *,
        canonical_external_user_id: str,
        alias_external_user_id: str,
    ) -> Dict[str, Any]:
        canonical_external = str(canonical_external_user_id or "").strip()
        alias_external = str(alias_external_user_id or "").strip()
        if not canonical_external:
            raise ValueError("canonical_external_user_id is required")
        if not alias_external or alias_external == canonical_external:
            return self.get_or_create_user(canonical_external)

        canonical_user = self.get_or_create_user(canonical_external)
        alias_user = self.get_user_by_external_user_id(alias_external)
        if not alias_user:
            return canonical_user

        alias_user_id = str(alias_user.get("id") or "").strip()
        canonical_user_id = str(canonical_user.get("id") or "").strip()
        if alias_user_id and canonical_user_id and alias_user_id != canonical_user_id:
            self.client.update_one(
                "conversations",
                filters={"user_id": f"eq.{alias_user_id}"},
                patch={"user_id": canonical_user_id, "updated_at": _now_iso()},
            )

        for table in (
            "catalog_interaction_history",
            "confidence_history",
            "policy_event_log",
            "dependency_validation_events",
        ):
            self.client.update_one(
                table,
                filters={"user_id": f"eq.{alias_external}"},
                patch={"user_id": canonical_external},
            )

        return canonical_user

    def update_conversation_context(self, conversation_id: str, session_context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        return self.client.update_one(
            "conversations",
            filters={"id": f"eq.{conversation_id}"},
            patch={"session_context_json": session_context, "updated_at": _now_iso()},
        )

    def update_user_profile(self, user_id: str, profile_json: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        return self.client.update_one(
            "users",
            filters={"id": f"eq.{user_id}"},
            patch={"profile_json": profile_json, "profile_updated_at": _now_iso(), "updated_at": _now_iso()},
        )

    def create_turn(self, conversation_id: str, user_message: str) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "conversation_id": conversation_id,
            "user_message": user_message,
            "assistant_message": "",
            "resolved_context_json": {},
            "created_at": _now_iso(),
        }
        return self.client.insert_one("conversation_turns", payload)

    def finalize_turn(
        self,
        *,
        turn_id: str,
        assistant_message: str,
        resolved_context: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        return self.client.update_one(
            "conversation_turns",
            filters={"id": f"eq.{turn_id}"},
            patch={
                "assistant_message": assistant_message,
                "resolved_context_json": resolved_context,
            },
        )

    def get_latest_turn(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        rows = self.client.select_many(
            "conversation_turns",
            filters={"conversation_id": f"eq.{conversation_id}"},
            order="created_at.desc",
            limit=1,
        )
        return rows[0] if rows else None

    def get_turn(self, turn_id: str) -> Optional[Dict[str, Any]]:
        return self.client.select_one("conversation_turns", filters={"id": f"eq.{turn_id}"})

    def log_model_call(
        self,
        *,
        conversation_id: str,
        turn_id: str,
        service: str,
        call_type: str,
        model: str,
        request_json: Dict[str, Any],
        response_json: Dict[str, Any],
        reasoning_notes: List[str],
        latency_ms: Optional[int] = None,
        status: str = "ok",
        error_message: str = "",
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "conversation_id": conversation_id,
            "turn_id": turn_id,
            "service": service,
            "call_type": call_type,
            "model": model,
            "request_json": request_json,
            "response_json": response_json,
            "reasoning_notes_json": reasoning_notes,
            "status": status,
            "error_message": error_message,
            "created_at": _now_iso(),
        }
        if latency_ms is not None:
            payload["latency_ms"] = latency_ms
        return self.client.insert_one("model_call_logs", payload)

    def create_feedback_event(
        self,
        *,
        user_id: str,
        conversation_id: str,
        turn_id: Optional[str] = None,
        outfit_rank: Optional[int] = None,
        garment_id: str,
        event_type: str,
        reward_value: int = 0,
        notes: str = "",
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "user_id": user_id,
            "conversation_id": conversation_id,
            "garment_id": garment_id,
            "event_type": event_type,
            "reward_value": reward_value,
            "notes": notes,
            "created_at": _now_iso(),
        }
        if turn_id:
            payload["turn_id"] = turn_id
        if outfit_rank is not None:
            payload["outfit_rank"] = outfit_rank
        return self.client.insert_one("feedback_events", payload)

    # -- catalog_interaction_history ----------------------------------------

    def create_catalog_interaction(
        self,
        *,
        user_id: str,
        product_id: str,
        interaction_type: str,
        conversation_id: Optional[str] = None,
        turn_id: Optional[str] = None,
        source_channel: str = "web",
        source_surface: str = "chat",
        metadata_json: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "user_id": user_id,
            "product_id": product_id,
            "interaction_type": interaction_type,
            "source_channel": source_channel,
            "source_surface": source_surface,
            "metadata_json": metadata_json or {},
            "created_at": _now_iso(),
        }
        if conversation_id:
            payload["conversation_id"] = conversation_id
        if turn_id:
            payload["turn_id"] = turn_id
        return self.client.insert_one("catalog_interaction_history", payload)

    def list_catalog_interactions(
        self,
        user_id: str,
        *,
        interaction_type: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        filters: Dict[str, str] = {"user_id": f"eq.{user_id}"}
        if interaction_type:
            filters["interaction_type"] = f"eq.{interaction_type}"
        return self.client.select_many(
            "catalog_interaction_history",
            filters=filters,
            order="created_at.desc",
            limit=limit,
        )

    # -- confidence_history --------------------------------------------------

    def create_confidence_history(
        self,
        *,
        user_id: str,
        confidence_type: str,
        score_pct: int,
        factors_json: Optional[List[Dict[str, Any]]] = None,
        conversation_id: Optional[str] = None,
        turn_id: Optional[str] = None,
        source_channel: str = "web",
        metadata_json: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "user_id": user_id,
            "confidence_type": confidence_type,
            "score_pct": score_pct,
            "source_channel": source_channel,
            "factors_json": factors_json or [],
            "metadata_json": metadata_json or {},
            "created_at": _now_iso(),
        }
        if conversation_id:
            payload["conversation_id"] = conversation_id
        if turn_id:
            payload["turn_id"] = turn_id
        return self.client.insert_one("confidence_history", payload)

    def list_confidence_history(
        self,
        user_id: str,
        *,
        confidence_type: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        filters: Dict[str, str] = {"user_id": f"eq.{user_id}"}
        if confidence_type:
            filters["confidence_type"] = f"eq.{confidence_type}"
        return self.client.select_many(
            "confidence_history",
            filters=filters,
            order="created_at.desc",
            limit=limit,
        )

    # -- policy_event_log ----------------------------------------------------

    def create_policy_event(
        self,
        *,
        policy_event_type: str,
        input_class: str,
        reason_code: str,
        decision: str,
        rule_source: str = "rule",
        user_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        turn_id: Optional[str] = None,
        source_channel: str = "web",
        metadata_json: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "policy_event_type": policy_event_type,
            "input_class": input_class,
            "reason_code": reason_code,
            "decision": decision,
            "rule_source": rule_source,
            "source_channel": source_channel,
            "metadata_json": metadata_json or {},
            "created_at": _now_iso(),
        }
        if user_id:
            payload["user_id"] = user_id
        if conversation_id:
            payload["conversation_id"] = conversation_id
        if turn_id:
            payload["turn_id"] = turn_id
        return self.client.insert_one("policy_event_log", payload)

    def list_policy_events(
        self,
        *,
        user_id: Optional[str] = None,
        decision: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        filters: Dict[str, str] = {}
        if user_id:
            filters["user_id"] = f"eq.{user_id}"
        if decision:
            filters["decision"] = f"eq.{decision}"
        return self.client.select_many(
            "policy_event_log",
            filters=filters or None,
            order="created_at.desc",
            limit=limit,
        )

    # -- dependency_validation_events --------------------------------------

    def create_dependency_event(
        self,
        *,
        user_id: str,
        event_type: str,
        source_channel: str = "web",
        primary_intent: str = "",
        conversation_id: Optional[str] = None,
        turn_id: Optional[str] = None,
        metadata_json: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "user_id": user_id,
            "event_type": event_type,
            "source_channel": source_channel,
            "primary_intent": primary_intent,
            "metadata_json": metadata_json or {},
            "created_at": _now_iso(),
        }
        if conversation_id:
            payload["conversation_id"] = conversation_id
        if turn_id:
            payload["turn_id"] = turn_id
        return self.client.insert_one("dependency_validation_events", payload)

    def list_dependency_events(
        self,
        *,
        user_id: Optional[str] = None,
        event_type: Optional[str] = None,
        source_channel: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        filters: Dict[str, str] = {}
        if user_id:
            filters["user_id"] = f"eq.{user_id}"
        if event_type:
            filters["event_type"] = f"eq.{event_type}"
        if source_channel:
            filters["source_channel"] = f"eq.{source_channel}"
        return self.client.select_many(
            "dependency_validation_events",
            filters=filters or None,
            order="created_at.asc",
            limit=limit,
        )

    # -- user_comfort_learning ------------------------------------------------

    def insert_comfort_learning_signal(self, **kwargs: Any) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "user_id": kwargs["user_id"],
            "signal_type": kwargs["signal_type"],
            "signal_source": kwargs["signal_source"],
            "detected_seasonal_direction": kwargs["detected_seasonal_direction"],
            "created_at": _now_iso(),
        }
        for optional_key in ("garment_id", "conversation_id", "turn_id", "feedback_event_id"):
            if kwargs.get(optional_key):
                payload[optional_key] = kwargs[optional_key]
        return self.client.insert_one("user_comfort_learning", payload)

    def count_comfort_signals(self, user_id: str, signal_type: str, detected_seasonal_direction: str) -> int:
        rows = self.client.select_many(
            "user_comfort_learning",
            filters={
                "user_id": f"eq.{user_id}",
                "signal_type": f"eq.{signal_type}",
                "detected_seasonal_direction": f"eq.{detected_seasonal_direction}",
            },
        )
        return len(rows)

    def get_comfort_signals(self, user_id: str, signal_type: Optional[str] = None) -> List[Dict[str, Any]]:
        filters: Dict[str, str] = {"user_id": f"eq.{user_id}"}
        if signal_type:
            filters["signal_type"] = f"eq.{signal_type}"
        return self.client.select_many(
            "user_comfort_learning",
            filters=filters,
            order="created_at.desc",
        )

    # -- conversation & turn listing for UI --------------------------------

    def archive_conversation(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        return self.client.update_one(
            "conversations",
            filters={"id": f"eq.{conversation_id}"},
            patch={"status": "archived", "updated_at": _now_iso()},
        )

    def rename_conversation(self, conversation_id: str, title: str) -> Optional[Dict[str, Any]]:
        return self.client.update_one(
            "conversations",
            filters={"id": f"eq.{conversation_id}"},
            patch={"title": title, "updated_at": _now_iso()},
        )

    def list_conversations_for_user(
        self,
        user_id: str,
        *,
        status: str = "active",
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        filters: Dict[str, str] = {"user_id": f"eq.{user_id}"}
        if status:
            filters["status"] = f"eq.{status}"
        return self.client.select_many(
            "conversations",
            filters=filters,
            order="updated_at.desc",
            limit=limit,
        )

    def list_turns_for_conversation(
        self,
        conversation_id: str,
    ) -> List[Dict[str, Any]]:
        return self.client.select_many(
            "conversation_turns",
            filters={"conversation_id": f"eq.{conversation_id}"},
            order="created_at.asc",
        )

    def list_recent_results_for_user(
        self,
        user_id: str,
        *,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        conversations = self.client.select_many(
            "conversations",
            filters={"user_id": f"eq.{user_id}"},
            columns="id",
        )
        if not conversations:
            return []
        conv_ids = [c["id"] for c in conversations]
        turns = self.client.select_many(
            "conversation_turns",
            filters={"conversation_id": f"in.({','.join(conv_ids)})"},
            order="created_at.desc",
            limit=limit,
        )
        return [
            t for t in turns
            if t.get("resolved_context_json") and t.get("assistant_message")
        ]

    def log_tool_trace(
        self,
        *,
        conversation_id: str,
        turn_id: str,
        tool_name: str,
        input_json: Dict[str, Any],
        output_json: Dict[str, Any],
        latency_ms: Optional[int] = None,
        status: str = "ok",
        error_message: str = "",
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "conversation_id": conversation_id,
            "turn_id": turn_id,
            "tool_name": tool_name,
            "input_json": input_json,
            "output_json": output_json,
            "status": status,
            "error_message": error_message,
            "created_at": _now_iso(),
        }
        if latency_ms is not None:
            payload["latency_ms"] = latency_ms
        return self.client.insert_one("tool_traces", payload)

    # -- virtual_tryon_images -------------------------------------------------

    def insert_tryon_image(
        self,
        *,
        user_id: str,
        conversation_id: str = "",
        turn_id: str = "",
        outfit_rank: int = 0,
        garment_ids: List[str],
        garment_source: str = "catalog",
        person_image_path: str,
        encrypted_filename: str,
        file_path: str,
        mime_type: str = "image/png",
        file_size_bytes: int = 0,
        generation_model: str = "gemini-3.1-flash-image-preview",
        quality_score_pct: Optional[int] = None,
        metadata_json: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "user_id": user_id,
            "garment_ids": sorted(garment_ids),
            "garment_source": garment_source,
            "person_image_path": person_image_path,
            "encrypted_filename": encrypted_filename,
            "file_path": file_path,
            "mime_type": mime_type,
            "file_size_bytes": file_size_bytes,
            "generation_model": generation_model,
            "metadata_json": metadata_json or {},
            "created_at": _now_iso(),
        }
        if conversation_id:
            payload["conversation_id"] = conversation_id
        if turn_id:
            payload["turn_id"] = turn_id
        if outfit_rank:
            payload["outfit_rank"] = outfit_rank
        if quality_score_pct is not None:
            payload["quality_score_pct"] = quality_score_pct
        return self.client.insert_one("virtual_tryon_images", payload)

    def find_tryon_image_by_garments(
        self,
        user_id: str,
        garment_ids: List[str],
    ) -> Optional[Dict[str, Any]]:
        """Find an existing try-on for the same user + garment set (cache lookup)."""
        sorted_ids = sorted(garment_ids)
        # PostgreSQL array equality: {a,b} = {a,b}
        array_literal = "{" + ",".join(sorted_ids) + "}"
        rows = self.client.select_many(
            "virtual_tryon_images",
            filters={
                "user_id": f"eq.{user_id}",
                "garment_ids": f"eq.{array_literal}",
            },
            order="created_at.desc",
            limit=1,
        )
        return rows[0] if rows else None
