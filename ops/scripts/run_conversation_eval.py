#!/usr/bin/env python3
import argparse
import csv
import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple
from uuid import uuid4


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _now_tag() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _clamp_01(value: float) -> float:
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value


def _norm_text(value: Any) -> str:
    return str(value or "").strip().lower()


def _contains_any(text: str, keywords: List[str]) -> bool:
    if not keywords:
        return False
    return any(k in text for k in keywords if k)


def _keyword_hit_ratio(titles: List[str], keywords: List[str]) -> float:
    if not titles:
        return 0.0
    if not keywords:
        return 0.5
    hits = 0
    for title in titles:
        if _contains_any(title, keywords):
            hits += 1
    return _clamp_01(hits / len(titles))


def _average(values: List[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def _score_ratio(item: Dict[str, Any]) -> float:
    score = float(item.get("score", 0.0) or 0.0)
    max_score = float(item.get("max_score", 0.0) or 0.0)
    if max_score <= 0:
        return 0.0
    return _clamp_01(score / max_score)


def _diversity_ratio(items: List[Dict[str, Any]]) -> float:
    if not items:
        return 0.0
    keys = []
    for item in items:
        keys.append(
            str(item.get("outfit_id") or item.get("garment_id") or item.get("title") or "").strip().lower()
        )
    unique = len({k for k in keys if k})
    if unique == 0:
        return 0.0
    return _clamp_01(unique / len(items))


def _build_required_checks(
    turn_result: Dict[str, Any],
    recommendation_fetch_ok: bool,
) -> Dict[str, bool]:
    return {
        "turn_id": bool(str(turn_result.get("turn_id", "")).strip()),
        "recommendation_run_id": bool(str(turn_result.get("recommendation_run_id", "")).strip()),
        "recommendation_fetch_ok": bool(recommendation_fetch_ok),
        "non_empty_recommendations": len(list(turn_result.get("recommendations") or [])) > 0,
    }


def evaluate_case(
    *,
    case_spec: Dict[str, Any],
    turn_result: Dict[str, Any],
    recommendation_fetch_ok: bool,
    rubric: Dict[str, Any],
    max_results: int,
    result_filter: str,
) -> Dict[str, Any]:
    recommendations = list(turn_result.get("recommendations") or [])
    resolved_context = dict(turn_result.get("resolved_context") or {})
    titles = [_norm_text(item.get("title", "")) for item in recommendations]

    expected_occasion = _norm_text(case_spec.get("expected_occasion", ""))
    expected_archetypes = [_norm_text(x) for x in list(case_spec.get("expected_archetype_any") or [])]
    preferred_keywords = [_norm_text(x) for x in list(case_spec.get("preferred_title_keywords") or []) if _norm_text(x)]
    avoid_keywords = [_norm_text(x) for x in list(case_spec.get("avoid_title_keywords") or []) if _norm_text(x)]

    occasion_key = _norm_text(resolved_context.get("occasion", "")) or expected_occasion
    occasion_guardrails = dict((rubric.get("occasion_guardrails") or {}).get(occasion_key) or {})
    occasion_avoid = [_norm_text(x) for x in list(occasion_guardrails.get("avoid_keywords") or []) if _norm_text(x)]
    all_avoid_keywords = sorted(set(avoid_keywords + occasion_avoid))

    occasion_match = 1.0 if (not expected_occasion or _norm_text(resolved_context.get("occasion", "")) == expected_occasion) else 0.0
    archetype_match = (
        1.0
        if (not expected_archetypes or _norm_text(resolved_context.get("archetype", "")) in set(expected_archetypes))
        else 0.0
    )
    coverage = _clamp_01(len(recommendations) / max(max_results, 1))
    preferred_hit_ratio = _keyword_hit_ratio(titles, preferred_keywords)
    avoid_hit_ratio = _keyword_hit_ratio(titles, all_avoid_keywords) if all_avoid_keywords else 0.0
    anti_keyword_guardrail = 1.0 - avoid_hit_ratio
    avg_confidence = _average([float(item.get("compatibility_confidence", 0.0) or 0.0) for item in recommendations])
    avg_score_ratio = _average([_score_ratio(item) for item in recommendations])
    diversity = _diversity_ratio(recommendations)

    recommendation_kinds = {_norm_text(item.get("recommendation_kind", "")) for item in recommendations}
    complete_only_integrity = 1.0
    if _norm_text(result_filter) == "complete_only":
        complete_only_integrity = 1.0 if "outfit_combo" not in recommendation_kinds else 0.0

    dimensions: Dict[str, float] = {
        "context_occasion": occasion_match,
        "context_archetype": archetype_match,
        "coverage": coverage,
        "keyword_alignment": preferred_hit_ratio,
        "anti_keyword_guardrail": anti_keyword_guardrail,
        "confidence": _clamp_01(avg_confidence),
        "score_quality": _clamp_01(avg_score_ratio),
        "diversity": diversity,
        "complete_only_integrity": complete_only_integrity,
    }

    weights = {str(k): float(v) for k, v in dict(rubric.get("weights") or {}).items()}
    weighted_sum = 0.0
    weight_total = 0.0
    weighted_breakdown: Dict[str, float] = {}
    for dim, weight in weights.items():
        value = _clamp_01(float(dimensions.get(dim, 0.0)))
        contrib = weight * value
        weighted_sum += contrib
        weight_total += weight
        weighted_breakdown[dim] = contrib
    normalized_score = weighted_sum / weight_total if weight_total > 0 else 0.0

    checks = _build_required_checks(turn_result=turn_result, recommendation_fetch_ok=recommendation_fetch_ok)
    required_checks = [str(x) for x in list(rubric.get("required_integrity_checks") or [])]
    missing_integrity_checks = [check for check in required_checks if not checks.get(check, False)]

    thresholds = dict(rubric.get("thresholds") or {})
    pass_score = float(thresholds.get("pass_score", 0.72) or 0.72)
    warning_score = float(thresholds.get("warning_score", 0.58) or 0.58)
    min_returned_results = int(thresholds.get("min_returned_results", 1) or 1)
    min_avg_conf = float(thresholds.get("min_avg_compatibility_confidence", 0.45) or 0.45)

    notes: List[str] = []
    if len(recommendations) < min_returned_results:
        notes.append(f"returned_results_below_threshold:{len(recommendations)}<{min_returned_results}")
    if avg_confidence < min_avg_conf:
        notes.append(f"avg_confidence_below_threshold:{avg_confidence:.3f}<{min_avg_conf:.3f}")
    if occasion_match < 1.0 and expected_occasion:
        notes.append("occasion_mismatch")
    if archetype_match < 1.0 and expected_archetypes:
        notes.append("archetype_mismatch")
    if avoid_hit_ratio > 0.0:
        notes.append("avoid_keyword_hits_detected")
    if complete_only_integrity < 1.0:
        notes.append("complete_only_integrity_failed")
    if turn_result.get("needs_clarification"):
        notes.append("clarification_requested")
    if missing_integrity_checks:
        notes.append("missing_integrity_checks:" + ",".join(missing_integrity_checks))

    status = "pass"
    if missing_integrity_checks:
        status = "fail_integrity"
    elif normalized_score < warning_score:
        status = "fail"
    elif normalized_score < pass_score:
        status = "warning"

    return {
        "prompt_id": str(case_spec.get("id", "")),
        "prompt": str(case_spec.get("prompt", "")),
        "resolved_context": resolved_context,
        "recommendation_count": len(recommendations),
        "score": round(normalized_score, 6),
        "status": status,
        "dimensions": {k: round(v, 6) for k, v in dimensions.items()},
        "weighted_breakdown": {k: round(v, 6) for k, v in weighted_breakdown.items()},
        "integrity_checks": checks,
        "missing_integrity_checks": missing_integrity_checks,
        "notes": notes,
        "meta": {
            "avg_compatibility_confidence": round(avg_confidence, 6),
            "avg_score_ratio": round(avg_score_ratio, 6),
            "preferred_hit_ratio": round(preferred_hit_ratio, 6),
            "avoid_hit_ratio": round(avoid_hit_ratio, 6),
            "diversity_ratio": round(diversity, 6),
            "complete_only_integrity": round(complete_only_integrity, 6),
        },
    }


def aggregate_case_evals(case_evals: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not case_evals:
        return {
            "case_count": 0,
            "average_score": 0.0,
            "status_counts": {},
            "dimension_averages": {},
            "integrity_pass_rate": 0.0,
        }

    status_counts: Dict[str, int] = {}
    dimension_sum: Dict[str, float] = {}
    dimension_count: Dict[str, int] = {}
    integrity_pass = 0
    for case in case_evals:
        status = str(case.get("status", ""))
        status_counts[status] = status_counts.get(status, 0) + 1

        missing_checks = list(case.get("missing_integrity_checks") or [])
        if not missing_checks:
            integrity_pass += 1

        for dim, value in dict(case.get("dimensions") or {}).items():
            dimension_sum[dim] = dimension_sum.get(dim, 0.0) + float(value)
            dimension_count[dim] = dimension_count.get(dim, 0) + 1

    dimension_averages = {
        dim: round(dimension_sum[dim] / max(dimension_count[dim], 1), 6) for dim in sorted(dimension_sum.keys())
    }
    avg_score = _average([float(case.get("score", 0.0) or 0.0) for case in case_evals])

    return {
        "case_count": len(case_evals),
        "average_score": round(avg_score, 6),
        "status_counts": status_counts,
        "dimension_averages": dimension_averages,
        "integrity_pass_rate": round(integrity_pass / len(case_evals), 6),
    }


def _http_json(
    *,
    method: str,
    url: str,
    timeout_seconds: int,
    payload: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    data: bytes | None = None
    headers = {"Content-Type": "application/json"}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=True).encode("utf-8")
    req = urllib.request.Request(url=url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
            raw = resp.read().decode("utf-8")
            if not raw.strip():
                return {}
            return json.loads(raw)
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        detail = raw
        try:
            detail_json = json.loads(raw)
            detail = json.dumps(detail_json, ensure_ascii=True)
        except json.JSONDecodeError:
            pass
        raise RuntimeError(f"{method} {url} failed with HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"{method} {url} failed: {exc.reason}") from exc


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=True, indent=2)


def _append_jsonl(path: Path, row: Dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=True) + "\n")


def _write_cases_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _write_summary_md(path: Path, summary: Dict[str, Any], cases: List[Dict[str, Any]]) -> None:
    lines: List[str] = []
    lines.append("# Conversation Eval Summary")
    lines.append("")
    lines.append(f"- Cases: {summary.get('case_count', 0)}")
    lines.append(f"- Average score: {summary.get('average_score', 0.0)}")
    lines.append(f"- Integrity pass rate: {summary.get('integrity_pass_rate', 0.0)}")
    lines.append(f"- Status counts: {json.dumps(summary.get('status_counts', {}), ensure_ascii=True)}")
    lines.append("")
    lines.append("## Lowest-scoring cases")
    lines.append("")
    ranked = sorted(cases, key=lambda c: float(c.get("score", 0.0)))
    for case in ranked[:5]:
        lines.append(
            f"- {case.get('prompt_id','')} | score={case.get('score',0.0)} | status={case.get('status','')} | notes={';'.join(case.get('notes',[]))}"
        )
    lines.append("")
    lines.append("## Dimension averages")
    lines.append("")
    for key, value in dict(summary.get("dimension_averages") or {}).items():
        lines.append(f"- {key}: {value}")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def _load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run prompt-suite evaluation against conversation API and persist logs/evals."
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8010", help="Conversation API base URL.")
    parser.add_argument(
        "--suite",
        default="ops/evals/conversation_prompt_suite_diverse_v1.json",
        help="Prompt suite JSON path.",
    )
    parser.add_argument(
        "--rubric",
        default="ops/evals/conversation_eval_rubric_v1.json",
        help="Rubric JSON path.",
    )
    parser.add_argument("--out-dir", default="data/logs/evals", help="Eval artifact output directory.")
    parser.add_argument("--strictness", default="balanced", choices=["safe", "balanced", "bold"])
    parser.add_argument("--hard-filter-profile", default="rl_ready_minimal", choices=["rl_ready_minimal", "legacy"])
    parser.add_argument("--max-results", type=int, default=3)
    parser.add_argument(
        "--result-filter",
        default="complete_only",
        choices=["complete_only", "complete_plus_combos"],
        help="Recommendation result mix.",
    )
    parser.add_argument("--image-ref", action="append", default=[], help="Optional image refs sent in each turn.")
    parser.add_argument("--user-id-prefix", default="eval_user", help="External user ID prefix.")
    parser.add_argument("--initial-gender", default="female", help="Initial context gender.")
    parser.add_argument("--initial-age", default="25_30", help="Initial context age band.")
    parser.add_argument("--initial-occasion", default="", help="Optional fixed initial occasion.")
    parser.add_argument("--initial-archetype", default="", help="Optional fixed initial archetype.")
    parser.add_argument("--max-cases", type=int, default=0, help="Optional cap on number of prompts (0 = all).")
    parser.add_argument("--timeout-seconds", type=int, default=60)
    parser.add_argument(
        "--fail-on-integrity",
        action="store_true",
        help="Exit with code 2 when any case fails required integrity checks.",
    )
    return parser.parse_args()


def _build_initial_context(args: argparse.Namespace) -> Dict[str, str]:
    context = {
        "gender": str(args.initial_gender or "").strip(),
        "age": str(args.initial_age or "").strip(),
        "occasion": str(args.initial_occasion or "").strip(),
        "archetype": str(args.initial_archetype or "").strip(),
    }
    return {k: v for k, v in context.items() if v}


def _artifact_integrity_report(run_dir: Path, expected_files: List[str], case_count: int) -> Dict[str, Any]:
    missing_files = []
    for name in expected_files:
        if not (run_dir / name).exists():
            missing_files.append(name)

    line_counts: Dict[str, int] = {}
    for name in ("case_inputs.jsonl", "case_outputs.jsonl", "case_scores.jsonl"):
        path = run_dir / name
        if path.exists():
            with path.open("r", encoding="utf-8") as f:
                line_counts[name] = sum(1 for _ in f if _.strip())
        else:
            line_counts[name] = 0

    line_mismatch = {
        name: count for name, count in line_counts.items() if count != case_count
    }
    ok = (len(missing_files) == 0) and (len(line_mismatch) == 0)
    return {
        "ok": ok,
        "missing_files": missing_files,
        "line_counts": line_counts,
        "line_count_mismatch": line_mismatch,
    }


def main() -> int:
    args = _parse_args()
    try:
        suite_path = Path(args.suite)
        rubric_path = Path(args.rubric)
        out_root = Path(args.out_dir)

        suite = _load_json(suite_path)
        rubric = _load_json(rubric_path)
        prompts = list(suite.get("prompts") or [])
        if args.max_cases > 0:
            prompts = prompts[: args.max_cases]
        if not prompts:
            raise RuntimeError("Prompt suite has no prompts to evaluate.")

        run_id = f"{_now_tag()}_{str(suite.get('suite_id', 'suite'))}"
        run_dir = out_root / run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        paths = {
            "manifest": run_dir / "run_manifest.json",
            "inputs_jsonl": run_dir / "case_inputs.jsonl",
            "outputs_jsonl": run_dir / "case_outputs.jsonl",
            "scores_jsonl": run_dir / "case_scores.jsonl",
            "scores_csv": run_dir / "case_scores.csv",
            "summary_json": run_dir / "summary.json",
            "summary_md": run_dir / "summary.md",
            "integrity_json": run_dir / "artifact_integrity.json",
        }

        for jsonl_key in ("inputs_jsonl", "outputs_jsonl", "scores_jsonl"):
            paths[jsonl_key].write_text("", encoding="utf-8")

        run_manifest = {
            "run_id": run_id,
            "started_at": _now_iso(),
            "suite": {
                "path": str(suite_path),
                "suite_id": str(suite.get("suite_id", "")),
                "version": str(suite.get("version", "")),
                "prompt_count": len(prompts),
            },
            "rubric": {
                "path": str(rubric_path),
                "rubric_id": str(rubric.get("rubric_id", "")),
                "version": str(rubric.get("version", "")),
            },
            "settings": {
                "base_url": args.base_url.rstrip("/"),
                "strictness": args.strictness,
                "hard_filter_profile": args.hard_filter_profile,
                "max_results": args.max_results,
                "result_filter": args.result_filter,
                "image_refs": list(args.image_ref),
                "user_id_prefix": args.user_id_prefix,
                "initial_context": _build_initial_context(args),
                "timeout_seconds": args.timeout_seconds,
            },
        }
        _write_json(paths["manifest"], run_manifest)

        case_evals: List[Dict[str, Any]] = []
        base_url = args.base_url.rstrip("/")
        initial_context = _build_initial_context(args)

        for idx, case in enumerate(prompts, start=1):
            prompt_id = str(case.get("id", f"case_{idx}"))
            user_id = f"{args.user_id_prefix}_{prompt_id}_{str(uuid4())[:8]}"

            conversation_payload: Dict[str, Any] = {"user_id": user_id}
            if initial_context:
                conversation_payload["initial_context"] = initial_context

            conversation_resp: Dict[str, Any] = {}
            turn_payload: Dict[str, Any] = {}
            turn_resp: Dict[str, Any] = {}
            recommendation_resp: Dict[str, Any] = {}
            recommendation_fetch_ok = False
            error_message = ""

            try:
                conversation_resp = _http_json(
                    method="POST",
                    url=f"{base_url}/v1/conversations",
                    payload=conversation_payload,
                    timeout_seconds=args.timeout_seconds,
                )
                conversation_id = str(conversation_resp.get("conversation_id", ""))
                if not conversation_id:
                    raise RuntimeError("create conversation returned empty conversation_id")

                turn_payload = {
                    "user_id": user_id,
                    "message": str(case.get("prompt", "")),
                    "image_refs": list(args.image_ref),
                    "strictness": args.strictness,
                    "hard_filter_profile": args.hard_filter_profile,
                    "max_results": args.max_results,
                    "result_filter": args.result_filter,
                }
                turn_resp = _http_json(
                    method="POST",
                    url=f"{base_url}/v1/conversations/{conversation_id}/turns",
                    payload=turn_payload,
                    timeout_seconds=args.timeout_seconds,
                )
                run_id_value = str(turn_resp.get("recommendation_run_id", "")).strip()
                if run_id_value:
                    recommendation_resp = _http_json(
                        method="GET",
                        url=f"{base_url}/v1/recommendations/{run_id_value}",
                        timeout_seconds=args.timeout_seconds,
                    )
                    recommendation_fetch_ok = True
            except Exception as exc:  # noqa: BLE001
                error_message = str(exc)

            _append_jsonl(
                paths["inputs_jsonl"],
                {
                    "timestamp": _now_iso(),
                    "prompt_id": prompt_id,
                    "prompt": str(case.get("prompt", "")),
                    "conversation_payload": conversation_payload,
                    "turn_payload": turn_payload,
                },
            )
            _append_jsonl(
                paths["outputs_jsonl"],
                {
                    "timestamp": _now_iso(),
                    "prompt_id": prompt_id,
                    "conversation_response": conversation_resp,
                    "turn_response": turn_resp,
                    "recommendation_response": recommendation_resp,
                    "recommendation_fetch_ok": recommendation_fetch_ok,
                    "error": error_message,
                },
            )

            if error_message:
                case_eval = {
                    "prompt_id": prompt_id,
                    "prompt": str(case.get("prompt", "")),
                    "resolved_context": {},
                    "recommendation_count": 0,
                    "score": 0.0,
                    "status": "error",
                    "dimensions": {},
                    "weighted_breakdown": {},
                    "integrity_checks": {
                        "turn_id": False,
                        "recommendation_run_id": False,
                        "recommendation_fetch_ok": False,
                        "non_empty_recommendations": False,
                    },
                    "missing_integrity_checks": list(rubric.get("required_integrity_checks") or []),
                    "notes": [error_message],
                    "meta": {},
                }
            else:
                case_eval = evaluate_case(
                    case_spec=case,
                    turn_result=turn_resp,
                    recommendation_fetch_ok=recommendation_fetch_ok,
                    rubric=rubric,
                    max_results=args.max_results,
                    result_filter=args.result_filter,
                )

            _append_jsonl(paths["scores_jsonl"], case_eval)
            case_evals.append(case_eval)
            print(
                f"[{idx}/{len(prompts)}] {prompt_id} status={case_eval.get('status')} score={case_eval.get('score')}",
                flush=True,
            )

        summary = aggregate_case_evals(case_evals)
        summary["run_id"] = run_id
        summary["completed_at"] = _now_iso()

        csv_rows: List[Dict[str, Any]] = []
        for case in case_evals:
            csv_rows.append(
                {
                    "prompt_id": case.get("prompt_id", ""),
                    "status": case.get("status", ""),
                    "score": case.get("score", 0.0),
                    "recommendation_count": case.get("recommendation_count", 0),
                    "avg_compatibility_confidence": dict(case.get("meta") or {}).get("avg_compatibility_confidence", 0.0),
                    "avoid_hit_ratio": dict(case.get("meta") or {}).get("avoid_hit_ratio", 0.0),
                    "notes": ";".join(list(case.get("notes") or [])),
                }
            )
        _write_cases_csv(paths["scores_csv"], csv_rows)
        _write_json(paths["summary_json"], summary)
        _write_summary_md(paths["summary_md"], summary=summary, cases=case_evals)

        expected_files = [
            "run_manifest.json",
            "case_inputs.jsonl",
            "case_outputs.jsonl",
            "case_scores.jsonl",
            "case_scores.csv",
            "summary.json",
            "summary.md",
        ]
        artifact_integrity = _artifact_integrity_report(
            run_dir=run_dir,
            expected_files=expected_files,
            case_count=len(prompts),
        )
        _write_json(paths["integrity_json"], artifact_integrity)

        print(f"Eval run completed: {run_dir}", flush=True)
        print(json.dumps(summary, ensure_ascii=True, indent=2), flush=True)

        has_case_integrity_fail = any(case.get("missing_integrity_checks") for case in case_evals)
        if args.fail_on_integrity and (has_case_integrity_fail or not artifact_integrity.get("ok", False)):
            return 2
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
