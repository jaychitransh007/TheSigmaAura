"""Readiness checks — Item 3 of the Observability Hardening plan.

Distinguishes liveness (process is up — answer immediately, no
external calls) from readiness (process can serve real traffic —
verify upstreams are reachable). Kubernetes / load balancers /
service meshes need both: liveness drives restart decisions,
readiness drives traffic routing.

The three checks are intentionally fast (≤2s timeout each, run in
parallel) so the readiness probe stays under 3s even when one
upstream is degraded. A failed check translates to a 503 response
on ``/readyz`` so an unhealthy instance is taken out of the load
balancer rotation immediately.

Each check returns ``(ok: bool, error: str)``:
- ``ok`` = True when the upstream responds in a reasonable time
- ``error`` = human-readable detail when ``ok`` is False; empty otherwise
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, Optional, Tuple

DEFAULT_TIMEOUT_SECONDS = 2.0


def _http_head(url: str, headers: Optional[Dict[str, str]] = None,
               timeout: float = DEFAULT_TIMEOUT_SECONDS) -> Tuple[bool, str]:
    """HEAD request returning (ok, error). 200-399 = ok; auth/4xx/5xx = bad."""
    try:
        req = urllib.request.Request(url, method="HEAD", headers=headers or {})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = resp.status
        if 200 <= status < 400:
            return True, ""
        return False, f"unexpected status {status}"
    except urllib.error.HTTPError as exc:
        # Some endpoints respond 401/405 to a HEAD even when reachable —
        # treat 401 (unauth) and 405 (method not allowed) as "alive".
        if exc.code in (401, 405):
            return True, ""
        return False, f"http {exc.code}: {exc.reason}"
    except urllib.error.URLError as exc:
        return False, f"connection failed: {exc.reason}"
    except Exception as exc:  # noqa: BLE001 — health check must never raise
        return False, f"{type(exc).__name__}: {exc}"


def check_supabase(rest_url: str, service_role_key: str,
                   timeout: float = DEFAULT_TIMEOUT_SECONDS) -> Tuple[bool, str]:
    """Verify Supabase REST is reachable + auth works.

    Strategy: HEAD on the ``/users`` table with an empty filter and a
    1-row range — Supabase echoes status 200/206 if connection +
    permissions are fine, 401 if the service-role key is wrong.
    """
    try:
        url = f"{rest_url.rstrip('/')}/users?select=id&limit=1"
        req = urllib.request.Request(
            url, method="GET",
            headers={
                "apikey": service_role_key,
                "Authorization": f"Bearer {service_role_key}",
                "Range": "0-0",
                "Range-Unit": "items",
                "Accept": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = resp.status
        if 200 <= status < 400:
            return True, ""
        return False, f"unexpected status {status}"
    except urllib.error.HTTPError as exc:
        return False, f"http {exc.code}: {exc.reason}"
    except urllib.error.URLError as exc:
        return False, f"connection failed: {exc.reason}"
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}: {exc}"


def check_openai(api_key: Optional[str],
                 timeout: float = DEFAULT_TIMEOUT_SECONDS) -> Tuple[bool, str]:
    """HEAD api.openai.com/v1/models with auth header. Skips when key absent."""
    if not api_key:
        return False, "OPENAI_API_KEY not set"
    return _http_head(
        "https://api.openai.com/v1/models",
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=timeout,
    )


def check_gemini(api_key: Optional[str],
                 timeout: float = DEFAULT_TIMEOUT_SECONDS) -> Tuple[bool, str]:
    """HEAD generativelanguage.googleapis.com models endpoint. Skips when key absent."""
    if not api_key:
        return False, "GEMINI_API_KEY not set"
    # Gemini's public endpoint accepts the API key as a query parameter.
    return _http_head(
        f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}",
        timeout=timeout,
    )


def run_all_checks(
    *,
    supabase_rest_url: str,
    supabase_service_role_key: str,
    openai_api_key: Optional[str] = None,
    gemini_api_key: Optional[str] = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> Dict[str, Any]:
    """Run all dependency checks in parallel. Returns a structured report.

    A slow upstream cannot dominate the probe — total wall time is at
    most ``timeout`` seconds plus thread-pool overhead.
    """
    started = time.monotonic()
    checks: Dict[str, Tuple[bool, str]] = {}
    work = {
        "supabase": (check_supabase, (supabase_rest_url, supabase_service_role_key, timeout)),
        "openai":   (check_openai,   (openai_api_key, timeout)),
        "gemini":   (check_gemini,   (gemini_api_key, timeout)),
    }
    with ThreadPoolExecutor(max_workers=3) as executor:
        futs = {executor.submit(fn, *args): name for name, (fn, args) in work.items()}
        for fut in as_completed(futs):
            name = futs[fut]
            try:
                ok, err = fut.result(timeout=timeout + 1.0)
            except Exception as exc:  # noqa: BLE001
                ok, err = False, f"{type(exc).__name__}: {exc}"
            checks[name] = (ok, err)
    elapsed_ms = int((time.monotonic() - started) * 1000)
    return {
        "ready": all(ok for ok, _ in checks.values()),
        "elapsed_ms": elapsed_ms,
        "checks": {
            name: {"ok": ok, "error": err}
            for name, (ok, err) in sorted(checks.items())
        },
    }


def version_info() -> Dict[str, str]:
    """Return commit / deploy / env identifiers for the /version endpoint.

    Populated from environment variables the deploy pipeline sets:
        AURA_COMMIT_SHA      — git SHA of the deployed build (default "unknown")
        AURA_DEPLOYED_AT     — ISO timestamp of the deploy   (default "unknown")
        APP_ENV              — staging / production / local (default "unknown")
    """
    return {
        "commit": os.getenv("AURA_COMMIT_SHA", "unknown"),
        "deployed_at": os.getenv("AURA_DEPLOYED_AT", "unknown"),
        "env": os.getenv("APP_ENV", "unknown"),
    }
