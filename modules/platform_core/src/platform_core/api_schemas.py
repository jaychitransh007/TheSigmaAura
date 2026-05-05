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
    # When the user selects an existing wardrobe item (instead of
    # uploading a new image), the frontend sends the wardrobe item's
    # UUID here. The orchestrator loads the item directly from
    # user_wardrobe_items instead of re-enriching and re-saving,
    # avoiding duplicate wardrobe rows.
    wardrobe_item_id: str = Field(default="")
    # When the user selects a wishlisted catalog product from the
    # wishlist picker, the frontend sends the product_id here.
    # The orchestrator loads the product from catalog_enriched.
    wishlist_product_id: str = Field(default="")


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
    """API contract for an outfit card. Mirrors agentic_application.schemas.OutfitCard.

    R7 (May 5 2026): six rater dims now (added formality_pct +
    statement_pct; renamed inter_item_coherence_pct → pairing_pct).
    pairing_pct is None for complete (single-item) outfits — frontend
    drops the axis and renders a 5-axis pentagon instead of a hexagon.
    """
    rank: int
    title: str = ""
    reasoning: str = ""
    body_harmony_pct: int = 0
    color_suitability_pct: int = 0
    occasion_pct: Optional[int] = None
    pairing_pct: Optional[int] = None
    formality_pct: int = 0
    statement_pct: int = 0
    fashion_score_pct: int = 0
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


# -- Wishlist ----------------------------------------------------------------

class WishlistItem(BaseModel):
    product_id: str
    title: str = ""
    price: str = ""
    image_url: str = ""
    product_url: str = ""
    garment_category: str = ""
    garment_subtype: str = ""
    primary_color: str = ""
    wishlisted_at: str = ""


class WishlistResponse(BaseModel):
    user_id: str
    items: List[WishlistItem] = Field(default_factory=list)


# -- Trial Room (try-on gallery) ---------------------------------------------

class TryonGalleryItem(BaseModel):
    id: str
    image_url: str = ""
    garment_ids: List[str] = Field(default_factory=list)
    garment_source: str = ""
    created_at: str = ""


class TryonGalleryResponse(BaseModel):
    user_id: str
    items: List[TryonGalleryItem] = Field(default_factory=list)


# -- Intent-organized history (Phase 15) ------------------------------------


class IntentHistoryTurn(BaseModel):
    turn_id: str
    conversation_id: str = ""
    user_message: str = ""
    assistant_summary: str = ""
    outfits: List[Dict[str, Any]] = Field(default_factory=list)
    outfit_count: int = 0
    first_outfit_image: str = ""
    created_at: str = ""


class IntentHistoryGroup(BaseModel):
    group_key: str
    conversation_id: str
    intent: str = ""
    occasion: str = ""
    source: str = ""
    context_summary: str = ""
    turn_count: int = 0
    total_outfit_count: int = 0
    first_image: str = ""
    created_at: str = ""
    updated_at: str = ""
    turns: List[IntentHistoryTurn] = Field(default_factory=list)
    # May 1, 2026 — Outfits Tab Theme Taxonomy: theme_key is the
    # canonical bucket the group belongs to. Groups still exist
    # one-per-(intent, occasion, conversation); themes nest them.
    theme_key: str = "style_sessions"


class IntentHistoryThemeBlock(BaseModel):
    """One theme section on the Outfits tab — collapses related
    occasions (sangeet/mehendi/engagement/wedding) into a single
    user-recognisable bucket. May 1, 2026."""

    theme_key: str
    theme_label: str
    theme_description: str = ""
    group_count: int = 0
    total_outfit_count: int = 0
    most_recent_at: str = ""
    groups: List[IntentHistoryGroup] = Field(default_factory=list)


class IntentHistoryResponse(BaseModel):
    user_id: str
    groups: List[IntentHistoryGroup] = Field(default_factory=list)
    # May 1, 2026 — themed view for the Outfits tab. The flat ``groups``
    # list above is preserved for back-compat; new clients render
    # ``themes`` instead.
    themes: List[IntentHistoryThemeBlock] = Field(default_factory=list)


class RecentSignal(BaseModel):
    """Single timeline entry for the profile Recent-Signals strip."""

    label: str
    detail: str
    source: str  # comfort_learning | feedback | catalog
    when: str    # ISO timestamp


class RecentSignalsResponse(BaseModel):
    user_id: str
    signals: List[RecentSignal] = Field(default_factory=list)
