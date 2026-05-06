#!/usr/bin/env python3
"""Back-fill ``quality_signal`` on ``distillation_traces`` rows.

For each trace missing ``quality_signal``, look up downstream signals tied
to the same ``turn_id`` (currently: feedback_events) and write a small JSON
summary into the column. Distillation jobs filter
``WHERE quality_signal IS NOT NULL`` to use only labeled rows.

This script is idempotent — already-labeled rows are skipped (filter
includes ``quality_signal=is.null``). Safe to re-run.

Run manually for now:

    APP_ENV=staging python ops/scripts/backfill_quality_signal.py
    APP_ENV=staging python ops/scripts/backfill_quality_signal.py --since-hours 168 --batch-size 1000

Cron wiring is a follow-up — Pre-launch Step 1 acceptance only requires
the script to exist and run; nightly automation comes later.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[2]
for p in (ROOT, ROOT / "modules" / "platform_core" / "src"):
    sp = str(p)
    if sp not in sys.path:
        sys.path.insert(0, sp)

from platform_core.supabase_rest import SupabaseRestClient

_log = logging.getLogger(__name__)


def _load_env_file() -> None:
    """Load .env.{APP_ENV} (or .env.local) into os.environ — same idiom used
    by the catalog vector_store helpers so the two scripts behave the same
    way under APP_ENV=local|staging."""
    env_file = os.getenv("ENV_FILE", "").strip()
    app_env = os.getenv("APP_ENV", "").strip().lower()
    if not env_file and app_env == "staging":
        env_file = ".env.staging"
    elif not env_file and app_env == "local":
        env_file = ".env.local"
    elif not env_file and os.path.exists(".env.local"):
        env_file = ".env.local"
    if not env_file:
        raise RuntimeError("Set APP_ENV=local or APP_ENV=staging, or provide ENV_FILE explicitly.")
    if app_env in {"staging", "local"} and env_file and not os.path.exists(env_file):
        raise RuntimeError(f"APP_ENV={app_env} requires {env_file} to exist.")
    if env_file and os.path.exists(env_file):
        with open(env_file, "r", encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key:
                    os.environ[key] = value


def _build_client() -> SupabaseRestClient:
    rest_url = os.getenv("SUPABASE_REST_URL", "").strip()
    if not rest_url:
        base = os.getenv("SUPABASE_URL", "").strip() or os.getenv("API_URL", "").strip()
        if not base:
            raise RuntimeError("Missing SUPABASE_URL or SUPABASE_REST_URL in environment.")
        rest_url = base.rstrip("/")
        if not rest_url.endswith("/rest/v1"):
            rest_url = f"{rest_url}/rest/v1"
    service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not service_role_key:
        raise RuntimeError("Missing SUPABASE_SERVICE_ROLE_KEY in environment.")
    return SupabaseRestClient(rest_url=rest_url, service_role_key=service_role_key)


def _compute_quality_signal(turn_id: str, feedback_by_turn: Dict[str, List[str]]) -> Dict[str, Any]:
    """v1 quality signal: just propagate the user's per-turn feedback events.

    Future enhancements (intentionally out of scope for the skeleton):
      - downstream stage acceptance (did the rater pass this composer output?)
      - implicit signals (click-through, dwell time, hide actions)
      - cross-stage labels (architect→composer→rater chain quality)
    """
    events = feedback_by_turn.get(turn_id, [])
    return {
        "user_feedback_events": events,
        "has_positive": any(e in {"like", "save", "buy", "share"} for e in events),
        "has_negative": any(e in {"dislike", "skip", "hide"} for e in events),
        "computed_at": datetime.now(timezone.utc).isoformat(),
    }


def backfill(
    client: SupabaseRestClient,
    *,
    since_hours: int,
    batch_size: int,
    dry_run: bool,
) -> Dict[str, int]:
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=since_hours)).isoformat()

    pending = client.select_many(
        "distillation_traces",
        filters={
            "created_at": f"gte.{cutoff}",
            "quality_signal": "is.null",
        },
        columns="id,turn_id,stage",
        limit=batch_size,
        order="created_at.asc",
    )
    if not pending:
        _log.info("No pending traces to back-fill (cutoff=%s)", cutoff)
        return {"scanned": 0, "updated": 0, "skipped": 0}

    turn_ids = list({row["turn_id"] for row in pending if row.get("turn_id")})
    feedback_rows = client.select_many(
        "feedback_events",
        filters={"turn_id": f"in.({','.join(turn_ids)})"},
        columns="turn_id,event_type",
    ) if turn_ids else []

    feedback_by_turn: Dict[str, List[str]] = {}
    for row in feedback_rows:
        feedback_by_turn.setdefault(row["turn_id"], []).append(row.get("event_type") or "")

    updated = 0
    skipped = 0
    for trace in pending:
        signal = _compute_quality_signal(trace["turn_id"], feedback_by_turn)
        # v1: skip rows where there's no signal yet — leave NULL so the next
        # pass picks them up once feedback arrives.
        if not signal["user_feedback_events"]:
            skipped += 1
            continue
        if dry_run:
            updated += 1
            continue
        client.update_one(
            "distillation_traces",
            filters={"id": f"eq.{trace['id']}"},
            patch={"quality_signal": signal},
        )
        updated += 1

    return {"scanned": len(pending), "updated": updated, "skipped": skipped}


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--since-hours", type=int, default=25,
                        help="Look back N hours for unlabeled traces (default 25 — slight overlap with daily cron).")
    parser.add_argument("--batch-size", type=int, default=500,
                        help="Max rows scanned per run (default 500).")
    parser.add_argument("--dry-run", action="store_true",
                        help="Compute signals but skip writes.")
    args = parser.parse_args()

    _load_env_file()
    client = _build_client()
    result = backfill(
        client,
        since_hours=args.since_hours,
        batch_size=args.batch_size,
        dry_run=args.dry_run,
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
