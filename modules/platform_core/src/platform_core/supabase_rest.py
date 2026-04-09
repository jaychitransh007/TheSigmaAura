import json
from typing import Any, Dict, List, Optional
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class SupabaseError(RuntimeError):
    pass


class SupabaseRestClient:
    def __init__(self, rest_url: str, service_role_key: str, timeout_seconds: int = 60):
        self.rest_url = rest_url.rstrip("/")
        self.service_role_key = service_role_key
        self.timeout_seconds = timeout_seconds

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
            "apikey": self.service_role_key,
            "Authorization": f"Bearer {self.service_role_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Prefer": prefer,
        }
        data = None
        if body is not None:
            data = json.dumps(body, ensure_ascii=True).encode("utf-8")

        req = Request(url=url, method=method, headers=headers, data=data)
        try:
            with urlopen(req, timeout=self.timeout_seconds) as resp:
                raw = resp.read().decode("utf-8")
                if not raw:
                    return None
                return json.loads(raw)
        except HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            raise SupabaseError(f"Supabase request failed ({exc.code}) {method} {url}: {raw}") from exc

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

    def rpc(self, function_name: str, payload: Dict[str, Any]) -> Any:
        return self._request("POST", f"rpc/{function_name}", body=payload)

