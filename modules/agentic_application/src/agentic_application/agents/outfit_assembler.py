from __future__ import annotations

from typing import Any, Dict, List, Tuple
from uuid import uuid4

from ..intent_registry import FollowUpIntent
from ..schemas import (
    CombinedContext,
    OutfitCandidate,
    RecommendationPlan,
    RetrievedProduct,
    RetrievedSet,
)
from ..product_links import resolve_product_url


def _dedupe_lower(values: list) -> list[str]:
    """Return unique lowercase non-empty strings preserving order."""
    seen: set[str] = set()
    result: list[str] = []
    for v in values:
        s = str(v or "").strip().lower()
        if s and s not in seen:
            seen.add(s)
            result.append(s)
    return result


def _followup_pair_adjustment(
    top: RetrievedProduct,
    bottom: RetrievedProduct,
    combined_context: CombinedContext,
) -> tuple[float, list[str]]:
    """Return (score_adjustment, notes) based on follow-up intent."""
    intent = (combined_context.live.followup_intent or "").strip()
    if not intent:
        return 0.0, []

    previous = (combined_context.previous_recommendations or [None])[0]
    if not previous or not isinstance(previous, dict):
        return 0.0, []

    prev_colors = _dedupe_lower(previous.get("primary_colors") or [])
    prev_occasions = _dedupe_lower(previous.get("occasion_fits") or [])

    pair_colors = _dedupe_lower([
        _get_attr(top, "primary_color") or _get_attr(top, "PrimaryColor"),
        _get_attr(bottom, "primary_color") or _get_attr(bottom, "PrimaryColor"),
    ])
    pair_occasions = _dedupe_lower([
        _get_attr(top, "occasion_fit") or _get_attr(top, "OccasionFit"),
        _get_attr(bottom, "occasion_fit") or _get_attr(bottom, "OccasionFit"),
    ])

    adj = 0.0
    notes: list[str] = []

    if intent == FollowUpIntent.CHANGE_COLOR:
        overlapping = [c for c in pair_colors if c in prev_colors]
        if overlapping:
            penalty = 0.10 * len(overlapping)
            adj += penalty
            notes.append(f"followup penalty +{penalty:.2f}: color overlap {overlapping} with previous")
    elif intent == FollowUpIntent.SIMILAR_TO_PREVIOUS:
        matching_occasions = [o for o in pair_occasions if o in prev_occasions]
        if matching_occasions:
            adj -= 0.05
            notes.append("followup boost -0.05: occasion matches previous")
        matching_colors = [c for c in pair_colors if c in prev_colors]
        if matching_colors:
            boost = 0.03 * len(matching_colors)
            adj -= boost
            notes.append(f"followup boost -{boost:.2f}: {len(matching_colors)} shared color(s) with previous")

    return adj, notes


def _followup_complete_adjustment(
    product: RetrievedProduct,
    combined_context: CombinedContext,
) -> tuple[float, list[str]]:
    """Return (score_adjustment, notes) for a complete item based on follow-up intent."""
    intent = (combined_context.live.followup_intent or "").strip()
    if not intent:
        return 0.0, []

    previous = (combined_context.previous_recommendations or [None])[0]
    if not previous or not isinstance(previous, dict):
        return 0.0, []

    prev_colors = _dedupe_lower(previous.get("primary_colors") or [])
    prev_occasions = _dedupe_lower(previous.get("occasion_fits") or [])

    item_colors = _dedupe_lower([
        _get_attr(product, "primary_color") or _get_attr(product, "PrimaryColor"),
    ])
    item_occasions = _dedupe_lower([
        _get_attr(product, "occasion_fit") or _get_attr(product, "OccasionFit"),
    ])

    adj = 0.0
    notes: list[str] = []

    if intent == FollowUpIntent.CHANGE_COLOR:
        overlapping = [c for c in item_colors if c in prev_colors]
        if overlapping:
            penalty = 0.10 * len(overlapping)
            adj += penalty
            notes.append(f"followup penalty +{penalty:.2f}: color overlap {overlapping} with previous")
    elif intent == FollowUpIntent.SIMILAR_TO_PREVIOUS:
        matching_occasions = [o for o in item_occasions if o in prev_occasions]
        if matching_occasions:
            adj -= 0.05
            notes.append("followup boost -0.05: occasion matches previous")
        matching_colors = [c for c in item_colors if c in prev_colors]
        if matching_colors:
            boost = 0.03 * len(matching_colors)
            adj -= boost
            notes.append(f"followup boost -{boost:.2f}: {len(matching_colors)} shared color(s) with previous")

    return adj, notes


