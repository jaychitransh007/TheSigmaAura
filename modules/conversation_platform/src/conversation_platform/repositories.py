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

    def create_turn(
        self,
        conversation_id: str,
        user_message: str,
        *,
        mode_preference: Optional[str] = None,
        autonomy_level: Optional[str] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "conversation_id": conversation_id,
            "user_message": user_message,
            "assistant_message": "",
            "resolved_context_json": {},
            "created_at": _now_iso(),
        }
        if mode_preference is not None:
            payload["mode_preference"] = mode_preference
        if autonomy_level is not None:
            payload["autonomy_level"] = autonomy_level
        return self.client.insert_one("conversation_turns", payload)

    def finalize_turn(
        self,
        *,
        turn_id: str,
        assistant_message: str,
        resolved_context: Dict[str, Any],
        profile_snapshot_id: Optional[str],
        recommendation_run_id: Optional[str],
        resolved_mode: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        patch: Dict[str, Any] = {
            "assistant_message": assistant_message,
            "resolved_context_json": resolved_context,
        }
        if profile_snapshot_id is not None:
            patch["profile_snapshot_id"] = profile_snapshot_id
        if recommendation_run_id is not None:
            patch["recommendation_run_id"] = recommendation_run_id
        if resolved_mode is not None:
            patch["resolved_mode"] = resolved_mode
        return self.client.update_one(
            "conversation_turns",
            filters={"id": f"eq.{turn_id}"},
            patch=patch,
        )

    def get_turn(self, turn_id: str) -> Optional[Dict[str, Any]]:
        return self.client.select_one("conversation_turns", filters={"id": f"eq.{turn_id}"})

    def get_latest_turn(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        rows = self.client.select_many(
            "conversation_turns",
            filters={"conversation_id": f"eq.{conversation_id}"},
            order="created_at.desc",
            limit=1,
        )
        return rows[0] if rows else None

    def add_media_asset(
        self,
        *,
        user_id: str,
        conversation_id: str,
        source_type: str,
        source_ref: str,
        storage_url: str,
        mime_type: str = "",
    ) -> Dict[str, Any]:
        payload = {
            "user_id": user_id,
            "conversation_id": conversation_id,
            "source_type": source_type,
            "source_ref": source_ref,
            "storage_url": storage_url,
            "mime_type": mime_type,
            "created_at": _now_iso(),
        }
        return self.client.insert_one("media_assets", payload)

    def create_profile_snapshot(
        self,
        *,
        user_id: str,
        conversation_id: str,
        source_turn_id: str,
        profile_json: Dict[str, Any],
        gender: str,
        age: str,
        confidence_json: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        payload = {
            "user_id": user_id,
            "conversation_id": conversation_id,
            "source_turn_id": source_turn_id,
            "profile_json": profile_json,
            "gender": gender,
            "age": age,
            "confidence_json": confidence_json or {},
            "created_at": _now_iso(),
        }
        return self.client.insert_one("profile_snapshots", payload)

    def get_latest_profile_snapshot(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        rows = self.client.select_many(
            "profile_snapshots",
            filters={"conversation_id": f"eq.{conversation_id}"},
            order="created_at.desc",
            limit=1,
        )
        return rows[0] if rows else None

    def create_context_snapshot(
        self,
        *,
        conversation_id: str,
        source_turn_id: str,
        occasion: str,
        archetype: str,
        raw_text: str,
    ) -> Dict[str, Any]:
        payload = {
            "conversation_id": conversation_id,
            "source_turn_id": source_turn_id,
            "occasion": occasion,
            "archetype": archetype,
            "raw_text": raw_text,
            "created_at": _now_iso(),
        }
        return self.client.insert_one("context_snapshots", payload)

    def get_latest_context_snapshot(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        rows = self.client.select_many(
            "context_snapshots",
            filters={"conversation_id": f"eq.{conversation_id}"},
            order="created_at.desc",
            limit=1,
        )
        return rows[0] if rows else None

    def create_recommendation_run(
        self,
        *,
        conversation_id: str,
        turn_id: str,
        profile_snapshot_id: str,
        context_snapshot_id: str,
        strictness: str,
        hard_filter_profile: str,
        candidate_count: int,
        returned_count: int,
        resolved_mode: Optional[str] = None,
        requested_garment_types_json: Optional[List[str]] = None,
        style_constraints_json: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "conversation_id": conversation_id,
            "turn_id": turn_id,
            "profile_snapshot_id": profile_snapshot_id,
            "context_snapshot_id": context_snapshot_id,
            "strictness": strictness,
            "hard_filter_profile": hard_filter_profile,
            "candidate_count": candidate_count,
            "returned_count": returned_count,
            "created_at": _now_iso(),
        }
        if resolved_mode is not None:
            payload["resolved_mode"] = resolved_mode
        if requested_garment_types_json is not None:
            payload["requested_garment_types_json"] = requested_garment_types_json
        if style_constraints_json is not None:
            payload["style_constraints_json"] = style_constraints_json
        return self.client.insert_one("recommendation_runs", payload)

    def insert_recommendation_items(self, recommendation_run_id: str, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for item in items:
            reasons_payload: Dict[str, Any] = {
                "summary": item.get("reasons", ""),
                "raw_reasons": item.get("raw_reasons", []),
                "recommendation_kind": item.get("recommendation_kind", "single_garment"),
                "outfit_id": item.get("outfit_id", item.get("garment_id", "")),
                "component_count": int(item.get("component_count", 1) or 1),
                "component_ids": item.get("component_ids", []),
                "component_titles": item.get("component_titles", []),
                "component_image_urls": item.get("component_image_urls", []),
            }
            rows.append(
                {
                    "recommendation_run_id": recommendation_run_id,
                    "rank": item["rank"],
                    "garment_id": item["garment_id"],
                    "title": item["title"],
                    "image_url": item.get("image_url", ""),
                    "score": item["score"],
                    "max_score": item["max_score"],
                    "compatibility_confidence": item["compatibility_confidence"],
                    "flags_json": item.get("flags", []),
                    "reasons_json": reasons_payload,
                }
            )
        return self.client.insert_many("recommendation_items", rows)

    def get_recommendation_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        return self.client.select_one("recommendation_runs", filters={"id": f"eq.{run_id}"})

    def get_recommendation_items(self, run_id: str) -> List[Dict[str, Any]]:
        return self.client.select_many(
            "recommendation_items",
            filters={"recommendation_run_id": f"eq.{run_id}"},
            order="rank.asc",
        )

    def create_feedback_event(
        self,
        *,
        user_id: str,
        conversation_id: str,
        recommendation_run_id: str,
        garment_id: str,
        event_type: str,
        reward_value: int,
        notes: str,
    ) -> Dict[str, Any]:
        payload = {
            "user_id": user_id,
            "conversation_id": conversation_id,
            "recommendation_run_id": recommendation_run_id,
            "garment_id": garment_id,
            "event_type": event_type,
            "reward_value": reward_value,
            "notes": notes,
            "created_at": _now_iso(),
        }
        return self.client.insert_one("feedback_events", payload)

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
        status: str = "ok",
        error_message: str = "",
    ) -> Dict[str, Any]:
        payload = {
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
        return self.client.insert_one("model_call_logs", payload)

    def log_tool_trace(
        self,
        *,
        conversation_id: str,
        turn_id: str,
        tool_name: str,
        input_json: Dict[str, Any],
        output_json: Dict[str, Any],
        status: str = "ok",
        error_message: str = "",
    ) -> Dict[str, Any]:
        payload = {
            "conversation_id": conversation_id,
            "turn_id": turn_id,
            "tool_name": tool_name,
            "input_json": input_json,
            "output_json": output_json,
            "status": status,
            "error_message": error_message,
            "created_at": _now_iso(),
        }
        return self.client.insert_one("tool_traces", payload)

    # -- Checkout preparation ---------------------------------------------------

    def create_checkout_preparation(
        self,
        *,
        conversation_id: str,
        turn_id: Optional[str],
        recommendation_run_id: str,
        user_id: str,
        status: str = "pending",
        cart_payload_json: Optional[List[Dict[str, Any]]] = None,
        pricing_json: Optional[Dict[str, Any]] = None,
        validation_json: Optional[Dict[str, Any]] = None,
        checkout_ref: str = "",
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "conversation_id": conversation_id,
            "recommendation_run_id": recommendation_run_id,
            "user_id": user_id,
            "status": status,
            "cart_payload_json": cart_payload_json or [],
            "pricing_json": pricing_json or {},
            "validation_json": validation_json or {},
            "checkout_ref": checkout_ref,
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
        }
        if turn_id is not None:
            payload["turn_id"] = turn_id
        return self.client.insert_one("checkout_preparations", payload)

    def update_checkout_preparation(
        self,
        checkout_prep_id: str,
        patch: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        patch["updated_at"] = _now_iso()
        return self.client.update_one(
            "checkout_preparations",
            filters={"id": f"eq.{checkout_prep_id}"},
            patch=patch,
        )

    def get_checkout_preparation(self, checkout_prep_id: str) -> Optional[Dict[str, Any]]:
        return self.client.select_one("checkout_preparations", filters={"id": f"eq.{checkout_prep_id}"})

    def insert_checkout_preparation_items(
        self, checkout_preparation_id: str, items: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for item in items:
            rows.append(
                {
                    "checkout_preparation_id": checkout_preparation_id,
                    "rank": item["rank"],
                    "garment_id": item["garment_id"],
                    "title": item.get("title", ""),
                    "qty": item.get("qty", 1),
                    "unit_price": item.get("unit_price", 0),
                    "discount": item.get("discount", 0),
                    "final_price": item.get("final_price", 0),
                    "meta_json": item.get("meta_json", {}),
                }
            )
        return self.client.insert_many("checkout_preparation_items", rows)

    def get_checkout_preparation_items(self, checkout_preparation_id: str) -> List[Dict[str, Any]]:
        return self.client.select_many(
            "checkout_preparation_items",
            filters={"checkout_preparation_id": f"eq.{checkout_preparation_id}"},
            order="rank.asc",
        )
