#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path

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

from style_engine.ranker import (  # noqa: E402
    load_tier2_rules,
    read_csv_rows,
    write_ranked_csv,
)
from style_engine.outfit_engine import rank_recommendation_candidates  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Tier 2 personalized outfit ranking.")
    parser.add_argument("--input", default="out/filtered_outfits.csv", help="Input CSV path (usually Tier 1 output).")
    parser.add_argument("--profile", required=True, help="User profile JSON path for body harmony + preferences.")
    parser.add_argument("--output", default="out/ranked_outfits.csv", help="Output ranked CSV path.")
    parser.add_argument("--explain", default="out/ranked_outfits_explainability.json", help="Explainability JSON output path.")
    parser.add_argument("--limit", type=int, default=0, help="Optional max ranked rows to write (0 = all).")
    parser.add_argument(
        "--tier2-strictness",
        default="balanced",
        choices=["safe", "balanced", "bold"],
        help="Adjusts confidence multipliers and penalties without changing base rules.",
    )
    parser.add_argument(
        "--recommendation-mode",
        default="auto",
        choices=["auto", "outfit", "garment"],
        help="Recommendation mode. Auto prefers outfit mode unless request text is garment-specific.",
    )
    parser.add_argument(
        "--request-text",
        default="",
        help="Optional natural-language request text used for auto mode resolution.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    rows = read_csv_rows(args.input)
    with open(args.profile, "r", encoding="utf-8") as f:
        profile = json.load(f)
    rules = load_tier2_rules()

    ranked, recommendation_meta = rank_recommendation_candidates(
        rows=rows,
        user_profile=profile,
        tier2_rules=rules,
        strictness=args.tier2_strictness,
        mode=args.recommendation_mode,
        request_text=args.request_text,
        max_results=args.limit,
    )

    out_rows = [r.row for r in ranked]
    explain = {
        "total_input_rows": len(rows),
        "ranked_rows": len(ranked),
        "tier2_strictness": args.tier2_strictness,
        "recommendation_mode": args.recommendation_mode,
        "resolved_recommendation_mode": recommendation_meta.resolved_mode,
        "profile_used": profile,
        "recommendation_meta": {
            "requested_categories": recommendation_meta.requested_categories,
            "requested_subtypes": recommendation_meta.requested_subtypes,
            "single_candidates": recommendation_meta.single_candidates,
            "combo_candidates": recommendation_meta.combo_candidates,
        },
        "top_results": [
            {
                "id": r.row.get("id", ""),
                "title": r.row.get("title", ""),
                "tier2_final_score": r.final_score,
                "tier2_raw_score": r.raw_score,
                "confidence_multiplier": r.confidence_multiplier,
                "color_delta": r.color_delta,
                "flags": r.flags,
                "reasons": r.reasons,
                "penalties": r.penalties,
                "recommendation_kind": r.row.get("recommendation_kind", "single_garment"),
                "component_ids_json": r.row.get("component_ids_json", "[]"),
                "explainability": r.explainability,
            }
            for r in ranked[: min(25, len(ranked))]
        ],
        "explainability_contract": {
            "per_item_fields": [
                "tier2_raw_score",
                "tier2_confidence_multiplier",
                "tier2_color_delta",
                "tier2_final_score",
                "tier2_flags",
                "tier2_reasons",
                "tier2_penalties"
            ],
            "json_sections": [
                "conflict_engine",
                "top_positive_contributions",
                "top_negative_contributions",
                "formula"
            ]
        }
    }

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.explain).parent.mkdir(parents=True, exist_ok=True)
    write_ranked_csv(args.output, out_rows)
    with open(args.explain, "w", encoding="utf-8") as f:
        json.dump(explain, f, ensure_ascii=True, indent=2)

    print(f"input_rows={len(rows)}")
    print(f"ranked_rows={len(ranked)}")
    print(f"tier2_strictness={args.tier2_strictness}")
    print(f"recommendation_mode={args.recommendation_mode}")
    print(f"resolved_recommendation_mode={recommendation_meta.resolved_mode}")
    print(f"output_csv={args.output}")
    print(f"explain_json={args.explain}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
