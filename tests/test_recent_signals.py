"""Tests for the profile Recent-Signals timeline.

Covers:
- comfort_learning bucketing by (signal_source, direction) collapses repeated signals
- feedback_events aggregate likes / dislikes into one line each
- catalog_interaction_history aggregates save / skip into one line each
- old (>30d) rows are filtered out so the timeline reads as "recent"
- empty inputs return an empty list (caller renders editorial empty state)
- ordering is newest-first across sources
- the limit parameter caps output
"""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
for p in (
    ROOT,
    ROOT / "modules" / "agentic_application" / "src",
    ROOT / "modules" / "platform_core" / "src",
    ROOT / "modules" / "user" / "src",
    ROOT / "modules" / "catalog" / "src",
    ROOT / "modules" / "user_profiler" / "src",
):
    sp = str(p)
    if sp not in sys.path:
        sys.path.insert(0, sp)


from agentic_application.services.recent_signals import build_recent_signals


def _iso_days_ago(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


class RecentSignalsTests(unittest.TestCase):

    def test_empty_inputs_return_empty_list(self) -> None:
        out = build_recent_signals(
            comfort_rows=[], feedback_rows=[], catalog_rows=[],
        )
        self.assertEqual([], out)

    def test_comfort_learning_buckets_by_source_and_direction(self) -> None:
        rows = [
            {"signal_source": "outfit_like", "detected_seasonal_direction": "Autumn",
             "created_at": _iso_days_ago(2)},
            {"signal_source": "outfit_like", "detected_seasonal_direction": "Autumn",
             "created_at": _iso_days_ago(5)},
            {"signal_source": "outfit_like", "detected_seasonal_direction": "Autumn",
             "created_at": _iso_days_ago(10)},
        ]
        out = build_recent_signals(comfort_rows=rows, feedback_rows=[], catalog_rows=[])
        self.assertEqual(1, len(out))
        self.assertIn("Autumn", out[0]["label"])
        self.assertIn("3 likes", out[0]["detail"])

    def test_color_request_signals_use_distinct_copy(self) -> None:
        rows = [
            {"signal_source": "color_request", "detected_seasonal_direction": "Warm",
             "created_at": _iso_days_ago(1)},
        ]
        out = build_recent_signals(comfort_rows=rows, feedback_rows=[], catalog_rows=[])
        self.assertEqual(1, len(out))
        self.assertIn("Asked for warm tones explicitly", out[0]["label"])

    def test_old_comfort_rows_are_filtered_out(self) -> None:
        rows = [
            {"signal_source": "outfit_like", "detected_seasonal_direction": "Autumn",
             "created_at": _iso_days_ago(60)},
        ]
        out = build_recent_signals(comfort_rows=rows, feedback_rows=[], catalog_rows=[])
        self.assertEqual([], out)

    def test_feedback_aggregates_likes_and_dislikes(self) -> None:
        rows = [
            {"event_type": "like", "created_at": _iso_days_ago(1)},
            {"event_type": "like", "created_at": _iso_days_ago(2)},
            {"event_type": "dislike", "created_at": _iso_days_ago(3)},
        ]
        out = build_recent_signals(comfort_rows=[], feedback_rows=rows, catalog_rows=[])
        labels = [s["label"] for s in out]
        self.assertTrue(any("Liked 2 outfits" in lbl for lbl in labels))
        self.assertTrue(any("Pushed back on 1 outfit" in lbl for lbl in labels))

    def test_catalog_aggregates_save_and_skip(self) -> None:
        rows = [
            {"interaction_type": "save", "created_at": _iso_days_ago(1)},
            {"interaction_type": "save", "created_at": _iso_days_ago(2)},
            {"interaction_type": "skip", "created_at": _iso_days_ago(3)},
            {"interaction_type": "skip", "created_at": _iso_days_ago(4)},
        ]
        out = build_recent_signals(comfort_rows=[], feedback_rows=[], catalog_rows=rows)
        labels = [s["label"] for s in out]
        self.assertTrue(any("Saved 2 pieces" in lbl for lbl in labels))
        self.assertTrue(any("Skipped 2 items" in lbl for lbl in labels))

    def test_ordering_is_newest_first_across_sources(self) -> None:
        comfort = [{"signal_source": "outfit_like", "detected_seasonal_direction": "Autumn",
                    "created_at": _iso_days_ago(7)}]
        feedback = [{"event_type": "like", "created_at": _iso_days_ago(1)}]
        catalog = [{"interaction_type": "save", "created_at": _iso_days_ago(15)}]
        out = build_recent_signals(
            comfort_rows=comfort, feedback_rows=feedback, catalog_rows=catalog,
        )
        # Most recent timestamp first.
        self.assertEqual("feedback", out[0]["source"])
        self.assertEqual("comfort_learning", out[1]["source"])
        self.assertEqual("catalog", out[2]["source"])

    def test_limit_caps_output(self) -> None:
        # Five distinct signals across sources.
        comfort = [
            {"signal_source": "outfit_like", "detected_seasonal_direction": "Autumn",
             "created_at": _iso_days_ago(1)},
            {"signal_source": "color_request", "detected_seasonal_direction": "Warm",
             "created_at": _iso_days_ago(2)},
        ]
        feedback = [
            {"event_type": "like", "created_at": _iso_days_ago(3)},
            {"event_type": "dislike", "created_at": _iso_days_ago(4)},
        ]
        catalog = [
            {"interaction_type": "save", "created_at": _iso_days_ago(5)},
        ]
        out = build_recent_signals(
            comfort_rows=comfort, feedback_rows=feedback, catalog_rows=catalog, limit=2,
        )
        self.assertEqual(2, len(out))


if __name__ == "__main__":
    unittest.main()
