#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path


def _discover_repo_root() -> Path:
    here = Path(__file__).resolve()
    for base in [here.parent] + list(here.parents):
        if (base / "run_catalog_enrichment.py").exists():
            return base
    return here.parent


ROOT = _discover_repo_root()
for p in (
    ROOT,
    ROOT / "modules" / "user" / "src",
    ROOT / "modules" / "agentic_application" / "src",
    ROOT / "modules" / "catalog" / "src",
    ROOT / "modules" / "catalog_enrichment" / "src",
    ROOT / "modules" / "catalog_retrieval" / "src",
    ROOT / "modules" / "platform_core" / "src",
    ROOT / "modules" / "user_profiler" / "src",
    ROOT / "modules" / "onboarding" / "src",
):
    sp = str(p)
    if sp not in sys.path:
        sys.path.insert(0, sp)

import uvicorn  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run agentic application API server.")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host.")
    parser.add_argument("--port", type=int, default=8010, help="Bind port.")
    parser.add_argument("--reload", action="store_true", help="Enable auto reload.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    uvicorn.run(
        "agentic_application.api:create_app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        factory=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
