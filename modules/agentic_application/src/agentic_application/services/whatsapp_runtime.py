from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List
from urllib import error, request


_URL_PATTERN = re.compile(r"https?://\S+", re.IGNORECASE)


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso_datetime(value: str) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _infer_media_type(message_type: str, text: str) -> str:
    normalized_type = str(message_type or "").strip().lower()
    lowered_text = str(text or "").strip().lower()
    if normalized_type == "image":
        if "save" in lowered_text and "wardrobe" in lowered_text:
            return "wardrobe_item"
        if "look on me" in lowered_text or "on me" in lowered_text:
            return "garment_on_me"
        return "outfit_photo"
    if normalized_type in {"button", "interactive"} and ("buy" in lowered_text or "product" in lowered_text):
        return "product"
    if normalized_type == "text" and _URL_PATTERN.search(lowered_text):
        return "product"
    return ""


def _extract_link_url(*parts: str) -> str:
    for part in parts:
        match = _URL_PATTERN.search(str(part or ""))
        if match:
            return match.group(0).rstrip(").,!?")
    return ""


def verify_whatsapp_webhook(
    *,
    mode: str,
    verify_token: str,
    challenge: str,
    expected_verify_token: str,
) -> str:
    if mode != "subscribe":
        raise ValueError("Unsupported webhook mode.")
    if not expected_verify_token:
        raise ValueError("WhatsApp webhook verify token is not configured.")
    if verify_token != expected_verify_token:
        raise ValueError("WhatsApp webhook verify token mismatch.")
    return str(challenge or "")


def normalize_whatsapp_webhook_payload(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    entries = list((payload or {}).get("entry") or [])
    normalized: List[Dict[str, Any]] = []
    for entry in entries:
        for change in list((entry or {}).get("changes") or []):
            value = dict((change or {}).get("value") or {})
            contacts = list(value.get("contacts") or [])
            contact_map = {
                str(contact.get("wa_id") or "").strip(): str(((contact.get("profile") or {}).get("name") or "")).strip()
                for contact in contacts
                if str(contact.get("wa_id") or "").strip()
            }
            for message in list(value.get("messages") or []):
                msg = dict(message or {})
                message_type = str(msg.get("type") or "").strip().lower()
                from_phone = str(msg.get("from") or "").strip()
                text_body = str(((msg.get("text") or {}).get("body") or "")).strip()
                interactive = dict(msg.get("interactive") or {})
                button_text = str(((interactive.get("button_reply") or {}).get("title") or "")).strip()
                list_text = str(((interactive.get("list_reply") or {}).get("title") or "")).strip()
                caption = str(((msg.get("image") or {}).get("caption") or "")).strip()
                normalized_text = text_body or button_text or list_text or caption
                image_block = dict(msg.get("image") or {})
                image_url = str(image_block.get("link") or image_block.get("url") or "").strip()
                link_url = _extract_link_url(normalized_text, caption, image_url)

                normalized.append(
                    {
                        "phone_number": f"+{from_phone}" if from_phone and not from_phone.startswith("+") else from_phone,
                        "message": normalized_text,
                        "message_id": str(msg.get("id") or "").strip(),
                        "profile_name": contact_map.get(from_phone, ""),
                        "image_url": image_url,
                        "link_url": link_url,
                        "media_type": _infer_media_type(message_type, f"{normalized_text} {caption}"),
                        "message_type": message_type,
                        "raw_message": msg,
                    }
                )
    return normalized


@dataclass(frozen=True)
class WhatsAppDeliveryResult:
    delivered: bool
    skipped: bool = False
    status_code: int = 0
    response_text: str = ""
    error: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {
            "delivered": self.delivered,
            "skipped": self.skipped,
            "status_code": self.status_code,
            "response_text": self.response_text,
            "error": self.error,
        }


class WhatsAppCloudSender:
    def __init__(
        self,
        *,
        access_token: str = "",
        phone_number_id: str = "",
        api_version: str = "v22.0",
    ) -> None:
        self._access_token = str(access_token or "").strip()
        self._phone_number_id = str(phone_number_id or "").strip()
        self._api_version = str(api_version or "v22.0").strip() or "v22.0"

    def is_configured(self) -> bool:
        return bool(self._access_token and self._phone_number_id)

    def send_text_message(self, *, phone_number: str, message: str) -> WhatsAppDeliveryResult:
        if not self.is_configured():
            return WhatsAppDeliveryResult(
                delivered=False,
                skipped=True,
                error="missing_whatsapp_cloud_api_config",
            )

        url = (
            f"https://graph.facebook.com/{self._api_version}/"
            f"{self._phone_number_id}/messages"
        )
        body = json.dumps(
            {
                "messaging_product": "whatsapp",
                "to": phone_number.lstrip("+"),
                "type": "text",
                "text": {"preview_url": True, "body": str(message or "").strip()},
            }
        ).encode("utf-8")
        req = request.Request(
            url,
            data=body,
            headers={
                "Authorization": f"Bearer {self._access_token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=15) as resp:
                response_text = resp.read().decode("utf-8", errors="replace")
                return WhatsAppDeliveryResult(
                    delivered=200 <= int(resp.status) < 300,
                    status_code=int(resp.status),
                    response_text=response_text,
                )
        except error.HTTPError as exc:
            response_text = exc.read().decode("utf-8", errors="replace")
            return WhatsAppDeliveryResult(
                delivered=False,
                status_code=int(exc.code or 0),
                response_text=response_text,
                error=str(exc),
            )
        except Exception as exc:  # noqa: BLE001
            return WhatsAppDeliveryResult(
                delivered=False,
                error=str(exc),
            )


def evaluate_reengagement_trigger(
    *,
    previous_context: Dict[str, Any] | None,
    conversation_updated_at: str = "",
    reminder_type: str = "",
    now_iso: str = "",
) -> Dict[str, Any]:
    context = dict(previous_context or {})
    last_response_metadata = dict(context.get("last_response_metadata") or {})
    if bool(last_response_metadata.get("onboarding_required")):
        return {
            "eligible": False,
            "reason": "onboarding_required",
            "cooldown_hours": 0,
        }

    requested = str(reminder_type or "").strip()
    last_intent = str(context.get("last_intent") or "").strip()
    resolved_type = requested or last_intent or "followup"

    cooldown_by_type = {
        "shopping": 48,
        "shopping_decision": 48,
        "occasion": 36,
        "occasion_recommendation": 36,
        "wardrobe": 72,
        "pairing_request": 72,
        "outfit_check": 72,
        "capsule_or_trip_planning": 168,
        "reactivation": 168,
        "followup": 72,
    }
    cooldown_hours = int(cooldown_by_type.get(resolved_type, 72))
    conversation_dt = _parse_iso_datetime(conversation_updated_at)
    now_dt = _parse_iso_datetime(now_iso) or _now_utc()
    if conversation_dt is None:
        return {
            "eligible": True,
            "reason": "no_prior_timestamp",
            "cooldown_hours": cooldown_hours,
        }

    elapsed = now_dt - conversation_dt
    eligible = elapsed >= timedelta(hours=cooldown_hours)
    return {
        "eligible": eligible,
        "reason": "cooldown_satisfied" if eligible else "cooldown_active",
        "cooldown_hours": cooldown_hours,
        "elapsed_hours": round(max(elapsed.total_seconds(), 0) / 3600, 2),
        "next_eligible_at": (conversation_dt + timedelta(hours=cooldown_hours)).isoformat(),
    }
