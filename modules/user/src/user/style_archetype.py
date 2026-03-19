import csv
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional


ARCHETYPE_ORDER = [
    "classic",
    "dramatic",
    "romantic",
    "natural",
    "minimalist",
    "creative",
    "sporty",
    "edgy",
]

ARCHETYPE_ADJACENCY = {
    "classic": {"near": "minimalist", "far": "dramatic", "third": "natural"},
    "minimalist": {"near": "classic", "far": "edgy", "third": "sporty"},
    "romantic": {"near": "natural", "far": "creative", "third": "classic"},
    "natural": {"near": "romantic", "far": "sporty", "third": "classic"},
    "creative": {"near": "romantic", "far": "edgy", "third": "dramatic"},
    "edgy": {"near": "minimalist", "far": "creative", "third": "dramatic"},
    "dramatic": {"near": "classic", "far": "creative", "third": "edgy"},
    "sporty": {"near": "natural", "far": "minimalist", "third": "edgy"},
}

SELECTION_LIMIT_MIN = 3
SELECTION_LIMIT_MAX = 5
STYLE_ARCHETYPE_FILENAME_RE = re.compile(r"^[A-Z]\d+\.png$")


@dataclass(frozen=True)
class ArchetypeImage:
    id: str
    gender: str
    primary_archetype: str
    secondary_archetype: Optional[str]
    image_type: str
    intensity: str
    context: str
    image_url: str

    def as_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "gender": self.gender,
            "primaryArchetype": self.primary_archetype,
            "secondaryArchetype": self.secondary_archetype,
            "imageType": self.image_type,
            "intensity": self.intensity,
            "context": self.context,
            "imageUrl": self.image_url,
        }


def _repo_root() -> Path:
    here = Path(__file__).resolve()
    for base in [here.parent] + list(here.parents):
        if (base / "archetypes" / "style_archetype_image_prompts.csv").exists():
            return base
    raise FileNotFoundError("Could not locate archetypes/style_archetype_image_prompts.csv")


def _normalize_value(value: str) -> str:
    raw = (value or "").strip()
    if raw in {"—", "-", ""}:
        return ""
    return raw.lower().replace(" ", "_")


def style_asset_public_path(image_id: str) -> str:
    return f"/v1/onboarding/style-assets/choices/{image_id}.png"


def resolve_style_asset_file(filename: str) -> Optional[Path]:
    normalized = str(filename or "").strip()
    if not STYLE_ARCHETYPE_FILENAME_RE.fullmatch(normalized):
        return None
    path = _repo_root() / "archetypes" / "choices" / normalized
    if not path.exists():
        return None
    return path


