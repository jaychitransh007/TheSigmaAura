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

# Cross-outfit diversity cap: a single product_id may appear in at most this
# many of the assembled candidates. Prevents one top-scoring item from filling
# every recommendation slot when the user explicitly wants variety.
MAX_PRODUCT_REPEAT_PER_RUN = 2


def _get_attr(product: RetrievedProduct, key: str) -> str:
    """Get a normalized attribute from enriched data or metadata."""
    val = str(
        product.enriched_data.get(key)
        or product.metadata.get(key)
        or ""
    ).strip().lower()
    return val


def _formality_compatible(a: str, b: str) -> Tuple[bool, str]:
    allowed = _FORMALITY_COMPAT.get(a)
    if allowed is None:
        return True, ""
    if b in allowed:
        return True, ""
    return False, f"formality mismatch: {a} vs {b}"


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
    if not a or not b:
        return True, ""
    if a == b:
        return True, ""
    return False, f"occasion mismatch: {a} vs {b}"


def _pattern_compatible(a: str, b: str) -> Tuple[bool, str]:
    if not a or not b:
        return True, ""
    if a == "solid" or b == "solid":
        return True, ""
    # Both patterned: penalize but don't reject
    return True, "double pattern — consider if scales differ"


def _volume_compatible(a: str, b: str) -> Tuple[bool, str]:
    if a == "oversized" and b == "oversized":
        return False, "extreme volume conflict: both oversized"
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

        candidates = self._enforce_cross_outfit_diversity(candidates)
        return candidates

    @staticmethod
    def _enforce_cross_outfit_diversity(
        candidates: List[OutfitCandidate],
    ) -> List[OutfitCandidate]:
        """Cap product_id repetition across the candidate list.

        Walks candidates in score order and accepts each only if no item in it
        has already appeared in MAX_PRODUCT_REPEAT_PER_RUN previously-accepted
        candidates. Rejected candidates are appended at the tail in their
        original order so the assembler still returns at least the same count
        when no diverse alternative exists.
        """
        if not candidates:
            return candidates
        ordered = sorted(
            candidates,
            key=lambda c: float(getattr(c, "assembly_score", 0.0) or 0.0),
            reverse=True,
        )
        usage: Dict[str, int] = {}
        accepted: List[OutfitCandidate] = []
        deferred: List[OutfitCandidate] = []
        for candidate in ordered:
            item_ids = [
                str(item.get("product_id") or "").strip()
                for item in (candidate.items or [])
            ]
            item_ids = [pid for pid in item_ids if pid]
            if any(usage.get(pid, 0) >= MAX_PRODUCT_REPEAT_PER_RUN for pid in item_ids):
                deferred.append(candidate)
                continue
            for pid in item_ids:
                usage[pid] = usage.get(pid, 0) + 1
            note = f"diversity: accepted (product usage so far: {{', '.join(item_ids)}})"
            try:
                candidate.assembly_notes = list(candidate.assembly_notes or []) + [
                    "diversity_pass: accepted under product-repetition cap "
                    f"({MAX_PRODUCT_REPEAT_PER_RUN}/run)"
                ]
            except Exception:  # noqa: BLE001 — defensive on pydantic model attrs
                pass
            accepted.append(candidate)
        for candidate in deferred:
            try:
                candidate.assembly_notes = list(candidate.assembly_notes or []) + [
                    "diversity_pass: deferred — product appeared too many times"
                ]
            except Exception:  # noqa: BLE001
                pass
        return accepted + deferred

    def _assemble_complete(
        self, direction_id: str, sets: List[RetrievedSet], combined_context: CombinedContext | None = None,
    ) -> List[OutfitCandidate]:
        """Each complete product becomes one candidate."""
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
        tops: List[RetrievedProduct] = []
        bottoms: List[RetrievedProduct] = []
        for rs in sets:
            if rs.role == "top":
                tops.extend(rs.products)
            elif rs.role == "bottom":
                bottoms.extend(rs.products)

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

    def _evaluate_pair(
        self, top: RetrievedProduct, bottom: RetrievedProduct,
        combined_context: CombinedContext | None = None,
    ) -> Tuple[float, List[str]]:
        """Score a top+bottom pair. Returns (score, notes). Score 0 means rejected."""
        base_score = (top.similarity + bottom.similarity) / 2.0
        penalty = 0.0
        notes: List[str] = []

        # Formality compatibility
        top_form = _get_attr(top, "formality_level") or _get_attr(top, "FormalityLevel")
        bot_form = _get_attr(bottom, "formality_level") or _get_attr(bottom, "FormalityLevel")
        ok, note = _formality_compatible(top_form, bot_form)
        if not ok:
            return 0.0, [note]
        if note:
            notes.append(note)

        # Occasion compatibility
        top_occ = _get_attr(top, "occasion_fit") or _get_attr(top, "OccasionFit")
        bot_occ = _get_attr(bottom, "occasion_fit") or _get_attr(bottom, "OccasionFit")
        ok, note = _occasion_compatible(top_occ, bot_occ)
        if not ok:
            return 0.0, [note]
        if note:
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
            penalty += 0.05
            notes.append(note)

        # Volume
        top_vol = _get_attr(top, "volume_profile") or _get_attr(top, "VolumeProfile")
        bot_vol = _get_attr(bottom, "volume_profile") or _get_attr(bottom, "VolumeProfile")
        ok, note = _volume_compatible(top_vol, bot_vol)
        if not ok:
            return 0.0, [note]

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

        return max(base_score - penalty, 0.01), notes

    @staticmethod
    def _product_to_item(product: RetrievedProduct, role: str = "") -> Dict[str, Any]:
        metadata = product.metadata
        image_url = str(
            metadata.get("images__0__src")
            or metadata.get("images_0_src")
            or product.enriched_data.get("images__0__src")
            or product.enriched_data.get("images_0_src")
            or product.enriched_data.get("primary_image_url")
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
        if role:
            item["role"] = role
        return item
