"""URL host → brand display name map for TheSigmaVibe catalog.

Confirmed against the 14,242-row profile (2026-05-14). Every row in the
catalog has a URL on one of these 10 hosts. The retailer IS the brand —
this is a direct-to-consumer set, not a marketplace aggregation.
"""
from urllib.parse import urlparse

HOST_TO_BRAND: dict[str, str] = {
    "koskii.com": "Koskii",
    "showoffff.in": "Showoffff",
    "taruni.in": "Taruni",
    "nicobar.com": "Nicobar",
    "vastramay.com": "Vastramay",
    "powerlook.in": "Powerlook",
    "campussutra.com": "Campus Sutra",
    "offduty.in": "Off Duty",
    "fawn24.com": "Fawn24",
    "virgio.com": "Virgio",
}


def brand_from_url(url: str) -> str:
    if not url:
        return ""
    try:
        host = urlparse(url).netloc.lower()
        if host.startswith("www."):
            host = host[4:]
        return HOST_TO_BRAND.get(host, "")
    except Exception:
        return ""
