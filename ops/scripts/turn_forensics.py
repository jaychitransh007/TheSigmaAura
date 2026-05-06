"""Per-turn forensics for the composition engine + LLM pipeline.

Pulls a turn (or two for side-by-side comparison) from
``turn_traces`` + ``distillation_traces`` + ``model_call_logs`` and
prints a comparison report covering step-by-step latency, the
router decision, token counts, and a rough cost estimate.

This is the script we kept hand-rolling in ad-hoc Python during
flag-on testing — codified so the next forensic dive is one
command instead of a fresh script.

Usage:

    APP_ENV=staging PYTHONPATH=modules/agentic_application/src:modules/catalog/src:modules/platform_core/src:modules/style_engine/src:modules/user/src:modules/user_profiler/src \\
        python ops/scripts/turn_forensics.py <turn_id>

    # Side-by-side compare (left vs right; left is "after"):
    APP_ENV=staging PYTHONPATH=... python ops/scripts/turn_forensics.py \\
        <new_turn_id> --baseline <old_turn_id>

    # The 5 most-recent turns (no args):
    APP_ENV=staging PYTHONPATH=... python ops/scripts/turn_forensics.py --recent 5
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

_REPO_ROOT = Path(__file__).resolve().parents[2]


# Cost estimates (USD per 1M tokens) — May 2026 lineup. Approximate;
# the orchestrator's cost_estimator is the source of truth for billing,
# this script is read-only and only needs ballpark numbers for ops.
_COST_PER_M_INPUT: Dict[str, float] = {
    "gpt-5.2": 2.50,
    "gpt-5.4": 2.50,
    "gpt-5-mini": 0.50,
    "text-embedding-3-small": 0.02,
}
_COST_PER_M_OUTPUT: Dict[str, float] = {
    "gpt-5.2": 10.00,
    "gpt-5.4": 10.00,
    "gpt-5-mini": 2.00,
    "text-embedding-3-small": 0.0,
}
_COST_PER_RENDER_USD = 0.04  # Gemini virtual_tryon


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _client():
    from platform_core.supabase_rest import SupabaseRestClient

    rest_url = os.environ["SUPABASE_URL"].rstrip("/") + "/rest/v1"
    return SupabaseRestClient(
        rest_url=rest_url,
        service_role_key=os.environ["SUPABASE_SERVICE_ROLE_KEY"],
    )


def _fetch_turn(client, turn_id: str) -> Optional[Dict[str, Any]]:
    rows = client.select_many(
        "turn_traces",
        columns="turn_id,user_message,total_latency_ms,steps,created_at",
        filters={"turn_id": f"eq.{turn_id}"},
        limit=1,
    )
    return rows[0] if rows else None


def _fetch_distillation(client, turn_id: str) -> List[Dict[str, Any]]:
    return client.select_many(
        "distillation_traces",
        columns="stage,model,latency_ms,full_output",
        filters={"turn_id": f"eq.{turn_id}"},
        order="created_at.asc",
        limit=20,
    )


def _fetch_model_calls(client, turn_id: str) -> List[Dict[str, Any]]:
    return client.select_many(
        "model_call_logs",
        columns="call_type,model,latency_ms,prompt_tokens,completion_tokens,status",
        filters={"turn_id": f"eq.{turn_id}"},
        order="created_at.asc",
        limit=30,
    )


def _fetch_recent_turns(client, n: int) -> List[Dict[str, Any]]:
    return client.select_many(
        "turn_traces",
        columns="turn_id,user_message,total_latency_ms,created_at",
        filters={},
        order="created_at.desc",
        limit=n,
    )


def _estimate_cost(model_calls: List[Dict[str, Any]]) -> float:
    total = 0.0
    render_count = 0
    for m in model_calls:
        ct = m.get("call_type") or ""
        model = m.get("model") or ""
        prompt = int(m.get("prompt_tokens") or 0)
        completion = int(m.get("completion_tokens") or 0)
        if ct.startswith("virtual_tryon") and not ct.endswith("cache_hit"):
            render_count += 1
            continue
        in_rate = _COST_PER_M_INPUT.get(model, 0.0)
        out_rate = _COST_PER_M_OUTPUT.get(model, 0.0)
        total += (prompt * in_rate + completion * out_rate) / 1_000_000
    total += render_count * _COST_PER_RENDER_USD
    return total


def _router_decision_for_turn(distillation: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    for d in distillation:
        if d.get("stage") != "outfit_architect":
            continue
        out = d.get("full_output")
        if isinstance(out, dict) and "router_decision" in out:
            return out["router_decision"]
    return None


def _format_short_id(turn_id: str) -> str:
    return turn_id[:8] if turn_id else "?"


def _print_one_turn(client, turn_id: str) -> None:
    turn = _fetch_turn(client, turn_id)
    if not turn:
        print(f"turn {turn_id} not found", file=sys.stderr)
        return
    distillation = _fetch_distillation(client, turn_id)
    model_calls = _fetch_model_calls(client, turn_id)
    cost = _estimate_cost(model_calls)
    rd = _router_decision_for_turn(distillation)

    print(f"\n=== TURN {turn_id} ===")
    print(f"  user_message:     {(turn.get('user_message') or '')[:120]}")
    print(f"  created_at:       {turn.get('created_at')}")
    print(f"  total_latency_ms: {turn.get('total_latency_ms')}")
    print(f"  estimated_cost:   ${cost:.3f}")

    print("\n  --- ROUTER DECISION ---")
    if rd:
        print(f"  used_engine:      {rd.get('used_engine')}")
        print(f"  fallback_reason:  {rd.get('fallback_reason')}")
        print(f"  engine_confidence: {rd.get('engine_confidence')}")
        print(f"  engine_ms:        {rd.get('engine_ms')}")
        print(f"  yaml_gaps:        {rd.get('yaml_gaps')}")
        psum = rd.get("provenance_summary") or {}
        if psum:
            for k in ("omitted", "hard_widened", "soft_relaxed"):
                attrs = psum.get(k) or []
                if attrs:
                    print(f"  {k:<16}  {attrs}")
    else:
        print("  (no router_decision metadata — pre-PR-#150 turn or cache hit)")

    print("\n  --- STEPS (latency_ms) ---")
    for s in (turn.get("steps") or []):
        print(
            f"  {s.get('step', '?'):<22} model={str(s.get('model') or '-'):<28} ms={s.get('latency_ms')}  status={s.get('status')}"
        )

    print("\n  --- MODEL_CALL_LOGS ---")
    for m in model_calls:
        print(
            f"  {m['call_type']:<28} model={str(m.get('model') or '-'):<22} "
            f"ms={m.get('latency_ms'):>6}  "
            f"prompt={int(m.get('prompt_tokens') or 0):>5} "
            f"completion={int(m.get('completion_tokens') or 0):>5}  status={m.get('status')}"
        )


def _print_side_by_side(client, left_id: str, right_id: str) -> None:
    """Side-by-side latency table for two turns. Left is "after" /
    new; right is "baseline" / older. Useful when comparing a
    flag-on engine turn against its flag-off counterpart."""
    left_turn = _fetch_turn(client, left_id)
    right_turn = _fetch_turn(client, right_id)
    if not left_turn or not right_turn:
        print("one or both turns not found", file=sys.stderr)
        return
    l_d = _fetch_distillation(client, left_id)
    r_d = _fetch_distillation(client, right_id)
    l_m = _fetch_model_calls(client, left_id)
    r_m = _fetch_model_calls(client, right_id)

    l_steps = {s.get("step"): s.get("latency_ms") for s in (left_turn.get("steps") or [])}
    r_steps = {s.get("step"): s.get("latency_ms") for s in (right_turn.get("steps") or [])}
    l_steps["TOTAL"] = left_turn.get("total_latency_ms")
    r_steps["TOTAL"] = right_turn.get("total_latency_ms")

    stage_order = [
        "validate_request", "onboarding_gate", "user_context",
        "copilot_planner", "outfit_architect", "catalog_search",
        "outfit_composer", "outfit_rater", "tryon_render",
        "response_formatting", "attach_tryon_images", "TOTAL",
    ]

    l_short, r_short = _format_short_id(left_id), _format_short_id(right_id)
    print(f"\n{'stage':<22} | {l_short:>10} | {r_short:>10} | {'Δ ms':>10}")
    print("-" * 64)
    for st in stage_order:
        l_v = l_steps.get(st)
        r_v = r_steps.get(st)
        delta = ""
        if isinstance(l_v, int) and isinstance(r_v, int):
            delta = f"{l_v - r_v:+d}"
        print(
            f"{st:<22} | "
            f"{str(l_v) if l_v is not None else '-':>10} | "
            f"{str(r_v) if r_v is not None else '-':>10} | "
            f"{delta:>10}"
        )

    l_cost = _estimate_cost(l_m)
    r_cost = _estimate_cost(r_m)
    print(f"\n{'cost (est)':<22} | ${l_cost:>9.3f} | ${r_cost:>9.3f} | ${l_cost-r_cost:+.3f}")

    l_rd = _router_decision_for_turn(l_d)
    r_rd = _router_decision_for_turn(r_d)
    print(f"\n{'used_engine':<22} | {str(l_rd.get('used_engine') if l_rd else '-'):>10} | {str(r_rd.get('used_engine') if r_rd else '-'):>10} |")
    print(f"{'fallback_reason':<22} | {str(l_rd.get('fallback_reason') if l_rd else '-'):>10} | {str(r_rd.get('fallback_reason') if r_rd else '-'):>10} |")
    print(f"{'engine_ms':<22} | {str(l_rd.get('engine_ms') if l_rd else '-'):>10} | {str(r_rd.get('engine_ms') if r_rd else '-'):>10} |")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("turn_id", nargs="?", help="Turn UUID to inspect")
    parser.add_argument("--baseline", help="Compare turn_id (newer) vs --baseline (older)")
    parser.add_argument("--recent", type=int, default=0, help="Show the N most-recent turns and exit")
    parser.add_argument(
        "--env-file",
        type=Path,
        default=_REPO_ROOT / ".env.staging",
        help="Path to env file with Supabase keys (default: .env.staging)",
    )
    args = parser.parse_args(argv)

    _load_dotenv(args.env_file)
    if not os.environ.get("SUPABASE_URL"):
        print("SUPABASE_URL not set; ensure --env-file is correct", file=sys.stderr)
        return 2

    sys.path.insert(0, str(_REPO_ROOT / "modules" / "platform_core" / "src"))
    client = _client()

    if args.recent:
        for t in _fetch_recent_turns(client, args.recent):
            print(json.dumps({
                "turn_id": t["turn_id"],
                "msg": (t.get("user_message") or "")[:60],
                "ms": t.get("total_latency_ms"),
                "at": t.get("created_at"),
            }))
        return 0

    if not args.turn_id:
        parser.error("turn_id (or --recent N) required")

    if args.baseline:
        _print_side_by_side(client, args.turn_id, args.baseline)
    else:
        _print_one_turn(client, args.turn_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
