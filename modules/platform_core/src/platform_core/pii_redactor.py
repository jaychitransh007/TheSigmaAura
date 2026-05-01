"""PII redaction for observability rows — Item 7 of Observability Hardening.

`model_call_logs.request_json`, `turn_traces.user_message`, and
`turn_traces.profile_snapshot` historically stored raw user input plus the
analysed profile attributes. That made every operator with read access a
PII reader. This module is the single chokepoint that scrubs the data
before insertion.

Two layers:

1. **String redaction** — recognises emails, phone numbers, SSN-shaped
   numbers and replaces them with stable placeholders. Reversible only by
   rebuilding the input from the original message (we don't keep that).

2. **Profile band-fold** — the `BodyShape` / `SeasonalColorGroup` style
   attributes are useful operationally; the exact `height_cm`,
   `waist_cm`, and `date_of_birth` are not. They are folded into the
   same bands the interpreter already produces (`Petite|Average|Tall`,
   `WaistSizeBand`, age band) so dashboards keep their utility while
   the PII surface area shrinks.

Used by `repositories.log_model_call` and `repositories.insert_turn_trace`.
Caller can pass `redact_pii=False` for explicit opt-out (debug runs only).
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any, Dict


# ── String patterns ────────────────────────────────────────────────────
EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")
# Match common phone shapes — international, US, Indian. Loose by design;
# the cost of false positives is "[PHONE]" in a log line.
PHONE_RE = re.compile(
    r"(?<!\d)(?:\+?\d{1,3}[\s.\-]?)?(?:\(?\d{3,4}\)?[\s.\-]?)?\d{3}[\s.\-]?\d{4}(?!\d)"
)
SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")


def redact_string(text: str) -> str:
    """Scrub PII tokens from a free-text string."""
    if not isinstance(text, str) or not text:
        return text
    text = EMAIL_RE.sub("[EMAIL]", text)
    text = SSN_RE.sub("[SSN]", text)
    text = PHONE_RE.sub("[PHONE]", text)
    return text


def redact_value(value: Any) -> Any:
    """Recursively walk dicts and lists, redacting strings; leave other types alone."""
    if isinstance(value, str):
        return redact_string(value)
    if isinstance(value, dict):
        return {k: redact_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [redact_value(v) for v in value]
    if isinstance(value, tuple):
        return tuple(redact_value(v) for v in value)
    return value


# ── Profile bands ─────────────────────────────────────────────────────


def _height_band(height_cm: float) -> str:
    """Mirrors the interpreter's deterministic HeightCategory tiers."""
    if height_cm <= 0:
        return ""
    if height_cm < 160:
        return "Petite"
    if height_cm <= 175:
        return "Average"
    return "Tall"


def _waist_band(waist_cm: float) -> str:
    """Coarse waist band — keeps relative-size info without storing the cm value."""
    if waist_cm <= 0:
        return ""
    if waist_cm < 65:
        return "Very Small"
    if waist_cm < 75:
        return "Small"
    if waist_cm < 85:
        return "Medium"
    if waist_cm < 95:
        return "Large"
    return "Very Large"


def _age_band(dob: Any) -> str:
    """Convert date_of_birth (str or date) to a 5-year age band."""
    try:
        if isinstance(dob, str):
            dob_d = datetime.fromisoformat(dob.replace("Z", "+00:00")).date()
        elif isinstance(dob, datetime):
            dob_d = dob.date()
        elif isinstance(dob, date):
            dob_d = dob
        else:
            return ""
    except (ValueError, TypeError):
        return ""
    today = date.today()
    age = today.year - dob_d.year - (
        (today.month, today.day) < (dob_d.month, dob_d.day)
    )
    if age < 18:
        return "<18"
    if age >= 65:
        return "65+"
    bucket_start = (age // 5) * 5
    return f"{bucket_start}-{bucket_start + 4}"


def redact_profile(profile: Dict[str, Any]) -> Dict[str, Any]:
    """Fold continuous profile fields into bands. Returns a new dict.

    Only touches the small set of fields that are demonstrably PII.
    Style archetype, body shape category, color season etc. all stay.
    """
    if not isinstance(profile, dict):
        return profile  # type: ignore[return-value]
    out = dict(profile)

    if isinstance(out.get("height_cm"), (int, float)) and out["height_cm"]:
        out["height_band"] = _height_band(out["height_cm"])
        out.pop("height_cm", None)

    if isinstance(out.get("waist_cm"), (int, float)) and out["waist_cm"]:
        out["waist_band"] = _waist_band(out["waist_cm"])
        out.pop("waist_cm", None)

    if out.get("date_of_birth"):
        out["age_band"] = _age_band(out["date_of_birth"])
        out.pop("date_of_birth", None)

    # Drop the user's full name — the external_user_id is enough for
    # operational correlation; the name has no debugging value.
    out.pop("name", None)

    # Mobile / phone — already covered by string redaction but the
    # profile may have it as a structured field.
    out.pop("mobile", None)
    out.pop("phone", None)

    return out
