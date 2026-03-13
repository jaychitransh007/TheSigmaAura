from __future__ import annotations

from typing import Any, Dict, List, Tuple
from uuid import uuid4

from ..schemas import (
    CombinedContext,
    OutfitCandidate,
    RecommendationPlan,
    RetrievedProduct,
    RetrievedSet,
)
from ..product_links import resolve_product_url


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
                    self._assemble_complete(direction.direction_id, direction_sets)
                )
            elif direction.direction_type == "paired":
                candidates.extend(
                    self._assemble_paired(direction.direction_id, direction_sets)
                )

        return candidates

    def _assemble_complete(
        self, direction_id: str, sets: List[RetrievedSet]
    ) -> List[OutfitCandidate]:
        """Each complete product becomes one candidate."""
        candidates: List[OutfitCandidate] = []
        for rs in sets:
            if rs.role != "complete":
                continue
            for product in rs.products:
                candidates.append(
                    OutfitCandidate(
                        candidate_id=str(uuid4())[:8],
                        direction_id=direction_id,
                        candidate_type="complete",
                        items=[self._product_to_item(product)],
                        assembly_score=product.similarity,
                        assembly_notes=[],
                    )
                )
        return candidates

    def _assemble_paired(
        self, direction_id: str, sets: List[RetrievedSet]
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
                score, notes = self._evaluate_pair(top, bottom)
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
        self, top: RetrievedProduct, bottom: RetrievedProduct
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
