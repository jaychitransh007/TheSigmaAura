#!/usr/bin/env python3
import argparse
import subprocess
import sys
from pathlib import Path


def _discover_repo_root() -> Path:
    here = Path(__file__).resolve()
    for base in [here.parent] + list(here.parents):
        if (base / "supabase" / "migrations").exists():
            return base
    return here.parents[2]


ROOT = _discover_repo_root()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check local and linked remote Supabase migration sync.")
    parser.add_argument("--workdir", default=str(ROOT), help="Repo root containing supabase/")
    parser.add_argument("--strict", action="store_true", help="Fail if staging env file is missing.")
    return parser.parse_args()


def _run(cmd: list[str], cwd: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=cwd, text=True, capture_output=True, check=False)


def main() -> int:
    args = parse_args()
    workdir = args.workdir
    current_ref = Path(workdir, "supabase/.temp/project-ref")
    staging_env = Path(workdir, ".env.staging")

    result = _run(["supabase", "migration", "list"], workdir)
    sys.stdout.write(result.stdout)
    sys.stderr.write(result.stderr)
    if result.returncode != 0:
        return result.returncode

    if not current_ref.exists():
        print("status: missing linked project ref")
        return 2

    print(f"linked_project_ref: {current_ref.read_text(encoding='utf-8').strip()}")
    print(f"staging_env_present: {staging_env.exists()}")
    if args.strict and not staging_env.exists():
        print("status: missing .env.staging")
        return 3

    print("status: sync check completed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
