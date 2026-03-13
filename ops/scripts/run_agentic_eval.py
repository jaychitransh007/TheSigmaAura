#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_UNIT_SUITES = [
    "tests.test_agentic_application",
    "tests.test_agentic_application_api_ui",
]


def _run(command: list[str], *, env: dict[str, str] | None = None) -> int:
    print(f"$ {' '.join(command)}")
    completed = subprocess.run(command, cwd=ROOT, env=env)
    return int(completed.returncode)


def _unit_command(verbose: bool) -> list[str]:
    command = [sys.executable, "-m", "unittest"]
    command.extend(DEFAULT_UNIT_SUITES)
    if verbose:
        command.append("-v")
    return command


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the current agentic application evaluation harness.")
    parser.add_argument("--skip-unit", action="store_true", help="Skip focused unittest suites.")
    parser.add_argument("--smoke", action="store_true", help="Run the HTTP smoke flow after unit suites.")
    parser.add_argument("--base-url", default=os.getenv("BASE_URL", "http://127.0.0.1:8010"))
    parser.add_argument("--user-id", default=os.getenv("USER_ID", ""))
    parser.add_argument("--conversation-id", default=os.getenv("CONVERSATION_ID", ""))
    parser.add_argument(
        "--first-message",
        default=os.getenv("FIRST_MESSAGE", "Need a smart casual outfit for a work meeting"),
    )
    parser.add_argument(
        "--followup-message",
        default=os.getenv("FOLLOWUP_MESSAGE", "Show me something bolder"),
    )
    parser.add_argument("--quiet", action="store_true", help="Drop unittest -v output.")
    args = parser.parse_args()

    if not args.skip_unit:
        exit_code = _run(_unit_command(verbose=not args.quiet))
        if exit_code != 0:
            return exit_code

    if args.smoke:
        if not args.user_id:
            print("error: --user-id or USER_ID is required for --smoke", file=sys.stderr)
            return 2
        smoke_env = os.environ.copy()
        smoke_env.update(
            {
                "BASE_URL": args.base_url,
                "USER_ID": args.user_id,
                "CONVERSATION_ID": args.conversation_id,
                "FIRST_MESSAGE": args.first_message,
                "FOLLOWUP_MESSAGE": args.followup_message,
            }
        )
        return _run(["/bin/bash", "ops/scripts/smoke_test_agentic_application.sh"], env=smoke_env)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
