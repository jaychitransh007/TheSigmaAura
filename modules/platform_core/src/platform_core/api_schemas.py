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
    channel: str = Field(default="web", pattern=r"^(web|whatsapp)$")


class WhatsAppInboundRequest(BaseModel):
    phone_number: str = Field(min_length=7, max_length=32)
    message: str = Field(default="", max_length=4000)
    conversation_id: str = ""
    user_id: str = ""
    message_id: str = ""
    profile_name: str = ""
    image_url: str = ""
    link_url: str = ""
    media_type: str = Field(default="", pattern=r"^(|product|outfit_photo|wardrobe_item|garment_on_me)$")


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
    body_harmony_pct: int = 0
    color_suitability_pct: int = 0
    style_fit_pct: int = 0
    risk_tolerance_pct: int = 0
    occasion_pct: int = 0
    comfort_boundary_pct: int = 0
    specific_needs_pct: int = 0
    pairing_coherence_pct: int = 0
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


class WhatsAppInboundResponse(TurnResponse):
    user_id: str
    channel: str = "whatsapp"
    conversation_created: bool = False
    phone_number: str = ""
    input_message_id: str = ""


class WhatsAppReminderRequest(BaseModel):
    phone_number: str = ""
    user_id: str = ""
    conversation_id: str = ""
    reminder_type: str = Field(default="", pattern=r"^(|followup|reactivation|shopping|wardrobe|occasion)$")


class WhatsAppReminderResponse(BaseModel):
    user_id: str
    conversation_id: str = ""
    channel: str = "whatsapp"
    reminder_type: str = ""
    assistant_message: str
    follow_up_suggestions: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class WhatsAppDeepLinkRequest(BaseModel):
    phone_number: str = ""
    user_id: str = ""
    conversation_id: str = ""
    task: str = Field(
        default="",
        pattern=r"^(|complete_onboarding|improve_profile|manage_wardrobe|review_tryon|capsule_planner|chat)$",
    )


class WhatsAppDeepLinkResponse(BaseModel):
    user_id: str
    conversation_id: str = ""
    channel: str = "whatsapp"
    task: str
    assistant_message: str
    deep_link_url: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ReferralEventRequest(BaseModel):
    user_id: str = Field(min_length=1)
    channel: str = Field(default="web", pattern=r"^(web|whatsapp)$")
    referral_type: str = Field(default="invite", pattern=r"^(invite|share|referral)$")
    target: str = ""
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ReferralEventResponse(BaseModel):
    success: bool
    event_id: str = ""
    user_id: str
    referral_type: str


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
