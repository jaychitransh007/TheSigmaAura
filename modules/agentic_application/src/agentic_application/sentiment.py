from __future__ import annotations

from typing import Dict, List


_SENTIMENT_RULES = (
    ("anxious", -0.65, ("anxious", "nervous", "worried", "stress", "panic", "unsure")),
    ("frustrated", -0.75, ("frustrated", "annoyed", "hate", "awful", "terrible", "confusing")),
    ("confident", 0.75, ("confident", "powerful", "sharp", "polished", "strong")),
    ("positive", 0.55, ("love", "great", "good", "beautiful", "amazing", "perfect")),
    ("negative", -0.55, ("bad", "ugly", "wrong", "dislike", "unflattering", "worse")),
    ("uncertain", -0.25, ("maybe", "not sure", "not certain", "wondering", "should i", "could i")),
)


def extract_sentiment(message: str) -> Dict[str, object]:
    lowered = str(message or "").strip().lower()
    if not lowered:
        return {
            "sentiment_label": "neutral",
            "sentiment_score": 0.0,
            "intensity": 0.0,
            "cues": [],
        }

    matched_label = "neutral"
    matched_score = 0.0
    matched_cues: List[str] = []

    for label, score, cues in _SENTIMENT_RULES:
        cue_hits = [cue for cue in cues if cue in lowered]
        if cue_hits:
            matched_label = label
            matched_score = score
            matched_cues = cue_hits
            break

    intensity = min(1.0, max(abs(matched_score), 0.15 if matched_cues else 0.0))
    return {
        "sentiment_label": matched_label,
        "sentiment_score": matched_score,
        "intensity": intensity,
        "cues": matched_cues,
    }


__all__ = ["extract_sentiment"]
