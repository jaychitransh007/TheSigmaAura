#!/usr/bin/env python3
"""Extract Panel N SQL blocks from `docs/OPERATIONS.md` into `ops/dashboards/`.

Usage:
    python ops/scripts/extract_dashboard_sql.py

Output files: `ops/dashboards/panel_NN_<slug>.sql` — one per Panel header
in OPERATIONS.md. Each file concatenates every ```sql fenced block under
the panel and prepends a comment header pointing back to the doc so you
can paste straight into Supabase Studio / Metabase / Grafana.

Re-run this any time `docs/OPERATIONS.md` changes a panel's SQL — the
extractor overwrites in place.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "docs" / "OPERATIONS.md"
DEST_DIR = REPO_ROOT / "ops" / "dashboards"

PANEL_HEADER_RE = re.compile(r"^## Panel (\d+)\s+—\s+(.+?)\s*$")


def _slug(s: str) -> str:
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    return s.strip("_")[:60]


def main() -> int:
    if not SRC.exists():
        print(f"missing: {SRC}", file=sys.stderr)
        return 2
    DEST_DIR.mkdir(parents=True, exist_ok=True)

    text = SRC.read_text(encoding="utf-8").splitlines()

    panels: list[tuple[int, str, list[str]]] = []  # (number, title, sql_blocks)
    cur_panel: tuple[int, str] | None = None
    cur_blocks: list[str] = []
    in_sql = False
    cur_sql: list[str] = []

    for line in text:
        m = PANEL_HEADER_RE.match(line)
        if m:
            if cur_panel is not None:
                panels.append((cur_panel[0], cur_panel[1], cur_blocks))
            cur_panel = (int(m.group(1)), m.group(2).strip())
            cur_blocks = []
            in_sql = False
            cur_sql = []
            continue
        if cur_panel is None:
            continue
        if line.strip().startswith("```sql"):
            in_sql = True
            cur_sql = []
            continue
        if in_sql and line.strip().startswith("```"):
            in_sql = False
            cur_blocks.append("\n".join(cur_sql).rstrip() + "\n")
            cur_sql = []
            continue
        if in_sql:
            cur_sql.append(line)

    if cur_panel is not None:
        panels.append((cur_panel[0], cur_panel[1], cur_blocks))

    written: list[str] = []
    for number, title, blocks in panels:
        if not blocks:
            continue
        slug = _slug(title)
        path = DEST_DIR / f"panel_{number:02d}_{slug}.sql"
        header = (
            f"-- Panel {number} — {title}\n"
            f"-- Source: docs/OPERATIONS.md (auto-extracted; do not hand-edit)\n"
            f"-- Regenerate with: python3 ops/scripts/extract_dashboard_sql.py\n"
            f"\n"
        )
        body = "\n".join(blocks).rstrip() + "\n"
        path.write_text(header + body, encoding="utf-8")
        written.append(path.name)

    index_path = DEST_DIR / "README.md"
    index_lines = [
        "# Aura Operations Dashboards — SQL Files",
        "",
        "Each `panel_NN_*.sql` file is auto-extracted from `docs/OPERATIONS.md`",
        "by `ops/scripts/extract_dashboard_sql.py`. The doc is the source of truth;",
        "this directory makes the SQL paste-ready for Supabase Studio / Metabase / Grafana.",
        "",
        "## Files",
        "",
    ]
    for name in written:
        index_lines.append(f"- [`{name}`]({name})")
    index_lines.append("")
    index_path.write_text("\n".join(index_lines), encoding="utf-8")

    print(f"Wrote {len(written)} panel files to {DEST_DIR}")
    for name in written:
        print(f"  - {name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
