"""Tests for Digital Draping Service — 4-season distribution computation and top-N selection."""

import sys
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[1]
for p in (
    ROOT,
    ROOT / "modules" / "platform_core" / "src",
    ROOT / "modules" / "user" / "src",
):
    sp = str(p)
    if sp not in sys.path:
        sys.path.insert(0, sp)

# Stub out heavy dependencies to avoid import chain
sys.modules.setdefault("user_profiler", MagicMock())
sys.modules.setdefault("user_profiler.config", MagicMock())
sys.modules.setdefault("openai", MagicMock())

from user.draping import (
    ALL_SEASONS,
    TIEBREAK_PRIORITY,
    DigitalDrapingService,
    DrapingResult,
    DrapingRound,
    _hex_to_rgba,
)


class TestHexToRgba:
    def test_basic(self):
        assert _hex_to_rgba("#FF0000") == (255, 0, 0, 89)

    def test_with_custom_alpha(self):
        assert _hex_to_rgba("#00FF00", alpha=128) == (0, 255, 0, 128)

    def test_no_hash(self):
        assert _hex_to_rgba("0000FF") == (0, 0, 255, 89)


class TestAllSeasons:
    def test_four_seasons(self):
        assert ALL_SEASONS == ["Spring", "Summer", "Autumn", "Winter"]

    def test_tiebreak_prefers_autumn_then_winter(self):
        assert TIEBREAK_PRIORITY["Autumn"] > TIEBREAK_PRIORITY["Winter"]
        assert TIEBREAK_PRIORITY["Winter"] > TIEBREAK_PRIORITY["Spring"]
        assert TIEBREAK_PRIORITY["Spring"] > TIEBREAK_PRIORITY["Summer"]


class TestComputeDistribution:
    def _make_rounds(self, temp_winner, temp_conf, season_winner, season_conf,
                     confirm_winner=None, confirm_conf=0.7):
        """Build 2 or 3 rounds for the 4-season draping chain."""
        r1 = DrapingRound(1, "Warm vs Cool", "#D4AF37", "#C0C0C0", "warm", "cool",
                          choice="A" if temp_winner == "warm" else "B",
                          confidence=temp_conf, reasoning="",
                          winner_label=temp_winner)

        if temp_winner == "warm":
            label_a, label_b = "Spring", "Autumn"
        else:
            label_a, label_b = "Summer", "Winter"

        r2 = DrapingRound(2, f"{label_a} vs {label_b}", "#aaa", "#bbb",
                          label_a, label_b,
                          choice="A" if season_winner == label_a else "B",
                          confidence=season_conf, reasoning="",
                          winner_label=season_winner)

        rounds = [r1, r2]

        if confirm_winner:
            neighbor = {"Spring": "Summer", "Summer": "Spring",
                        "Autumn": "Winter", "Winter": "Autumn"}
            loser = neighbor[confirm_winner]
            r3 = DrapingRound(3, f"{confirm_winner} vs {loser}", "#ccc", "#ddd",
                              confirm_winner, loser,
                              choice="A", confidence=confirm_conf,
                              reasoning="", winner_label=confirm_winner)
            rounds.append(r3)

        return rounds

    def test_distribution_sums_to_one(self):
        rounds = self._make_rounds("warm", 0.8, "Autumn", 0.75, "Autumn", 0.7)
        result = DigitalDrapingService._compute_distribution(rounds, "warm")
        total = sum(result.values())
        assert abs(total - 1.0) < 0.01, f"Distribution sums to {total}"

    def test_all_4_seasons_present(self):
        rounds = self._make_rounds("cool", 0.7, "Winter", 0.8, "Winter", 0.7)
        result = DigitalDrapingService._compute_distribution(rounds, "cool")
        assert set(result.keys()) == set(ALL_SEASONS)

    def test_high_confidence_warm_autumn(self):
        rounds = self._make_rounds("warm", 0.95, "Autumn", 0.95, "Autumn", 0.9)
        result = DigitalDrapingService._compute_distribution(rounds, "warm")
        assert result["Autumn"] == max(result.values())
        assert result["Autumn"] > 0.5

    def test_high_confidence_cool_winter(self):
        rounds = self._make_rounds("cool", 0.95, "Winter", 0.95, "Winter", 0.9)
        result = DigitalDrapingService._compute_distribution(rounds, "cool")
        assert result["Winter"] == max(result.values())

    def test_high_confidence_warm_spring(self):
        rounds = self._make_rounds("warm", 0.9, "Spring", 0.9, "Spring", 0.85)
        result = DigitalDrapingService._compute_distribution(rounds, "warm")
        assert result["Spring"] == max(result.values())

    def test_high_confidence_cool_summer(self):
        rounds = self._make_rounds("cool", 0.9, "Summer", 0.9, "Summer", 0.85)
        result = DigitalDrapingService._compute_distribution(rounds, "cool")
        assert result["Summer"] == max(result.values())

    def test_low_confidence_spreads_probability(self):
        rounds = self._make_rounds("warm", 0.55, "Spring", 0.55, "Spring", 0.55)
        result = DigitalDrapingService._compute_distribution(rounds, "warm")
        max_prob = max(result.values())
        min_prob = min(result.values())
        assert max_prob - min_prob < 0.35, "Low confidence should spread probability"

    def test_two_rounds_only(self):
        rounds = self._make_rounds("warm", 0.8, "Autumn", 0.75)
        result = DigitalDrapingService._compute_distribution(rounds, "warm")
        total = sum(result.values())
        assert abs(total - 1.0) < 0.01
        assert result["Autumn"] == max(result.values())

    def test_confirmation_round_shifts(self):
        # R1: warm, R2: Spring wins, R3: Summer beats Spring
        r1 = DrapingRound(1, "Warm vs Cool", "#D4AF37", "#C0C0C0", "warm", "cool",
                          choice="A", confidence=0.6, reasoning="", winner_label="warm")
        r2 = DrapingRound(2, "Spring vs Autumn", "#aaa", "#bbb", "Spring", "Autumn",
                          choice="A", confidence=0.6, reasoning="", winner_label="Spring")
        r3 = DrapingRound(3, "Spring vs Summer", "#ccc", "#ddd", "Spring", "Summer",
                          choice="B", confidence=0.8, reasoning="", winner_label="Summer")
        result = DigitalDrapingService._compute_distribution([r1, r2, r3], "warm")
        # Summer should have gained probability from Spring
        assert result["Summer"] > result["Spring"]


