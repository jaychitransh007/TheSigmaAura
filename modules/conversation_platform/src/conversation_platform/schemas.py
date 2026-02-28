from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


Strictness = Literal["safe", "balanced", "bold"]
HardFilterProfile = Literal["rl_ready_minimal", "legacy"]
ResultFilter = Literal["complete_only", "complete_plus_combos"]
FeedbackEventType = Literal["dislike", "like", "share", "buy", "skip", "no_action"]


class ResolvedContext(BaseModel):
    occasion: str = ""
    archetype: str = ""
    gender: str = ""
    age: str = ""


class CreateConversationRequest(BaseModel):
    user_id: str = Field(min_length=1)
    initial_context: Optional[ResolvedContext] = None


class ConversationResponse(BaseModel):
    conversation_id: str
    user_id: str
    status: str
    created_at: str


class CreateTurnRequest(BaseModel):
    user_id: str = Field(min_length=1)
    message: str = Field(min_length=1, max_length=4000)
    image_refs: List[str] = Field(default_factory=list)
    strictness: Strictness = "balanced"
    hard_filter_profile: HardFilterProfile = "rl_ready_minimal"
    max_results: int = Field(default=12, ge=1, le=50)
    result_filter: ResultFilter = "complete_plus_combos"


class RecommendationItem(BaseModel):
    rank: int
    garment_id: str
    title: str
    image_url: str
    score: float
    max_score: float
    compatibility_confidence: float
    reasons: str
    recommendation_kind: str = "single_garment"
    outfit_id: str = ""
    component_count: int = 1
    component_ids: List[str] = Field(default_factory=list)
    component_titles: List[str] = Field(default_factory=list)
    component_image_urls: List[str] = Field(default_factory=list)


class TurnResponse(BaseModel):
    conversation_id: str
    turn_id: str
    assistant_message: str
    resolved_context: ResolvedContext
    profile_snapshot_id: Optional[str] = None
    recommendation_run_id: Optional[str] = None
    recommendations: List[RecommendationItem] = Field(default_factory=list)
    needs_clarification: bool = False
    clarifying_question: str = ""


JobStatus = Literal["running", "completed", "failed"]


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
    latest_profile_snapshot_id: Optional[str] = None
    latest_recommendation_run_id: Optional[str] = None


class FeedbackRequest(BaseModel):
    user_id: str = Field(min_length=1)
    conversation_id: str = Field(min_length=1)
    recommendation_run_id: str = Field(min_length=1)
    garment_id: str = Field(min_length=1)
    event_type: FeedbackEventType
    notes: str = ""


class FeedbackResponse(BaseModel):
    event_id: str
    reward_value: int


class RecommendationRunResponse(BaseModel):
    recommendation_run_id: str
    strictness: str
    hard_filter_profile: str
    items: List[RecommendationItem]
    meta: Dict[str, int]
