from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List

from platform_core.supabase_rest import SupabaseRestClient

from ..intent_registry import Intent


def _parse_ts(value: str) -> datetime:
    text = str(value or "").strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _safe_ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round((numerator / denominator) * 100.0, 1)


def _top_counts(counter: Counter[str], *, limit: int = 5) -> List[Dict[str, Any]]:
    return [{"key": key, "count": count} for key, count in counter.most_common(limit)]


def build_dependency_report(
    *,
    onboarding_profiles: List[Dict[str, Any]],
    dependency_events: List[Dict[str, Any]],
    wardrobe_items: List[Dict[str, Any]],
    feedback_events: List[Dict[str, Any]],
    catalog_interactions: List[Dict[str, Any]],
) -> Dict[str, Any]:
    onboarded_profiles = [row for row in onboarding_profiles if bool(row.get("onboarding_complete"))]
    onboarded_user_ids = {str(row.get("user_id") or "").strip() for row in onboarded_profiles if str(row.get("user_id") or "").strip()}

    turn_events = [
        row for row in dependency_events
        if str(row.get("event_type") or "") == "turn_completed"
        and str(row.get("user_id") or "").strip() in onboarded_user_ids
    ]
    events_by_user: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in turn_events:
        events_by_user[str(row.get("user_id") or "").strip()].append(row)
    for rows in events_by_user.values():
        rows.sort(key=lambda row: _parse_ts(str(row.get("created_at") or "")))

    sessions_by_user: Dict[str, List[Dict[str, Any]]] = {}
    session_gap = timedelta(hours=12)
    for user_id, rows in events_by_user.items():
        sessions: List[Dict[str, Any]] = []
        current: Dict[str, Any] | None = None
        for row in rows:
            ts = _parse_ts(str(row.get("created_at") or ""))
            metadata = dict(row.get("metadata_json") or {})
            if current is None or ts - current["last_seen_at"] > session_gap:
                if current is not None:
                    current["intent_counts"] = dict(current["intent_counts"])
                    current["memory_sources"] = sorted(current["memory_sources"])
                current = {
                    "started_at": ts,
                    "last_seen_at": ts,
                    "source_channel": str(row.get("source_channel") or "web"),
                    "turn_count": 0,
                    "intent_counts": Counter(),
                    "memory_sources": set(),
                }
                sessions.append(current)
            current["last_seen_at"] = ts
            current["turn_count"] += 1
            primary_intent = str(row.get("primary_intent") or "").strip()
            if primary_intent:
                current["intent_counts"][primary_intent] += 1
            for source in list(metadata.get("memory_sources_read") or []):
                value = str(source or "").strip()
                if value:
                    current["memory_sources"].add(value)
        if current is not None:
            current["intent_counts"] = dict(current["intent_counts"])
            current["memory_sources"] = sorted(current["memory_sources"])
        sessions_by_user[user_id] = sessions

    acquisition_counter: Counter[str] = Counter()
    cohort_users: Dict[str, set[str]] = defaultdict(set)
    profile_by_user = {
        str(row.get("user_id") or "").strip(): row
        for row in onboarded_profiles
        if str(row.get("user_id") or "").strip()
    }
    for user_id, row in profile_by_user.items():
        source = str(row.get("acquisition_source") or "unknown").strip() or "unknown"
        acquisition_counter[source] += 1
        cohort_users[source].add(user_id)

    second_session_users = 0
    third_session_users = 0
    repeat_sessions_total = 0
    repeat_flags: Dict[str, bool] = {}

    session_behavior: Dict[int, Dict[str, Any]] = {
        1: {"count": 0, "channels": Counter(), "intents": Counter(), "turns_total": 0},
        2: {"count": 0, "channels": Counter(), "intents": Counter(), "turns_total": 0},
        3: {"count": 0, "channels": Counter(), "intents": Counter(), "turns_total": 0},
    }

    for user_id in onboarded_user_ids:
        sessions = sessions_by_user.get(user_id, [])
        repeat_flags[user_id] = False
        if len(sessions) >= 2 and sessions[1]["started_at"] - sessions[0]["started_at"] <= timedelta(days=14):
            second_session_users += 1
            repeat_flags[user_id] = True
        if len(sessions) >= 3 and sessions[2]["started_at"] - sessions[0]["started_at"] <= timedelta(days=30):
            third_session_users += 1
        for index, session in enumerate(sessions, start=1):
            if index >= 2:
                repeat_sessions_total += 1
            if index <= 3:
                bucket = session_behavior[index]
                bucket["count"] += 1
                bucket["channels"][session["source_channel"]] += 1
                bucket["turns_total"] += int(session["turn_count"])
                for intent_name, count in dict(session["intent_counts"]).items():
                    bucket["intents"][intent_name] += int(count)

    recurring_by_cohort: Dict[str, List[Dict[str, Any]]] = {}
    for cohort, user_ids in cohort_users.items():
        recurring_counter: Counter[str] = Counter()
        for user_id in user_ids:
            sessions = sessions_by_user.get(user_id, [])
            intent_session_counts: Counter[str] = Counter()
            for session in sessions:
                for intent_name in dict(session.get("intent_counts") or {}).keys():
                    intent_session_counts[intent_name] += 1
            for intent_name, count in intent_session_counts.items():
                if count >= 2:
                    recurring_counter[intent_name] += 1
        recurring_by_cohort[cohort] = _top_counts(recurring_counter, limit=6)

    wardrobe_users = {str(row.get("user_id") or "").strip() for row in wardrobe_items if bool(row.get("is_active", True))}
    feedback_users = {
        str(row.get("user_id") or "").strip()
        for row in dependency_events
        if str(row.get("event_type") or "") == "turn_completed"
        and str(row.get("primary_intent") or "") == Intent.FEEDBACK_SUBMISSION
    }
    catalog_users = {str(row.get("user_id") or "").strip() for row in catalog_interactions}

    def memory_lift(label: str, users_with_signal: Iterable[str]) -> Dict[str, Any]:
        with_signal = {user_id for user_id in users_with_signal if user_id in onboarded_user_ids}
        without_signal = onboarded_user_ids - with_signal
        repeat_with = sum(1 for user_id in with_signal if repeat_flags.get(user_id, False))
        repeat_without = sum(1 for user_id in without_signal if repeat_flags.get(user_id, False))
        with_rate = _safe_ratio(repeat_with, len(with_signal))
        without_rate = _safe_ratio(repeat_without, len(without_signal))
        return {
            "memory_input": label,
            "users_with_signal": len(with_signal),
            "repeat_users_with_signal": repeat_with,
            "repeat_rate_with_signal_pct": with_rate,
            "users_without_signal": len(without_signal),
            "repeat_users_without_signal": repeat_without,
            "repeat_rate_without_signal_pct": without_rate,
            "lift_pct_points": round(with_rate - without_rate, 1),
        }

    report = {
        "overview": {
            "onboarded_user_count": len(onboarded_user_ids),
            "second_session_within_14d_count": second_session_users,
            "second_session_within_14d_rate_pct": _safe_ratio(second_session_users, len(onboarded_user_ids)),
            "third_session_within_30d_count": third_session_users,
            "third_session_within_30d_rate_pct": _safe_ratio(third_session_users, len(onboarded_user_ids)),
            "repeat_sessions_total": repeat_sessions_total,
        },
        "acquisition_sources": _top_counts(acquisition_counter, limit=10),
        "session_behavior": {
            f"session_{index}": {
                "session_count": bucket["count"],
                "avg_turns_per_session": round(bucket["turns_total"] / bucket["count"], 2) if bucket["count"] else 0.0,
                "channel_distribution": _top_counts(bucket["channels"], limit=4),
                "top_intents": _top_counts(bucket["intents"], limit=6),
            }
            for index, bucket in session_behavior.items()
        },
        "recurring_anchor_intents_by_cohort": recurring_by_cohort,
        "memory_input_retention_lift": [
            memory_lift("wardrobe_items", wardrobe_users),
            memory_lift("feedback_history", feedback_users),
            memory_lift("catalog_interaction_history", catalog_users),
        ],
    }
    return report


class DependencyReportingService:
    def __init__(self, client: SupabaseRestClient) -> None:
        self._client = client

    def build_report(self) -> Dict[str, Any]:
        onboarding_profiles = self._client.select_many("onboarding_profiles", order="created_at.asc")
        dependency_events = self._client.select_many("dependency_validation_events", order="created_at.asc")
        wardrobe_items = self._client.select_many("user_wardrobe_items", order="created_at.asc")
        feedback_events = self._client.select_many("feedback_events", order="created_at.asc")
        catalog_interactions = self._client.select_many("catalog_interaction_history", order="created_at.asc")
        return build_dependency_report(
            onboarding_profiles=onboarding_profiles,
            dependency_events=dependency_events,
            wardrobe_items=wardrobe_items,
            feedback_events=feedback_events,
            catalog_interactions=catalog_interactions,
        )
