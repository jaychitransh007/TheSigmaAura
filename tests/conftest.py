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

# Dynamically discover module src/ directories so a new modules/<name>/
# pulled into the monorepo doesn't need a manual conftest update.
# `sorted()` keeps the order deterministic so test-collection order is
# stable across machines.
_MODULE_SRC_DIRS = (
    _REPO_ROOT,
    *sorted((_REPO_ROOT / "modules").glob("*/src")),
)

# Move-to-front (rather than insert-only-if-absent) so the local source
# always wins over a stale PYTHONPATH entry or an installed package
# with the same module name. Without this, an env that exported the
# same path further back in sys.path would silently let pytest import
# from there.
for _path in _MODULE_SRC_DIRS:
    _str = str(_path)
    if _str in sys.path:
        sys.path.remove(_str)
    sys.path.insert(0, _str)
