#!/usr/bin/env python3
import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from catalog_enrichment.config_registry import load_reinforcement_framework  # noqa: E402
from catalog_enrichment.styling_filters import (  # noqa: E402
    UserContext,
    filter_catalog_rows,
    filter_catalog_rows_minimal_hard,
    load_tier_a_rules,
    parse_relaxed_filters,
    read_csv_rows as read_filter_csv_rows,
    write_csv_rows,
)
from catalog_enrichment.tier2_ranker import (  # noqa: E402
    load_tier2_rules,
    rank_garments,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run full styling engine: hard filters + Tier 2 ranking + RL-ready logs."
    )
    parser.add_argument("--input", default="out/enriched.csv", help="Input enriched CSV.")
    parser.add_argument("--profile", required=True, help="User profile JSON path for Tier 2 ranking.")
    parser.add_argument("--occasion", required=True, help="Occasion context (e.g. 'Night Out').")
    parser.add_argument("--archetype", required=True, help="Archetype context (e.g. 'Glamorous').")
    parser.add_argument("--gender", required=True, help="User gender.")
    parser.add_argument("--age", required=True, help="Age band: 18-24, 25-30, 30-35.")
    parser.add_argument("--user-id", default="anonymous", help="User id for telemetry logs.")
    parser.add_argument("--session-id", default="", help="Session id for telemetry logs (auto-generated if empty).")
    parser.add_argument(
        "--hard-filter-profile",
        default="rl_ready_minimal",
        choices=["rl_ready_minimal", "legacy"],
        help="Hard filter profile. Use rl_ready_minimal for ML/RL-ready architecture.",
    )
    parser.add_argument(
        "--relax",
        action="append",
        default=[],
        help=(
            "Relax Tier 1 hard filters in legacy mode only: price, age, archetype, occasion_archetype. "
            "Repeat or comma-separate."
        ),
    )
    parser.add_argument(
        "--tier2-strictness",
        default="balanced",
        choices=["safe", "balanced", "bold"],
        help="Tier 2 strictness profile.",
    )
    parser.add_argument("--limit", type=int, default=0, help="Optional max displayed ranked rows (0 = all).")
    parser.add_argument("--out-dir", default="out", help="Output directory for artifacts.")
    parser.add_argument("--prefix", default="style_pipeline", help="Artifact filename prefix.")
    return parser.parse_args()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_ranked_csv(path: Path, rows: List[Dict[str, str]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _write_csv(path: Path, rows: List[Dict[str, Any]], fieldnames: List[str] | None = None) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    if fieldnames is None:
        fieldnames = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _strip_internal_fields(row: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(row)
    out.pop("_row_idx", None)
    return out


def _build_summary_rows(ranked_rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    for i, row in enumerate(ranked_rows, start=1):
        out.append(
            {
                "rank": str(i),
                "id": str(row.get("id", "")),
                "title": str(row.get("title", "")),
                "images__0__src": str(row.get("images__0__src", "")),
                "images__1__src": str(row.get("images__1__src", "")),
                "tier2_final_score": str(row.get("tier2_final_score", "")),
                "tier2_max_score": str(row.get("tier2_max_score", "")),
                "tier2_compatibility_confidence": str(row.get("tier2_compatibility_confidence", "")),
                "tier2_flags": str(row.get("tier2_flags", "")),
            }
        )
    return out


def _filter_rows(
    rows: List[Dict[str, str]],
    ctx: UserContext,
    t1_rules: Dict[str, Any],
    hard_filter_profile: str,
    relax_args: List[str],
) -> Tuple[List[Dict[str, str]], List[Dict[str, Any]], List[str]]:
    if hard_filter_profile == "legacy":
        relaxed = parse_relaxed_filters(relax_args)
        passed, failed = filter_catalog_rows(rows=rows, ctx=ctx, rules=t1_rules, relaxed_filters=relaxed)
        return passed, failed, sorted(relaxed)

    passed, failed = filter_catalog_rows_minimal_hard(rows=rows, ctx=ctx, rules=t1_rules)
    return passed, failed, []


def _build_candidate_logs(
    all_rows: List[Dict[str, str]],
    failed_by_idx: Dict[str, List[str]],
    ranked_by_idx: Dict[str, Dict[str, str]],
    rank_pos_by_idx: Dict[str, int],
    request_id: str,
    session_id: str,
    user_id: str,
    context_payload: Dict[str, Any],
    scoring_formula_version: str,
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    context_json = json.dumps(context_payload, ensure_ascii=True, separators=(",", ":"))
    for row in all_rows:
        idx = str(row.get("_row_idx", ""))
        fail_reasons = failed_by_idx.get(idx, [])
        ranked_row = ranked_by_idx.get(idx, {})
        is_pass = len(fail_reasons) == 0
        out.append(
            {
                "request_id": request_id,
                "session_id": session_id,
                "user_id": user_id,
                "timestamp": _now_iso(),
                "row_idx": idx,
                "garment_id": row.get("id", ""),
                "title": row.get("title", ""),
                "store": row.get("store", ""),
                "price": row.get("price", ""),
                "primary_color": row.get("PrimaryColor", ""),
                "secondary_color": row.get("SecondaryColor", ""),
                "hard_filter_pass": "1" if is_pass else "0",
                "hard_filter_fail_reasons": "|".join(fail_reasons),
                "shown_rank_position": str(rank_pos_by_idx.get(idx, "")),
                "total_score": ranked_row.get("tier2_final_score", ""),
                "max_score": ranked_row.get("tier2_max_score", ""),
                "compatibility_confidence": ranked_row.get("tier2_compatibility_confidence", ""),
                "scoring_formula_version": scoring_formula_version,
                "user_context_json": context_json,
            }
        )
    return out


def _build_impression_logs(
    ranked_rows: List[Dict[str, str]],
    request_id: str,
    session_id: str,
    user_id: str,
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for rank_pos, row in enumerate(ranked_rows, start=1):
        out.append(
            {
                "request_id": request_id,
                "session_id": session_id,
                "user_id": user_id,
                "timestamp": _now_iso(),
                "shown_rank_position": rank_pos,
                "garment_id": row.get("id", ""),
                "title": row.get("title", ""),
                "total_score": row.get("tier2_final_score", ""),
                "max_score": row.get("tier2_max_score", ""),
                "compatibility_confidence": row.get("tier2_compatibility_confidence", ""),
                "exploration_flag": "0",
                "propensity": "",
            }
        )
    return out


def _build_outcome_template_logs(
    ranked_rows: List[Dict[str, str]],
    request_id: str,
    session_id: str,
    user_id: str,
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for row in ranked_rows:
        out.append(
            {
                "event_id": str(uuid4()),
                "request_id": request_id,
                "session_id": session_id,
                "user_id": user_id,
                "timestamp": "",
                "garment_id": row.get("id", ""),
                "title": row.get("title", ""),
                "event_type": "",
                "reward_value": "",
                "notes": "Fill event_type with one of: like, share, buy, skip",
            }
        )
    return out


def main() -> int:
    try:
        args = parse_args()
        out_dir = Path(args.out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        rf_cfg = load_reinforcement_framework()
        request_id = str(uuid4())
        session_id = args.session_id.strip() or str(uuid4())
        user_id = args.user_id.strip() or "anonymous"

        filtered_csv = out_dir / f"{args.prefix}_filtered.csv"
        filter_failures_json = out_dir / f"{args.prefix}_filter_failures.json"
        ranked_csv = out_dir / f"{args.prefix}_ranked.csv"
        explain_json = out_dir / f"{args.prefix}_ranked_explainability.json"
        summary_csv = out_dir / f"{args.prefix}_ranked_summary.csv"
        request_log_json = out_dir / f"{args.prefix}_request_log.json"
        candidate_log_csv = out_dir / f"{args.prefix}_candidate_set_log.csv"
        impression_log_csv = out_dir / f"{args.prefix}_impression_log.csv"
        outcome_template_csv = out_dir / f"{args.prefix}_outcome_event_log_template.csv"

        rows = read_filter_csv_rows(args.input)
        for i, r in enumerate(rows):
            r["_row_idx"] = str(i)

        with open(args.profile, "r", encoding="utf-8") as f:
            profile = json.load(f)

        t1_rules = load_tier_a_rules()
        t2_rules = load_tier2_rules()
        ctx = UserContext(
            occasion=args.occasion,
            archetype=args.archetype,
            gender=args.gender,
            age=args.age,
        )

        passed, failed, relaxed = _filter_rows(
            rows=rows,
            ctx=ctx,
            t1_rules=t1_rules,
            hard_filter_profile=args.hard_filter_profile,
            relax_args=args.relax,
        )
        write_csv_rows(str(filtered_csv), [_strip_internal_fields(r) for r in passed])

        with filter_failures_json.open("w", encoding="utf-8") as f:
            json.dump(
                {
                    "request_id": request_id,
                    "session_id": session_id,
                    "user_id": user_id,
                    "total_rows": len(rows),
                    "passed_rows": len(passed),
                    "failed_rows": len(failed),
                    "hard_filter_profile": args.hard_filter_profile,
                    "context": {
                        "occasion": args.occasion,
                        "archetype": args.archetype,
                        "gender": args.gender,
                        "age": args.age,
                        "relaxed_filters": relaxed,
                    },
                    "failures": failed,
                },
                f,
                ensure_ascii=True,
                indent=2,
            )

        ranked_all = rank_garments(rows=passed, user_profile=profile, rules=t2_rules, strictness=args.tier2_strictness)
        if args.limit > 0:
            ranked_all = ranked_all[: args.limit]

        ranked_rows = [_strip_internal_fields(r.row) for r in ranked_all]
        _write_ranked_csv(ranked_csv, ranked_rows)
        _write_csv(summary_csv, _build_summary_rows(ranked_rows))

        failed_by_idx = {}
        for f in failed:
            idx = str(f.get("row_idx", ""))
            if not idx:
                # fallback resolve by id/title if row_idx not provided
                for r in rows:
                    if r.get("id", "") == f.get("id", "") and r.get("title", "") == f.get("title", ""):
                        idx = str(r.get("_row_idx", ""))
                        break
            failed_by_idx[idx] = list(f.get("fail_reasons", []))

        ranked_by_idx: Dict[str, Dict[str, str]] = {}
        rank_pos_by_idx: Dict[str, int] = {}
        for pos, rr in enumerate(ranked_rows, start=1):
            idx = str(rr.get("_row_idx", ""))
            if idx:
                ranked_by_idx[idx] = rr
                rank_pos_by_idx[idx] = pos
        if not ranked_by_idx:
            # if _row_idx stripped, recover from passed rows in order
            for pos, rr in enumerate(ranked_rows, start=1):
                for pr in passed:
                    if pr.get("id", "") == rr.get("id", "") and pr.get("title", "") == rr.get("title", ""):
                        idx = str(pr.get("_row_idx", ""))
                        ranked_by_idx[idx] = rr
                        rank_pos_by_idx[idx] = pos
                        break

        context_payload = {
            "occasion": args.occasion,
            "age": args.age,
            "gender": args.gender,
            "archetype": args.archetype,
            "body_harmony": {k: v for k, v in profile.items() if k != "color_preferences"},
            "color_preferences": profile.get("color_preferences", {}),
        }
        candidate_rows = _build_candidate_logs(
            all_rows=rows,
            failed_by_idx=failed_by_idx,
            ranked_by_idx=ranked_by_idx,
            rank_pos_by_idx=rank_pos_by_idx,
            request_id=request_id,
            session_id=session_id,
            user_id=user_id,
            context_payload=context_payload,
            scoring_formula_version="tier2_formula_v1",
        )
        _write_csv(candidate_log_csv, candidate_rows)

        impression_rows = _build_impression_logs(
            ranked_rows=ranked_rows,
            request_id=request_id,
            session_id=session_id,
            user_id=user_id,
        )
        _write_csv(impression_log_csv, impression_rows)
        outcome_template_rows = _build_outcome_template_logs(
            ranked_rows=ranked_rows,
            request_id=request_id,
            session_id=session_id,
            user_id=user_id,
        )
        _write_csv(outcome_template_csv, outcome_template_rows)

        with request_log_json.open("w", encoding="utf-8") as f:
            json.dump(
                {
                    "request_id": request_id,
                    "session_id": session_id,
                    "user_id": user_id,
                    "timestamp": _now_iso(),
                    "hard_filter_profile": args.hard_filter_profile,
                    "tier2_strictness": args.tier2_strictness,
                    "reward_policy_version": rf_cfg.get("reward_policy_version", "reward_policy_v1"),
                    "reward_weights": rf_cfg.get("reward_weights", {}),
                    "context": context_payload,
                    "artifacts": {
                        "filtered_csv": str(filtered_csv),
                        "filter_failures_json": str(filter_failures_json),
                        "ranked_csv": str(ranked_csv),
                        "ranked_summary_csv": str(summary_csv),
                        "candidate_set_log_csv": str(candidate_log_csv),
                        "impression_log_csv": str(impression_log_csv),
                        "outcome_event_log_template_csv": str(outcome_template_csv),
                    },
                },
                f,
                ensure_ascii=True,
                indent=2,
            )

        with explain_json.open("w", encoding="utf-8") as f:
            json.dump(
                {
                    "request_id": request_id,
                    "session_id": session_id,
                    "user_id": user_id,
                    "input_rows": len(rows),
                    "tier1_passed_rows": len(passed),
                    "tier1_failed_rows": len(failed),
                    "tier2_ranked_rows": len(ranked_rows),
                    "hard_filter_profile": args.hard_filter_profile,
                    "tier2_strictness": args.tier2_strictness,
                    "profile_path": args.profile,
                    "artifacts": {
                        "filtered_csv": str(filtered_csv),
                        "filter_failures_json": str(filter_failures_json),
                        "ranked_csv": str(ranked_csv),
                        "ranked_summary_csv": str(summary_csv),
                        "request_log_json": str(request_log_json),
                        "candidate_set_log_csv": str(candidate_log_csv),
                        "impression_log_csv": str(impression_log_csv),
                        "outcome_event_log_template_csv": str(outcome_template_csv),
                    },
                    "top_results": [
                        {
                            "rank": i + 1,
                            "id": r.row.get("id", ""),
                            "title": r.row.get("title", ""),
                            "image_1": r.row.get("images__0__src", ""),
                            "image_2": r.row.get("images__1__src", ""),
                            "tier2_final_score": r.final_score,
                            "tier2_max_score": r.row.get("tier2_max_score", ""),
                            "tier2_compatibility_confidence": r.row.get("tier2_compatibility_confidence", ""),
                            "tier2_raw_score": r.raw_score,
                            "tier2_confidence_multiplier": r.confidence_multiplier,
                            "tier2_flags": r.flags,
                        }
                        for i, r in enumerate(ranked_all[:25])
                    ],
                },
                f,
                ensure_ascii=True,
                indent=2,
            )

        print(f"request_id={request_id}")
        print(f"session_id={session_id}")
        print(f"user_id={user_id}")
        print(f"input_rows={len(rows)}")
        print(f"tier1_profile={args.hard_filter_profile}")
        print(f"tier1_passed={len(passed)}")
        print(f"tier1_failed={len(failed)}")
        print(f"tier2_ranked={len(ranked_rows)}")
        print(f"filtered_csv={filtered_csv}")
        print(f"filter_failures_json={filter_failures_json}")
        print(f"ranked_csv={ranked_csv}")
        print(f"ranked_summary_csv={summary_csv}")
        print(f"request_log_json={request_log_json}")
        print(f"candidate_set_log_csv={candidate_log_csv}")
        print(f"impression_log_csv={impression_log_csv}")
        print(f"outcome_event_log_template_csv={outcome_template_csv}")
        print(f"explain_json={explain_json}")
        return 0
    except (ValueError, FileNotFoundError, json.JSONDecodeError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
