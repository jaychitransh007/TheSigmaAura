"""Tests for the ops/alerts/ rules and the sync_alerts.py validator (Item 9)."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
ALERTS_DIR = REPO_ROOT / "ops" / "alerts"
SYNC_PATH = REPO_ROOT / "ops" / "scripts" / "sync_alerts.py"


def _load_sync_module():
    spec = importlib.util.spec_from_file_location("sync_alerts", SYNC_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


class AlertRulesShape(unittest.TestCase):
    """Item 9 (May 1, 2026): every alert YAML in the repo must validate."""

    def setUp(self) -> None:
        self.sync = _load_sync_module()

    def test_all_alerts_validate(self) -> None:
        files = sorted(p for p in ALERTS_DIR.glob("*.yaml") if not p.name.startswith("_"))
        self.assertGreater(len(files), 0, "no alert YAML files present")
        for path in files:
            with self.subTest(alert=path.name):
                alert = self.sync._load_yaml(path)
                errors = self.sync._validate(path.name, alert)
                self.assertEqual([], errors, f"{path.name}: {errors}")

    def test_alert_names_are_namespaced_with_aura_prefix(self) -> None:
        for path in ALERTS_DIR.glob("*.yaml"):
            alert = self.sync._load_yaml(path)
            self.assertTrue(
                str(alert.get("alert", "")).startswith("aura_"),
                f"{path.name}: alert name {alert.get('alert')!r} should start with 'aura_'",
            )

    def test_severity_field_is_p1_or_p2(self) -> None:
        for path in ALERTS_DIR.glob("*.yaml"):
            alert = self.sync._load_yaml(path)
            self.assertIn(alert.get("severity"), {"P1", "P2"}, f"{path.name}: bad severity")

    def test_emit_prometheus_produces_text_with_groups_header(self) -> None:
        files = sorted(p for p in ALERTS_DIR.glob("*.yaml") if not p.name.startswith("_"))
        alerts = [(p.name, self.sync._load_yaml(p)) for p in files]
        out = self.sync._emit_prometheus(alerts)
        self.assertIn("groups:", out)
        self.assertIn("name: aura.rules", out)
        # Each alert name should appear in the output
        for path in files:
            alert = self.sync._load_yaml(path)
            self.assertIn(alert["alert"], out)


if __name__ == "__main__":
    unittest.main()
