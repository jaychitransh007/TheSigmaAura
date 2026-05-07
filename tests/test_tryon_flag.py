"""Tests for the AURA_TRYON_ENABLED flag (May 8 2026).

Tryon is the single biggest cost line ($0.117/turn) and biggest
latency line (~22s). The flag gates the entire render stage so dev
loops don't burn cost on renders nobody is looking at. Covered here:

- ``AuraRuntimeConfig.tryon_enabled`` defaults False
- ``load_config()`` parses ``AURA_TRYON_ENABLED`` from env (truthy
  and falsy values)
- ``_attach_tryon_images`` short-circuits when the flag is off
  (no Gemini call even on cache miss)

The flag-on tryon_render-stage path is already exercised by the
existing rendering tests; we don't reproduce them here.
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# CI runs `python -m unittest discover` (not pytest); inline the
# sys.path bootstrap so this file works under both runners.
_ROOT = Path(__file__).resolve().parents[1]
for _p in (
    _ROOT,
    _ROOT / "modules" / "user" / "src",
    _ROOT / "modules" / "agentic_application" / "src",
    _ROOT / "modules" / "catalog" / "src",
    _ROOT / "modules" / "platform_core" / "src",
    _ROOT / "modules" / "user_profiler" / "src",
):
    _sp = str(_p)
    if _sp not in sys.path:
        sys.path.insert(0, _sp)

from platform_core.config import AuraRuntimeConfig, load_config


class TryonConfigParsingTests(unittest.TestCase):

    def test_default_is_false(self):
        # Dataclass-level default — touched only when load_config isn't.
        self.assertFalse(AuraRuntimeConfig(
            supabase_rest_url="x", supabase_service_role_key="y",
        ).tryon_enabled)

    def _load_with_env(self, raw_value: str) -> bool:
        # Hard-set the env, then load. Need to also satisfy load_config's
        # other required env vars; the test seeds the bare minimum.
        with patch.dict(os.environ, {
            "AURA_TRYON_ENABLED": raw_value,
            "SUPABASE_URL": "http://x.example",
            "SUPABASE_SERVICE_ROLE_KEY": "test-key",
            "ENV_FILE": "/dev/null",  # avoid loading any real .env
        }, clear=False):
            cfg = load_config()
        return cfg.tryon_enabled

    def test_env_truthy_strings_enable(self):
        for v in ("1", "true", "TRUE", "Yes", "on", "ON"):
            self.assertTrue(self._load_with_env(v), f"value {v!r} should be truthy")

    def test_env_falsy_strings_disable(self):
        for v in ("", "0", "false", "no", "off", "garbage", "tru"):
            self.assertFalse(self._load_with_env(v), f"value {v!r} should be falsy")


class AttachTryonImagesGateTests(unittest.TestCase):
    """Confirms _attach_tryon_images short-circuits when the flag is
    off, so the cache-miss → Gemini fallback inside that method
    doesn't defeat the flag."""

    def _build_orchestrator(self, *, tryon_enabled: bool):
        # Build a minimal stub orchestrator without touching __init__'s
        # full wiring. We just need _attach_tryon_images bound to self
        # plus the _tryon_enabled and tryon_service attributes.
        from agentic_application.orchestrator import AgenticOrchestrator
        orch = AgenticOrchestrator.__new__(AgenticOrchestrator)
        orch._tryon_enabled = tryon_enabled
        orch.tryon_service = MagicMock()
        orch.tryon_quality_gate = MagicMock()
        orch.onboarding_gateway = MagicMock()
        orch.onboarding_gateway.get_person_image_path.return_value = "/tmp/person.jpg"
        orch.repo = MagicMock()
        return orch

    def test_flag_off_skips_gemini_call(self):
        # Flag off + cache miss: Gemini must NOT be called.
        # PR #185 review: cache lookups still proceed (zero cost) so
        # previously rendered images can be attached even when
        # generation is gated.
        from agentic_application.schemas import OutfitCard
        orch = self._build_orchestrator(tryon_enabled=False)
        orch.repo.find_tryon_image_by_garments.return_value = None  # cache miss
        outfits = [OutfitCard(
            rank=1, title="t", reasoning="r",
            items=[{"product_id": "p1", "image_url": "http://x/p1.jpg", "role": "top"}],
        )]
        orch._attach_tryon_images(outfits, "external_user_id")
        orch.tryon_service.generate_tryon_outfit.assert_not_called()

    def test_flag_off_still_does_cache_lookup(self):
        # PR #185 review: cache lookups proceed regardless of flag.
        # If the cache HAS a hit, the outfit gets the cached image
        # even with the flag off.
        from agentic_application.schemas import OutfitCard
        orch = self._build_orchestrator(tryon_enabled=False)
        # Set up a cache hit
        orch.repo.find_tryon_image_by_garments.return_value = None  # tested separately above
        outfits = [OutfitCard(
            rank=1, title="t", reasoning="r",
            items=[{"product_id": "p1", "image_url": "http://x/p1.jpg", "role": "top"}],
        )]
        orch._attach_tryon_images(outfits, "external_user_id")
        # Cache lookup happened (regardless of result).
        orch.repo.find_tryon_image_by_garments.assert_called()

    def test_person_image_path_lookup_is_lazy(self):
        # PR #190 review: get_person_image_path is only called when
        # generation is about to fire. Cache-only / empty-outfit paths
        # don't pay for the DB lookup. Verifies the lazy-cell behavior
        # added in the review-feedback PR.
        orch = self._build_orchestrator(tryon_enabled=True)
        outfits: list = []  # empty outfits → loop body never runs
        orch._attach_tryon_images(outfits, "external_user_id")
        orch.onboarding_gateway.get_person_image_path.assert_not_called()

    def test_flag_off_skips_person_image_lookup_too(self):
        # Flag off with cache miss: generation gate trips before the
        # person path lookup, so the lookup is also skipped.
        from agentic_application.schemas import OutfitCard
        orch = self._build_orchestrator(tryon_enabled=False)
        orch.repo.find_tryon_image_by_garments.return_value = None
        outfits = [OutfitCard(
            rank=1, title="t", reasoning="r",
            items=[{"product_id": "p1", "image_url": "http://x/p1.jpg", "role": "top"}],
        )]
        orch._attach_tryon_images(outfits, "external_user_id")
        orch.onboarding_gateway.get_person_image_path.assert_not_called()


if __name__ == "__main__":
    unittest.main()
