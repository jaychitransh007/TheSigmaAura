from __future__ import annotations

from typing import Any, Dict, List

from .schemas import RecommendationConfidence, RecommendationConfidenceFactor


def evaluate_recommendation_confidence(
    *,
    answer_mode: str,
    profile_confidence_score_pct: int,
    intent_confidence: float,
    top_match_score: float,
    second_match_score: float = 0.0,
    retrieved_product_count: int = 0,
    candidate_count: int = 0,
    response_outfit_count: int = 0,
    wardrobe_items_used: int = 0,
    restricted_item_exclusion_count: int = 0,
) -> RecommendationConfidence:
    factors: List[RecommendationConfidenceFactor] = []

    factors.append(_factor(
        factor="top_match_strength",
        score=round(_clamp(top_match_score) * 30.0, 2),
        max_score=30.0,
        detail=f"Top recommendation match score was {top_match_score:.2f}.",
    ))
    separation = max(0.0, _clamp(top_match_score) - _clamp(second_match_score))
    factors.append(_factor(
        factor="ranking_separation",
        score=round(min(separation / 0.25, 1.0) * 10.0, 2),
        max_score=10.0,
        detail=f"Top-vs-next score separation was {separation:.2f}.",
    ))
    retrieval_depth_score = min(float(retrieved_product_count), 24.0) / 24.0
    factors.append(_factor(
        factor="retrieval_depth",
        score=round(retrieval_depth_score * 15.0, 2),
        max_score=15.0,
        detail=f"{retrieved_product_count} retrieved products supported the final answer.",
    ))
    candidate_support_score = min(float(candidate_count), 12.0) / 12.0
    factors.append(_factor(
        factor="candidate_support",
        score=round(candidate_support_score * 10.0, 2),
        max_score=10.0,
        detail=f"{candidate_count} assembled candidates were evaluated.",
    ))
    outfit_count_score = min(float(response_outfit_count), 3.0) / 3.0
    factors.append(_factor(
        factor="response_coverage",
        score=round(outfit_count_score * 5.0, 2),
        max_score=5.0,
        detail=f"{response_outfit_count} outfit options were returned.",
    ))
    factors.append(_factor(
        factor="profile_grounding",
        score=round((_clamp(profile_confidence_score_pct / 100.0)) * 15.0, 2),
        max_score=15.0,
        detail=f"Profile confidence was {profile_confidence_score_pct}%.",
    ))
    factors.append(_factor(
        factor="intent_clarity",
        score=round(_clamp(intent_confidence) * 10.0, 2),
        max_score=10.0,
        detail=f"Intent confidence was {intent_confidence:.2f}.",
    ))

    source_score = 0.0
    if answer_mode == "wardrobe_first":
        source_score = 5.0 if wardrobe_items_used >= 2 else 3.0 if wardrobe_items_used == 1 else 0.0
        source_detail = f"{wardrobe_items_used} wardrobe item(s) anchored the answer."
    else:
        source_score = 5.0 if retrieved_product_count >= max(response_outfit_count, 1) else 2.5
        source_detail = "Catalog retrieval directly grounded the answer."
    factors.append(_factor(
        factor="source_grounding",
        score=source_score,
        max_score=5.0,
        detail=source_detail,
    ))

    penalty_score = max(0.0, 5.0 - min(float(restricted_item_exclusion_count), 5.0))
    factors.append(_factor(
        factor="safety_stability",
        score=round(penalty_score, 2),
        max_score=5.0,
        detail=(
            "No restricted items had to be removed from the answer."
            if restricted_item_exclusion_count == 0
            else f"{restricted_item_exclusion_count} restricted item(s) were excluded before returning the answer."
        ),
    ))

    total = sum(f.max_score for f in factors) or 100.0
    earned = sum(f.score for f in factors)
    score_pct = int(round((earned / total) * 100))
    band = "high" if score_pct >= 80 else "medium" if score_pct >= 60 else "low"

    strengths = [f.detail for f in factors if f.score >= (f.max_score * 0.75) and f.max_score > 0]
    weaknesses = [f.detail for f in factors if f.score < (f.max_score * 0.45) and f.max_score > 0]
    explanation: List[str] = []
    if strengths:
        explanation.append(f"Strongest evidence: {strengths[0]}")
    if len(strengths) > 1:
        explanation.append(f"Also helpful: {strengths[1]}")
    if weaknesses:
        explanation.append(f"Confidence was limited by: {weaknesses[0]}")

    if answer_mode == "wardrobe_first":
        summary = (
            f"{band.title()} confidence because the answer is grounded in your saved wardrobe"
            f" and your current profile confidence is {profile_confidence_score_pct}%."
        )
    else:
        summary = (
            f"{band.title()} confidence based on retrieval strength, evaluation separation,"
            f" and your current profile confidence of {profile_confidence_score_pct}%."
        )

    return RecommendationConfidence(
        score_pct=score_pct,
        confidence_band=band,
        summary=summary,
        explanation=explanation,
        factors=factors,
    )


def _factor(*, factor: str, score: float, max_score: float, detail: str) -> RecommendationConfidenceFactor:
    return RecommendationConfidenceFactor(
        factor=factor,
        score=max(0.0, min(score, max_score)),
        max_score=max_score,
        detail=detail,
    )


def _clamp(value: float) -> float:
    return max(0.0, min(float(value or 0.0), 1.0))
