from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from .intent_registry import Action, Intent


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
    wardrobe_items: List[Dict[str, Any]] = Field(default_factory=list)

    profile_richness: str = "minimal"  # full | moderate | basic | minimal


class ProfileConfidenceFactor(BaseModel):
    factor: str
    satisfied: bool = False
    score: float = 0.0
    max_score: float = 0.0
    detail: str = ""
    improvement_action: str = ""


class ProfileConfidence(BaseModel):
    score_pct: int = 0
    analysis_confidence_pct: int = 0
    satisfied_factors: List[str] = Field(default_factory=list)
    missing_factors: List[str] = Field(default_factory=list)
    improvement_actions: List[str] = Field(default_factory=list)
    factors: List[ProfileConfidenceFactor] = Field(default_factory=list)


class RecommendationConfidenceFactor(BaseModel):
    factor: str
    score: float = 0.0
    max_score: float = 0.0
    detail: str = ""


class RecommendationConfidence(BaseModel):
    score_pct: int = 0
    confidence_band: str = "low"
    summary: str = ""
    explanation: List[str] = Field(default_factory=list)
    factors: List[RecommendationConfidenceFactor] = Field(default_factory=list)


class OnboardingGateResult(BaseModel):
    allowed: bool = False
    status: str = "onboarding_required"
    message: str = ""
    missing_steps: List[str] = Field(default_factory=list)
    improvement_actions: List[str] = Field(default_factory=list)
    profile_confidence: ProfileConfidence = Field(default_factory=ProfileConfidence)


class IntentClassification(BaseModel):
    primary_intent: str = Intent.OCCASION_RECOMMENDATION
    confidence: float = 0.0
    secondary_intents: List[str] = Field(default_factory=list)
    reason_codes: List[str] = Field(default_factory=list)


# --- Live Context ---


class LiveContext(BaseModel):
    user_need: str
    occasion_signal: Optional[str] = None
    formality_hint: Optional[str] = None
    time_hint: Optional[str] = None
    specific_needs: List[str] = Field(default_factory=list)
    is_followup: bool = False
    followup_intent: Optional[str] = None
    anchor_garment: Optional[Dict[str, Any]] = None
    # Phase 13: planner-extracted signals forwarded to the outfit architect.
    # These mirror the same-named fields on CopilotResolvedContext; the
    # orchestrator copies them into LiveContext so the architect payload
    # can expose them under a `live_context` key.
    weather_context: str = ""
    time_of_day: str = ""
    target_product_type: str = ""


# --- Conversation Memory ---


class ConversationMemory(BaseModel):
    occasion_signal: Optional[str] = None
    formality_hint: Optional[str] = None
    time_hint: Optional[str] = None
    specific_needs: List[str] = Field(default_factory=list)
    followup_count: int = 0
    last_recommendation_ids: List[str] = Field(default_factory=list)
    recent_intents: List[str] = Field(default_factory=list)
    recent_channels: List[str] = Field(default_factory=list)
    last_user_need: Optional[str] = None
    wardrobe_item_count: int = 0
    wardrobe_memory_enabled: bool = False


# --- Combined Context ---


class CombinedContext(BaseModel):
    user: UserContext
    live: LiveContext
    hard_filters: Dict[str, Any] = Field(default_factory=dict)
    previous_recommendations: Optional[List[Dict[str, Any]]] = None
    conversation_memory: Optional[ConversationMemory] = None
    conversation_history: Optional[List[Dict[str, str]]] = None
    catalog_inventory: Optional[List[Dict[str, Any]]] = None
    # Product IDs the user has previously disliked. Loaded from feedback_events
    # at turn start and used by catalog_search_agent to exclude these items
    # from retrieval results so disliked products do not reappear across turns.
    disliked_product_ids: List[str] = Field(default_factory=list)


# --- Outfit Architect output ---


class QuerySpec(BaseModel):
    query_id: str
    role: str  # complete | top | bottom
    # Filter values can be strings (single value) or lists of strings
    # (multi-value — the SQL function matches ANY value in the array).
    hard_filters: Dict[str, Any] = Field(default_factory=dict)
    query_document: str


class DirectionSpec(BaseModel):
    direction_id: str  # A | B | C
    direction_type: str  # complete | paired | three_piece
    label: str
    queries: List[QuerySpec]


class ResolvedContextBlock(BaseModel):
    occasion_signal: Optional[str] = None
    formality_hint: Optional[str] = None
    time_hint: Optional[str] = None
    specific_needs: List[str] = Field(default_factory=list)
    is_followup: bool = False
    followup_intent: Optional[str] = None
    # Phase 13B: ranking intent signal for downstream reranker/assembler.
    # conservative | balanced | expressive | formal_first | comfort_first
    ranking_bias: str = "balanced"


