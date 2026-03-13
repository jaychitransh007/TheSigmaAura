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


class OutfitItem(BaseModel):
    product_id: str
    similarity: float = 0.0
    title: str = ""
    image_url: str = ""
    price: str = ""
    product_url: str = ""
    garment_category: str = ""
    garment_subtype: str = ""
    primary_color: str = ""
    role: str = ""


class OutfitCard(BaseModel):
    rank: int
    title: str = ""
    reasoning: str = ""
    body_note: str = ""
    color_note: str = ""
    style_note: str = ""
    occasion_note: str = ""
    items: List[OutfitItem] = Field(default_factory=list)


class TurnResponse(BaseModel):
    conversation_id: str
    turn_id: str
    assistant_message: str
    resolved_context: ResolvedContext
    filters_applied: Dict[str, str] = Field(default_factory=dict)
    outfits: List[OutfitCard] = Field(default_factory=list)
    follow_up_suggestions: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


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
