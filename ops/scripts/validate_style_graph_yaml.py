#!/usr/bin/env python3
"""Validate that every garment-attribute value used in the style_graph
YAML files exists in the canonical garment_attributes.json.

Run from repo root:
    python ops/scripts/validate_style_graph_yaml.py
"""
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load_canonical():
    cfg_path = ROOT / "modules/style_engine/configs/config/garment_attributes.json"
    with open(cfg_path) as f:
        cfg = json.load(f)
    enum_attrs = cfg["enum_attributes"]
    text_attrs = set(cfg["text_attributes"])
    known_attrs = set(enum_attrs.keys()) | text_attrs
    return enum_attrs, text_attrs, known_attrs


def parse_yaml_loosely(path, enum_attrs, text_attrs, known_attrs):
    """Walk the YAML files and extract every (garment_attr, value) pair
    that appears under flatters: or avoid:. Lightweight regex parser —
    avoids a yaml dep."""
    text = path.read_text()
    bad_attrs = []
    bad_values = []

    current_section = None
    indent_section = None

    lines = text.split("\n")
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        if re.match(r"^\s*(flatters|avoid):\s*(\{\}|$)", line):
            section = re.match(r"^\s*(flatters|avoid):", line).group(1)
            current_section = section
            indent_section = len(line) - len(line.lstrip())
            continue

        if current_section is not None:
            indent = len(line) - len(line.lstrip())
            if indent <= indent_section and stripped:
                if not re.match(r"^\s*(flatters|avoid|notes):", line):
                    current_section = None

        if current_section:
            m = re.match(r"^\s+([A-Z][A-Za-z]+):\s*\[([^\]]*)\]", line)
            if m:
                attr = m.group(1)
                values_str = m.group(2)

                if attr not in known_attrs:
                    bad_attrs.append((path.name, i + 1, attr, line.strip()))
                    continue

                if attr in text_attrs:
                    continue

                canonical = set(enum_attrs[attr])
                vals = [v.strip().strip('"').strip("'") for v in values_str.split(",")]
                for v in vals:
                    if not v:
                        continue
                    if v not in canonical:
                        bad_values.append((path.name, i + 1, attr, v))

    return bad_attrs, bad_values


def main():
    enum_attrs, text_attrs, known_attrs = load_canonical()
    style_graph = ROOT / "knowledge/style_graph"
    if not style_graph.exists():
        print(f"No style_graph dir at {style_graph} — nothing to validate.")
        return 0

    files = sorted(style_graph.rglob("*.yaml"))
    if not files:
        print(f"No YAML files under {style_graph} — nothing to validate.")
        return 0

    total_bad_attrs = []
    total_bad_values = []
    for f in files:
        bad_attrs, bad_values = parse_yaml_loosely(f, enum_attrs, text_attrs, known_attrs)
        total_bad_attrs.extend(bad_attrs)
        total_bad_values.extend(bad_values)

    print(f"Validated {len(files)} file(s).")

    if total_bad_attrs:
        print(f"\n=== UNKNOWN ATTRIBUTE NAMES ({len(total_bad_attrs)}) ===")
        for fname, lineno, attr, _ in total_bad_attrs:
            print(f"  {fname}:{lineno}  {attr}")

    if total_bad_values:
        print(f"\n=== INVALID VALUES ({len(total_bad_values)}) ===")
        grouped = defaultdict(list)
        for fname, lineno, attr, val in total_bad_values:
            grouped[attr].append((fname, lineno, val))
        for attr in sorted(grouped):
            print(f"\n  {attr} (canonical: {enum_attrs.get(attr, [])})")
            for fname, lineno, val in grouped[attr][:20]:
                print(f"    {fname}:{lineno}  '{val}' is NOT in canonical")
            if len(grouped[attr]) > 20:
                print(f"    ... and {len(grouped[attr]) - 20} more")

    if not total_bad_attrs and not total_bad_values:
        print("ALL VALUES VALID ✓")
        return 0
    print(f"\n=== TOTAL: {len(total_bad_attrs)} bad attrs, {len(total_bad_values)} bad values ===")
    return 1


if __name__ == "__main__":
    sys.exit(main())
