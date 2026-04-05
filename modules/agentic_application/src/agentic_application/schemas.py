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


# --- Conversation Memory ---


class ConversationMemory(BaseModel):
    occasion_signal: Optional[str] = None
    formality_hint: Optional[str] = None
    time_hint: Optional[str] = None
    specific_needs: List[str] = Field(default_factory=list)
    plan_type: Optional[str] = None
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
    hard_filters: Dict[str, str] = Field(default_factory=dict)
    previous_recommendations: Optional[List[Dict[str, Any]]] = None
    conversation_memory: Optional[ConversationMemory] = None
    conversation_history: Optional[List[Dict[str, str]]] = None
    catalog_inventory: Optional[List[Dict[str, Any]]] = None


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
    item_ids: List[str] = Field(default_factory=list)


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


class CopilotActionParameters(BaseModel):
    verdict: Optional[str] = None
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
