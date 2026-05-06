"""Synthetic profile pool for the recipe-bootstrap run.

The bootstrap pipeline (Pre-launch Step 3) runs the existing slow
architect + composer for every grid cell. Each cell is conditioned on a
profile matching the cell's (archetype, gender) so recipes capture
profile-conditional variation. This module produces the deterministic
pool those cells draw from.

Vocabulary lifted from ``modules/style_engine/configs/config/user_context_attributes.json``:

- 12 style archetypes (canonical values in user_context_attributes.json)
- 2 gender expressions (the schema check on ``user_style_preference_snapshots``)
- 3 age bands (18_24, 25_30, 30_35)

Body frame and palette taxonomies match the deterministic 12-sub-season
color analysis interpreter and the body-analysis output.
"""
from __future__ import annotations

import random
from dataclasses import asdict, dataclass
from typing import Dict, List


# 12 style archetypes — canonical values from user_context_attributes.json.
ARCHETYPES: List[str] = [
    "classic",
    "minimalist",
    "modern_professional",
    "romantic",
    "glamorous",
    "dramatic",
    "creative",
    "natural",
    "sporty",
    "trend_forward",
    "bohemian",
    "edgy",
]

GENDERS: List[str] = ["male", "female"]

AGE_BANDS: List[str] = ["18_24", "25_30", "30_35"]

# Body frames vary by gender; the analysis pipeline only emits frames
# from the gender-appropriate set, so the synthetic pool follows suit.
BODY_FRAMES: Dict[str, List[str]] = {
    "male": ["rectangle", "triangle", "inverted_triangle", "athletic"],
    "female": ["rectangle", "hourglass", "pear", "apple", "inverted_triangle"],
}

HEIGHT_BANDS: List[str] = ["short", "average", "tall"]

# 12 sub-season palette taxonomy (deterministic interpreter is the source
# of truth — see modules/user/src/user/analysis.py).
PALETTES: List[str] = [
    "true_spring", "warm_spring", "light_spring",
    "true_summer", "cool_summer", "light_summer",
    "true_autumn", "warm_autumn", "soft_autumn",
    "true_winter", "cool_winter", "deep_winter",
]

RISK_TOLERANCE: List[str] = ["conservative", "moderate", "adventurous"]
FORMALITY_LEAN: List[str] = ["casual", "balanced", "formal"]
BUDGET_BANDS: List[str] = ["budget", "mid", "premium"]

# Plausible secondary archetypes for each primary — when the bootstrap
# runs the architect, blends like classic/minimalist (80/20) read as
# coherent style stories. Random secondaries (e.g., classic/edgy) would
# generate noisy recipes.
ARCHETYPE_SECONDARIES: Dict[str, List[str]] = {
    "classic": ["minimalist", "modern_professional"],
    "minimalist": ["classic", "modern_professional"],
    "modern_professional": ["classic", "minimalist"],
    "romantic": ["bohemian", "natural"],
    "glamorous": ["dramatic", "trend_forward"],
    "dramatic": ["glamorous", "edgy"],
    "creative": ["bohemian", "trend_forward"],
    "natural": ["minimalist", "bohemian"],
    "sporty": ["natural", "minimalist"],
    "trend_forward": ["glamorous", "edgy"],
    "bohemian": ["romantic", "natural"],
    "edgy": ["dramatic", "trend_forward"],
}

# Bias the pool toward archetypes the planner sees most in production.
# Production traffic skews toward classic/minimalist/modern_professional
# (~40% combined per Phase 12 analysis); the rest get baseline coverage.
ARCHETYPE_WEIGHTS: List[int] = [3, 3, 3, 2, 2, 2, 2, 2, 1, 2, 1, 1]


@dataclass
class SyntheticProfile:
    profile_id: str
    primary_archetype: str
    secondary_archetype: str
    blend_ratio_primary: int
    blend_ratio_secondary: int
    gender: str
    age_band: str
    body_frame: str
    height_band: str
    skin_palette: str
    risk_tolerance: str
    formality_lean: str
    budget_band: str

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


def generate_profile_pool(
    *,
    target_size: int = 75,
    seed: int = 42,
) -> List[SyntheticProfile]:
    """Generate a deterministic synthetic profile pool.

    First pass guarantees one profile per (archetype × gender) combo
    (24 profiles minimum). Remaining slots are weighted-sampled toward
    the archetypes that dominate production traffic so recipes for
    common cells get more profile-side variation.
    """
    rng = random.Random(seed)
    profiles: List[SyntheticProfile] = []

    # Pass 1: guaranteed coverage of (archetype × gender).
    for archetype in ARCHETYPES:
        for gender in GENDERS:
            profiles.append(_make_profile(rng, archetype, gender, len(profiles)))

    # Pass 2: fill to target_size with traffic-weighted sampling.
    while len(profiles) < target_size:
        archetype = rng.choices(ARCHETYPES, weights=ARCHETYPE_WEIGHTS, k=1)[0]
        gender = rng.choice(GENDERS)
        profiles.append(_make_profile(rng, archetype, gender, len(profiles)))

    return profiles


def _make_profile(
    rng: random.Random, archetype: str, gender: str, idx: int
) -> SyntheticProfile:
    secondary_options = ARCHETYPE_SECONDARIES.get(archetype) or [
        a for a in ARCHETYPES if a != archetype
    ]
    secondary = rng.choice(secondary_options)
    blend_primary = rng.choice([60, 70, 80, 90, 100])
    blend_secondary = 100 - blend_primary

    return SyntheticProfile(
        profile_id=f"p_{idx:03d}_{archetype}_{gender}",
        primary_archetype=archetype,
        secondary_archetype=secondary if blend_secondary > 0 else "",
        blend_ratio_primary=blend_primary,
        blend_ratio_secondary=blend_secondary,
        gender=gender,
        age_band=rng.choice(AGE_BANDS),
        body_frame=rng.choice(BODY_FRAMES[gender]),
        height_band=rng.choice(HEIGHT_BANDS),
        skin_palette=rng.choice(PALETTES),
        risk_tolerance=rng.choice(RISK_TOLERANCE),
        formality_lean=rng.choice(FORMALITY_LEAN),
        budget_band=rng.choice(BUDGET_BANDS),
    )
