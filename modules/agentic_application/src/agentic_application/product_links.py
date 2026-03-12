from __future__ import annotations


_STORE_DOMAINS = {
    "andamen": "andamen.com",
    "bunaai": "bunaai.com",
    "dashanddot": "dashanddot.com",
    "houseoffett": "houseoffett.com",
    "ikkivi": "ikkivi.com",
    "kalki": "kalkifashion.com",
    "kharakapas": "kharakapas.com",
    "lovepangolin": "lovepangolin.com",
    "nicobar": "nicobar.com",
    "powerlook": "powerlook.in",
    "saltattire": "saltattire.com",
    "suta": "suta.in",
    "thebearhouse": "thebearhouse.com",
    "thehouseofrare": "thehouseofrare.com",
}


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

    normalized_store = str(store or "").strip().lower()
    normalized_handle = str(handle or "").strip().strip("/")
    if not normalized_handle:
        normalized_handle = url
    normalized_handle = str(normalized_handle or "").strip().strip("/")
    if not normalized_handle:
        return ""

    domain = _STORE_DOMAINS.get(normalized_store)
    if not domain:
        return ""
    return f"https://www.{domain}/products/{normalized_handle}"


__all__ = ["resolve_product_url"]
