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
    # May 2026: style_goal carries the per-turn directional cue from chat
    # (e.g. "edgy", "old-money classic", "minimalist"). Replaces the
    # per-user stored archetype in driving directional vocabulary.
    style_goal: str = ""


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
    # R4 (May 5 2026): aggregated like/dislike *attributes* (not IDs).
    # Shape: {"disliked": {axis: [{"value": v, "count": n}, ...]}, "liked": {...}}
    # Surfaced to Composer for soft preference (lean away from disliked
    # attributes when picking items). Rater no longer consumes this — see
    # PR #89, May 5 2026 — and PR 2 (this PR) replaces this aggregate signal
    # with the richer episodic timeline below for the architect.
    archetypal_preferences: Dict[str, Any] = Field(default_factory=dict)
    # Episodic memory: chronological timeline of the user's recent
    # like/dislike events (last 30 days by default), each row carrying the
    # user_query that produced the outfit and the full attribute set of the
    # garment. Surfaced to the Architect so it can find context-dependent
    # patterns (e.g. "user disliked solid navy at the office, but liked it
    # for date night") and bias retrieval queries accordingly. Empty list
    # for cold-start users.
    recent_user_actions: List[Dict[str, Any]] = Field(default_factory=list)


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


class RecommendationPlan(BaseModel):
    retrieval_count: int = 5
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


# --- Outfit candidate (after Composer + Rater, May 3 2026) ---
#
# An outfit ready for try-on rendering and visual evaluation. Built
# either by the LLM ranker (Composer + Rater) on the catalog pipeline,
# or hand-constructed by the orchestrator on the wardrobe-anchored
# pipeline. The wardrobe-anchored path skips the Rater and pre-fills
# fashion_score = 100 (already-validated).


class OutfitCandidate(BaseModel):
    candidate_id: str
    direction_id: str
    candidate_type: str  # complete | paired | three_piece
    items: List[Dict[str, Any]] = Field(default_factory=list)
    # LLM-ranker scores. fashion_score is the gating field downstream;
    # the sub-scores stay attached so the response payload can show
    # the breakdown in the UI later. For wardrobe items, the orchestrator
    # sets fashion_score = 100 and the rest to neutral (2).
    fashion_score: int = 0  # 0–100 (blended from 1/2/3 sub-scores)
    # R7 (May 5 2026): six sub-scores on a 1/2/3 scale.
    # 1 = clear miss, 2 = works, 3 = clear win.
    occasion_fit: int = 2
    body_harmony: int = 2
    color_harmony: int = 2
    # R7: renamed from inter_item_coherence; scoped to fit + fabric only
    # (formality_consistency moved to `formality`; detail_rhythm moved
    # to `statement`). For complete (single-item) outfits the LLM emits
    # 3 and the blender drops the dim. Optional so unset / legacy data
    # propagates as None all the way to the radar (axis hidden) rather
    # than getting masked as a phantom 3.
    pairing: Optional[int] = None
    # R7 (May 5 2026): formality is now its own axis (was double-counted
    # inside occasion_fit + inter_item_coherence). Always emitted.
    formality: int = 2
    # R7 (May 5 2026): pattern density + embellishment intensity.
    # Always emitted; the question is whether the level *matches* the
    # request, not whether the outfit is loud or quiet in absolute terms.
    statement: int = 2
    composer_id: str = ""  # Empty for wardrobe-anchored candidates.
    composer_rationale: str = ""
    rater_rationale: str = ""
    unsuitable: bool = False  # Hard veto from the Rater.
    # Stylist-flavored outfit title carried over from ComposedOutfit.name.
    # Empty for wardrobe-anchored candidates (those don't go through the
    # composer); the orchestrator handles the empty case at the promotion site.
    name: str = ""


# --- LLM ranker output (Composer + Rater, May 3 2026) ---
#
# Composer: takes the retrieved item pool grouped by direction, plus
# user message + context, and constructs up to 10 coherent outfits.
#
# Rater: takes the composed outfits, plus user message + context, and
# scores each on a 4-dimension rubric, computes an overall fashion_score,
# orders them, and flags any unsuitable.
#
# Both agents are LLM-driven (gpt-5-mini). They replace the deterministic
# OutfitAssembler + Reranker; cosine similarity is reduced to a retrieval
# primitive only — all reasoning about whether items belong together is
# done by the LLM.


class ComposedOutfit(BaseModel):
    composer_id: str  # Composer-assigned label (e.g., "C1", "C2") for downstream traceability.
    direction_id: str  # A | B | C — which architect direction this outfit was constructed from.
    direction_type: str  # complete | paired | three_piece
    item_ids: List[str]  # Pool item IDs the Composer picked. Must all exist in the pool.
    rationale: str  # The Composer's brief reasoning for this construction.
    # Short stylist-flavored title for the outfit (e.g., "Sharp Navy Boardroom",
    # "Soft Cream Daywear"). Surfaced as the user-facing card title; the
    # orchestrator falls back to "Outfit N" only when this is empty.
    name: str = ""