class TestSelectTopGroups:
    def test_clear_winner(self):
        dist = {"Spring": 0.60, "Summer": 0.15, "Autumn": 0.15, "Winter": 0.10}
        result = DigitalDrapingService._select_top_groups(dist)
        assert len(result) == 1
        assert result[0]["value"] == "Spring"

    def test_clear_winner_by_gap(self):
        # Gap of 0.30 between #1 and #2 → clear single winner
        dist = {"Autumn": 0.55, "Winter": 0.15, "Spring": 0.20, "Summer": 0.10}
        result = DigitalDrapingService._select_top_groups(dist)
        assert len(result) == 1
        assert result[0]["value"] == "Autumn"

    def test_two_groups_when_close(self):
        dist = {"Autumn": 0.35, "Spring": 0.30, "Winter": 0.20, "Summer": 0.15}
        result = DigitalDrapingService._select_top_groups(dist)
        assert len(result) == 2
        values = [g["value"] for g in result]
        assert "Autumn" in values
        assert "Spring" in values

    def test_three_plus_clash_prefers_autumn_winter(self):
        # All 4 seasons very close — should pick Autumn and Winter
        dist = {"Spring": 0.26, "Summer": 0.24, "Autumn": 0.26, "Winter": 0.24}
        result = DigitalDrapingService._select_top_groups(dist)
        assert len(result) == 2
        values = [g["value"] for g in result]
        assert "Autumn" in values
        assert "Winter" in values

    def test_three_close_prefers_autumn(self):
        # Three close, one distant
        dist = {"Spring": 0.30, "Autumn": 0.30, "Winter": 0.30, "Summer": 0.10}
        result = DigitalDrapingService._select_top_groups(dist)
        assert len(result) == 2
        assert result[0]["value"] == "Autumn"
        assert result[1]["value"] == "Winter"

    def test_empty_distribution(self):
        result = DigitalDrapingService._select_top_groups({})
        assert result == []

    def test_source_field(self):
        dist = {s: 0.25 for s in ALL_SEASONS}
        result = DigitalDrapingService._select_top_groups(dist)
        for group in result:
            assert group["source"] == "draping"
            assert "value" in group
            assert "probability" in group


class TestDrapingResult:
    def test_to_dict(self):
        result = DrapingResult(
            chain_log=[{"round": 1}],
            distribution={"Spring": 0.5, "Summer": 0.2, "Autumn": 0.2, "Winter": 0.1},
            selected_groups=[{"value": "Spring", "probability": 0.5, "source": "draping"}],
            primary_season="Spring",
        )
        d = result.to_dict()
        assert d["primary_season"] == "Spring"
        assert len(d["chain_log"]) == 1
        assert len(d["distribution"]) == 4
        assert "selected_groups" in d
