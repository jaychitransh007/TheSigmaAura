#!/usr/bin/env python3
"""Seed an in-memory dataset and assert the dependency report aggregates correctly.

Usage:
    python ops/scripts/validate_dependency_report.py

Exits 0 on success, 1 on the first failed assertion.

This is an executable validation harness for ``build_dependency_report``. It
seeds:
  - 5 onboarded users across 2 acquisition cohorts
  - a mix of single-session, repeat-session and 3+ session users
  - both web and whatsapp turns
  - wardrobe / feedback / catalog signals so the memory-lift section has data
And then asserts the expected counts and rates.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
for p in (
    REPO_ROOT,
    REPO_ROOT / "modules" / "user" / "src",
    REPO_ROOT / "modules" / "agentic_application" / "src",
    REPO_ROOT / "modules" / "catalog" / "src",
    REPO_ROOT / "modules" / "platform_core" / "src",
    REPO_ROOT / "modules" / "user_profiler" / "src",
):
    sp = str(p)
    if sp not in sys.path:
        sys.path.insert(0, sp)

from agentic_application.intent_registry import Intent  # noqa: E402
from agentic_application.services.dependency_reporting import (  # noqa: E402
    build_dependency_report,
)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def main() -> int:
    base = datetime(2026, 4, 1, 9, 0, tzinfo=timezone.utc)

    # ---- 5 onboarded users across 2 cohorts ----
    onboarding_profiles = [
        {"user_id": f"u{i}", "onboarding_complete": True, "acquisition_source": cohort}
        for i, cohort in enumerate(
            ["instagram", "instagram", "instagram", "referral", "referral"], start=1
        )
    ]

    # ---- Sessions:
    #   u1: 1 session  (no repeat)
    #   u2: 2 sessions, 5 days apart (within 14d  -> counts as second_session)
    #   u3: 3 sessions, 5 + 20 days apart (3rd within 30d -> counts as third_session)
    #   u4: 1 session
    #   u5: 2 sessions, 10 days apart (within 14d)
    dep_events = []

    def turn(user, ts, channel="web", intent=Intent.OCCASION_RECOMMENDATION,
             memory_sources=None):
        dep_events.append({
            "user_id": user,
            "event_type": "turn_completed",
            "primary_intent": intent,
            "source_channel": channel,
            "metadata_json": {"memory_sources_read": memory_sources or []},
            "created_at": _iso(ts),
        })

    # u1 — single session
    turn("u1", base)

    # u2 — second session within 14d
    turn("u2", base)
    turn("u2", base + timedelta(days=5))

    # u3 — three sessions within 30d
    turn("u3", base)
    turn("u3", base + timedelta(days=5))
    turn("u3", base + timedelta(days=20), channel="whatsapp",
         intent=Intent.PAIRING_REQUEST)

    # u4 — single session
    turn("u4", base)

    # u5 — second session within 14d, used wardrobe memory
    turn("u5", base, memory_sources=["wardrobe_memory"])
    turn("u5", base + timedelta(days=10), memory_sources=["wardrobe_memory"])

    # ---- Memory-lift signals:
    #   wardrobe_items: u3, u5
    #   feedback events: u3
    #   catalog interactions: u2
    wardrobe_items = [
        {"user_id": "u3", "is_active": True},
        {"user_id": "u5", "is_active": True},
    ]
    # feedback events (the report counts feedback_submission turns, not raw rows)
    dep_events.append({
        "user_id": "u3",
        "event_type": "turn_completed",
        "primary_intent": Intent.FEEDBACK_SUBMISSION,
        "source_channel": "web",
        "metadata_json": {},
        "created_at": _iso(base + timedelta(days=21)),
    })
    catalog_interactions = [{"user_id": "u2"}]
    feedback_events = []  # report uses dep_events for feedback_users

    report = build_dependency_report(
        onboarding_profiles=onboarding_profiles,
        dependency_events=dep_events,
        wardrobe_items=wardrobe_items,
        feedback_events=feedback_events,
        catalog_interactions=catalog_interactions,
    )

    failures: list[str] = []

    def expect(label: str, actual, expected) -> None:
        if actual != expected:
            failures.append(f"{label}: expected {expected!r}, got {actual!r}")
        else:
            print(f"  PASS: {label} = {actual}")

    overview = report["overview"]
    expect("onboarded_user_count", overview["onboarded_user_count"], 5)
    # u2, u3, u5 -> 3 users with second session within 14d
    expect("second_session_within_14d_count", overview["second_session_within_14d_count"], 3)
    # u3 -> 1 user with third session within 30d
    expect("third_session_within_30d_count", overview["third_session_within_30d_count"], 1)

    # acquisition cohorts
    cohort_counts = {row["key"]: row["count"] for row in report["acquisition_sources"]}
    expect("acquisition_sources.instagram", cohort_counts.get("instagram"), 3)
    expect("acquisition_sources.referral", cohort_counts.get("referral"), 2)

    # memory lift: wardrobe signal
    wardrobe_lift = next(
        row for row in report["memory_input_retention_lift"]
        if row["memory_input"] == "wardrobe_items"
    )
    expect("wardrobe_lift.users_with_signal", wardrobe_lift["users_with_signal"], 2)
    # u3 (3 sessions) and u5 (2 sessions) both repeat -> 2/2 = 100%
    expect("wardrobe_lift.repeat_users_with_signal", wardrobe_lift["repeat_users_with_signal"], 2)
    expect("wardrobe_lift.repeat_rate_with_signal_pct", wardrobe_lift["repeat_rate_with_signal_pct"], 100.0)

    # session behavior
    sb = report["session_behavior"]
    expect("session_1.session_count", sb["session_1"]["session_count"], 5)
    expect("session_2.session_count", sb["session_2"]["session_count"], 3)
    expect("session_3.session_count", sb["session_3"]["session_count"], 1)

    # whatsapp channel made it through into session 3
    s3_channels = {row["key"]: row["count"] for row in sb["session_3"]["channel_distribution"]}
    expect("session_3.channel_distribution.whatsapp", s3_channels.get("whatsapp"), 1)

    if failures:
        print()
        print("FAILED:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print()
    print(f"All {len([k for k in dir() if not k.startswith('_')])} assertions passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
