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


class ResolveConversationRequest(BaseModel):
    user_id: str = Field(min_length=1)


class ConversationResponse(BaseModel):
    conversation_id: str
    user_id: str
    status: str
    created_at: str


class ResolveConversationResponse(ConversationResponse):
    reused_existing: bool = False


class CreateTurnRequest(BaseModel):
    user_id: str = Field(min_length=1)
    message: str = Field(min_length=1, max_length=4000)
    channel: str = Field(default="web", pattern=r"^(web)$")
    image_data: str = Field(default="", max_length=10_000_000)


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
    formality_level: str = ""
    occasion_fit: str = ""
    pattern_type: str = ""
    volume_profile: str = ""
    fit_type: str = ""
    silhouette_type: str = ""
    source: str = ""


class OutfitCard(BaseModel):
    rank: int
    title: str = ""
    reasoning: str = ""
    body_note: str = ""
    color_note: str = ""
    style_note: str = ""
    occasion_note: str = ""
    # 6 always-evaluated dimensions
    body_harmony_pct: int = 0
    color_suitability_pct: int = 0
    style_fit_pct: int = 0
    risk_tolerance_pct: int = 0
    comfort_boundary_pct: int = 0
    pairing_coherence_pct: int = 0
    # 3 context-gated dimensions — Optional[int] mirrors the application
    # OutfitCard schema. None means "not evaluated this turn" because
    # the relevant input was absent in live_context. See Phase 12B
    # follow-up (April 9 2026) in docs/CURRENT_STATE.md.
    occasion_pct: Optional[int] = None
    specific_needs_pct: Optional[int] = None
    weather_time_pct: Optional[int] = None
    classic_pct: int = 0
    dramatic_pct: int = 0
    romantic_pct: int = 0
    natural_pct: int = 0
    minimalist_pct: int = 0
    creative_pct: int = 0
    sporty_pct: int = 0
    edgy_pct: int = 0
    tryon_image: str = ""
    items: List[OutfitItem] = Field(default_factory=list)


class FeedbackRequest(BaseModel):
    outfit_rank: int
    event_type: str = Field(pattern=r"^(like|dislike)$")
    notes: str = ""
    turn_id: str = ""
    item_ids: List[str] = Field(default_factory=list)


class TurnResponse(BaseModel):
    conversation_id: str
    turn_id: str
    assistant_message: str
    response_type: str = "recommendation"
    resolved_context: ResolvedContext
    filters_applied: Dict[str, str] = Field(default_factory=dict)
    outfits: List[OutfitCard] = Field(default_factory=list)
    follow_up_suggestions: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class DependencyReportResponse(BaseModel):
    report: Dict[str, Any] = Field(default_factory=dict)


JobStatus = str


class TurnStageEvent(BaseModel):
    timestamp: str
    stage: str
    detail: str = ""
    message: str = ""


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


# -- Listing schemas for UI ------------------------------------------------


class RenameConversationRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)


class ConversationListItem(BaseModel):
    conversation_id: str
    status: str
    title: str = ""
    preview: str = ""
    occasion: str = ""
    created_at: str = ""
    updated_at: str = ""


class ConversationListResponse(BaseModel):
    user_id: str
    conversations: List[ConversationListItem] = Field(default_factory=list)


class TurnListItem(BaseModel):
    turn_id: str
    role: str = ""
    user_message: str = ""
    assistant_message: str = ""
    resolved_context: Optional[Dict[str, Any]] = None
    created_at: str = ""


class TurnListResponse(BaseModel):
    conversation_id: str
    turns: List[TurnListItem] = Field(default_factory=list)


class ResultListItem(BaseModel):
    turn_id: str
    conversation_id: str
    user_message: str = ""
    assistant_message: str = ""
    occasion: str = ""
    intent: str = ""
    source: str = ""
    outfit_count: int = 0
    first_outfit_image: str = ""
    created_at: str = ""


class ResultListResponse(BaseModel):
    user_id: str
    results: List[ResultListItem] = Field(default_factory=list)
