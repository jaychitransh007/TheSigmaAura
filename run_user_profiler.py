#!/usr/bin/env python3
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
    ROOT / "modules" / "catalog" / "src",
    ROOT / "modules" / "style_engine" / "src",
    ROOT / "modules" / "user_profiler" / "src",
):
    sp = str(p)
    if sp not in sys.path:
        sys.path.insert(0, sp)


from user_profiler.main import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