# ─── ranking_bias scoring coefficients ──────────────────────────────────
#
# Architect-emitted `ranking_bias` (one of: balanced, conservative, expressive,
# formal_first, comfort_first) modulates how the assembler weighs penalties
# and applies bias-specific bonuses on top of the base similarity score.
#
# `_pen` keys multiply existing penalties — values >1.0 amplify, <1.0 soften.
# `_bonus` keys add to the *penalty* term (which is then subtracted from the
# base score), so:
#   - a NEGATIVE bonus value boosts the candidate (lowers penalty)
#   - a POSITIVE bonus value penalises it (raises penalty)
#
# `loud_bonus` triggers on bold/expressive signals (non-solid pattern, high
# saturation, or visible embellishment); `formal_bonus` triggers when both
# items show high formality signal strength at semi_formal+ formality;
# `comfort_bonus` triggers on relaxed fit + flowing/soft drape.
_BIAS_COEFS: Dict[str, Dict[str, float]] = {
    "balanced":      {"form_pen": 1.0, "occ_pen": 1.0, "vol_pen": 1.0, "pat_pen": 1.0, "loud_bonus": 0.0,   "formal_bonus": 0.0,   "comfort_bonus": 0.0},
    "conservative":  {"form_pen": 1.5, "occ_pen": 1.5, "vol_pen": 1.3, "pat_pen": 1.5, "loud_bonus": +0.05, "formal_bonus": 0.0,   "comfort_bonus": 0.0},
    "expressive":    {"form_pen": 0.7, "occ_pen": 0.9, "vol_pen": 0.8, "pat_pen": 0.6, "loud_bonus": -0.10, "formal_bonus": 0.0,   "comfort_bonus": 0.0},
    "formal_first":  {"form_pen": 1.7, "occ_pen": 1.5, "vol_pen": 1.0, "pat_pen": 1.0, "loud_bonus": 0.0,   "formal_bonus": -0.10, "comfort_bonus": 0.0},
    "comfort_first": {"form_pen": 0.8, "occ_pen": 0.9, "vol_pen": 0.6, "pat_pen": 1.0, "loud_bonus": 0.0,   "formal_bonus": 0.0,   "comfort_bonus": -0.08},
}

_FORMAL_HIGH_SIGNALS = {"high", "very_high", "strong", "very_strong"}
_FORMAL_OK_LEVELS = {"semi_formal", "formal", "ultra_formal"}
_LOUD_PATTERNS = {"floral", "geometric", "abstract", "stripe", "stripes", "check", "checks", "plaid", "graphic", "print", "embellished"}
_LOUD_SATURATIONS = {"high", "vivid", "bold", "saturated"}
_LOUD_EMBELLISHMENT = {"moderate", "heavy", "elaborate", "ornate", "statement"}
_RELAXED_FITS = {"relaxed", "loose", "oversized"}
_SOFT_DRAPES = {"flowing", "fluid", "soft", "drapey", "draped"}


def _resolve_bias(combined_context: "CombinedContext | None") -> Dict[str, float]:
    """Look up the bias coefficient row, defaulting to balanced."""
    if combined_context is None:
        return _BIAS_COEFS["balanced"]
    bias = (combined_context.live.ranking_bias or "balanced").strip().lower()
    return _BIAS_COEFS.get(bias, _BIAS_COEFS["balanced"])


def _is_loud(product: RetrievedProduct) -> bool:
    """True when a product carries strong expressive signals."""
    pat = (_get_attr(product, "pattern_type") or _get_attr(product, "PatternType") or "").strip().lower()
    sat = (_get_attr(product, "color_saturation") or _get_attr(product, "ColorSaturation") or "").strip().lower()
    emb = (_get_attr(product, "embellishment_level") or _get_attr(product, "EmbellishmentLevel") or "").strip().lower()
    if pat and pat != "solid" and pat in _LOUD_PATTERNS:
        return True
    if sat in _LOUD_SATURATIONS:
        return True
    if emb in _LOUD_EMBELLISHMENT:
        return True
    return False


def _is_high_formality(product: RetrievedProduct) -> bool:
    """True when a product shows high formality signal at semi_formal+ level."""
    sig = (_get_attr(product, "formality_signal_strength") or _get_attr(product, "FormalitySignalStrength") or "").strip().lower()
    lvl = (_get_attr(product, "formality_level") or _get_attr(product, "FormalityLevel") or "").strip().lower()
    return sig in _FORMAL_HIGH_SIGNALS and lvl in _FORMAL_OK_LEVELS


