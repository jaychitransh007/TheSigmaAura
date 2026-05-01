#!/usr/bin/env python3
"""Validate and emit Aura alert rules — Item 9 of Observability Hardening.

Reads every ``ops/alerts/*.yaml`` file, validates the schema, and emits
the rules in Prometheus AlertManager format on stdout. Extend the
``_emit_*`` family below when wiring into Datadog Monitors or PagerDuty.

Usage:
    python3 ops/scripts/sync_alerts.py [--check-only] [--format prometheus]

Exit codes:
    0 — every rule validated; emission completed
    1 — at least one rule failed validation
    2 — usage error
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

REPO_ROOT = Path(__file__).resolve().parents[2]
ALERTS_DIR = REPO_ROOT / "ops" / "alerts"

REQUIRED_FIELDS = ("alert", "description", "expr", "for", "severity", "runbook", "labels", "annotations")
VALID_SEVERITIES = {"P1", "P2"}


def _load_yaml(path: Path) -> Dict[str, Any]:
    """Tiny YAML loader that handles the simple subset our alert files use.

    We avoid PyYAML because the project doesn't ship it; the alert format
    is restricted to flat keys + nested labels/annotations dicts +
    multiline string values via the ``|`` indicator. If the alert
    schema gets richer, swap to PyYAML.
    """
    text = path.read_text(encoding="utf-8")
    out: Dict[str, Any] = {}
    cur_key: str | None = None
    cur_dict: Dict[str, str] | None = None
    cur_block_lines: List[str] | None = None
    cur_block_indent = 0

    for raw in text.splitlines():
        line = raw.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        # Block scalar continuation
        if cur_block_lines is not None and (line.startswith(" " * cur_block_indent) or line.startswith("\t")):
            cur_block_lines.append(line[cur_block_indent:])
            continue
        if cur_block_lines is not None:
            out[cur_key] = "\n".join(cur_block_lines).rstrip()
            cur_block_lines = None
            cur_key = None

        if line.startswith("  ") and cur_dict is not None:
            k, _, v = line.strip().partition(":")
            cur_dict[k.strip()] = v.strip().strip('"').strip("'")
            continue
        cur_dict = None
        if ":" not in line:
            continue
        k, _, v = line.partition(":")
        k = k.strip()
        v = v.strip()
        if v == "|":
            cur_key = k
            cur_block_lines = []
            cur_block_indent = 2
            continue
        if not v:
            cur_dict = {}
            out[k] = cur_dict
            continue
        out[k] = v.strip('"').strip("'")
    if cur_block_lines is not None and cur_key is not None:
        out[cur_key] = "\n".join(cur_block_lines).rstrip()
    return out


def _validate(name: str, alert: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    for field in REQUIRED_FIELDS:
        if field not in alert or alert[field] in ("", None, {}):
            errors.append(f"{name}: missing required field {field!r}")
    if alert.get("severity") not in VALID_SEVERITIES:
        errors.append(f"{name}: severity must be one of {sorted(VALID_SEVERITIES)}; got {alert.get('severity')!r}")
    if "alert" in alert and not str(alert["alert"]).startswith("aura_"):
        errors.append(f"{name}: alert name must start with 'aura_' for namespacing")
    runbook = str(alert.get("runbook") or "")
    if runbook and runbook.startswith("docs/") and not (REPO_ROOT / runbook.split("#")[0]).exists():
        errors.append(f"{name}: runbook path {runbook!r} does not resolve in the repo")
    return errors


def _emit_prometheus(alerts: List[Tuple[str, Dict[str, Any]]]) -> str:
    lines: List[str] = ["groups:", "  - name: aura.rules", "    rules:"]
    for _, a in alerts:
        lines.append(f"      - alert: {a['alert']}")
        lines.append(f"        expr: |")
        for line in str(a["expr"]).splitlines():
            lines.append(f"          {line}")
        lines.append(f"        for: {a['for']}")
        lines.append(f"        labels:")
        labels = a.get("labels", {}) or {}
        labels.setdefault("severity", a.get("severity"))
        for k, v in sorted(labels.items()):
            lines.append(f"          {k}: \"{v}\"")
        ann = a.get("annotations", {}) or {}
        if "runbook" in a:
            ann.setdefault("runbook_url", a["runbook"])
        lines.append(f"        annotations:")
        for k, v in sorted(ann.items()):
            lines.append(f"          {k}: \"{v}\"")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-only", action="store_true", help="Validate without emitting output.")
    parser.add_argument("--format", default="prometheus", choices=("prometheus",))
    args = parser.parse_args()

    if not ALERTS_DIR.exists():
        print(f"alerts directory not found: {ALERTS_DIR}", file=sys.stderr)
        return 2

    files = sorted(p for p in ALERTS_DIR.glob("*.yaml") if not p.name.startswith("_"))
    if not files:
        print("no *.yaml files found", file=sys.stderr)
        return 2

    alerts: List[Tuple[str, Dict[str, Any]]] = []
    errors: List[str] = []
    for path in files:
        alert = _load_yaml(path)
        errs = _validate(path.name, alert)
        if errs:
            errors.extend(errs)
        else:
            alerts.append((path.name, alert))

    if errors:
        print("VALIDATION FAILED:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    print(f"OK: {len(alerts)} alert(s) validated", file=sys.stderr)
    if args.check_only:
        return 0

    if args.format == "prometheus":
        print(_emit_prometheus(alerts))

    return 0


if __name__ == "__main__":
    sys.exit(main())
