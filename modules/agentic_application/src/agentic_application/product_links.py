from __future__ import annotations

import re

# Known Shopify CDN shop-ID → store domain mapping.
# The CDN path is ``cdn.shopify.com/s/files/1/{a}/{b}/{c}/{d}/…``
# where {a}/{b}/{c}/{d} identifies the store.  We key on the first
# three segments (``{a}/{b}/{c}``) which is unique enough in practice.
# Verified via live product-page checks (HTTP 200) or existing CSV data.
_SHOPIFY_CDN_STORE_MAP: dict[str, str] = {
    "0618/3183/9957": "bombayshirtcompany.com",
    "0409/0209/9097": "thesouledstore.com",
    "0105/8881/5418": "bunaai.com",
    "0517/2939/9964": "flik.in",
    "0270/5129/4854": "www.nicobar.com",
    "0842/6559/9252": "showoffff.in",
    "0103/1890/5441": "offduty.in",
}

_CDN_RE = re.compile(
    r"cdn\.shopify\.com/s/files/1/(\d{4}/\d{4}/\d{4})"
)


def _extract_shopify_store_domain(image_url: str) -> str:
    """Derive the store domain from a Shopify CDN image URL."""
    m = _CDN_RE.search(image_url)
    if not m:
        return ""
    return _SHOPIFY_CDN_STORE_MAP.get(m.group(1), "")


def resolve_product_url(
    *,
    raw_url: str = "",
    store: str = "",
    handle: str = "",
    image_url: str = "",
) -> str:
    url = str(raw_url or "").strip()
    if url.startswith("http://") or url.startswith("https://"):
        return url
    if url.startswith("/"):
        url = url[1:]
    if url and "." in url and "/" in url:
        return f"https://{url}"

    # The URL is a bare Shopify handle (e.g. "cedar-green-cotton-oxford-shirt").
    # Try to reconstruct the full URL from the CDN image path.
    slug = url or str(handle or "").strip()
    if slug and re.fullmatch(r"[a-z0-9][a-z0-9_-]*", slug):
        domain = _extract_shopify_store_domain(str(image_url or ""))
        if domain:
            return f"https://{domain}/products/{slug}"

    return ""


__all__ = ["resolve_product_url"]