def _is_comfortable(product: RetrievedProduct) -> bool:
    """True when a product reads as relaxed-fit + flowing drape."""
    fit = (_get_attr(product, "fit_type") or _get_attr(product, "FitType") or "").strip().lower()
    drape = (_get_attr(product, "fabric_drape") or _get_attr(product, "FabricDrape") or "").strip().lower()
    return fit in _RELAXED_FITS and drape in _SOFT_DRAPES


def _apply_bias_bonus(
    products: List[RetrievedProduct], coefs: Dict[str, float],
) -> Tuple[float, List[str]]:
    """Compute bias-driven adjustment to the penalty + accompanying notes.

    Returns ``(penalty_delta, notes)``. Negative delta = score boost (since
    score = base - penalty). Iterates the supplied products and stacks
    multi-item triggers (e.g. both items are loud → bonus applies twice).
    """
    delta = 0.0
    notes: List[str] = []
    if not products:
        return 0.0, notes

    loud = coefs.get("loud_bonus", 0.0)
    formal = coefs.get("formal_bonus", 0.0)
    comfort = coefs.get("comfort_bonus", 0.0)

    if loud:
        loud_count = sum(1 for p in products if _is_loud(p))
        if loud_count:
            adj = loud * loud_count
            delta += adj
            notes.append(f"bias loud_bonus {adj:+.3f}: {loud_count} expressive item(s)")
    if formal:
        # Only apply when ALL items in the outfit are high-formality.
        if all(_is_high_formality(p) for p in products):
            delta += formal
            notes.append(f"bias formal_bonus {formal:+.3f}: high-formality outfit")
    if comfort:
        comfort_count = sum(1 for p in products if _is_comfortable(p))
        if comfort_count:
            adj = comfort * comfort_count
            delta += adj
            notes.append(f"bias comfort_bonus {adj:+.3f}: {comfort_count} relaxed/flowing item(s)")

    return delta, notes


# Formality compatibility: levels that can pair together.
_FORMALITY_COMPAT: Dict[str, set] = {
    "casual": {"casual", "smart_casual"},
    "smart_casual": {"casual", "smart_casual", "business_casual"},
    "business_casual": {"smart_casual", "business_casual", "semi_formal"},
    "semi_formal": {"business_casual", "semi_formal", "formal"},
    "formal": {"semi_formal", "formal", "ultra_formal"},
    "ultra_formal": {"formal", "ultra_formal"},
}

# Color temperature compatibility.
_TEMP_COMPAT: Dict[str, set] = {
    "warm": {"warm", "neutral"},
    "cool": {"cool", "neutral"},
    "neutral": {"warm", "cool", "neutral"},
}

MAX_PAIRED_CANDIDATES = 30

# Valid garment_category values for each retrieval role.  Products whose
# enriched garment_category falls outside the allowed set for their role
# are filtered out before assembly scoring — this prevents accessories
# (pocket squares, dupattas) and mis-tagged items from appearing as
# tops, bottoms, or outerwear.
_VALID_CATEGORIES_FOR_ROLE: Dict[str, set[str]] = {
    "top": {"top"},
    "bottom": {"bottom"},
    "outerwear": {"outerwear"},
    "complete": {"set", "one_piece", "complete"},
}


def _is_valid_for_role(product: "RetrievedProduct", role: str) -> bool:
    """Check if a product's garment_category is compatible with the role."""
    allowed = _VALID_CATEGORIES_FOR_ROLE.get(role)
    if not allowed:
        return True  # unknown role — don't block
    cat = str(
        product.enriched_data.get("garment_category")
        or product.metadata.get("garment_category")
        or ""
    ).strip().lower()
    if not cat:
        return True  # no category data — let it through
    return cat in allowed

# Cross-outfit diversity cap: a single product_id may appear in at most this
# many of the assembled candidates that are returned to the evaluator and,
# ultimately, the user. Set to 1 so each garment shows up in exactly one
# recommended outfit — the one where it pairs best. Candidates that would
# exceed this cap are *dropped* (not deferred), so the evaluator never sees
# duplicates and cannot promote a duplicate into the final 3.
#
# This rule applies to the main catalog pipeline only. It does NOT apply to:
#   - wardrobe-first pairing (anchor is structural, appears in both the
#     wardrobe and catalog-alternatives cards by design)
#
# Note: capsule/trip planning was removed in Phase 12A and will return as a
# distinct intent in a later phase; when it does, it will need its own
# diversity model that allows pieces to recur across dayparts (that's what
# "capsule" means).
MAX_PRODUCT_REPEAT_PER_RUN = 1


