#!/usr/bin/env python3
"""Reranker calibration skeleton — fits learned weights from staging telemetry.

Usage:
    APP_ENV=staging python ops/scripts/calibrate_reranker.py [--days N] [--min-turns N] [--out PATH]

Reads ``tool_traces`` rows where ``tool_name='reranker_decision'`` joined with
``feedback_events`` (per ``turn_id`` + ``outfit_rank``) over the last N days
and fits a small weighted-sum model:

    effective_score = w1 * assembly_score
                    + w2 * archetype_proximity
                    + w3 * weather_time_match
                    - w4 * prior_dislike_count

Output is written to ``data/reranker_weights.json``. The Reranker reads that
file at boot via ``agentic_application.agents.reranker._load_weights``; if
absent (today's default), the legacy assembly-score-only behaviour is
preserved.

**This script intentionally stays a skeleton until staging accumulates
≥200 labelled turns.** The fit is gated on the input size — without enough
data, a curve fit produces noisy, misleading weights. The script exits
non-zero with a clear message in that case.

The May 1, 2026 commit ships:
  - the data fetch (telemetry + feedback join)
  - the labelled-turn count check
  - the JSON write contract
  - a regression-safe default emission path

The actual curve fit is a one-line scikit-learn call once enough data is
available; the TODO at the bottom of ``_fit_weights`` flags the only line
that needs to change.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

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


# Minimum labelled turns required before we trust a fit. Below this we
# emit defaults and exit non-zero so the caller knows calibration was
# skipped.
DEFAULT_MIN_LABELLED_TURNS = 200

# Default lookback window — enough that bursts of activity smooth out
# but not so long that we mix old + new architect prompt versions.
DEFAULT_DAYS = 30

DEFAULT_OUT = REPO_ROOT / "data" / "reranker_weights.json"

DEFAULT_WEIGHTS: Dict[str, float] = {
    "w_assembly_score": 1.0,
    "w_archetype_proximity": 0.0,
    "w_weather_time_match": 0.0,
    "w_prior_dislike": 0.0,
}


def _connect():
    """Resolve a Supabase REST client from the active env file.

    Returns a tuple ``(client, repo)`` where ``repo`` exposes the same
    methods used by the orchestrator (``log_tool_trace`` etc.) so we can
    re-use its query helpers.
    """
    from platform_core.config import load_config
    from platform_core.repositories import ConversationRepository
    from platform_core.supabase_rest import SupabaseRestClient

    cfg = load_config()
    client = SupabaseRestClient(
        rest_url=cfg.supabase_rest_url,
        service_role_key=cfg.supabase_service_role_key,
    )
    repo = ConversationRepository(client=client)
    return client, repo


def _fetch_decisions(client, since: datetime) -> List[Dict[str, Any]]:
    """Pull `reranker_decision` rows from `tool_traces` since the cutoff."""
    rows = client.select_many(
        "tool_traces",
        filters={"tool_name": "eq.reranker_decision"},
        order="created_at.desc",
        limit=10_000,
    )
    cutoff_iso = since.isoformat()
    return [r for r in rows if str(r.get("created_at", "")) >= cutoff_iso]


def _fetch_feedback(client, since: datetime) -> List[Dict[str, Any]]:
    """Pull feedback events since the cutoff for label resolution."""
    rows = client.select_many(
        "feedback_events",
        filters={},
        order="created_at.desc",
        limit=10_000,
    )
    cutoff_iso = since.isoformat()
    return [r for r in rows if str(r.get("created_at", "")) >= cutoff_iso]


def _rank_position_prior(feedback: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Aggregate a per-rank like rate across all feedback rows.

    The reranker emits ranked outfits at positions 0/1/2 (rank 1/2/3 on
    the user surface). When the team doesn't yet have ``reranker_decision``
    rows joined to feedback, we can still observe how feedback distributes
    across ranks. The rank with the highest like rate becomes the prior;
    the reranker can use that prior to nudge candidates within the tie
    window even before per-feature calibration is possible.

    Returns the aggregated stats. Caller decides how to convert into a
    weight delta in `data/reranker_weights.json`.
    """
    from collections import Counter

    likes = Counter()
    dislikes = Counter()
    for fb in feedback:
        rank = fb.get("outfit_rank")
        evt = str(fb.get("event_type") or "").lower()
        if rank is None or evt not in ("like", "dislike"):
            continue
        if evt == "like":
            likes[int(rank)] += 1
        else:
            dislikes[int(rank)] += 1

    stats: Dict[str, Any] = {"per_rank": {}, "total_like": 0, "total_dislike": 0}
    for rank in sorted(set(likes) | set(dislikes)):
        l = likes.get(rank, 0)
        d = dislikes.get(rank, 0)
        total = l + d
        stats["per_rank"][rank] = {
            "like": l,
            "dislike": d,
            "like_rate": (l / total) if total else 0.0,
            "n": total,
        }
        stats["total_like"] += l
        stats["total_dislike"] += d
    return stats


