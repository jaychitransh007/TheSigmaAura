import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
for p in (
    ROOT,
    ROOT / "modules" / "catalog" / "src",
    ROOT / "modules" / "platform_core" / "src",
):
    sp = str(p)
    if sp not in sys.path:
        sys.path.insert(0, sp)

from catalog.enrichment.main import run
from platform_core.logging_config import configure_logging


if __name__ == "__main__":
    # AURA_LOG_FORMAT=json (or LOG_FORMAT=json) emits structured JSON
    # records — same shape as run_agentic_application.py — so log
    # aggregators get a consistent envelope across all entry points.
    configure_logging()
    run()
