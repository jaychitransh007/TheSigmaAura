#!/usr/bin/env python3
"""Sweep aged observability rows — Item 12 of Observability Hardening (May 1, 2026).

Deletes from the high-volume observability tables (``model_call_logs``,
``tool_traces``, ``turn_traces``) where ``created_at < now() - N days``.
The aggregate-y tables that serve dashboards (``feedback_events``,
``dependency_validation_events``, ``policy_event_log``, ``user_comfort_learning``)
are NOT swept by this script — those rows feed retention / lift metrics
that need long-term history.

Usage:
    python3 ops/scripts/cleanup_observability_logs.py [--days N] [--dry-run]
        [--tables model_call_logs,tool_traces,turn_traces]

Recommend running daily as a cron / GitHub Action / Supabase scheduled
function with --days 30. Idempotent — re-running on the same day deletes
nothing further.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, List

REPO_ROOT = Path(__file__).resolve().parents[2]
for p in (
    REPO_ROOT,
    REPO_ROOT / "modules" / "platform_core" / "src",
    REPO_ROOT / "modules" / "user_profiler" / "src",
):
    sp = str(p)
    if sp not in sys.path:
        sys.path.insert(0, sp)


DEFAULT_DAYS = 30
DEFAULT_TABLES = ("model_call_logs", "tool_traces", "turn_traces")
DEFAULT_PAGE_SIZE = 500


def _connect():
    from platform_core.config import load_config
    from platform_core.supabase_rest import SupabaseRestClient

    cfg = load_config()
    return SupabaseRestClient(
        rest_url=cfg.supabase_rest_url,
        service_role_key=cfg.supabase_service_role_key,
    )


def _sweep_table(client, table: str, cutoff_iso: str, dry_run: bool) -> int:
    """Delete rows older than ``cutoff_iso`` in pages of 500."""
    total = 0
    while True:
        rows = client.select_many(
            table,
            filters={"created_at": f"lt.{cutoff_iso}"},
            columns="id",
            limit=DEFAULT_PAGE_SIZE,
        )
        if not rows:
            break
        if dry_run:
            total += len(rows)
            # Estimate how many pages remain by re-checking; only run
            # one page for dry-run to keep it fast.
            print(f"  [dry-run] {table}: would delete {len(rows)} rows in this page; sample of remaining set")
            return total
        for r in rows:
            try:
                client.delete_one(table, filters={"id": f"eq.{r['id']}"})
                total += 1
            except Exception as exc:  # noqa: BLE001
                print(f"  WARN: delete failed for {table}.id={r['id']}: {exc}", file=sys.stderr)
        if len(rows) < DEFAULT_PAGE_SIZE:
            break
    return total


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=DEFAULT_DAYS,
                        help=f"Retention window in days (default {DEFAULT_DAYS}).")
    parser.add_argument("--dry-run", action="store_true",
                        help="Only count rows that would be deleted.")
    parser.add_argument("--tables", default=",".join(DEFAULT_TABLES),
                        help="Comma-separated list of observability tables to sweep.")
    args = parser.parse_args(argv)

    cutoff = datetime.now(timezone.utc) - timedelta(days=args.days)
    cutoff_iso = cutoff.isoformat()
    tables = [t.strip() for t in args.tables.split(",") if t.strip()]

    print(f"Cutoff: {cutoff_iso} ({args.days} days back)")
    print(f"Tables: {', '.join(tables)}")
    if args.dry_run:
        print("Mode:   dry-run (no deletes)")
    else:
        print("Mode:   live")

    try:
        client = _connect()
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: could not connect to Supabase: {exc}", file=sys.stderr)
        return 2

    grand_total = 0
    for table in tables:
        try:
            n = _sweep_table(client, table, cutoff_iso, args.dry_run)
        except Exception as exc:  # noqa: BLE001
            print(f"ERROR sweeping {table}: {exc}", file=sys.stderr)
            return 3
        grand_total += n
        verb = "would delete" if args.dry_run else "deleted"
        print(f"  {table}: {verb} {n} row(s)")

    print(f"Total: {grand_total}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