def _label_turns(
    decisions: List[Dict[str, Any]],
    feedback: List[Dict[str, Any]],
) -> List[Tuple[Dict[str, Any], int]]:
    """Pair each kept candidate with a label: +1 like, -1 dislike, 0 unlabelled.

    The reranker logs kept candidates with their candidate_id + rank. The
    feedback table stores user reactions per (turn_id, outfit_rank). We
    join on turn_id + rank — anything else stays 0.
    """
    fb_by_turn: Dict[str, Dict[int, str]] = {}
    for fb in feedback:
        tid = str(fb.get("turn_id") or "")
        rank = fb.get("outfit_rank")
        evt = str(fb.get("event_type") or "")
        if not tid or rank is None or not evt:
            continue
        fb_by_turn.setdefault(tid, {})[int(rank)] = evt

    labelled: List[Tuple[Dict[str, Any], int]] = []
    for dec in decisions:
        out = dec.get("output_json") or {}
        kept = out.get("kept") or []
        in_ = dec.get("input_json") or {}
        turn_id = str(dec.get("turn_id") or "")
        for c in kept:
            rank = int(c.get("rank") or -1)
            evt = fb_by_turn.get(turn_id, {}).get(rank, "")
            label = 1 if evt == "like" else (-1 if evt == "dislike" else 0)
            row = {
                "turn_id": turn_id,
                "candidate_id": c.get("candidate_id"),
                "rank": rank,
                "assembly_score": float(c.get("assembly_score") or 0.0),
                "bias": in_.get("bias") or "balanced",
            }
            labelled.append((row, label))
    return labelled


def _fit_weights(
    samples: List[Tuple[Dict[str, Any], int]],
    min_required: int,
) -> Tuple[Dict[str, float], str]:
    """Fit reranker weights or fall back to defaults with a reason message.

    Returns ``(weights, message)``. When ``samples`` (i.e. labelled
    `tool_traces.reranker_decision` rows joined to feedback) are sparse
    we keep the full-feature defaults — the reranker stays on the
    assembly-score-only path until enough decision rows accumulate.

    The rank-position prior is computed separately by ``_rank_position_prior``
    and emitted as a *metric* alongside the weights JSON. It informs human
    UX decisions (e.g., "is rank-3 even worth shipping?") rather than the
    reranker's per-candidate scoring.
    """
    weights = dict(DEFAULT_WEIGHTS)
    labelled = [s for s in samples if s[1] != 0]

    if len(labelled) < min_required:
        return (
            weights,
            f"reranker_decision rows: have {len(labelled)} labelled, "
            f"need ≥{min_required} for the full feature fit. Emitting defaults.",
        )

    # TODO(staging-ready, blocked on data): replace with a real fit.
    # The shape we want once decision-log data is available:
    #   import numpy as np
    #   from sklearn.linear_model import Ridge
    #   X = np.array([[s["assembly_score"], <archetype_prox>, <weather_match>, <prior_dislike>]
    #                 for s, _ in labelled])
    #   y = np.array([label for _, label in labelled])
    #   model = Ridge(alpha=1.0).fit(X, y)
    #   weights["w_assembly_score"] = float(model.coef_[0])
    #   weights["w_archetype_proximity"] = float(model.coef_[1])
    #   weights["w_weather_time_match"] = float(model.coef_[2])
    #   weights["w_prior_dislike"] = float(-model.coef_[3])
    notes.append(
        f"{len(labelled)} labelled turns available — full Ridge fit still a "
        f"TODO. See _fit_weights() in this file."
    )
    return (weights, " | ".join(notes))


