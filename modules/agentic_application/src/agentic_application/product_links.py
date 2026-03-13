from __future__ import annotations

def resolve_product_url(
    *,
    raw_url: str = "",
    store: str = "",
    handle: str = "",
) -> str:
    url = str(raw_url or "").strip()
    if url.startswith("http://") or url.startswith("https://"):
        return url
    if url.startswith("/"):
        url = url[1:]
    if url and "." in url and "/" in url:
        return f"https://{url}"
    return ""


__all__ = ["resolve_product_url"]
