"""Pre-compute canonical embeddings for the composition canonicalize layer.

Generates ``modules/agentic_application/src/agentic_application/composition/
canonical_embeddings.json`` — the static artifact the canonicalize module
loads at process start.

Run when the YAMLs change (new occasions, archetype updates, etc.). The
output is committed to the repo so production cold starts don't need an
OpenAI API call.

Usage:

    APP_ENV=staging PYTHONPATH=modules/agentic_application/src:modules/catalog/src:modules/platform_core/src:modules/style_engine/src:modules/user/src:modules/user_profiler/src \\
        python ops/scripts/build_canonical_embeddings.py

What gets embedded per axis:

- occasion: 44 entries from occasion.yaml. Embedded as
  ``"<key>: <notes>"``. Notes are 1-3 sentences of stylist context;
  exactly the right grain for matching free-text planner output.
- weather: 10 entries from weather.yaml. Embedded as
  ``"<key>: <description>. <notes>"`` (description is short and very
  semantic, notes adds the indian-region context).
- archetype: 12 entries from archetype.yaml::primary_archetype.
  Embedded as ``"<key>: <notes truncated to ~250 chars>"`` so long
  notes don't dilute the signal toward edge-case examples.
- risk_tolerance: 3 entries from archetype.yaml::risk_tolerance.
  Notes are short; embedded full.
- seasonal: 12 SubSeason + 4 SeasonalColorGroup entries from palette.yaml,
  flattened into one bank. Notes are mostly stylist context; embedded
  as ``"<key>: <notes>"``. The engine's dual-dimension exact-match runs
  first; this bank is the embedding fallback for non-exact inputs like
  generic "Autumn" → "Soft Autumn".

All vectors are 256-dim text-embedding-3-small (the canonicalize
module's ``EMBEDDING_DIMENSIONS`` constant). 256 is plenty for these
short, semantically-distinct texts and keeps the JSON artifact under
~500KB.

The script is idempotent and tolerant of partial output — re-running
produces a byte-identical file (text-embedding-3-small is deterministic
for a fixed model + dimensions).
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

# Ensure module imports work when invoked outside pytest.
_REPO_ROOT = Path(__file__).resolve().parents[2]
for sub in (
    "modules/agentic_application/src",
    "modules/catalog/src",
    "modules/platform_core/src",
    "modules/style_engine/src",
    "modules/user/src",
    "modules/user_profiler/src",
):
    p = str(_REPO_ROOT / sub)
    if p not in sys.path:
        sys.path.insert(0, p)


_log = logging.getLogger("build_canonical_embeddings")


# Output path co-located with the canonicalize module so a single
# Python file read on process start is enough to load the artifact.
_OUTPUT_PATH = (
    _REPO_ROOT
    / "modules"
    / "agentic_application"
    / "src"
    / "agentic_application"
    / "composition"
    / "canonical_embeddings.json"
)


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _truncate(text: str, max_chars: int) -> str:
    text = (text or "").strip()
    if len(text) <= max_chars:
        return text
    # Cut on a sentence boundary if one exists below the limit.
    cut = text.rfind(". ", 0, max_chars)
    if cut > max_chars // 2:
        return text[: cut + 1]
    return text[:max_chars]


def _build_corpus() -> Dict[str, List[Tuple[str, str]]]:
    """Walk the YAMLs and build {axis: [(key, embedding_text)]}."""
    from agentic_application.composition.yaml_loader import load_style_graph

    graph = load_style_graph()

    out: Dict[str, List[Tuple[str, str]]] = {
        "occasion": [],
        "weather": [],
        "archetype": [],
        "risk_tolerance": [],
        "seasonal": [],
    }

    # Occasion — full notes (1-3 sentences typically)
    for name, occ in graph.occasion.items():
        text = f"{name}: {_truncate(occ.mapping.notes, 600)}".strip(": ").strip()
        out["occasion"].append((name, text))

    # Weather — description + notes
    for name, w in graph.weather.items():
        desc = (w.description or "").strip()
        notes = _truncate(w.mapping.notes, 600)
        text = f"{name}: {desc}. {notes}".strip()
        out["weather"].append((name, text))

    # Archetype — truncate long notes to keep signal on the core identity
    for name, mapping in (graph.archetype.get("primary_archetype") or {}).items():
        text = f"{name}: {_truncate(mapping.notes, 250)}"
        out["archetype"].append((name, text))

    # Risk tolerance — full notes (short)
    for name, mapping in (graph.archetype.get("risk_tolerance") or {}).items():
        text = f"{name}: {mapping.notes}".strip(": ").strip()
        out["risk_tolerance"].append((name, text))

    # Seasonal — flatten SubSeason + SeasonalColorGroup. The same key
    # appearing in both dimensions is unusual; if it happens, the
    # SubSeason variant wins (more specific).
    seen_seasonal: set[str] = set()
    for name, mapping in (graph.palette.get("SubSeason") or {}).items():
        text = f"{name}: {_truncate(mapping.notes, 400)}"
        out["seasonal"].append((name, text))
        seen_seasonal.add(name)
    for name, mapping in (graph.palette.get("SeasonalColorGroup") or {}).items():
        if name in seen_seasonal:
            continue
        text = f"{name}: {_truncate(mapping.notes, 400)}"
        out["seasonal"].append((name, text))

    return out


def _embed_axis(
    embed_client, texts: List[str]
) -> List[List[float]]:
    """Single batched embedding call for one axis. Up to ~50 texts at
    a time; OpenAI's endpoint accepts much more but smaller batches
    keep memory + retry behavior simple."""
    if not texts:
        return []
    return embed_client(texts)


def main(argv: List[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--env-file",
        type=Path,
        default=_REPO_ROOT / ".env.staging",
        help="Path to env file with OPENAI_API_KEY (default: .env.staging)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=_OUTPUT_PATH,
        help="Output JSON path (default: composition/canonical_embeddings.json)",
    )
    args = parser.parse_args(argv)

    _load_dotenv(args.env_file)

    if not os.environ.get("OPENAI_API_KEY"):
        print(
            "OPENAI_API_KEY not set; ensure --env-file points at a real env file",
            file=sys.stderr,
        )
        return 2

    from agentic_application.composition.canonicalize import default_embed_client

    embed = default_embed_client()
    corpus = _build_corpus()

    payload: Dict[str, Dict[str, List[float]]] = {}
    total = 0
    for axis, items in corpus.items():
        keys = [k for k, _ in items]
        texts = [t for _, t in items]
        _log.info("embedding axis=%s n=%d", axis, len(items))
        vectors = _embed_axis(embed, texts)
        if len(vectors) != len(items):
            print(
                f"axis={axis}: expected {len(items)} vectors, got {len(vectors)}",
                file=sys.stderr,
            )
            return 3
        # Round to 6 significant figures to keep the JSON file tight
        # without losing semantic precision (cosine doesn't change
        # appreciably below ~1e-4 noise).
        payload[axis] = {
            k: [round(float(x), 6) for x in v]
            for k, v in zip(keys, vectors)
        }
        total += len(items)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    size_kb = args.output.stat().st_size / 1024
    _log.info(
        "wrote %s (%d entries across %d axes, %.0f KB)",
        args.output, total, len(corpus), size_kb,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
