#!/usr/bin/env python3
import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

def _discover_repo_root() -> Path:
    here = Path(__file__).resolve()
    for base in [here.parent] + list(here.parents):
        if (base / "run_catalog_enrichment.py").exists():
            return base
    return here.parents[2]


ROOT = _discover_repo_root()
for p in (
    ROOT,
    ROOT / "modules" / "catalog_enrichment" / "src",
    ROOT / "modules" / "style_engine" / "src",
):
    sp = str(p)
    if sp not in sys.path:
        sys.path.insert(0, sp)

from catalog_enrichment.config_registry import load_reinforcement_framework  # noqa: E402


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Append one outcome event row for RL-ready styling logs.")
    parser.add_argument("--log-file", required=True, help="CSV path to append event rows.")
    parser.add_argument("--request-id", required=True)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--user-id", required=True)
    parser.add_argument("--garment-id", required=True)
    parser.add_argument("--title", default="")
    parser.add_argument("--event-type", required=True, choices=["like", "share", "buy", "skip"])
    parser.add_argument("--timestamp", default="", help="Optional ISO timestamp (defaults to now UTC).")
    parser.add_argument("--notes", default="")
    return parser.parse_args()


def main() -> int:
    try:
        args = parse_args()
        cfg = load_reinforcement_framework()
        rewards = dict(cfg.get("reward_weights") or {})
        reward_value = rewards.get(args.event_type)
        if reward_value is None:
            raise ValueError(f"Missing reward mapping for event type: {args.event_type}")

        event = {
            "event_id": str(uuid4()),
            "request_id": args.request_id,
            "session_id": args.session_id,
            "user_id": args.user_id,
            "timestamp": args.timestamp or _now_iso(),
            "garment_id": args.garment_id,
            "title": args.title,
            "event_type": args.event_type,
            "reward_value": reward_value,
            "reward_policy_version": cfg.get("reward_policy_version", "reward_policy_v1"),
            "notes": args.notes,
        }

        path = Path(args.log_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        fieldnames = list(event.keys())
        file_exists = path.exists() and path.stat().st_size > 0
        with path.open("a", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            if not file_exists:
                writer.writeheader()
            writer.writerow(event)

        print(json.dumps(event, ensure_ascii=True))
        return 0
    except (ValueError, FileNotFoundError, json.JSONDecodeError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
