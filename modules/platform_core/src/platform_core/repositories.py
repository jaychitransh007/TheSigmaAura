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

