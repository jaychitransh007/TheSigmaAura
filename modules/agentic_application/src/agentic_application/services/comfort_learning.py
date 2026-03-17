"""Comfort Learning Service — refines seasonal palette over time based on behavioral signals."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from platform_core.repositories import ConversationRepository
from platform_core.supabase_rest import SupabaseRestClient

# Maps each seasonal group to characteristic color families and temperature
SEASON_COLOR_MAP: Dict[str, Dict[str, Any]] = {
    "Spring": {
        "temperature": "warm",
        "colors": [
            "peach", "coral", "ivory", "light gold", "camel", "warm beige",
            "golden yellow", "warm coral", "turquoise", "warm green",
            "bright coral", "clear red", "hot pink",
        ],
    },
    "Summer": {
        "temperature": "cool",
        "colors": [
            "lavender", "powder blue", "soft pink", "light grey", "mauve",
            "dusty rose", "periwinkle", "slate blue", "soft white",
            "muted teal", "dusty pink", "sage",
        ],
    },
    "Autumn": {
        "temperature": "warm",
        "colors": [
            "olive", "muted gold", "terracotta", "sage green", "warm taupe",
            "rust", "burnt orange", "olive green", "warm brown", "gold",
            "chocolate brown", "forest green", "burnt sienna", "dark teal", "burgundy",
        ],
    },
    "Winter": {
        "temperature": "cool",
        "colors": [
            "true red", "royal blue", "emerald", "black", "white",
            "icy blue", "charcoal", "deep purple", "fuchsia",
            "dark navy", "dark burgundy",
        ],
    },
}

# Color keyword to seasonal direction mapping
COLOR_TO_SEASON: Dict[str, str] = {}
for _season, _info in SEASON_COLOR_MAP.items():
    for _color in _info["colors"]:
        COLOR_TO_SEASON[_color.lower()] = _season

# Common color keywords and their most likely seasonal direction
COMMON_COLOR_KEYWORDS: Dict[str, str] = {
    "red": "Winter",
    "blue": "Summer",
    "navy": "Winter",
    "green": "Autumn",
    "olive": "Autumn",
    "pink": "Spring",
    "coral": "Spring",
    "burgundy": "Autumn",
    "rust": "Autumn",
    "teal": "Autumn",
    "lavender": "Summer",
    "purple": "Winter",
    "gold": "Autumn",
    "silver": "Winter",
    "white": "Winter",
    "black": "Winter",
    "grey": "Summer",
    "gray": "Summer",
    "beige": "Spring",
    "brown": "Autumn",
    "cream": "Spring",
    "ivory": "Spring",
    "orange": "Autumn",
    "yellow": "Spring",
    "turquoise": "Spring",
    "emerald": "Winter",
    "charcoal": "Winter",
    "mauve": "Summer",
    "sage": "Autumn",
    "terracotta": "Autumn",
    "tan": "Autumn",
    "khaki": "Autumn",
    "maroon": "Autumn",
    "peach": "Spring",
    "periwinkle": "Summer",
    "fuchsia": "Winter",
    "magenta": "Winter",
}

HIGH_INTENT_THRESHOLD = 5


class ComfortLearningService:
    def __init__(self, client: SupabaseRestClient) -> None:
        self._client = client

    def detect_high_intent_signal(
        self,
        *,
        user_id: str,
        garment_id: str,
        conversation_id: Optional[str] = None,
        turn_id: Optional[str] = None,
        feedback_event_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        garment = self._client.select_one(
            "catalog_enriched",
            filters={"product_id": f"eq.{garment_id}"},
        )
        if not garment:
            return None

        primary_color = str(garment.get("primary_color") or "").lower().strip()
        color_temp = str(garment.get("color_temperature") or "").lower().strip()

        seasonal_direction = self._map_color_to_season(primary_color, color_temp)
        if not seasonal_direction:
            return None

        effective = self._get_effective_seasonal_groups(user_id)
        current_group_values = {g.get("value", "") for g in (effective or [])}

        if seasonal_direction in current_group_values:
            return None

        signal = self._insert_comfort_signal(
            user_id=user_id,
            signal_type="high_intent",
            signal_source="outfit_like",
            detected_seasonal_direction=seasonal_direction,
            garment_id=garment_id,
            conversation_id=conversation_id,
            turn_id=turn_id,
            feedback_event_id=feedback_event_id,
        )

        self.evaluate_and_update(user_id)
        return signal

    def detect_low_intent_signal(
        self,
        *,
        user_id: str,
        color_keywords: List[str],
        conversation_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        signals = []
        for keyword in color_keywords:
            direction = COMMON_COLOR_KEYWORDS.get(keyword.lower().strip())
            if not direction:
                direction = COLOR_TO_SEASON.get(keyword.lower().strip())
            if not direction:
                continue

            signal = self._insert_comfort_signal(
                user_id=user_id,
                signal_type="low_intent",
                signal_source="color_request",
                detected_seasonal_direction=direction,
                conversation_id=conversation_id,
            )
            if signal:
                signals.append(signal)

        return signals

    def evaluate_and_update(self, user_id: str) -> Optional[Dict[str, Any]]:
        counts = self._count_high_intent_by_direction(user_id)

        trigger_direction = None
        for direction, count in counts.items():
            if count >= HIGH_INTENT_THRESHOLD:
                trigger_direction = direction
                break

        if not trigger_direction:
            return None

        effective = self._get_effective_seasonal_groups(user_id)
        current_groups = list(effective or [])

        current_values = {g.get("value", "") for g in current_groups}
        if trigger_direction in current_values:
            return None

        if len(current_groups) >= 2:
            # Max 2 groups for 4-season system — replace lowest probability
            current_groups.sort(key=lambda g: g.get("probability", 0))
            current_groups[0] = {
                "value": trigger_direction,
                "probability": 0.15,
                "source": "comfort_learning",
            }
        else:
            current_groups.append({
                "value": trigger_direction,
                "probability": 0.15,
                "source": "comfort_learning",
            })

        self._supersede_current_effective(user_id)

        return self._insert_effective_seasonal_groups(
            user_id=user_id,
            seasonal_groups=current_groups,
            source="comfort_learning",
        )

    def _map_color_to_season(self, primary_color: str, color_temp: str) -> Optional[str]:
        if primary_color in COMMON_COLOR_KEYWORDS:
            return COMMON_COLOR_KEYWORDS[primary_color]
        if primary_color in COLOR_TO_SEASON:
            return COLOR_TO_SEASON[primary_color]
        if color_temp == "warm":
            return "Autumn"
        if color_temp == "cool":
            return "Summer"
        return None

    def _get_effective_seasonal_groups(self, user_id: str) -> List[Dict[str, Any]]:
        rows = self._client.select_many(
            "user_effective_seasonal_groups",
            filters={"user_id": f"eq.{user_id}", "superseded_at": "is.null"},
            order="created_at.desc",
            limit=1,
        )
        if rows:
            return rows[0].get("seasonal_groups") or []
        return []

    def _count_high_intent_by_direction(self, user_id: str) -> Dict[str, int]:
        rows = self._client.select_many(
            "user_comfort_learning",
            filters={"user_id": f"eq.{user_id}", "signal_type": "eq.high_intent"},
        )
        counts: Dict[str, int] = {}
        for row in rows:
            direction = row.get("detected_seasonal_direction", "")
            if direction:
                counts[direction] = counts.get(direction, 0) + 1
        return counts

    def _insert_comfort_signal(self, **kwargs: Any) -> Optional[Dict[str, Any]]:
        payload = {
            "user_id": kwargs["user_id"],
            "signal_type": kwargs["signal_type"],
            "signal_source": kwargs["signal_source"],
            "detected_seasonal_direction": kwargs["detected_seasonal_direction"],
        }
        if kwargs.get("garment_id"):
            payload["garment_id"] = kwargs["garment_id"]
        if kwargs.get("conversation_id"):
            payload["conversation_id"] = kwargs["conversation_id"]
        if kwargs.get("turn_id"):
            payload["turn_id"] = kwargs["turn_id"]
        if kwargs.get("feedback_event_id"):
            payload["feedback_event_id"] = kwargs["feedback_event_id"]
        return self._client.insert_one("user_comfort_learning", payload)

    def _supersede_current_effective(self, user_id: str) -> None:
        from datetime import datetime, timezone
        rows = self._client.select_many(
            "user_effective_seasonal_groups",
            filters={"user_id": f"eq.{user_id}", "superseded_at": "is.null"},
        )
        now = datetime.now(timezone.utc).isoformat()
        for row in rows:
            self._client.update_one(
                "user_effective_seasonal_groups",
                filters={"id": f"eq.{row['id']}"},
                patch={"superseded_at": now},
            )

    def _insert_effective_seasonal_groups(
        self,
        *,
        user_id: str,
        seasonal_groups: List[Dict[str, Any]],
        source: str,
    ) -> Dict[str, Any]:
        return self._client.insert_one("user_effective_seasonal_groups", {
            "user_id": user_id,
            "seasonal_groups": seasonal_groups,
            "source": source,
        })
