"""Tests for the cross-conversation fallback in the explanation
handler + the underlying ConversationRepository helper.

When the user asks "why did you recommend that?" in a fresh
conversation that doesn't carry the prior recommendation summary
(frontend opened a new chat between recommendation and follow-up),
the explanation handler now falls back to the user's most-recently-
updated conversation that DOES carry recommendations.
"""
from __future__ import annotations

import unittest
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

# sys.path setup is centralised in tests/conftest.py.
from platform_core.repositories import ConversationRepository


class _FakeClient:
    """In-memory stub of SupabaseRestClient for the conversation table."""

    def __init__(self, rows: List[Dict[str, Any]]):
        self._rows = rows

    def select_many(
        self,
        table: str,
        *,
        columns: str = "*",
        filters: Optional[Dict[str, str]] = None,
        order: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        assert table == "conversations"
        out = list(self._rows)
        if filters:
            for k, v in filters.items():
                want = v.split("eq.", 1)[1] if v.startswith("eq.") else v
                out = [r for r in out if str(r.get(k)) == want]
        if order and order.endswith(".desc"):
            key = order.split(".")[0]
            out.sort(key=lambda r: r.get(key) or "", reverse=True)
        if limit:
            out = out[:limit]
        return out


class GetLatestConversationWithRecommendationsTests(unittest.TestCase):

    def test_returns_most_recent_conversation_with_recommendations(self):
        rows = [
            {
                "id": "conv1", "user_id": "u1", "updated_at": "2026-05-07T18:00:00",
                "session_context_json": {"last_recommendations": [{"title": "old"}]},
            },
            {
                "id": "conv2", "user_id": "u1", "updated_at": "2026-05-07T19:00:00",
                "session_context_json": {"last_recommendations": [{"title": "newer"}]},
            },
            # Fresh conversation that the user is currently in — empty.
            {
                "id": "conv3", "user_id": "u1", "updated_at": "2026-05-07T20:00:00",
                "session_context_json": {},
            },
        ]
        repo = ConversationRepository(_FakeClient(rows))
        result = repo.get_latest_conversation_with_recommendations("u1")
        self.assertIsNotNone(result)
        self.assertEqual(result["id"], "conv2")
        self.assertEqual(
            result["session_context_json"]["last_recommendations"][0]["title"],
            "newer",
        )

    def test_excludes_specified_conversation_id(self):
        # Don't pick the conversation the user is actively in.
        rows = [
            {
                "id": "current_conv", "user_id": "u1", "updated_at": "2026-05-07T20:00:00",
                "session_context_json": {"last_recommendations": [{"title": "x"}]},
            },
            {
                "id": "older_conv", "user_id": "u1", "updated_at": "2026-05-07T18:00:00",
                "session_context_json": {"last_recommendations": [{"title": "y"}]},
            },
        ]
        repo = ConversationRepository(_FakeClient(rows))
        result = repo.get_latest_conversation_with_recommendations(
            "u1", exclude_conversation_id="current_conv",
        )
        self.assertIsNotNone(result)
        self.assertEqual(result["id"], "older_conv")

    def test_returns_none_when_no_conversation_has_recommendations(self):
        rows = [
            {
                "id": "conv1", "user_id": "u1", "updated_at": "2026-05-07T18:00:00",
                "session_context_json": {},
            },
            {
                "id": "conv2", "user_id": "u1", "updated_at": "2026-05-07T19:00:00",
                "session_context_json": {"memory": {}},
            },
        ]
        repo = ConversationRepository(_FakeClient(rows))
        self.assertIsNone(repo.get_latest_conversation_with_recommendations("u1"))

    def test_returns_none_for_user_with_no_conversations(self):
        repo = ConversationRepository(_FakeClient([]))
        self.assertIsNone(repo.get_latest_conversation_with_recommendations("u1"))

    def test_only_scans_user_owned_conversations(self):
        rows = [
            {
                "id": "other_user_conv", "user_id": "u2", "updated_at": "2026-05-07T20:00:00",
                "session_context_json": {"last_recommendations": [{"title": "leak"}]},
            },
            {
                "id": "my_conv", "user_id": "u1", "updated_at": "2026-05-07T18:00:00",
                "session_context_json": {"last_recommendations": [{"title": "mine"}]},
            },
        ]
        repo = ConversationRepository(_FakeClient(rows))
        result = repo.get_latest_conversation_with_recommendations("u1")
        # Must only see u1's conversations — "leak" must NOT appear.
        self.assertIsNotNone(result)
        self.assertEqual(result["id"], "my_conv")

    def test_scan_limit_caps_walk_depth(self):
        # 12 conversations, only the 11th has recommendations. Default
        # scan_limit=10, so we shouldn't find it. With explicit higher
        # scan_limit, we should.
        rows = []
        for i in range(12):
            rows.append({
                "id": f"conv{i}", "user_id": "u1",
                "updated_at": f"2026-05-{8-i:02d}T12:00:00",
                "session_context_json": (
                    {"last_recommendations": [{"title": "found"}]} if i == 10 else {}
                ),
            })
        repo = ConversationRepository(_FakeClient(rows))
        # Default scan_limit=10 → can't see conv at depth 10.
        # (rows are sorted updated_at.desc → the conv with recommendations
        # is at index 10 in the sorted order, beyond the default 10-row scan.)
        self.assertIsNone(repo.get_latest_conversation_with_recommendations("u1"))
        # With higher scan_limit, we find it.
        result = repo.get_latest_conversation_with_recommendations("u1", scan_limit=15)
        self.assertIsNotNone(result)


if __name__ == "__main__":
    unittest.main()
