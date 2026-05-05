import json
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

import httpx


class SupabaseError(RuntimeError):
    pass


# May 5, 2026 — switched from urllib.request.urlopen to a per-instance
# httpx.Client. The previous implementation opened a fresh TCP/TLS
# connection on every Supabase round trip. Pre-LLM DB pre-amble
# (onboarding_gate + user_context) was running ~2.8s/turn for what
# should be sub-200ms-per-call work. httpx.Client maintains a
# keep-alive connection pool, so subsequent calls in a turn re-use
# the established TLS session.
_DEFAULT_POOL_LIMITS = httpx.Limits(
    max_connections=20,
    max_keepalive_connections=10,
    keepalive_expiry=30.0,
)


class SupabaseRestClient:
    def __init__(self, rest_url: str, service_role_key: str, timeout_seconds: int = 60):
        self.rest_url = rest_url.rstrip("/")
        self.service_role_key = service_role_key
        self.timeout_seconds = timeout_seconds
        # Per-instance pool. Orchestrator constructs one SupabaseRestClient
        # at startup and reuses it across turns, so a single pool serves
        # the whole process. http2=True multiplexes concurrent reads
        # (e.g. once we parallelise onboarding_gate ↔ user_context in
        # PR E) over one connection.
        self._http = httpx.Client(
            timeout=httpx.Timeout(timeout_seconds, connect=5.0),
            limits=_DEFAULT_POOL_LIMITS,
            headers={
                "apikey": service_role_key,
                "Authorization": f"Bearer {service_role_key}",
                "Accept": "application/json",
            },
        )

    def close(self) -> None:
        """Release the HTTP connection pool. Tests should call this in
        teardown; production process exit handles it implicitly."""
        try:
            self._http.close()
        except Exception:  # noqa: BLE001
            pass

    def _request(
        self,
        method: str,
        path: str,
        *,
        query: Optional[Dict[str, Any]] = None,
        body: Any = None,
        prefer: str = "return=representation",
    ) -> Any:
        url = f"{self.rest_url}/{path.lstrip('/')}"
        if query:
            encoded = urlencode(query, doseq=True, safe="(),.*")
            url = f"{url}?{encoded}"

        headers = {
            "Content-Type": "application/json",
            "Prefer": prefer,
        }
        content = None
        if body is not None:
            content = json.dumps(body, ensure_ascii=True).encode("utf-8")

        # Item 5 (May 1, 2026): track external-call latency for the
        # /metrics endpoint so slow Supabase queries surface in
        # dashboards without log scraping.
        import time as _time
        started = _time.monotonic()
        status = "ok"
        try:
            resp = self._http.request(method, url, headers=headers, content=content)
            if resp.status_code >= 400:
                status = f"http_{resp.status_code}"
                raise SupabaseError(
                    f"Supabase request failed ({resp.status_code}) {method} {url}: {resp.text}"
                )
            raw = resp.text
            if not raw:
                return None
            return json.loads(raw)
        except SupabaseError:
            raise
        except Exception:
            status = "error"
            raise
        finally:
            try:
                from .metrics import observe_external_call
                observe_external_call(
                    service="supabase",
                    operation=f"{method} {path.split('?')[0]}",
                    status=status,
                    latency_ms=(_time.monotonic() - started) * 1000.0,
                )
            except Exception:  # noqa: BLE001
                pass

    def insert_one(self, table: str, row: Dict[str, Any]) -> Dict[str, Any]:
        out = self._request("POST", table, body=row)
        if isinstance(out, list) and out:
            return out[0]
        if isinstance(out, dict):
            return out
        raise SupabaseError(f"Unexpected insert response for {table}: {out}")

    def insert_many(self, table: str, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not rows:
            return []
        out = self._request("POST", table, body=rows)
        if isinstance(out, list):
            return out
        if isinstance(out, dict):
            return [out]
        raise SupabaseError(f"Unexpected bulk insert response for {table}: {out}")

    def upsert_many(self, table: str, rows: List[Dict[str, Any]], *, on_conflict: str) -> List[Dict[str, Any]]:
        if not rows:
            return []
        out = self._request(
            "POST",
            table,
            query={"on_conflict": on_conflict},
            body=rows,
            prefer="resolution=merge-duplicates,return=representation",
        )
        if isinstance(out, list):
            return out
        if isinstance(out, dict):
            return [out]
        raise SupabaseError(f"Unexpected bulk upsert response for {table}: {out}")

    def select_many(
        self,
        table: str,
        *,
        filters: Optional[Dict[str, str]] = None,
        columns: str = "*",
        order: Optional[str] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        query: Dict[str, Any] = {"select": columns}
        if filters:
            query.update(filters)
        if order:
            query["order"] = order
        if limit is not None:
            query["limit"] = str(limit)
        if offset is not None and offset > 0:
            query["offset"] = str(offset)
        out = self._request("GET", table, query=query, prefer="")
        if isinstance(out, list):
            return out
        if out is None:
            return []
        raise SupabaseError(f"Unexpected select response for {table}: {out}")

    def select_one(self, table: str, *, filters: Dict[str, str], columns: str = "*") -> Optional[Dict[str, Any]]:
        rows = self.select_many(table, filters=filters, columns=columns, limit=1)
        return rows[0] if rows else None

    def update_one(self, table: str, *, filters: Dict[str, str], patch: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        out = self._request("PATCH", table, query=filters, body=patch)
        if isinstance(out, list):
            return out[0] if out else None
        if isinstance(out, dict):
            return out
        if out is None:
            return None
        raise SupabaseError(f"Unexpected update response for {table}: {out}")

    def delete_one(self, table: str, *, filters: Dict[str, str]) -> None:
        """Delete row(s) matching ``filters``. Used by GDPR data-subject
        deletion (Item 7, May 1, 2026). Caller is responsible for using
        a sufficiently narrow filter to avoid mass deletion."""
        self._request("DELETE", table, query=filters, prefer="return=minimal")

    def rpc(self, function_name: str, payload: Dict[str, Any]) -> Any:
        return self._request("POST", f"rpc/{function_name}", body=payload)

