"""Digital Draping Service — LLM-based seasonal color analysis via relative comparison."""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from openai import OpenAI
from PIL import Image, ImageOps

from user_profiler.config import get_api_key

from .repository import OnboardingRepository


def _repo_root() -> Path:
    here = Path(__file__).resolve()
    for base in [here.parent] + list(here.parents):
        if (base / "prompt").exists():
            return base
    raise FileNotFoundError("Could not locate repo root containing prompt directory.")


DRAPING_PROMPT = (_repo_root() / "prompt" / "digital_draping.md").read_text(encoding="utf-8").strip()

# 4 seasonal color groups
ALL_SEASONS = ["Spring", "Summer", "Autumn", "Winter"]

# Tiebreaker priority when 3+ groups clash (higher = preferred)
TIEBREAK_PRIORITY = {"Autumn": 4, "Winter": 3, "Spring": 2, "Summer": 1}

# Round 1: Warm vs Cool drape colors
WARM_COOL_COLORS = ("#D4AF37", "#C0C0C0")  # Gold vs Silver

# Round 2: Within-branch differentiation
BRANCH_COLORS = {
    "warm": {
        # Spring: bright peach/coral vs Autumn: deep earthy rust/olive
        "a_hex": "#FFB07C",  # Peach-coral (Spring)
        "b_hex": "#8B5E3C",  # Warm russet (Autumn)
        "label_a": "Spring",
        "label_b": "Autumn",
    },
    "cool": {
        # Summer: soft muted lavender vs Winter: deep vivid royal blue
        "a_hex": "#B4A7D6",  # Soft lavender (Summer)
        "b_hex": "#1A237E",  # Deep navy-indigo (Winter)
        "label_a": "Summer",
        "label_b": "Winter",
    },
}

# Round 3: Confirmation — winner vs cross-temperature neighbor
# Spring neighbor = Summer (both light), Autumn neighbor = Winter (both deep)
CROSS_NEIGHBOR = {
    "Spring": "Summer",
    "Summer": "Spring",
    "Autumn": "Winter",
    "Winter": "Autumn",
}
CONFIRMATION_COLORS = {
    "Spring": "#FFD700",   # Bright gold
    "Summer": "#87CEEB",   # Sky blue
    "Autumn": "#CD853F",   # Peru / warm brown
    "Winter": "#4169E1",   # Royal blue
}

_DRAPING_JSON_SCHEMA = {
    "type": "json_schema",
    "name": "draping_choice",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["choice", "confidence", "reasoning"],
        "properties": {
            "choice": {"type": "string", "enum": ["A", "B"]},
            "confidence": {"type": "number"},
            "reasoning": {"type": "string"},
        },
    },
}


@dataclass
class DrapingRound:
    round_number: int
    question: str
    color_a: str
    color_b: str
    label_a: str
    label_b: str
    choice: str = ""
    confidence: float = 0.0
    reasoning: str = ""
    winner_label: str = ""


def _confidence_to_points(confidence: float) -> int:
    """Map float confidence to categorical points: Strong=3, Moderate=2, Slight=1."""
    if confidence > 0.8:
        return 3
    if confidence >= 0.6:
        return 2
    return 1


@dataclass
class DrapingResult:
    chain_log: List[Dict[str, Any]] = field(default_factory=list)
    distribution: Dict[str, float] = field(default_factory=dict)
    selected_groups: List[Dict[str, Any]] = field(default_factory=list)
    primary_season: str = ""
    confidence_margin: int = 0  # gap between winner and runner-up point totals

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chain_log": self.chain_log,
            "distribution": self.distribution,
            "selected_groups": self.selected_groups,
            "primary_season": self.primary_season,
            "confidence_margin": self.confidence_margin,
        }


def _hex_to_rgba(hex_color: str, alpha: int = 89) -> Tuple[int, int, int, int]:
    hex_color = hex_color.lstrip("#")
    r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
    return (r, g, b, alpha)


