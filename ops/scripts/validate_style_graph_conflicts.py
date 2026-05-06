#!/usr/bin/env python3
"""Within each user-attribute value's section, check that no garment
attribute has the same value in both `flatters` and `avoid`.

Run from repo root:
    python ops/scripts/validate_style_graph_conflicts.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def find_conflicts(path):
    text = path.read_text()
    lines = text.split("\n")

    conflicts = []
    # Walk through file, track current user attribute + value being processed
    user_attr = None
    user_value = None
    flatters = {}  # garment_attr → set of values
    avoid = {}
    in_flatters = False
    in_avoid = False

    def _flush(uattr, uval, fl, av):
        if not (uattr and uval):
            return
        for gattr, fvals in fl.items():
            avals = av.get(gattr, set())
            both = fvals & avals
            if both:
                conflicts.append((path.name, uattr, uval, gattr, sorted(both)))

    for i, line in enumerate(lines):
        # Top-level user attribute: e.g. "BodyShape:" at column 0
        m_uattr = re.match(r"^([A-Z][A-Za-z]+):\s*$", line)
        if m_uattr:
            _flush(user_attr, user_value, flatters, avoid)
            user_attr = m_uattr.group(1)
            user_value = None
            flatters, avoid = {}, {}
            in_flatters = in_avoid = False
            continue

        # User-attribute value: e.g. "  Hourglass:" or "  \"Flat / Minimal\":"
        m_uval = re.match(r"^  ([A-Z\"][^:]*):\s*$", line)
        if m_uval and user_attr:
            _flush(user_attr, user_value, flatters, avoid)
            user_value = m_uval.group(1).strip().strip('"')
            flatters, avoid = {}, {}
            in_flatters = in_avoid = False
            continue

        # flatters: / avoid: markers
        if re.match(r"^    flatters:", line):
            in_flatters = True
            in_avoid = False
            continue
        if re.match(r"^    avoid:", line):
            in_flatters = False
            in_avoid = True
            continue
        if re.match(r"^    notes:", line):
            in_flatters = in_avoid = False
            continue

        # Garment attribute line under flatters/avoid
        m_gattr = re.match(r"^      ([A-Z][A-Za-z]+):\s*\[([^\]]*)\]", line)
        if m_gattr and (in_flatters or in_avoid):
            gattr = m_gattr.group(1)
            vals = {v.strip().strip('"').strip("'") for v in m_gattr.group(2).split(",") if v.strip()}
            if in_flatters:
                flatters.setdefault(gattr, set()).update(vals)
            else:
                avoid.setdefault(gattr, set()).update(vals)

    _flush(user_attr, user_value, flatters, avoid)
    return conflicts


def main():
    style_graph = ROOT / "knowledge/style_graph"
    if not style_graph.exists():
        print(f"No style_graph dir at {style_graph} — nothing to validate.")
        return 0
    files = sorted(style_graph.rglob("*.yaml"))
    if not files:
        print(f"No YAML files under {style_graph} — nothing to validate.")
        return 0
    all_conflicts = []
    for f in files:
        all_conflicts.extend(find_conflicts(f))

    if not all_conflicts:
        print("NO CONFLICTS — every garment attr value appears in either flatters or avoid, never both ✓")
        return 0

    print(f"=== CONFLICTS ({len(all_conflicts)}) ===")
    for fname, uattr, uval, gattr, both in all_conflicts:
        print(f"  {fname}  {uattr}.{uval}  {gattr}: {both} (in BOTH flatters and avoid)")
    return 1


if __name__ == "__main__":
    sys.exit(main())
