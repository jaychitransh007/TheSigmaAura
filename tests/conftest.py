"""Pytest fixture: add the project's src-layout module roots to ``sys.path``.

Aura uses a multi-module src-layout (``modules/<name>/src/<name>/...``)
without a top-level package install, so test files have historically
prepended each module's src directory to ``sys.path`` themselves. That
boilerplate is repeated in every test file and is the kind of thing
pytest's ``conftest.py`` is meant to centralise.

This file runs at collection time, before any test module is imported,
so the imports inside test files (``from agentic_application... import
...``) resolve cleanly without per-file path manipulation.

New test files should NOT repeat the ``sys.path.insert`` block — just
import what they need. Older files still carry the inline setup; it's
idempotent (each insert is guarded by ``if sp not in sys.path``) and
gets cleaned up incrementally as files are touched.
"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]

_MODULE_SRC_DIRS = (
    _REPO_ROOT,
    _REPO_ROOT / "modules" / "agentic_application" / "src",
    _REPO_ROOT / "modules" / "catalog" / "src",
    _REPO_ROOT / "modules" / "platform_core" / "src",
    _REPO_ROOT / "modules" / "style_engine" / "src",
    _REPO_ROOT / "modules" / "user" / "src",
    _REPO_ROOT / "modules" / "user_profiler" / "src",
)

for _path in _MODULE_SRC_DIRS:
    _str = str(_path)
    if _str not in sys.path:
        sys.path.insert(0, _str)