@lru_cache(maxsize=1)
def load_style_archetype_pool() -> List[ArchetypeImage]:
    csv_path = _repo_root() / "archetypes" / "style_archetype_image_prompts.csv"
    images_dir = _repo_root() / "archetypes" / "choices"
    rows: List[ArchetypeImage] = []
    with csv_path.open("r", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            image_id = (row.get("ID") or "").strip()
            if not re.match(r"^[A-Z]\d+$", image_id):
                continue
            primary = _normalize_value(row.get("Archetype") or "")
            if primary not in ARCHETYPE_ORDER:
                continue
            image = ArchetypeImage(
                id=image_id,
                gender=_normalize_value(row.get("Gender") or ""),
                primary_archetype=primary,
                secondary_archetype=_normalize_value(row.get("Secondary") or "") or None,
                image_type=_normalize_value(row.get("Image Type") or ""),
                intensity=_normalize_value(row.get("Intensity") or ""),
                context=_normalize_value(row.get("Context") or ""),
                image_url=style_asset_public_path(image_id),
            )
            if not (images_dir / f"{image_id}.png").exists():
                continue
            rows.append(image)
    return rows


def images_for_gender(gender: str) -> List[ArchetypeImage]:
    normalized = "female" if gender == "female" else "male"
    return [image for image in load_style_archetype_pool() if image.gender == normalized]


def initial_layer_images(gender: str) -> List[Dict[str, Any]]:
    pool = images_for_gender(gender)
    selected: List[Dict[str, Any]] = []
    for archetype in ARCHETYPE_ORDER:
        image = find_image(
            pool,
            exclude_ids=set(),
            primary_archetype=archetype,
            secondary_archetype=None,
            image_type="pure",
            intensity="moderate",
        )
        if image is not None:
            selected.append(image.as_dict())
    return selected


def find_image(
    pool: List[ArchetypeImage],
    *,
    exclude_ids: set[str],
    primary_archetype: Optional[str] = None,
    secondary_archetype: Optional[str] = None,
    image_type: Optional[str] = None,
    intensity: Optional[str] = None,
    context: Optional[str] = None,
) -> Optional[ArchetypeImage]:
    for image in pool:
        if image.id in exclude_ids:
            continue
        if primary_archetype is not None and image.primary_archetype != primary_archetype:
            continue
        if secondary_archetype is not None and image.secondary_archetype != secondary_archetype:
            continue
        if secondary_archetype is None and image.secondary_archetype is not None:
            continue
        if image_type is not None and image.image_type != image_type:
            continue
        if intensity is not None and image.intensity != intensity:
            continue
        if context is not None and image.context != context:
            continue
        return image
    return None


def find_blend_image(pool: List[ArchetypeImage], arch1: str, arch2: str, exclude_ids: set[str]) -> Optional[ArchetypeImage]:
    return (
        find_image(pool, exclude_ids=exclude_ids, primary_archetype=arch1, secondary_archetype=arch2, image_type="blend")
        or find_image(pool, exclude_ids=exclude_ids, primary_archetype=arch2, secondary_archetype=arch1, image_type="blend")
    )


def _fill_fallback(pool: List[ArchetypeImage], exclude_ids: set[str], preferred: List[Dict[str, Optional[str]]]) -> ArchetypeImage:
    for query in preferred:
        image = find_image(
            pool,
            exclude_ids=exclude_ids,
            primary_archetype=query.get("primary_archetype"),
            secondary_archetype=query.get("secondary_archetype"),
            image_type=query.get("image_type"),
            intensity=query.get("intensity"),
            context=query.get("context"),
        )
        if image is not None:
            return image
    for image in pool:
        if image.id not in exclude_ids:
            return image
    raise ValueError("No available style archetype images remain.")


def generate_layer2(pool: List[ArchetypeImage], trigger: ArchetypeImage, exclude_ids: set[str]) -> List[Dict[str, Any]]:
    neighbors = ARCHETYPE_ADJACENCY[trigger.primary_archetype]
    candidates = [
        find_image(pool, exclude_ids=exclude_ids, primary_archetype=trigger.primary_archetype, secondary_archetype=None, image_type="pure", intensity="bold"),
        find_blend_image(pool, trigger.primary_archetype, neighbors["near"], exclude_ids),
        find_blend_image(pool, trigger.primary_archetype, neighbors["far"], exclude_ids),
        find_image(pool, exclude_ids=exclude_ids, primary_archetype=trigger.primary_archetype, secondary_archetype=None, image_type="pure", intensity="restrained"),
    ]
    results: List[Dict[str, Any]] = []
    used_ids = set(exclude_ids)
    for idx, candidate in enumerate(candidates, start=1):
        image = candidate or _fill_fallback(
            pool,
            used_ids,
            [
                {"primary_archetype": trigger.primary_archetype, "secondary_archetype": None, "image_type": "pure", "intensity": "moderate"},
                {"primary_archetype": trigger.primary_archetype, "secondary_archetype": None, "image_type": "context", "context": "casual"},
                {"primary_archetype": trigger.primary_archetype, "secondary_archetype": neighbors["third"], "image_type": "blend"},
                {"primary_archetype": neighbors["near"], "secondary_archetype": None, "image_type": "pure", "intensity": "moderate"},
            ],
        )
        used_ids.add(image.id)
        payload = image.as_dict()
        payload["position"] = idx
        results.append(payload)
    return results


def generate_layer3(
    pool: List[ArchetypeImage],
    base_trigger: ArchetypeImage,
    trigger2: Dict[str, Any],
    exclude_ids: set[str],
) -> List[Dict[str, Any]]:
    base = base_trigger.primary_archetype
    neighbors = ARCHETYPE_ADJACENCY[base]
    position = int(trigger2.get("position") or 0)
    trigger2_secondary = trigger2.get("secondaryArchetype") or trigger2.get("primaryArchetype")

    if position == 1:
        candidate_queries = [
            {"primary_archetype": base, "secondary_archetype": None, "image_type": "context", "context": "casual"},
            {"primary_archetype": base, "secondary_archetype": None, "image_type": "context", "context": "elevated"},
            {"primary_archetype": base, "secondary_archetype": neighbors["third"], "image_type": "blend"},
            {"primary_archetype": neighbors["near"], "secondary_archetype": None, "image_type": "pure", "intensity": "moderate"},
        ]
    elif position == 2:
        blend_arch = str(trigger2_secondary)
        blend_neighbors = ARCHETYPE_ADJACENCY[blend_arch]
        candidate_queries = [
            {"primary_archetype": blend_arch, "secondary_archetype": None, "image_type": "pure", "intensity": "moderate"},
            {"primary_archetype": blend_arch, "secondary_archetype": None, "image_type": "pure", "intensity": "bold"},
            {"primary_archetype": base, "secondary_archetype": None, "image_type": "context", "context": "casual"},
            {"primary_archetype": blend_arch, "secondary_archetype": blend_neighbors["near"], "image_type": "blend"},
        ]
    elif position == 3:
        far_arch = str(trigger2_secondary)
        candidate_queries = [
            {"primary_archetype": far_arch, "secondary_archetype": None, "image_type": "pure", "intensity": "moderate"},
            {"primary_archetype": far_arch, "secondary_archetype": None, "image_type": "pure", "intensity": "restrained"},
            {"primary_archetype": base, "secondary_archetype": None, "image_type": "context", "context": "elevated"},
            {"primary_archetype": far_arch, "secondary_archetype": ARCHETYPE_ADJACENCY[far_arch]["near"], "image_type": "blend"},
        ]
    else:
        candidate_queries = [
            {"primary_archetype": base, "secondary_archetype": None, "image_type": "context", "context": "casual"},
            {"primary_archetype": neighbors["near"], "secondary_archetype": None, "image_type": "pure", "intensity": "restrained"},
            {"primary_archetype": neighbors["far"], "secondary_archetype": None, "image_type": "pure", "intensity": "restrained"},
            {"primary_archetype": base, "secondary_archetype": None, "image_type": "context", "context": "elevated"},
        ]

    results: List[Dict[str, Any]] = []
    used_ids = set(exclude_ids)
    for idx, query in enumerate(candidate_queries, start=1):
        image = (
            find_blend_image(pool, str(query["primary_archetype"]), str(query["secondary_archetype"]), used_ids)
            if query.get("image_type") == "blend" and query.get("secondary_archetype")
            else find_image(
                pool,
                exclude_ids=used_ids,
                primary_archetype=query.get("primary_archetype"),
                secondary_archetype=query.get("secondary_archetype"),
                image_type=query.get("image_type"),
                intensity=query.get("intensity"),
                context=query.get("context"),
            )
        )
        image = image or _fill_fallback(
            pool,
            used_ids,
            [
                query,
                {"primary_archetype": base, "secondary_archetype": None, "image_type": "context", "context": "casual"},
                {"primary_archetype": base, "secondary_archetype": None, "image_type": "context", "context": "elevated"},
                {"primary_archetype": neighbors["third"], "secondary_archetype": None, "image_type": "pure", "intensity": "moderate"},
            ],
        )
        used_ids.add(image.id)
        payload = image.as_dict()
        payload["position"] = idx
        results.append(payload)
    return results


def selection_session(gender: str) -> Dict[str, Any]:
    layer1 = initial_layer_images(gender)
    pool = [image.as_dict() for image in images_for_gender(gender)]
    return {
        "gender": "female" if gender == "female" else "male",
        "layer1": layer1,
        "pool": pool,
        "adjacency": ARCHETYPE_ADJACENCY,
        "minSelections": SELECTION_LIMIT_MIN,
        "maxSelections": SELECTION_LIMIT_MAX,
    }


def interpret_style_preference(gender: str, shown_images: List[Dict[str, Any]], selections: List[Dict[str, Any]]) -> Dict[str, Any]:
    if len(selections) < SELECTION_LIMIT_MIN or len(selections) > SELECTION_LIMIT_MAX:
        raise ValueError("Select between 3 and 5 images.")

    scores = {key: 0.0 for key in ARCHETYPE_ORDER}
    selected_ids: List[str] = []
    selected_images: Dict[str, str] = {}
    for selection in selections:
        image = selection["image"]
        selected_ids.append(str(image["id"]))
        selected_images[str(selection["selectionOrder"])] = f"{image['id']}.png"
        scores[str(image["primaryArchetype"])] += 1.0
        if image.get("secondaryArchetype"):
            scores[str(image["secondaryArchetype"])] += 0.5

    ordered = sorted(scores.items(), key=lambda item: (-item[1], ARCHETYPE_ORDER.index(item[0])))
    primary, primary_score = ordered[0]
    secondary = None
    secondary_score = 0.0
    if len(ordered) > 1 and ordered[1][1] >= primary_score * 0.3:
        secondary, secondary_score = ordered[1]

    if secondary:
        total = primary_score + secondary_score
        blend_ratio = {
            "primary": round(primary_score / total * 100),
            "secondary": round(secondary_score / total * 100),
        }
    else:
        blend_ratio = {"primary": 100, "secondary": 0}

    risk_tolerance = _determine_risk_tolerance(selections)
    formality_lean = _determine_formality_lean(selections)
    comfort_boundaries = _determine_comfort_boundaries(selections, shown_images)
    pattern_type = _classify_pattern(selections, secondary, blend_ratio)

    return {
        "primaryArchetype": primary,
        "secondaryArchetype": secondary,
        "blendRatio": blend_ratio,
        "riskTolerance": risk_tolerance,
        "formalityLean": formality_lean,
        "patternType": pattern_type,
        "comfortBoundaries": comfort_boundaries,
        "archetypeScores": scores,
        "selectedImageIds": selected_ids,
        "selectedImages": selected_images,
        "gender": gender,
        "completedAt": datetime.now(timezone.utc).isoformat(),
        "selectionCount": len(selections),
    }


def _determine_risk_tolerance(selections: List[Dict[str, Any]]) -> str:
    intensity_scores = {"restrained": 0, "moderate": 0, "bold": 0}
    touched = set()
    bridge_far = False
    for selection in selections:
        image = selection["image"]
        intensity_scores[str(image["intensity"])] += 1
        touched.add(str(image["primaryArchetype"]))
        if image.get("secondaryArchetype"):
            touched.add(str(image["secondaryArchetype"]))
        if int(selection.get("layer") or 0) >= 2 and int(selection.get("position") or 0) == 3:
            bridge_far = True
    risk_score = intensity_scores["bold"] * 2 + intensity_scores["moderate"]
    if bridge_far:
        risk_score += 1
    if len(touched) >= 4:
        risk_score += 2
    elif len(touched) >= 3:
        risk_score += 1
    max_possible = (len(selections) * 2) + 3
    normalized = round((risk_score / max_possible) * 4) + 1
    if normalized <= 1:
        return "conservative"
    if normalized <= 2:
        return "moderate-conservative"
    if normalized <= 3:
        return "moderate"
    if normalized <= 4:
        return "moderate-adventurous"
    return "adventurous"


def _determine_formality_lean(selections: List[Dict[str, Any]]) -> str:
    casual = 0.0
    elevated = 0.0
    neutral = 0.0
    for selection in selections:
        image = selection["image"]
        if image["context"] == "casual":
            casual += 1
        elif image["context"] == "elevated":
            elevated += 1
        else:
            neutral += 1
        if image["intensity"] == "restrained":
            casual += 0.5
        if image["intensity"] == "bold":
            elevated += 0.5
    total = casual + elevated + neutral
    if total == 0:
        return "balanced"
    if casual / total > 0.6:
        return "casual-leaning"
    if elevated / total > 0.6:
        return "elevated-leaning"
    return "balanced"


def _determine_comfort_boundaries(selections: List[Dict[str, Any]], shown_images: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    selected_ids = {str(selection["image"]["id"]) for selection in selections}
    shown_by_arch: Dict[str, int] = {key: 0 for key in ARCHETYPE_ORDER}
    selected_by_arch: Dict[str, int] = {key: 0 for key in ARCHETYPE_ORDER}
    shown_bold = 0
    selected_bold = 0
    shown_restrained = 0
    selected_restrained = 0
    for image in shown_images:
        primary = str(image["primaryArchetype"])
        shown_by_arch[primary] += 1
        if image["intensity"] == "bold":
            shown_bold += 1
        if image["intensity"] == "restrained":
            shown_restrained += 1
        if str(image["id"]) in selected_ids:
            selected_by_arch[primary] += 1
            if image["intensity"] == "bold":
                selected_bold += 1
            if image["intensity"] == "restrained":
                selected_restrained += 1
    boundaries: List[Dict[str, str]] = []
    for archetype, shown_count in shown_by_arch.items():
        if shown_count >= 2 and selected_by_arch[archetype] == 0:
            boundaries.append({"type": "archetype_aversion", "value": archetype, "confidence": "high"})
    if shown_bold >= 2 and selected_bold == 0:
        boundaries.append({"type": "intensity_ceiling", "value": "avoids_bold", "confidence": "high"})
    if shown_restrained >= 2 and selected_restrained == 0:
        boundaries.append({"type": "intensity_floor", "value": "avoids_restrained", "confidence": "high"})
    return boundaries


def _classify_pattern(selections: List[Dict[str, Any]], secondary: Optional[str], blend_ratio: Dict[str, int]) -> str:
    touched = set()
    for selection in selections:
        image = selection["image"]
        touched.add(str(image["primaryArchetype"]))
        if image.get("secondaryArchetype"):
            touched.add(str(image["secondaryArchetype"]))
    if len(touched) <= 1:
        return "purist"
    if len(touched) == 2 and secondary and blend_ratio["primary"] >= 60:
        return "anchored_blend"
    if len(touched) == 2 and secondary and blend_ratio["primary"] < 60:
        return "balanced_blend"
    if len(touched) >= 3:
        return "eclectic"
    return "anchored_blend"
