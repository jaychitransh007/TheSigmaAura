from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# --- Request ---


class RecommendationRequest(BaseModel):
    user_id: str
    conversation_id: str
    message: str


# --- User Context ---


class UserContext(BaseModel):
    user_id: str
    gender: str
    date_of_birth: Optional[str] = None
    profession: Optional[str] = None
    height_cm: Optional[float] = None
    waist_cm: Optional[float] = None

    analysis_attributes: Dict[str, Any] = Field(default_factory=dict)
    derived_interpretations: Dict[str, Any] = Field(default_factory=dict)
    style_preference: Dict[str, Any] = Field(default_factory=dict)

    profile_richness: str = "minimal"  # full | moderate | basic | minimal


# --- Live Context ---


class LiveContext(BaseModel):
    user_need: str
    occasion_signal: Optional[str] = None
    formality_hint: Optional[str] = None
    time_hint: Optional[str] = None
    specific_needs: List[str] = Field(default_factory=list)
    is_followup: bool = False
    followup_intent: Optional[str] = None


# --- Conversation Memory ---


class ConversationMemory(BaseModel):
    occasion_signal: Optional[str] = None
    formality_hint: Optional[str] = None
    time_hint: Optional[str] = None
    specific_needs: List[str] = Field(default_factory=list)
    plan_type: Optional[str] = None
    followup_count: int = 0
    last_recommendation_ids: List[str] = Field(default_factory=list)


# --- Combined Context ---


class CombinedContext(BaseModel):
    user: UserContext
    live: LiveContext
    hard_filters: Dict[str, str] = Field(default_factory=dict)
    previous_recommendations: Optional[List[Dict[str, Any]]] = None
    conversation_memory: Optional[ConversationMemory] = None
    conversation_history: Optional[List[Dict[str, str]]] = None


# --- Outfit Architect output ---


class QuerySpec(BaseModel):
    query_id: str
    role: str  # complete | top | bottom
    hard_filters: Dict[str, str] = Field(default_factory=dict)
    query_document: str


class DirectionSpec(BaseModel):
    direction_id: str  # A | B | C
    direction_type: str  # complete | paired
    label: str
    queries: List[QuerySpec]


class ResolvedContextBlock(BaseModel):
    occasion_signal: Optional[str] = None
    formality_hint: Optional[str] = None
    time_hint: Optional[str] = None
    specific_needs: List[str] = Field(default_factory=list)
    is_followup: bool = False
    followup_intent: Optional[str] = None


class RecommendationPlan(BaseModel):
    plan_type: str  # complete_only | paired_only | mixed
    retrieval_count: int = 12
    directions: List[DirectionSpec]
    plan_source: str = "llm"
    resolved_context: Optional[ResolvedContextBlock] = None


# --- Retrieval output ---


class RetrievedProduct(BaseModel):
    product_id: str
    similarity: float = 0.0
    metadata: Dict[str, Any] = Field(default_factory=dict)
    enriched_data: Dict[str, Any] = Field(default_factory=dict)


class RetrievedSet(BaseModel):
    direction_id: str
    query_id: str
    role: str  # complete | top | bottom
    products: List[RetrievedProduct] = Field(default_factory=list)
    applied_filters: Dict[str, str] = Field(default_factory=dict)


# --- Assembly output ---


class OutfitCandidate(BaseModel):
    candidate_id: str
    direction_id: str
    candidate_type: str  # complete | paired
    items: List[Dict[str, Any]] = Field(default_factory=list)
    assembly_score: float = 0.0
    assembly_notes: List[str] = Field(default_factory=list)


# --- Evaluation output ---


class EvaluatedRecommendation(BaseModel):
    candidate_id: str
    rank: int = 0
    match_score: float = 0.0
    title: str = ""
    reasoning: str = ""
    body_note: str = ""
    color_note: str = ""
    style_note: str = ""
    occasion_note: str = ""
    item_ids: List[str] = Field(default_factory=list)


# --- Response ---


class OutfitCard(BaseModel):
    rank: int
    title: str
    reasoning: str = ""
    body_note: str = ""
    color_note: str = ""
    style_note: str = ""
    occasion_note: str = ""
    items: List[Dict[str, Any]] = Field(default_factory=list)
    tryon_image: Optional[str] = None  # data URL of virtual try-on image


class RecommendationResponse(BaseModel):
    success: bool = True
    message: str = ""
    outfits: List[OutfitCard] = Field(default_factory=list)
    follow_up_suggestions: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
