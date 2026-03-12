from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ResolvedContext(BaseModel):
    request_summary: str = ""
    occasion: str = ""
    style_goal: str = ""


class InitialProfile(BaseModel):
    consent_flags: Optional[Dict[str, bool]] = None


class CreateConversationRequest(BaseModel):
    user_id: str = Field(min_length=1)
    initial_context: Optional[ResolvedContext] = None
    initial_profile: Optional[InitialProfile] = None


class ConversationResponse(BaseModel):
    conversation_id: str
    user_id: str
    status: str
    created_at: str


class CreateTurnRequest(BaseModel):
    user_id: str = Field(min_length=1)
    message: str = Field(min_length=1, max_length=4000)


class RecommendationItem(BaseModel):
    rank: int
    product_id: str
    title: str
    image_url: str = ""
    similarity: float
    price: str = ""
    garment_category: str = ""
    garment_subtype: str = ""
    styling_completeness: str = ""
    primary_color: str = ""
    metadata: Dict[str, Any] = Field(default_factory=dict)


class TurnResponse(BaseModel):
    conversation_id: str
    turn_id: str
    assistant_message: str
    resolved_context: ResolvedContext
    retrieval_query_document: str = ""
    filters_applied: Dict[str, str] = Field(default_factory=dict)
    recommendations: List[RecommendationItem] = Field(default_factory=list)


JobStatus = str


class TurnStageEvent(BaseModel):
    timestamp: str
    stage: str
    detail: str = ""


class TurnJobStartResponse(BaseModel):
    conversation_id: str
    job_id: str
    status: JobStatus


class TurnJobStatusResponse(BaseModel):
    conversation_id: str
    job_id: str
    status: JobStatus
    stages: List[TurnStageEvent] = Field(default_factory=list)
    error: str = ""
    result: Optional[Dict[str, Any]] = None


class ConversationStateResponse(BaseModel):
    conversation_id: str
    user_id: str
    status: str
    latest_context: Optional[ResolvedContext] = None