def _get_attr(product: RetrievedProduct, key: str) -> str:
    """Get a normalized attribute from enriched data or metadata."""
    val = str(
        product.enriched_data.get(key)
        or product.metadata.get(key)
        or ""
    ).strip().lower()
    return val


def _formality_compatible(a: str, b: str) -> Tuple[bool, str]:
    """Check formality compatibility. Returns (ok, note).

    April 9, 2026: converted from hard rejection to soft penalty.
    The previous behavior returned (False, ...) on any mismatch, which
    hard-rejected the pair at score=0. This caused zero-candidate
    outcomes when a casual anchor (e.g. track pants) was paired with
    smart_casual catalog shirts — every pair was rejected, producing
    empty outfits. Now mismatches are penalized but never rejected
    outright, so the assembler always produces candidates for the
    evaluator to judge visually.
    """
    if not a or not b:
        return True, ""
    allowed = _FORMALITY_COMPAT.get(a)
    if allowed is None:
        return True, ""
    if b in allowed:
        return True, ""
    return True, f"formality gap: {a} vs {b}"


def _color_temp_compatible(a: str, b: str) -> Tuple[bool, str]:
    if not a or not b:
        return True, ""
    allowed = _TEMP_COMPAT.get(a)
    if allowed is None:
        return True, ""
    if b in allowed:
        return True, ""
    return False, f"color temperature clash: {a} vs {b}"


def _occasion_compatible(a: str, b: str) -> Tuple[bool, str]:
    """Check occasion compatibility. Returns (ok, note).

    April 9, 2026: converted from hard rejection to soft penalty.
    The previous exact-match check rejected any pair where the two
    items had different occasion_fit tags — even when both were
    perfectly reasonable for the same context (e.g. "casual" top with
    "evening" pants). Now mismatches are penalized but never rejected
    outright.
    """
    if not a or not b:
        return True, ""
    if a == b:
        return True, ""
    return True, f"occasion gap: {a} vs {b}"


def _pattern_compatible(a: str, b: str) -> Tuple[bool, str]:
    if not a or not b:
        return True, ""
    if a == "solid" or b == "solid":
        return True, ""
    # Both patterned: penalize but don't reject
    return True, "double pattern — consider if scales differ"


def _volume_compatible(a: str, b: str) -> Tuple[bool, str]:
    """Check volume compatibility. Returns (ok, note).

    April 9, 2026: converted from hard rejection to soft penalty.
    Double-oversized is penalized but not rejected outright — the
    visual evaluator can judge whether the actual rendered look works.
    """
    if a == "oversized" and b == "oversized":
        return True, "extreme volume: both oversized"
    return True, ""