class DigitalDrapingService:
    def __init__(self, repo: OnboardingRepository, *, model: str = "gpt-5.4") -> None:
        self._repo = repo
        self._model = model

    def _generate_overlay_pair(
        self, headshot_path: str, color_a: str, color_b: str
    ) -> Tuple[str, str]:
        path = Path(headshot_path).expanduser().resolve()
        with Image.open(path) as img:
            base = ImageOps.exif_transpose(img).convert("RGBA")

        w, h = base.size
        drape_top = int(h * 0.55)

        images_b64 = []
        for color_hex in (color_a, color_b):
            overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            drape_color = _hex_to_rgba(color_hex, alpha=89)  # ~0.35 opacity
            for y in range(drape_top, h):
                for x in range(w):
                    overlay.putpixel((x, y), drape_color)
            composite = Image.alpha_composite(base, overlay).convert("RGB")
            buf = BytesIO()
            composite.save(buf, format="JPEG", quality=90)
            images_b64.append(base64.b64encode(buf.getvalue()).decode("ascii"))

        return images_b64[0], images_b64[1]

    def _call_draping_llm(self, image_a_b64: str, image_b_b64: str, round_context: str) -> Dict[str, Any]:
        client = OpenAI(api_key=get_api_key())
        prompt_text = DRAPING_PROMPT + f"\n\n## Round Context\n{round_context}"
        response = client.responses.create(
            model=self._model,
            input=[
                {"role": "system", "content": [{"type": "input_text", "text": prompt_text}]},
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": "Compare Image A and Image B. Which overlay creates better harmony?"},
                        {"type": "input_image", "image_url": f"data:image/jpeg;base64,{image_a_b64}"},
                        {"type": "input_image", "image_url": f"data:image/jpeg;base64,{image_b_b64}"},
                    ],
                },
            ],
            text={"format": _DRAPING_JSON_SCHEMA},
        )
        return json.loads(getattr(response, "output_text", "") or "{}")

    def run_draping(
        self,
        user_id: str,
        headshot_path: str,
        attributes: Dict[str, Any],
        *,
        analysis_snapshot_id: str = "",
    ) -> DrapingResult:
        rounds: List[DrapingRound] = []
        overlay_paths: List[tuple[str, str]] = []

        # Round 1: Warm vs Cool
        r1, paths1 = self._run_round_with_persistence(
            user_id, headshot_path, 1, "Warm vs Cool undertone",
            WARM_COOL_COLORS[0], WARM_COOL_COLORS[1],
            "warm", "cool",
            analysis_snapshot_id=analysis_snapshot_id,
        )
        rounds.append(r1)
        overlay_paths.append(paths1)
        temperature = r1.winner_label  # "warm" or "cool"

        # Round 2: Within-branch (Spring vs Autumn, or Summer vs Winter)
        branch = BRANCH_COLORS[temperature]
        r2, paths2 = self._run_round_with_persistence(
            user_id, headshot_path, 2,
            f"{branch['label_a']} vs {branch['label_b']}",
            branch["a_hex"], branch["b_hex"],
            branch["label_a"], branch["label_b"],
            analysis_snapshot_id=analysis_snapshot_id,
        )
        rounds.append(r2)
        overlay_paths.append(paths2)
        primary_season = r2.winner_label

        # Round 3: Confirmation — primary vs cross-temperature neighbor
        neighbor = CROSS_NEIGHBOR[primary_season]
        r3, paths3 = self._run_round_with_persistence(
            user_id, headshot_path, 3,
            f"Confirmation: {primary_season} vs {neighbor}",
            CONFIRMATION_COLORS[primary_season],
            CONFIRMATION_COLORS[neighbor],
            primary_season, neighbor,
            analysis_snapshot_id=analysis_snapshot_id,
        )
        rounds.append(r3)
        overlay_paths.append(paths3)

        chain_log = [
            {
                "round": r.round_number,
                "question": r.question,
                "color_a": r.color_a,
                "color_b": r.color_b,
                "label_a": r.label_a,
                "label_b": r.label_b,
                "choice": r.choice,
                "confidence": r.confidence,
                "reasoning": r.reasoning,
                "winner_label": r.winner_label,
            }
            for r in rounds
        ]

        distribution = self._compute_distribution(rounds, temperature)
        selected = self._select_top_groups(distribution)
        margin = self._compute_confidence_margin(rounds, selected[0]["value"] if selected else primary_season)

        return DrapingResult(
            chain_log=chain_log,
            distribution=distribution,
            selected_groups=selected,
            primary_season=selected[0]["value"] if selected else primary_season,
            confidence_margin=margin,
        )

    def _run_round_with_persistence(
        self,
        user_id: str,
        headshot_path: str,
        round_number: int,
        question: str,
        color_a: str,
        color_b: str,
        label_a: str,
        label_b: str,
        *,
        analysis_snapshot_id: str = "",
    ) -> tuple[DrapingRound, tuple[str, str]]:
        """Run a draping round, persist overlay images to disk, record in DB."""
        result = self._run_round(headshot_path, round_number, question, color_a, color_b, label_a, label_b)

        # Save overlay images to disk
        img_a_b64, img_b_b64 = self._generate_overlay_pair(headshot_path, color_a, color_b)
        draping_dir = Path("data/draping/overlays")
        draping_dir.mkdir(parents=True, exist_ok=True)
        path_a = str(draping_dir / f"{user_id}_r{round_number}_a.jpg")
        path_b = str(draping_dir / f"{user_id}_r{round_number}_b.jpg")
        try:
            Path(path_a).write_bytes(base64.b64decode(img_a_b64))
            Path(path_b).write_bytes(base64.b64decode(img_b_b64))
        except Exception:
            path_a, path_b = "", ""

        # Persist to DB
        try:
            self._repo.insert_draping_overlay(
                user_id=user_id,
                analysis_snapshot_id=analysis_snapshot_id,
                round_number=round_number,
                round_question=question,
                image_a_path=path_a,
                image_b_path=path_b,
                color_a=color_a,
                color_b=color_b,
                label_a=label_a,
                label_b=label_b,
                choice=result.choice,
                confidence=result.confidence,
                reasoning=result.reasoning,
                winner_label=result.winner_label,
            )
        except Exception:
            pass  # best-effort — draping result is still valid without DB persistence

        return result, (path_a, path_b)

    def _run_round(
        self,
        headshot_path: str,
        round_number: int,
        question: str,
        color_a: str,
        color_b: str,
        label_a: str,
        label_b: str,
    ) -> DrapingRound:
        img_a, img_b = self._generate_overlay_pair(headshot_path, color_a, color_b)
        result = self._call_draping_llm(img_a, img_b, f"Round {round_number}: {question}")
        choice = result.get("choice", "A")
        confidence = max(0.0, min(1.0, float(result.get("confidence", 0.5))))
        reasoning = result.get("reasoning", "")
        winner = label_a if choice == "A" else label_b

        return DrapingRound(
            round_number=round_number,
            question=question,
            color_a=color_a,
            color_b=color_b,
            label_a=label_a,
            label_b=label_b,
            choice=choice,
            confidence=confidence,
            reasoning=reasoning,
            winner_label=winner,
        )

    @staticmethod
    def _compute_distribution(
        rounds: List[DrapingRound],
        temperature: str,
    ) -> Dict[str, float]:
        dist: Dict[str, float] = {s: 0.0 for s in ALL_SEASONS}

        # Round 1: warm/cool split
        r1 = rounds[0]
        r1_conf = r1.confidence
        if temperature == "warm":
            warm_share, cool_share = r1_conf, 1.0 - r1_conf
        else:
            warm_share, cool_share = 1.0 - r1_conf, r1_conf

        dist["Spring"] = warm_share / 2.0
        dist["Autumn"] = warm_share / 2.0
        dist["Summer"] = cool_share / 2.0
        dist["Winter"] = cool_share / 2.0

        # Round 2: within-branch split
        if len(rounds) > 1:
            r2 = rounds[1]
            r2_conf = r2.confidence
            winner = r2.winner_label
            loser = r2.label_a if winner == r2.label_b else r2.label_b
            pair_total = dist[winner] + dist[loser]
            dist[winner] = r2_conf * pair_total
            dist[loser] = (1.0 - r2_conf) * pair_total

        # Round 3: confirmation adjusts primary vs cross-neighbor
        if len(rounds) > 2:
            r3 = rounds[2]
            r3_conf = r3.confidence
            winner = r3.winner_label
            loser = r3.label_a if winner == r3.label_b else r3.label_b
            pair_total = dist[winner] + dist[loser]
            dist[winner] = r3_conf * pair_total
            dist[loser] = (1.0 - r3_conf) * pair_total

        # Normalize
        total = sum(dist.values())
        if total > 0:
            dist = {s: round(v / total, 4) for s, v in dist.items()}

        return dist

    @staticmethod
    def _compute_confidence_margin(rounds: List[DrapingRound], primary: str) -> int:
        """Sum categorical confidence points for the primary season vs runner-up.

        Each round's confidence maps to Strong(3)/Moderate(2)/Slight(1).
        Points go to the primary when the round's winner is the primary or
        supports it (same temperature branch). Otherwise points go to runner-up.
        The margin is winner_points - runner_up_points.
        """
        # Map each season to a set of labels that "support" it across rounds
        warm_seasons = {"Spring", "Autumn", "warm"}
        cool_seasons = {"Summer", "Winter", "cool"}
        primary_camp = warm_seasons if primary in warm_seasons else cool_seasons

        winner_pts = 0
        runner_pts = 0
        for r in rounds:
            pts = _confidence_to_points(r.confidence)
            if r.winner_label in primary_camp or r.winner_label == primary:
                winner_pts += pts
            else:
                runner_pts += pts
        return winner_pts - runner_pts

    @staticmethod
    def _select_top_groups(distribution: Dict[str, float]) -> List[Dict[str, Any]]:
        sorted_seasons = sorted(distribution.items(), key=lambda x: x[1], reverse=True)

        if not sorted_seasons:
            return []

        p = [prob for _, prob in sorted_seasons]

        # Clear winner: top probability > 0.50 OR gap to second > 0.20
        if p[0] > 0.50 or (len(p) > 1 and p[0] - p[1] > 0.20):
            return [{"value": sorted_seasons[0][0], "probability": sorted_seasons[0][1], "source": "draping"}]

        # Clash between top 2 (gap <= 0.20)
        if len(p) > 2 and p[1] - p[2] > 0.10:
            return [
                {"value": sorted_seasons[0][0], "probability": sorted_seasons[0][1], "source": "draping"},
                {"value": sorted_seasons[1][0], "probability": sorted_seasons[1][1], "source": "draping"},
            ]

        # 3+ groups clashing — prefer Autumn first, then Winter
        clashing = [s for s, prob in sorted_seasons if p[0] - prob <= 0.10]
        if len(clashing) < 2:
            # Fallback: top 2 by probability
            clashing = [s for s, _ in sorted_seasons[:2]]
        preferred = sorted(clashing, key=lambda s: TIEBREAK_PRIORITY.get(s, 0), reverse=True)
        return [
            {"value": preferred[0], "probability": distribution[preferred[0]], "source": "draping"},
            {"value": preferred[1], "probability": distribution[preferred[1]], "source": "draping"},
        ]