class RecommendationPlan(BaseModel):
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
    applied_filters: Dict[str, Any] = Field(default_factory=dict)


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
    # 5 always-evaluated dimensions — these are graded for every
    # candidate because their inputs are present once onboarding is
    # complete (body shape, palette, style preference, etc.).
    body_harmony_pct: int = 0
    color_suitability_pct: int = 0
    style_fit_pct: int = 0
    risk_tolerance_pct: int = 0
    comfort_boundary_pct: int = 0
    # Phase 12B follow-ups (April 9 2026): 4 context-gated dimensions
    # are Optional. The visual evaluator returns None when the gating
    # condition is not met:
    #   - occasion_pct: live_context.occasion_signal is None
    #   - weather_time_pct: weather_context AND time_of_day are empty
    #   - specific_needs_pct: specific_needs list is empty
    #   - pairing_coherence_pct: intent is garment_evaluation /
    #     style_discovery / explanation_request (no outfit being paired)
    # Coercing None to 0 would re-introduce the bug where the holistic
    # match_score and the PDP card radar chart show phantom defaults
    # instead of "not evaluated this turn". The legacy text-only
    # OutfitEvaluator still emits 0; that path is retired in Phase 12E.
    occasion_pct: Optional[int] = None
    specific_needs_pct: Optional[int] = None
    weather_time_pct: Optional[int] = None
    pairing_coherence_pct: Optional[int] = None
    classic_pct: int = 0
    dramatic_pct: int = 0
    romantic_pct: int = 0
    natural_pct: int = 0
    minimalist_pct: int = 0
    creative_pct: int = 0
    sporty_pct: int = 0
    edgy_pct: int = 0
    item_ids: List[str] = Field(default_factory=list)
    # Phase 12B: optional fields populated by VisualEvaluatorAgent for the
    # outfit_check / garment_evaluation single-candidate path. The list
    # form remains the canonical shape for occasion_recommendation /
    # pairing_request which use multiple candidates.
    overall_verdict: str = ""  # great_choice | good_with_tweaks | consider_changes | needs_rethink
    overall_note: str = ""
    strengths: List[str] = Field(default_factory=list)
    improvements: List[Dict[str, Any]] = Field(default_factory=list)


# --- Response ---


class OutfitItem(BaseModel):
    product_id: str = ""
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
    source: str = ""


class OutfitCard(BaseModel):
    rank: int
    title: str
    reasoning: str = ""
    body_note: str = ""
    color_note: str = ""
    style_note: str = ""
    occasion_note: str = ""
    # 5 always-evaluated dimensions
    body_harmony_pct: int = 0
    color_suitability_pct: int = 0
    style_fit_pct: int = 0
    risk_tolerance_pct: int = 0
    comfort_boundary_pct: int = 0
    # 4 context-gated dimensions — None means "not evaluated this turn".
    # pairing_coherence_pct is null for garment_evaluation / style_discovery
    # / explanation_request (no outfit being paired); the other 3 are null
    # when their live_context inputs are absent. The frontend drops null
    # dimensions from the radar chart.
    occasion_pct: Optional[int] = None
    specific_needs_pct: Optional[int] = None
    weather_time_pct: Optional[int] = None
    pairing_coherence_pct: Optional[int] = None
    classic_pct: int = 0
    dramatic_pct: int = 0
    romantic_pct: int = 0
    natural_pct: int = 0
    minimalist_pct: int = 0
    creative_pct: int = 0
    sporty_pct: int = 0
    edgy_pct: int = 0
    items: List[Dict[str, Any]] = Field(default_factory=list)
    tryon_image: Optional[str] = None  # data URL of virtual try-on image


class CopilotResolvedContext(BaseModel):
    occasion_signal: Optional[str] = None
    formality_hint: Optional[str] = None
    time_hint: Optional[str] = None
    specific_needs: List[str] = Field(default_factory=list)
    is_followup: bool = False
    followup_intent: Optional[str] = None
    style_goal: str = ""
    # "auto" (default), "wardrobe" (user wants only wardrobe items),
    # or "catalog" (user wants only catalog items). Extracted by the planner
    # from phrases like "from my wardrobe" or "from the catalog".
    source_preference: str = "auto"
    # Phase 12A additions:
    # When the user asks for a specific garment type without an occasion
    # ("show me shirts"), `occasion_recommendation` absorbs what used to be
    # a `product_browse` intent. The architect uses target_product_type to
    # narrow the catalog search.
    target_product_type: str = ""
    # Free-form weather context extracted from the message ("rainy",
    # "humid", "cold", "summer day", etc.). Phase 12C wires this into the
    # architect and visual evaluator prompts as a thinking direction.
    weather_context: str = ""
    # Free-form time-of-day extracted from the message ("morning",
    # "evening", "late night"). Distinct from `time_hint` (which is the
    # legacy daytime/evening enum); both stay until Phase 12C reconciles.
    time_of_day: str = ""


class CopilotActionParameters(BaseModel):
    # Phase 12A: replaced legacy `verdict` (string buy/skip/conditional)
    # with `purchase_intent: bool`. The Phase 12B response formatter
    # computes the buy/skip/conditional verdict deterministically from the
    # evaluator scores; the planner only needs to flag whether the user is
    # asking from a commercial framing.
    purchase_intent: bool = False
    target_piece: Optional[str] = None
    detected_colors: List[str] = Field(default_factory=list)
    detected_garments: List[str] = Field(default_factory=list)
    product_urls: List[str] = Field(default_factory=list)
    feedback_event_type: Optional[str] = None
    wardrobe_item_title: Optional[str] = None


class CopilotPlanResult(BaseModel):
    intent: str = Intent.OCCASION_RECOMMENDATION
    intent_confidence: float = 0.0
    action: str = Action.RESPOND_DIRECTLY
    context_sufficient: bool = True
    assistant_message: str = ""
    follow_up_suggestions: List[str] = Field(default_factory=list)
    resolved_context: CopilotResolvedContext = Field(default_factory=CopilotResolvedContext)
    action_parameters: CopilotActionParameters = Field(default_factory=CopilotActionParameters)


class RecommendationResponse(BaseModel):
    success: bool = True
    message: str = ""
    response_type: str = "recommendation"  # "recommendation" | "clarification"
    outfits: List[OutfitCard] = Field(default_factory=list)
    follow_up_suggestions: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