def _emit(
    weights: Dict[str, float],
    out_path: Path,
    message: str,
    *,
    metrics: Optional[Dict[str, Any]] = None,
) -> None:
    """Write the reranker weights file with optional observability metrics.

    The reranker reads only the ``weights`` block at boot; ``metrics`` is
    operational telemetry (e.g., observed rank-position like-rate gap)
    persisted alongside so dashboards and UX decisions can reason about
    user behaviour without a separate query.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload: Dict[str, Any] = {
        "weights": weights,
        "metadata": {
            "fitted_at": datetime.now(timezone.utc).isoformat(),
            "message": message,
        },
    }
    if metrics:
        payload["metrics"] = metrics
    with out_path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
    print(f"Wrote {out_path}")
    print(f"  {message}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=DEFAULT_DAYS,
                        help="lookback window in days (default 30)")
    parser.add_argument("--min-turns", type=int, default=DEFAULT_MIN_LABELLED_TURNS,
                        help="minimum labelled turns required to fit (default 200)")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT,
                        help="output JSON path")
    parser.add_argument("--dry-run", action="store_true",
                        help="run the data fetch but skip writing the weights file")
    args = parser.parse_args()

    if not os.environ.get("APP_ENV") and not os.environ.get("ENV_FILE"):
        print("Set APP_ENV=staging (or ENV_FILE=...) so the supabase client can find creds.", file=sys.stderr)
        return 2

    cutoff = datetime.now(timezone.utc) - timedelta(days=args.days)
    print(f"Fetching reranker_decision rows since {cutoff.isoformat()}…")

    try:
        client, _ = _connect()
        decisions = _fetch_decisions(client, cutoff)
        feedback = _fetch_feedback(client, cutoff)
    except Exception as exc:  # noqa: BLE001 — script-level
        print(f"Failed to fetch telemetry: {exc}", file=sys.stderr)
        return 3

    samples = _label_turns(decisions, feedback)
    rank_prior = _rank_position_prior(feedback)
    weights, message = _fit_weights(samples, args.min_turns)

    metrics: Dict[str, Any] = {
        "decision_log_rows": len(decisions),
        "feedback_rows": len(feedback),
        "labelled_samples": sum(1 for s in samples if s[1] != 0),
    }
    if rank_prior and rank_prior.get("per_rank"):
        rates = {
            str(r): round(stats["like_rate"], 4)
            for r, stats in rank_prior["per_rank"].items()
            if stats["n"]
        }
        if rates:
            metrics["rank_position_like_rate"] = rates
            metrics["rank_position_spread"] = round(max(rates.values()) - min(rates.values()), 4)
            metrics["rank_position_total_likes"] = rank_prior.get("total_like", 0)
            metrics["rank_position_total_dislikes"] = rank_prior.get("total_dislike", 0)
            print(f"  rank_position_like_rate: {rates}")

    if args.dry_run:
        print(f"[dry-run] would emit weights={weights}")
        print(f"[dry-run] would emit metrics={metrics}")
        print(f"[dry-run] {message}")
        # Exit 1 when calibration was skipped due to sparse data so callers
        # can detect the no-op state. Defaults are the safe outcome.
        return 1 if weights == DEFAULT_WEIGHTS else 0

    _emit(weights, args.out, message, metrics=metrics)
    # Exit 1 when we wrote defaults due to sparse data; 0 once a real
    # fit replaces them.
    return 1 if weights == DEFAULT_WEIGHTS else 0


if __name__ == "__main__":
    sys.exit(main())
