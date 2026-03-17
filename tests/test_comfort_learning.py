"""Tests for Comfort Learning Service — 4-season system."""

import sys
import importlib.util
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[1]
for p in (
    ROOT,
    ROOT / "modules" / "platform_core" / "src",
    ROOT / "modules" / "user" / "src",
    ROOT / "modules" / "agentic_application" / "src",
):
    sp = str(p)
    if sp not in sys.path:
        sys.path.insert(0, sp)

# Stub out heavy dependencies
sys.modules.setdefault("user_profiler", MagicMock())
sys.modules.setdefault("user_profiler.config", MagicMock())
sys.modules.setdefault("openai", MagicMock())
sys.modules.setdefault("fastapi", MagicMock())
sys.modules.setdefault("fastapi.responses", MagicMock())
sys.modules.setdefault("pydantic", MagicMock())

# Import directly from the module file to avoid __init__.py chain
_spec = importlib.util.spec_from_file_location(
    "comfort_learning",
    ROOT / "modules" / "agentic_application" / "src" / "agentic_application" / "services" / "comfort_learning.py",
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

COMMON_COLOR_KEYWORDS = _mod.COMMON_COLOR_KEYWORDS
COLOR_TO_SEASON = _mod.COLOR_TO_SEASON
HIGH_INTENT_THRESHOLD = _mod.HIGH_INTENT_THRESHOLD
SEASON_COLOR_MAP = _mod.SEASON_COLOR_MAP
ComfortLearningService = _mod.ComfortLearningService


class FakeClient:
    """Minimal fake for SupabaseRestClient."""

    def __init__(self):
        self._tables = {}
        self._next_id = 0

    def insert_one(self, table, payload):
        self._next_id += 1
        row = {"id": str(self._next_id), **payload}
        self._tables.setdefault(table, []).append(row)
        return row

    def select_one(self, table, filters=None):
        rows = self._filter(table, filters)
        return rows[0] if rows else None

    def select_many(self, table, filters=None, order=None, limit=None):
        rows = self._filter(table, filters)
        if order and "desc" in order:
            rows = list(reversed(rows))
        if limit:
            rows = rows[:limit]
        return rows

    def update_one(self, table, filters=None, patch=None):
        rows = self._filter(table, filters)
        if rows:
            rows[0].update(patch or {})
            return rows[0]
        return None

    def _filter(self, table, filters):
        all_rows = self._tables.get(table, [])
        if not filters:
            return list(all_rows)
        result = []
        for row in all_rows:
            match = True
            for key, condition in (filters or {}).items():
                if condition.startswith("eq."):
                    expected = condition[3:]
                    if str(row.get(key, "")) != expected:
                        match = False
                elif condition == "is.null":
                    if row.get(key) is not None:
                        match = False
            if match:
                result.append(row)
        return result


class TestColorMapping:
    def test_four_seasons_only(self):
        assert set(SEASON_COLOR_MAP.keys()) == {"Spring", "Summer", "Autumn", "Winter"}

    def test_all_seasons_have_colors(self):
        for season in SEASON_COLOR_MAP:
            assert len(SEASON_COLOR_MAP[season]["colors"]) > 0

    def test_all_seasons_have_temperature(self):
        for season in SEASON_COLOR_MAP:
            assert SEASON_COLOR_MAP[season]["temperature"] in ("warm", "cool")

    def test_common_keywords_map_to_valid_seasons(self):
        for color, season in COMMON_COLOR_KEYWORDS.items():
            assert season in SEASON_COLOR_MAP, f"{color} maps to unknown season {season}"

    def test_warm_colors_map_to_warm_seasons(self):
        warm_seasons = {"Spring", "Autumn"}
        for color in ["coral", "rust", "gold", "orange", "peach"]:
            assert COMMON_COLOR_KEYWORDS[color] in warm_seasons, f"{color} should be warm"

    def test_cool_colors_map_to_cool_seasons(self):
        cool_seasons = {"Summer", "Winter"}
        for color in ["navy", "purple", "emerald", "fuchsia", "lavender"]:
            assert COMMON_COLOR_KEYWORDS[color] in cool_seasons, f"{color} should be cool"


class TestDetectHighIntentSignal:
    def test_detects_signal_for_outside_group(self):
        client = FakeClient()
        client.insert_one("user_effective_seasonal_groups", {
            "user_id": "user1",
            "seasonal_groups": [{"value": "Autumn", "probability": 0.7, "source": "draping"}],
            "source": "draping",
            "superseded_at": None,
        })
        client.insert_one("catalog_enriched", {
            "product_id": "g1",
            "primary_color": "blue",
            "color_temperature": "cool",
        })

        service = ComfortLearningService(client)
        result = service.detect_high_intent_signal(user_id="user1", garment_id="g1")
        assert result is not None
        assert result["signal_type"] == "high_intent"
        assert result["detected_seasonal_direction"] == "Summer"

    def test_no_signal_for_inside_group(self):
        client = FakeClient()
        client.insert_one("user_effective_seasonal_groups", {
            "user_id": "user1",
            "seasonal_groups": [{"value": "Autumn", "probability": 0.7, "source": "draping"}],
            "source": "draping",
            "superseded_at": None,
        })
        client.insert_one("catalog_enriched", {
            "product_id": "g2",
            "primary_color": "rust",
            "color_temperature": "warm",
        })

        service = ComfortLearningService(client)
        result = service.detect_high_intent_signal(user_id="user1", garment_id="g2")
        assert result is None

    def test_no_signal_for_unknown_garment(self):
        client = FakeClient()
        service = ComfortLearningService(client)
        result = service.detect_high_intent_signal(user_id="user1", garment_id="nonexistent")
        assert result is None


class TestDetectLowIntentSignal:
    def test_maps_color_keywords(self):
        client = FakeClient()
        service = ComfortLearningService(client)
        signals = service.detect_low_intent_signal(
            user_id="user1",
            color_keywords=["navy", "emerald"],
        )
        assert len(signals) == 2
        directions = {s["detected_seasonal_direction"] for s in signals}
        assert "Winter" in directions

    def test_ignores_unknown_colors(self):
        client = FakeClient()
        service = ComfortLearningService(client)
        signals = service.detect_low_intent_signal(
            user_id="user1",
            color_keywords=["xyznonexistent"],
        )
        assert len(signals) == 0

    def test_low_intent_does_not_trigger_update(self):
        client = FakeClient()
        service = ComfortLearningService(client)
        for _ in range(10):
            service.detect_low_intent_signal(user_id="user1", color_keywords=["navy"])
        rows = client.select_many("user_effective_seasonal_groups", filters={"user_id": "eq.user1"})
        assert len(rows) == 0


class TestEvaluateAndUpdate:
    def _setup_with_signals(self, client, user_id, direction, count, current_groups=None):
        if current_groups:
            client.insert_one("user_effective_seasonal_groups", {
                "user_id": user_id,
                "seasonal_groups": current_groups,
                "source": "draping",
                "superseded_at": None,
            })
        for _ in range(count):
            client.insert_one("user_comfort_learning", {
                "user_id": user_id,
                "signal_type": "high_intent",
                "signal_source": "outfit_like",
                "detected_seasonal_direction": direction,
            })

    def test_triggers_at_threshold(self):
        client = FakeClient()
        current = [{"value": "Autumn", "probability": 0.7, "source": "draping"}]
        self._setup_with_signals(client, "user1", "Summer", HIGH_INTENT_THRESHOLD, current)

        service = ComfortLearningService(client)
        result = service.evaluate_and_update("user1")
        assert result is not None
        groups = result["seasonal_groups"]
        values = [g["value"] for g in groups]
        assert "Summer" in values

    def test_does_not_trigger_below_threshold(self):
        client = FakeClient()
        current = [{"value": "Autumn", "probability": 0.7, "source": "draping"}]
        self._setup_with_signals(client, "user1", "Summer", HIGH_INTENT_THRESHOLD - 1, current)

        service = ComfortLearningService(client)
        result = service.evaluate_and_update("user1")
        assert result is None

    def test_max_two_groups(self):
        client = FakeClient()
        current = [
            {"value": "Autumn", "probability": 0.5, "source": "draping"},
            {"value": "Winter", "probability": 0.3, "source": "draping"},
        ]
        self._setup_with_signals(client, "user1", "Summer", HIGH_INTENT_THRESHOLD, current)

        service = ComfortLearningService(client)
        result = service.evaluate_and_update("user1")
        assert result is not None
        groups = result["seasonal_groups"]
        assert len(groups) <= 2
        values = [g["value"] for g in groups]
        assert "Summer" in values
        # The lowest-probability group (Winter at 0.3) should have been replaced
        assert "Winter" not in values

    def test_adds_group_when_under_two(self):
        client = FakeClient()
        current = [{"value": "Autumn", "probability": 0.7, "source": "draping"}]
        self._setup_with_signals(client, "user1", "Summer", HIGH_INTENT_THRESHOLD, current)

        service = ComfortLearningService(client)
        result = service.evaluate_and_update("user1")
        groups = result["seasonal_groups"]
        assert len(groups) == 2
        values = [g["value"] for g in groups]
        assert "Autumn" in values
        assert "Summer" in values

    def test_supersedes_old_effective_row(self):
        client = FakeClient()
        current = [{"value": "Autumn", "probability": 0.7, "source": "draping"}]
        self._setup_with_signals(client, "user1", "Summer", HIGH_INTENT_THRESHOLD, current)

        service = ComfortLearningService(client)
        service.evaluate_and_update("user1")

        all_rows = client.select_many("user_effective_seasonal_groups", filters={"user_id": "eq.user1"})
        superseded = [r for r in all_rows if r.get("superseded_at") is not None]
        active = [r for r in all_rows if r.get("superseded_at") is None]
        assert len(superseded) == 1
        assert len(active) == 1

    def test_no_duplicate_direction(self):
        client = FakeClient()
        current = [{"value": "Summer", "probability": 0.5, "source": "draping"}]
        self._setup_with_signals(client, "user1", "Summer", HIGH_INTENT_THRESHOLD, current)

        service = ComfortLearningService(client)
        result = service.evaluate_and_update("user1")
        assert result is None
