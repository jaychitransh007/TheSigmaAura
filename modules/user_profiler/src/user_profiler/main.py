import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from .config import UserProfilerConfig, get_api_key
from .service import infer_user_profile


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Infer user profile from image + natural-language context using two OpenAI calls "
            "(visual reasoning + textual reasoning)."
        )
    )
    parser.add_argument("--image", required=True, help="User image path or URL.")
    parser.add_argument("--context-text", required=True, help="User natural-language context text.")
    parser.add_argument("--out", default="data/logs/user_profile_inference.json", help="Combined JSON output path.")
    parser.add_argument(
        "--style-profile-out",
        default="data/logs/user_style_profile.json",
        help="Style profile JSON output path for downstream retrieval and orchestration.",
    )
    parser.add_argument(
        "--style-context-out",
        default="data/logs/user_style_context.json",
        help="Style context JSON output path (occasion/archetype/gender/age).",
    )
    return parser.parse_args()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def run() -> None:
    args = parse_args()
    api_key = get_api_key()
    out_path = Path(args.out)
    config = UserProfilerConfig(output_dir=str(out_path.parent))

    visual, textual, style_input, call_logs = infer_user_profile(
        api_key=api_key,
        image_ref=args.image,
        context_text=args.context_text,
        config=config,
    )

    combined = {
        "timestamp": _now_iso(),
        "models": {
            "visual": config.visual_model,
            "textual": config.textual_model,
        },
        "openai_calls": 2,
        "visual_profile": visual,
        "text_context": textual,
        "style_pipeline_input": style_input,
        "logs": call_logs,
        "visual_reasoning_notes": call_logs.get("visual_call", {}).get("reasoning_notes", []),
        "retrieval_context_hint": (
            "Use the saved profile and context JSON outputs as inputs to the "
            "LLM retrieval query builder and catalog embedding search."
        ),
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(combined, ensure_ascii=True, indent=2), encoding="utf-8")

    profile_out = Path(args.style_profile_out)
    profile_out.parent.mkdir(parents=True, exist_ok=True)
    profile_out.write_text(
        json.dumps(style_input["profile"], ensure_ascii=True, indent=2),
        encoding="utf-8",
    )

    context_out = Path(args.style_context_out)
    context_out.parent.mkdir(parents=True, exist_ok=True)
    context_out.write_text(
        json.dumps(style_input["context"], ensure_ascii=True, indent=2),
        encoding="utf-8",
    )

    # Keep the CLI output simple and parse-friendly for automation.
    print(f"wrote: {out_path}")
    print(f"wrote: {profile_out}")
    print(f"wrote: {context_out}")


def main() -> int:
    try:
        run()
        return 0
    except Exception as exc:
        print(f"error: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