class ComposerResult(BaseModel):
    outfits: List[ComposedOutfit] = Field(default_factory=list)
    overall_assessment: str = "moderate"  # strong | moderate | weak | unsuitable
    pool_unsuitable: bool = False  # True when Composer judges the pool can't make any acceptable outfit.
    raw_response: str = ""  # Full LLM JSON, persisted for audit.
    # Token usage for THIS call (sums across the optional retry pass).
    # Carried on the result so concurrent turns don't race over a shared
    # ``last_usage`` instance attribute. Orchestrator reads from here.
    usage: Dict[str, int] = Field(default_factory=dict)
    # PR #80 (May 5 2026): how many LLM round-trips it took. 1 in the
    # happy path; 2 when the first attempt was a full hallucination
    # and the agent retried with a stricter suffix. Surfaced so the
    # ``rater_decision`` / ``composer_decision`` tool_traces can
    # distinguish single-shot from retry-rescued from retry-failed.
    attempt_count: int = 1


class RatedOutfit(BaseModel):
    composer_id: str  # Matches ComposedOutfit.composer_id
    rank: int = 0
    fashion_score: int = 0  # 0–100. Weighted blend of the 1/2/3 sub-scores (computed in code).
    # R7 (May 5 2026): six sub-scores on a 1/2/3 scale.
    occasion_fit: int = 2
    body_harmony: int = 2
    color_harmony: int = 2
    # R7: renamed from inter_item_coherence; scoped to fit + fabric.
    # Optional so the orchestrator can pass None for complete outfits
    # (radar drops the axis) without masking as a phantom 3.
    pairing: Optional[int] = None
    formality: int = 2
    statement: int = 2
    rationale: str = ""
    unsuitable: bool = False  # Hard veto — drop even if fashion_score is high.


class RaterResult(BaseModel):
    ranked_outfits: List[RatedOutfit] = Field(default_factory=list)
    overall_assessment: str = "moderate"  # strong | moderate | weak
    raw_response: str = ""  # Full LLM JSON, persisted for audit.
    # See ComposerResult.usage — same rationale.
    usage: Dict[str, int] = Field(default_factory=dict)
    # R3 (May 5 2026): which fashion_score weight profile was applied
    # this turn. One of WEIGHT_PROFILES keys ("default", "ceremonial",
    # "slimming", "bold", "comfortable"). Surfaced for telemetry so we
    # can SQL-grep "how often did the comfortable override fire?"
    fashion_score_weight_profile: str = "default"


# --- Evaluation output ---


class EvaluatedRecommendation(BaseModel):
    """Per-candidate evaluation row consumed by the response formatter.

    Post-V2 (May 5 2026): the visual_evaluator + outfit_check +
    garment_evaluation flows are gone. Only Rater-derived dims remain.

    R7 (May 5 2026): the rater shifted from 4 dims on a 0–100 scale to
    6 dims on a 1/2/3 scale. The ``_pct`` fields here are rescaled for
    UI consumption: 1 → 0%, 2 → 50%, 3 → 100%. The radar reads percents,
    so the underlying scale change doesn't break the chart contract.
    """
    candidate_id: str
    rank: int = 0
    match_score: float = 0.0
    title: str = ""
    reasoning: str = ""
    item_ids: List[str] = Field(default_factory=list)
    # Rater dimensions surfaced on the outfit-card radar. Each ``_pct``
    # is the rescaled 1/2/3 sub-score (1→0, 2→50, 3→100). occasion_pct
    # remains Optional for legacy paths but the Rater always populates it.
    body_harmony_pct: int = 0
    color_suitability_pct: int = 0
    occasion_pct: Optional[int] = None
    # R7: renamed from inter_item_coherence_pct. None for `complete`
    # (single-item) outfits where the dim doesn't apply; the radar
    # drops the axis when null.
    pairing_pct: Optional[int] = None
    # R7 (May 5 2026): formality and statement are their own axes now.
    formality_pct: int = 0
    statement_pct: int = 0
    # Overall blended score (Rater-derived). Centre label of the radar.
    fashion_score_pct: int = 0


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
    """User-facing outfit card.

    R7 (May 5 2026): radar moved from 4 axes to 6 (added Formality
    and Statement; renamed inter_item_coherence → Pairing scoped to
    fit + fabric). Each ``_pct`` is the rescaled 1/2/3 rater sub-score
    (1→0, 2→50, 3→100). For single-item complete outfits Pairing
    drops → 5 axes.
    """
    rank: int
    title: str
    reasoning: str = ""
    # Rater dimensions surfaced on the outfit-card radar.
    body_harmony_pct: int = 0
    color_suitability_pct: int = 0
    occasion_pct: Optional[int] = None
    # R7: paired/three_piece only; null for single-item complete outfits.
    pairing_pct: Optional[int] = None
    formality_pct: int = 0
    statement_pct: int = 0
    # Overall blended score (Rater-derived). Centre label of the radar.
    fashion_score_pct: int = 0
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
