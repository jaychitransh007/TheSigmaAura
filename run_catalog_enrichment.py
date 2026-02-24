import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
for p in (
    ROOT,
    ROOT / "modules" / "catalog_enrichment" / "src",
    ROOT / "modules" / "style_engine" / "src",
):
    sp = str(p)
    if sp not in sys.path:
        sys.path.insert(0, sp)

from catalog_enrichment.main import run


if __name__ == "__main__":
    run()
