from __future__ import annotations

import re
from typing import Any, Callable, Dict, List, Optional

from catalog_retrieval.config import CatalogEmbeddingConfig
from catalog_retrieval.embedder import CatalogEmbedder
from catalog_retrieval.query_builder import RetrievalQueryInput, StyleRequirementQueryBuilder
from catalog_retrieval.vector_store import SupabaseVectorStore
from onboarding.analysis import UserAnalysisService
from onboarding.repository import OnboardingRepository

from .config import ConversationPlatformConfig
from .repositories import ConversationRepository


class ConversationOrchestrator:
    def __init__(
        self,
        *,
        repo: ConversationRepository,
        onboarding_repo: OnboardingRepository,
        config: ConversationPlatformConfig,
    ) -> None:
        self.repo = repo
        self.onboarding_repo = onboarding_repo
        self.config = config
        self.analysis_service = UserAnalysisService(repo=onboarding_repo)
        self.query_builder = StyleRequirementQueryBuilder()
        self.embedder = CatalogEmbedder(CatalogEmbeddingConfig(embedding_dimensions=1536))
        self.vector_store = SupabaseVectorStore(repo.client)

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
        latest_context = dict(conversation.get("session_context_json") or {})
        return {
            "conversation_id": conversation["id"],
            "user_id": str(user.get("external_user_id") or ""),
            "status": conversation.get("status", "active"),
            "latest_context": latest_context or None,
        }

    def process_turn(
        self,
        *,
        conversation_id: str,
        external_user_id: str,
        message: str,
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

        analysis_status = self.analysis_service.get_analysis_status(external_user_id)
        if analysis_status.get("status") != "completed":
            raise ValueError("User analysis is not complete. Finish onboarding and profile analysis first.")

        previous_context = dict(conversation.get("session_context_json") or {})
        resolved_context = self._resolve_context(message=message, previous_context=previous_context)
        turn = self.repo.create_turn(conversation_id=conversation_id, user_message=message)
        turn_id = str(turn["id"])

        emit("build_retrieval_query", "started")
        query_document = self.query_builder.build_query_document(
            RetrievalQueryInput(
                profile=analysis_status.get("profile") or {},
                analysis_attributes=analysis_status.get("attributes") or {},
                derived_interpretations=analysis_status.get("derived_interpretations") or {},
                style_preference=((analysis_status.get("profile") or {}).get("style_preference") or {}),
                user_need=message,
                user_context=resolved_context,
            )
        )
        self.repo.log_model_call(
            conversation_id=conversation_id,
            turn_id=turn_id,
            service="catalog_retrieval",
            call_type="style_requirement_query",
            model="gpt-5-mini",
            request_json={
                "message": message,
                "resolved_context": resolved_context,
                "profile": analysis_status.get("profile") or {},
            },
            response_json={"query_document": query_document},
            reasoning_notes=[],
        )
        emit("build_retrieval_query", "completed")

        filters = self._build_filters(analysis_status.get("profile") or {}, query_document)

        emit("vector_search", "started")
        query_embedding = self.embedder.embed_texts([query_document])[0]
        matches = self.vector_store.similarity_search(
            query_embedding=query_embedding,
            match_count=self.config.retrieval_match_count,
            filters=filters,
        )
        self.repo.log_tool_trace(
            conversation_id=conversation_id,
            turn_id=turn_id,
            tool_name="catalog_retrieval.similarity_search",
            input_json={"filters": filters, "match_count": self.config.retrieval_match_count},
            output_json={"result_count": len(matches or [])},
        )
        emit("vector_search", "completed")

        recommendations = self._map_matches(matches or [])
        assistant_message = self._build_assistant_message(
            message=message,
            recommendations=recommendations,
            style_preference=((analysis_status.get("profile") or {}).get("style_preference") or {}),
        )

        self.repo.finalize_turn(
            turn_id=turn_id,
            assistant_message=assistant_message,
            resolved_context=resolved_context,
        )
        self.repo.update_conversation_context(
            conversation_id=conversation_id,
            session_context={**previous_context, **resolved_context, "last_query_document": query_document},
        )
        return {
            "conversation_id": conversation_id,
            "turn_id": turn_id,
            "assistant_message": assistant_message,
            "resolved_context": resolved_context,
            "retrieval_query_document": query_document,
            "filters_applied": filters,
            "recommendations": recommendations,
        }

    def _resolve_context(self, *, message: str, previous_context: Dict[str, Any]) -> Dict[str, str]:
        lowered = message.lower()
        occasion = str(previous_context.get("occasion") or "")
        style_goal = str(previous_context.get("style_goal") or "")
        for token in ("wedding", "office", "trip", "vacation", "date", "party", "festival", "casual"):
            if token in lowered:
                occasion = token
                break
        match = re.search(r"(look tall|look taller|look slimmer|look broader|look polished|look formal)", lowered)
        if match:
            style_goal = match.group(1)
        return {
            "request_summary": message.strip(),
            "occasion": occasion,
            "style_goal": style_goal,
        }

    def _build_filters(self, profile: Dict[str, Any], query_document: str) -> Dict[str, str]:
        labeled_values = self._extract_labeled_values(
            query_document,
            [
                "GarmentCategory",
                "GarmentSubtype",
                "StylingCompleteness",
                "FormalityLevel",
                "OccasionFit",
                "TimeOfDay",
                "PrimaryColor",
            ],
        )
        filters: Dict[str, str] = {}
        gender = str(profile.get("gender") or "").strip().lower()
        if gender == "male":
            filters["gender_expression"] = "masculine"
        elif gender == "female":
            filters["gender_expression"] = "feminine"

        mapping = {
            "GarmentCategory": "garment_category",
            "GarmentSubtype": "garment_subtype",
            "StylingCompleteness": "styling_completeness",
            "FormalityLevel": "formality_level",
            "OccasionFit": "occasion_fit",
            "TimeOfDay": "time_of_day",
            "PrimaryColor": "primary_color",
        }
        for source_key, target_key in mapping.items():
            value = self._normalize_filter_value(labeled_values.get(source_key, ""))
            if value:
                filters[target_key] = value
        return filters

    @staticmethod
    def _extract_labeled_values(document: str, field_names: List[str]) -> Dict[str, str]:
        values: Dict[str, str] = {}
        for line in document.splitlines():
            stripped = line.strip()
            if not stripped.startswith("- ") or ":" not in stripped:
                continue
            label, raw_value = stripped[2:].split(":", 1)
            label = label.strip()
            if label in field_names:
                values[label] = raw_value.strip()
        return values

    @staticmethod
    def _normalize_filter_value(value: str) -> str:
        raw = str(value or "").strip()
        if not raw:
            return ""
        lowered = raw.lower()
        if lowered in {"unknown", "unspecified", "n/a", "none"}:
            return ""
        lowered = lowered.split(",")[0].strip()
        lowered = re.sub(r"[^a-z0-9]+", "_", lowered).strip("_")
        return lowered

    @staticmethod
    def _map_matches(matches: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for index, match in enumerate(matches, start=1):
            metadata = dict(match.get("metadata_json") or {})
            rows.append(
                {
                    "rank": index,
                    "product_id": str(match.get("product_id") or metadata.get("id") or ""),
                    "title": str(metadata.get("title") or ""),
                    "image_url": str(metadata.get("images__0__src") or ""),
                    "similarity": float(match.get("similarity") or 0.0),
                    "price": str(metadata.get("price") or match.get("price") or ""),
                    "garment_category": str(match.get("garment_category") or metadata.get("GarmentCategory") or ""),
                    "garment_subtype": str(match.get("garment_subtype") or metadata.get("GarmentSubtype") or ""),
                    "styling_completeness": str(
                        match.get("styling_completeness") or metadata.get("StylingCompleteness") or ""
                    ),
                    "primary_color": str(match.get("primary_color") or metadata.get("PrimaryColor") or ""),
                    "metadata": metadata,
                }
            )
        return rows

    @staticmethod
    def _build_assistant_message(
        *,
        message: str,
        recommendations: List[Dict[str, Any]],
        style_preference: Dict[str, Any],
    ) -> str:
        if not recommendations:
            return "I could not find any catalog matches yet. Load more catalog embeddings or broaden the retrieval filters."
        primary = str(style_preference.get("primaryArchetype") or "").strip()
        lead_titles = ", ".join(item["title"] for item in recommendations[:3] if item.get("title"))
        if primary:
            return (
                f"I pulled {len(recommendations)} embedding matches for '{message}' with your {primary} style preference in mind. "
                f"Top candidates: {lead_titles}."
            )
        return f"I pulled {len(recommendations)} embedding matches for '{message}'. Top candidates: {lead_titles}."