class OutfitAssembler:
    """Assembles outfit candidates from retrieved product sets."""

    def assemble(
        self,
        retrieved_sets: List[RetrievedSet],
        plan: RecommendationPlan,
        combined_context: CombinedContext,
    ) -> List[OutfitCandidate]:
        candidates: List[OutfitCandidate] = []

        # Group retrieved sets by direction
        sets_by_direction: Dict[str, List[RetrievedSet]] = {}
        for rs in retrieved_sets:
            sets_by_direction.setdefault(rs.direction_id, []).append(rs)

        for direction in plan.directions:
            direction_sets = sets_by_direction.get(direction.direction_id, [])
            if direction.direction_type == "complete":
                candidates.extend(
                    self._assemble_complete(direction.direction_id, direction_sets, combined_context)
                )
            elif direction.direction_type == "paired":
                candidates.extend(
                    self._assemble_paired(direction.direction_id, direction_sets, combined_context)
                )
            elif direction.direction_type == "three_piece":
                candidates.extend(
                    self._assemble_three_piece(direction.direction_id, direction_sets, combined_context)
                )

        candidates = self._enforce_cross_outfit_diversity(candidates)
        return candidates

    @staticmethod
    def _enforce_cross_outfit_diversity(
        candidates: List[OutfitCandidate],
    ) -> List[OutfitCandidate]:
        """Enforce "each non-anchor garment appears in at most one recommendation".

        Walks candidates in assembly-score order (highest first) and accepts
        each only if none of its NON-ANCHOR items has already been used by
        a previously-accepted candidate. Because we walk in score order,
        the first time a given product_id appears is by definition its
        *highest-scoring pairing* — the pair where it fits best. Every
        later candidate containing that product is dropped.

        **Phase 12D anchor exemption:** items marked with ``is_anchor=True``
        are exempt from the "no repeats" rule. Pairing requests inject the
        user's anchor garment into every paired candidate by definition;
        without this exemption, the diversity pass would drop all but the
        first paired candidate, collapsing pairing turns to a single
        outfit. The orchestrator sets ``enriched_data["is_anchor"] = True``
        on the synthetic anchor RetrievedProduct it injects, and
        ``_product_to_item`` propagates that flag to the candidate item.

        Rejected candidates are **not** returned. The evaluator sees only
        the diverse set. This is the final-state invariant: if a non-anchor
        product is suppressed here, it cannot sneak back into the response
        via a high evaluation score on a duplicate candidate.
        """
        if not candidates:
            return candidates
        ordered = sorted(
            candidates,
            key=lambda c: float(getattr(c, "assembly_score", 0.0) or 0.0),
            reverse=True,
        )
        used: set[str] = set()
        accepted: List[OutfitCandidate] = []
        dropped_count = 0
        for candidate in ordered:
            # Anchor products are exempt from the "no repeats" rule —
            # they're allowed (in fact required) to appear in every paired
            # candidate of a pairing turn.
            non_anchor_item_ids = [
                str(item.get("product_id") or "").strip()
                for item in (candidate.items or [])
                if not item.get("is_anchor")
            ]
            non_anchor_item_ids = [pid for pid in non_anchor_item_ids if pid]
            if any(pid in used for pid in non_anchor_item_ids):
                dropped_count += 1
                continue
            for pid in non_anchor_item_ids:
                used.add(pid)
            try:
                candidate.assembly_notes = list(candidate.assembly_notes or []) + [
                    "diversity_pass: accepted (best pairing for its items, "
                    "no repeat allowed across outfits except anchors)"
                ]
            except Exception:  # noqa: BLE001 — defensive on pydantic model attrs
                pass
            accepted.append(candidate)
        if dropped_count and accepted:
            # Stamp a counter on the highest-scoring accepted candidate so
            # logs and turn artifacts show how many duplicates were dropped.
            try:
                accepted[0].assembly_notes = list(accepted[0].assembly_notes or []) + [
                    f"diversity_pass: dropped {dropped_count} duplicate candidate(s) "
                    "that would have re-used an already-accepted non-anchor product"
                ]
            except Exception:  # noqa: BLE001
                pass
        return accepted

    def _assemble_complete(
        self, direction_id: str, sets: List[RetrievedSet], combined_context: CombinedContext | None = None,
    ) -> List[OutfitCandidate]:
        """Each complete product becomes one candidate."""
        coefs = _resolve_bias(combined_context)
        candidates: List[OutfitCandidate] = []
        for rs in sets:
            if rs.role != "complete":
                continue
            for product in rs.products:
                score = product.similarity
                notes: List[str] = []
                if combined_context is not None:
                    adj, adj_notes = _followup_complete_adjustment(product, combined_context)
                    score = max(score - adj, 0.01)
                    notes.extend(adj_notes)
                bias_delta, bias_notes = _apply_bias_bonus([product], coefs)
                if bias_delta or bias_notes:
                    score = max(score - bias_delta, 0.01)
                    notes.extend(bias_notes)
                candidates.append(
                    OutfitCandidate(
                        candidate_id=str(uuid4())[:8],
                        direction_id=direction_id,
                        candidate_type="complete",
                        items=[self._product_to_item(product)],
                        assembly_score=score,
                        assembly_notes=notes,
                    )
                )
        return candidates

    def _assemble_paired(
        self, direction_id: str, sets: List[RetrievedSet], combined_context: CombinedContext | None = None,
    ) -> List[OutfitCandidate]:
        """Combine top + bottom products with compatibility pruning."""
        coefs = _resolve_bias(combined_context)
        tops: List[RetrievedProduct] = []
        bottoms: List[RetrievedProduct] = []
        for rs in sets:
            if rs.role == "top":
                tops.extend(p for p in rs.products if _is_valid_for_role(p, "top"))
            elif rs.role == "bottom":
                bottoms.extend(p for p in rs.products if _is_valid_for_role(p, "bottom"))

        if not tops or not bottoms:
            return []

        # Limit inputs to avoid combinatorial explosion
        tops = tops[:15]
        bottoms = bottoms[:15]

        scored_pairs: List[Tuple[float, List[str], RetrievedProduct, RetrievedProduct]] = []
        for top in tops:
            for bottom in bottoms:
                score, notes = self._evaluate_pair(top, bottom, combined_context)
                if score > 0:
                    bias_delta, bias_notes = _apply_bias_bonus([top, bottom], coefs)
                    if bias_delta or bias_notes:
                        score = max(score - bias_delta, 0.01)
                        notes = notes + bias_notes
                    scored_pairs.append((score, notes, top, bottom))

        # Sort by score descending, cap at MAX_PAIRED_CANDIDATES
        scored_pairs.sort(key=lambda x: x[0], reverse=True)
        scored_pairs = scored_pairs[:MAX_PAIRED_CANDIDATES]

        candidates: List[OutfitCandidate] = []
        for score, notes, top, bottom in scored_pairs:
            candidates.append(
                OutfitCandidate(
                    candidate_id=str(uuid4())[:8],
                    direction_id=direction_id,
                    candidate_type="paired",
                    items=[
                        self._product_to_item(top, role="top"),
                        self._product_to_item(bottom, role="bottom"),
                    ],
                    assembly_score=score,
                    assembly_notes=notes,
                )
            )
        return candidates

    def _assemble_three_piece(
        self, direction_id: str, sets: List[RetrievedSet], combined_context: CombinedContext | None = None,
    ) -> List[OutfitCandidate]:
        """Combine top + bottom + outerwear products."""
        coefs = _resolve_bias(combined_context)
        tops: List[RetrievedProduct] = []
        bottoms: List[RetrievedProduct] = []
        outerwear: List[RetrievedProduct] = []
        for rs in sets:
            if rs.role == "top":
                tops.extend(p for p in rs.products if _is_valid_for_role(p, "top"))
            elif rs.role == "bottom":
                bottoms.extend(p for p in rs.products if _is_valid_for_role(p, "bottom"))
            elif rs.role == "outerwear":
                outerwear.extend(p for p in rs.products if _is_valid_for_role(p, "outerwear"))

        if not tops or not bottoms or not outerwear:
            # Fall back to paired assembly if outerwear is missing
            if tops and bottoms:
                return self._assemble_paired(direction_id, sets, combined_context)
            return []

        # Cap inputs to avoid combinatorial explosion
        tops = tops[:10]
        bottoms = bottoms[:10]
        outerwear = outerwear[:10]

        scored: List[Tuple[float, List[str], RetrievedProduct, RetrievedProduct, RetrievedProduct]] = []
        for top in tops:
            for bottom in bottoms:
                # Skip if same product in both roles
                if top.product_id == bottom.product_id:
                    continue
                pair_score, pair_notes = self._evaluate_pair(top, bottom, combined_context)
                if pair_score <= 0:
                    continue
                for outer in outerwear:
                    # Skip if outerwear duplicates top or bottom
                    if outer.product_id in (top.product_id, bottom.product_id):
                        continue
                    outer_score, outer_notes = self._evaluate_pair(top, outer, combined_context)
                    if outer_score <= 0:
                        continue
                    # Three-piece score: weighted average of pair + outerwear coherence
                    total_score = (pair_score * 0.6) + (outer_score * 0.4)
                    notes = pair_notes + outer_notes
                    bias_delta, bias_notes = _apply_bias_bonus(
                        [top, bottom, outer], coefs,
                    )
                    if bias_delta or bias_notes:
                        total_score = max(total_score - bias_delta, 0.01)
                        notes = notes + bias_notes
                    scored.append((total_score, notes, top, bottom, outer))

        scored.sort(key=lambda x: x[0], reverse=True)
        scored = scored[:MAX_PAIRED_CANDIDATES]

        candidates: List[OutfitCandidate] = []
        for score, notes, top, bottom, outer in scored:
            candidates.append(
                OutfitCandidate(
                    candidate_id=str(uuid4())[:8],
                    direction_id=direction_id,
                    candidate_type="three_piece",
                    items=[
                        self._product_to_item(top, role="top"),
                        self._product_to_item(bottom, role="bottom"),
                        self._product_to_item(outer, role="outerwear"),
                    ],
                    assembly_score=score,
                    assembly_notes=notes,
                )
            )
        return candidates

    def _evaluate_pair(
        self, top: RetrievedProduct, bottom: RetrievedProduct,
        combined_context: CombinedContext | None = None,
    ) -> Tuple[float, List[str]]:
        """Score a top+bottom pair. Returns (score, notes). Score 0 means rejected."""
        base_score = (top.similarity + bottom.similarity) / 2.0
        penalty = 0.0
        notes: List[str] = []

        # ranking_bias coefficients shape penalty weights and unlock the
        # bias-bonus pass at the bottom of this method.
        coefs = _resolve_bias(combined_context)

        # Formality compatibility (soft penalty, not hard rejection)
        top_form = _get_attr(top, "formality_level") or _get_attr(top, "FormalityLevel")
        bot_form = _get_attr(bottom, "formality_level") or _get_attr(bottom, "FormalityLevel")
        ok, note = _formality_compatible(top_form, bot_form)
        if note:
            penalty += 0.20 * coefs["form_pen"]
            notes.append(note)

        # Occasion compatibility (soft penalty, not hard rejection)
        top_occ = _get_attr(top, "occasion_fit") or _get_attr(top, "OccasionFit")
        bot_occ = _get_attr(bottom, "occasion_fit") or _get_attr(bottom, "OccasionFit")
        ok, note = _occasion_compatible(top_occ, bot_occ)
        if note:
            penalty += 0.15 * coefs["occ_pen"]
            notes.append(note)

        # Color temperature
        top_temp = _get_attr(top, "color_temperature") or _get_attr(top, "ColorTemperature")
        bot_temp = _get_attr(bottom, "color_temperature") or _get_attr(bottom, "ColorTemperature")
        ok, note = _color_temp_compatible(top_temp, bot_temp)
        if not ok:
            penalty += 0.15
            notes.append(note)
        if note and ok:
            notes.append(note)

        # Pattern
        top_pat = _get_attr(top, "pattern_type") or _get_attr(top, "PatternType")
        bot_pat = _get_attr(bottom, "pattern_type") or _get_attr(bottom, "PatternType")
        ok, note = _pattern_compatible(top_pat, bot_pat)
        if note:
            penalty += 0.05 * coefs["pat_pen"]
            notes.append(note)

        # Volume (soft penalty, not hard rejection)
        top_vol = _get_attr(top, "volume_profile") or _get_attr(top, "VolumeProfile")
        bot_vol = _get_attr(bottom, "volume_profile") or _get_attr(bottom, "VolumeProfile")
        ok, note = _volume_compatible(top_vol, bot_vol)
        if note:
            penalty += 0.25 * coefs["vol_pen"]
            notes.append(note)

        # Fit coherence — relaxed bottom with structured/regular top is a mismatch
        # for anything at or above smart-casual formality.
        top_fit = _get_attr(top, "fit_type") or _get_attr(top, "FitType")
        bot_fit = _get_attr(bottom, "fit_type") or _get_attr(bottom, "FitType")
        if top_fit and bot_fit:
            structured_top = top_fit in ("regular", "tailored", "slim")
            relaxed_bottom = bot_fit == "relaxed"
            if structured_top and relaxed_bottom:
                semi_formal_or_above = top_form in (
                    "smart_casual", "business_casual", "semi_formal", "formal", "ultra_formal",
                )
                if semi_formal_or_above:
                    penalty += 0.12
                    notes.append(f"fit mismatch: {top_fit} top with {bot_fit} bottom at {top_form}")

        # Texture compatibility — mismatched textures weaken outfit cohesion.
        top_tex = _get_attr(top, "fabric_texture") or _get_attr(top, "FabricTexture")
        bot_tex = _get_attr(bottom, "fabric_texture") or _get_attr(bottom, "FabricTexture")
        if top_tex and bot_tex and top_tex != bot_tex:
            clash = {top_tex, bot_tex}
            if "textured" in clash and clash & {"smooth", "matte"}:
                penalty += 0.08
                notes.append(f"texture clash: {top_tex} top with {bot_tex} bottom")

        # Follow-up intent scoring adjustments
        if combined_context is not None:
            fu_adj, fu_notes = _followup_pair_adjustment(top, bottom, combined_context)
            penalty += fu_adj
            notes.extend(fu_notes)

        # NOTE: bias bonus is NOT applied here. It's applied once per
        # candidate at the assembly-method level (`_assemble_paired`,
        # `_assemble_complete`, `_assemble_three_piece`) so three-piece
        # candidates don't double-count when this method is called twice
        # (top+bottom and top+outer).

        return max(base_score - penalty, 0.01), notes

    @staticmethod
    def _product_to_item(product: RetrievedProduct, role: str = "") -> Dict[str, Any]:
        metadata = product.metadata
        # Catalog rows expose image URLs at images__0__src / primary_image_url.
        # Wardrobe rows leave image_url empty and store the file under
        # image_path (relative to the repo root, e.g. "data/onboarding/...").
        # The visual-eval try-on render path skips items whose image_url is
        # empty, so a wardrobe-anchor would silently drop out and Gemini
        # would only see the catalog half of the outfit. Resolve from either
        # source so wardrobe-anchored pairings include the user's actual
        # garment in the render.
        image_url = str(
            metadata.get("images__0__src")
            or metadata.get("images_0_src")
            or product.enriched_data.get("images__0__src")
            or product.enriched_data.get("images_0_src")
            or product.enriched_data.get("primary_image_url")
            or product.enriched_data.get("image_url")
            or product.enriched_data.get("image_path")
            or ""
        )
        title = str(
            metadata.get("title")
            or product.enriched_data.get("title")
            or product.product_id
            or ""
        )
        price = str(
            metadata.get("price")
            or product.enriched_data.get("price")
            or ""
        )
        product_url = resolve_product_url(
            raw_url=str(
                metadata.get("url")
                or product.enriched_data.get("url")
                or product.enriched_data.get("product_url")
                or ""
            ),
            store=str(
                product.enriched_data.get("store")
                or metadata.get("store")
                or ""
            ),
            handle=str(
                product.enriched_data.get("handle")
                or metadata.get("handle")
                or ""
            ),
            image_url=image_url,
        )
        item: Dict[str, Any] = {
            "product_id": product.product_id,
            "similarity": product.similarity,
            "title": title,
            "image_url": image_url,
            "price": price,
            "product_url": product_url,
            "garment_category": str(
                product.enriched_data.get("garment_category")
                or metadata.get("GarmentCategory") or ""
            ),
            "garment_subtype": str(
                product.enriched_data.get("garment_subtype")
                or metadata.get("GarmentSubtype") or ""
            ),
            "styling_completeness": str(
                product.enriched_data.get("styling_completeness")
                or metadata.get("StylingCompleteness") or ""
            ),
            "primary_color": str(
                product.enriched_data.get("primary_color")
                or metadata.get("PrimaryColor") or ""
            ),
            "formality_level": str(
                product.enriched_data.get("formality_level")
                or metadata.get("FormalityLevel") or ""
            ),
            "occasion_fit": str(
                product.enriched_data.get("occasion_fit")
                or metadata.get("OccasionFit") or ""
            ),
            "pattern_type": str(
                product.enriched_data.get("pattern_type")
                or metadata.get("PatternType") or ""
            ),
            "volume_profile": str(
                product.enriched_data.get("volume_profile")
                or metadata.get("VolumeProfile") or ""
            ),
            "fit_type": str(
                product.enriched_data.get("fit_type")
                or metadata.get("FitType") or ""
            ),
            "silhouette_type": str(
                product.enriched_data.get("silhouette_type")
                or metadata.get("SilhouetteType") or ""
            ),
        }
        # Tag wardrobe-shaped items with source="wardrobe" so the
        # try-on render path's _detect_garment_source can label the
        # outfit correctly (wardrobe / catalog / mixed) instead of
        # falling through to the catalog default. Detection: a wardrobe
        # row carries image_path but lacks the catalog identifiers
        # (handle/store). The orchestrator's anchor injection passes
        # the wardrobe row dict straight into enriched_data, so this
        # detection runs there too.
        explicit_source = str(product.enriched_data.get("source") or "").strip().lower()
        if explicit_source in ("wardrobe", "catalog"):
            item["source"] = explicit_source
        elif product.enriched_data.get("image_path") and not (
            product.enriched_data.get("handle") or product.enriched_data.get("store")
        ):
            item["source"] = "wardrobe"
        # Phase 12D: propagate the is_anchor flag from enriched_data so the
        # cross-outfit diversity pass can exempt anchor products from the
        # "no repeats across outfits" rule. The orchestrator sets this on
        # the synthetic anchor RetrievedProduct it injects for pairing
        # requests; the anchor MUST appear in all paired candidates by
        # definition.
        if product.enriched_data.get("is_anchor"):
            item["is_anchor"] = True
        if role:
            item["role"] = role
        return item
