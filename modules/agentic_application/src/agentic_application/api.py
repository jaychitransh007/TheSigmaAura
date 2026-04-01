from datetime import datetime, timezone
import re
from threading import Lock, Thread
from typing import Any, Dict, List
from uuid import uuid4

from catalog.admin_api import create_catalog_admin_router
from catalog.ui import get_catalog_admin_html
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, Response

from platform_core.api_schemas import (
    ConversationListItem,
    ConversationListResponse,
    ConversationResponse,
    ConversationStateResponse,
    CreateConversationRequest,
    CreateTurnRequest,
    DependencyReportResponse,
    FeedbackRequest,
    ReferralEventRequest,
    ReferralEventResponse,
    ResolveConversationRequest,
    ResolveConversationResponse,
    ResultListItem,
    ResultListResponse,
    TurnJobStartResponse,
    TurnJobStatusResponse,
    TurnListItem,
    TurnListResponse,
    TurnResponse,
    WhatsAppDeepLinkRequest,
    WhatsAppDeepLinkResponse,
    WhatsAppInboundRequest,
    WhatsAppInboundResponse,
    WhatsAppReminderRequest,
    WhatsAppReminderResponse,
)
from platform_core.config import load_config
from platform_core.fallback_messages import graceful_policy_message
from platform_core.repositories import ConversationRepository
from platform_core.image_moderation import ImageModerationService, image_block_message
from platform_core.restricted_categories import detect_restricted_category
from platform_core.supabase_rest import SupabaseError, SupabaseRestClient
from platform_core.ui import get_web_ui_html

from pydantic import BaseModel

from .orchestrator import AgenticOrchestrator
from .services.comfort_learning import ComfortLearningService
from .services.dependency_reporting import DependencyReportingService
from .services.onboarding_gateway import ApplicationUserGateway
from .services.tryon_quality_gate import TryonQualityGate
from .services.whatsapp_deep_links import build_whatsapp_deep_link
from .services.whatsapp_reengagement import build_whatsapp_reengagement_message
from .services.whatsapp_runtime import (
    WhatsAppCloudSender,
    evaluate_reengagement_trigger,
    normalize_whatsapp_webhook_payload,
    verify_whatsapp_webhook,
)
from .services.tryon_service import TryonService
from .services.whatsapp_formatter import format_turn_response_for_whatsapp


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_whatsapp_phone_number(raw_phone_number: str) -> str:
    cleaned = re.sub(r"[^\d+]", "", str(raw_phone_number or "").strip())
    if cleaned.startswith("++"):
        cleaned = "+" + cleaned.lstrip("+")
    if cleaned and not cleaned.startswith("+"):
        cleaned = f"+{cleaned}"
    digit_count = len(re.sub(r"\D", "", cleaned))
    if digit_count < 7:
        raise ValueError("WhatsApp phone number is invalid.")
    return cleaned


def _resolve_whatsapp_external_user_id(
    *,
    phone_number: str,
    user_id: str = "",
    onboarding_gateway: ApplicationUserGateway | None = None,
    repo: ConversationRepository | None = None,
) -> str:
    explicit_user = str(user_id or "").strip()
    if explicit_user:
        return explicit_user
    alias_external_user_id = f"whatsapp:{phone_number}"
    canonical_user_id = ""
    if onboarding_gateway is not None:
        canonical_user_id = str(onboarding_gateway.resolve_user_id_by_mobile(phone_number) or "").strip()
    if canonical_user_id:
        if repo is not None:
            repo.merge_external_user_identity(
                canonical_external_user_id=canonical_user_id,
                alias_external_user_id=alias_external_user_id,
            )
        return canonical_user_id
    return alias_external_user_id


def _build_whatsapp_runtime_message(payload: WhatsAppInboundRequest) -> tuple[str, Dict[str, Any]]:
    raw_message = str(payload.message or "").strip()
    image_url = str(payload.image_url or "").strip()
    link_url = str(payload.link_url or "").strip()
    media_type = str(payload.media_type or "").strip()

    prefix = ""
    if not raw_message:
        if media_type == "product":
            prefix = "Should I buy this?"
        elif media_type == "outfit_photo":
            prefix = "Outfit check this."
        elif media_type == "wardrobe_item":
            prefix = "Save this to my wardrobe."
        elif media_type == "garment_on_me":
            prefix = "How will this look on me?"
        elif link_url and image_url:
            prefix = "How will this look on me?"
        elif link_url:
            prefix = "Should I buy this?"
        elif image_url:
            prefix = "Outfit check this."

    parts: List[str] = []
    if prefix:
        parts.append(prefix)
    if raw_message:
        parts.append(raw_message)
    if link_url and link_url not in " ".join(parts):
        parts.append(link_url)
    if image_url and image_url not in " ".join(parts):
        parts.append(image_url)

    normalized = " ".join(part for part in parts if part).strip()
    if not normalized:
        raise ValueError("WhatsApp inbound message must include text, an image URL, or a link URL.")

    return normalized, {
        "raw_message": raw_message,
        "normalized_message": normalized,
        "image_url": image_url,
        "link_url": link_url,
        "media_type": media_type,
        "has_image": bool(image_url),
        "has_link": bool(link_url),
    }


def _base_app_url_from_rest_url(rest_url: str) -> str:
    value = str(rest_url or "").strip()
    if value.endswith("/rest/v1"):
        return value[: -len("/rest/v1")]
    return value.rstrip("/")


_TURN_JOB_LOCK = Lock()
_TURN_JOBS: Dict[str, Dict[str, Any]] = {}


def create_app() -> FastAPI:
    cfg = load_config()
    client = SupabaseRestClient(
        rest_url=cfg.supabase_rest_url,
        service_role_key=cfg.supabase_service_role_key,
        timeout_seconds=cfg.request_timeout_seconds,
    )
    repo = ConversationRepository(client)
    onboarding_gateway = ApplicationUserGateway(client)
    orchestrator = AgenticOrchestrator(repo=repo, onboarding_gateway=onboarding_gateway, config=cfg)
    image_moderation = ImageModerationService()
    dependency_reporting = DependencyReportingService(client)
    whatsapp_sender = WhatsAppCloudSender(
        access_token=getattr(cfg, "whatsapp_access_token", ""),
        phone_number_id=getattr(cfg, "whatsapp_phone_number_id", ""),
        api_version=getattr(cfg, "whatsapp_api_version", "v22.0"),
    )

    tryon_service = TryonService()
    tryon_quality_gate = TryonQualityGate()

    app = FastAPI(title="Sigma Aura Agentic Application", version="3.0.0")

    def log_policy_event(
        *,
        policy_event_type: str,
        input_class: str,
        reason_code: str,
        decision: str = "blocked",
        user_id: str = "",
        conversation_id: str = "",
        turn_id: str = "",
        source_channel: str = "web",
        metadata_json: Dict[str, Any] | None = None,
    ) -> None:
        try:
            repo.create_policy_event(
                policy_event_type=policy_event_type,
                input_class=input_class,
                reason_code=reason_code,
                decision=decision,
                rule_source="rule",
                user_id=user_id or None,
                conversation_id=conversation_id or None,
                turn_id=turn_id or None,
                source_channel=source_channel,
                metadata_json=metadata_json or {},
            )
        except Exception:
            pass

    def log_dependency_event(
        *,
        event_type: str,
        user_id: str,
        source_channel: str = "web",
        primary_intent: str = "",
        conversation_id: str = "",
        turn_id: str = "",
        metadata_json: Dict[str, Any] | None = None,
    ) -> None:
        try:
            if user_id:
                repo.get_or_create_user(user_id)
            repo.create_dependency_event(
                user_id=user_id,
                event_type=event_type,
                source_channel=source_channel,
                primary_intent=primary_intent,
                conversation_id=conversation_id or None,
                turn_id=turn_id or None,
                metadata_json=metadata_json or {},
            )
        except Exception:
            pass

    onboarding_gateway.set_policy_logger(log_policy_event)
    onboarding_gateway.set_dependency_logger(log_dependency_event)

    app.include_router(onboarding_gateway.create_router())
    app.include_router(create_catalog_admin_router())

    @app.get("/onboard", response_class=HTMLResponse, include_in_schema=False)
    def onboard(user: str = "", focus: str = "") -> HTMLResponse:
        return HTMLResponse(
            content=onboarding_gateway.render_onboarding_html(user_id=user, focus=focus),
            headers={
                "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
                "Pragma": "no-cache",
                "Expires": "0",
            },
        )

    @app.get("/onboard/processing", response_class=HTMLResponse, include_in_schema=False)
    def onboard_processing(user: str = "") -> HTMLResponse:
        return HTMLResponse(
            content=onboarding_gateway.render_processing_html(user_id=user),
            headers={
                "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
                "Pragma": "no-cache",
                "Expires": "0",
            },
        )

    @app.get("/admin/catalog", response_class=HTMLResponse, include_in_schema=False)
    def catalog_admin() -> HTMLResponse:
        return HTMLResponse(
            content=get_catalog_admin_html(),
            headers={
                "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
                "Pragma": "no-cache",
                "Expires": "0",
            },
        )

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    def home(user: str = "", focus: str = "", view: str = "", source: str = "", conversation_id: str = "") -> HTMLResponse:
        if str(focus or "").strip().lower() == "wardrobe":
            html = onboarding_gateway.render_wardrobe_manager_html(user_id=user)
            return HTMLResponse(
                content=html,
                headers={
                    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
                    "Pragma": "no-cache",
                    "Expires": "0",
                },
            )
        status = onboarding_gateway.get_onboarding_status(user) if user else {"onboarding_complete": False}
        analysis_status = onboarding_gateway.get_analysis_status(user) if user else {"status": "not_started"}
        if not status.get("onboarding_complete"):
            html = onboarding_gateway.render_onboarding_html(user_id=user, focus=focus)
        elif analysis_status.get("status") != "completed":
            html = onboarding_gateway.render_processing_html(user_id=user)
        else:
            resolved_view = str(view or "").strip().lower()
            if not resolved_view:
                focus_map = {
                    "chat": "chat",
                    "planner": "chat",
                    "tryon": "chat",
                    "profile": "profile",
                    "wardrobe": "wardrobe",
                    "results": "results",
                }
                resolved_view = focus_map.get(str(focus or "").strip().lower(), "chat")
            html = get_web_ui_html(
                user_id=user,
                active_view=resolved_view,
                source=source,
                focus=focus,
                conversation_id=conversation_id,
            )
        return HTMLResponse(
            content=html,
            headers={
                "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
                "Pragma": "no-cache",
                "Expires": "0",
            },
        )

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon() -> Response:
        return Response(status_code=204)

    @app.get("/healthz")
    def healthz() -> dict:
        return {"ok": True}

    @app.post("/v1/conversations", response_model=ConversationResponse)
    def create_conversation(payload: CreateConversationRequest) -> ConversationResponse:
        try:
            out = orchestrator.create_conversation(
                external_user_id=payload.user_id,
                initial_context=payload.initial_context.model_dump() if payload.initial_context else None,
                initial_profile=payload.initial_profile.model_dump(exclude_none=True) if payload.initial_profile else None,
            )
            return ConversationResponse(**out)
        except (ValueError, SupabaseError, RuntimeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/v1/conversations/resolve", response_model=ResolveConversationResponse)
    def resolve_conversation(payload: ResolveConversationRequest) -> ResolveConversationResponse:
        try:
            out = orchestrator.resolve_active_conversation(external_user_id=payload.user_id)
            return ResolveConversationResponse(**out)
        except (ValueError, SupabaseError, RuntimeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/v1/conversations/{conversation_id}", response_model=ConversationStateResponse)
    def get_conversation(conversation_id: str) -> ConversationStateResponse:
        try:
            out = orchestrator.get_conversation_state(conversation_id=conversation_id)
            return ConversationStateResponse(**out)
        except (ValueError, SupabaseError, RuntimeError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/v1/conversations/{conversation_id}/turns", response_model=TurnResponse)
    def create_turn(conversation_id: str, payload: CreateTurnRequest) -> TurnResponse:
        try:
            out = orchestrator.process_turn(
                conversation_id=conversation_id,
                external_user_id=payload.user_id,
                message=payload.message,
                channel=payload.channel,
                image_data=payload.image_data or "",
            )
            return TurnResponse(**out)
        except (ValueError, SupabaseError, RuntimeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/v1/channels/whatsapp/inbound", response_model=WhatsAppInboundResponse)
    def whatsapp_inbound(payload: WhatsAppInboundRequest) -> WhatsAppInboundResponse:
        try:
            normalized_phone = _normalize_whatsapp_phone_number(payload.phone_number)
            normalized_message, normalized_input = _build_whatsapp_runtime_message(payload)
            external_user_id = _resolve_whatsapp_external_user_id(
                phone_number=normalized_phone,
                user_id=payload.user_id,
                onboarding_gateway=onboarding_gateway,
                repo=repo,
            )
            conversation_created = False
            conversation_id = str(payload.conversation_id or "").strip()

            restricted_match = detect_restricted_category(
                normalized_message,
                str(normalized_input.get("image_url") or ""),
                str(normalized_input.get("link_url") or ""),
            )
            if restricted_match:
                log_policy_event(
                    policy_event_type="restricted_category_guardrail",
                    input_class="whatsapp_item_input",
                    reason_code="restricted_category_upload",
                    user_id=external_user_id,
                    conversation_id=conversation_id,
                    source_channel="whatsapp",
                    metadata_json={
                        "matched_term": restricted_match,
                        "message_id": str(payload.message_id or "").strip(),
                    },
                )
                raise ValueError(graceful_policy_message("restricted_category_upload"))
            if normalized_input.get("has_link") or normalized_input.get("media_type") in {"product", "wardrobe_item", "garment_on_me"}:
                log_policy_event(
                    policy_event_type="restricted_category_guardrail",
                    input_class="whatsapp_item_input",
                    reason_code="allowed_category",
                    decision="allowed",
                    user_id=external_user_id,
                    conversation_id=conversation_id,
                    source_channel="whatsapp",
                    metadata_json={
                        "message_id": str(payload.message_id or "").strip(),
                        "media_type": str(normalized_input.get("media_type") or ""),
                    },
                )

            if normalized_input.get("image_url"):
                moderation = image_moderation.moderate_url(
                    image_url=str(normalized_input.get("image_url") or ""),
                    purpose="whatsapp_image_input",
                )
                if not moderation.allowed:
                    log_policy_event(
                        policy_event_type="image_upload_guardrail",
                        input_class="whatsapp_image_input",
                        reason_code=str(moderation.reason_code or "explicit_nudity"),
                        user_id=external_user_id,
                        conversation_id=conversation_id,
                        source_channel="whatsapp",
                        metadata_json={
                            "message_id": str(payload.message_id or "").strip(),
                            "image_url": str(normalized_input.get("image_url") or ""),
                        },
                    )
                    raise ValueError(
                        graceful_policy_message(
                            str(moderation.reason_code or ""),
                            default=image_block_message(str(moderation.reason_code or "")),
                        )
                    )
                log_policy_event(
                    policy_event_type="image_upload_guardrail",
                    input_class="whatsapp_image_input",
                    reason_code=str(moderation.reason_code or "safe_image"),
                    decision="allowed",
                    user_id=external_user_id,
                    conversation_id=conversation_id,
                    source_channel="whatsapp",
                    metadata_json={
                        "message_id": str(payload.message_id or "").strip(),
                        "image_url": str(normalized_input.get("image_url") or ""),
                    },
                )

            if not conversation_id:
                user_row = repo.get_or_create_user(external_user_id)
                latest_conversation = repo.get_latest_conversation_for_user(str(user_row.get("id") or ""))
                if latest_conversation:
                    conversation_id = str(latest_conversation.get("id") or "")
                else:
                    created = orchestrator.create_conversation(
                        external_user_id=external_user_id,
                        initial_context={
                            "entry_channel": "whatsapp",
                            "whatsapp_phone_number": normalized_phone,
                            "whatsapp_profile_name": str(payload.profile_name or "").strip(),
                            "whatsapp_message_id": str(payload.message_id or "").strip(),
                            "whatsapp_input": normalized_input,
                        },
                    )
                    conversation_id = str(created["conversation_id"])
                    conversation_created = True

            out = orchestrator.process_turn(
                conversation_id=conversation_id,
                external_user_id=external_user_id,
                message=normalized_message,
                channel="whatsapp",
            )
            out = format_turn_response_for_whatsapp(out)
            out["metadata"] = {
                **dict(out.get("metadata") or {}),
                "whatsapp_input": normalized_input,
            }
            return WhatsAppInboundResponse(
                **out,
                user_id=external_user_id,
                channel="whatsapp",
                conversation_created=conversation_created,
                phone_number=normalized_phone,
                input_message_id=str(payload.message_id or "").strip(),
            )
        except (ValueError, SupabaseError, RuntimeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/v1/channels/whatsapp/webhook")
    def whatsapp_webhook_verify(
        hub_mode: str = Query(default="", alias="hub.mode"),
        hub_verify_token: str = Query(default="", alias="hub.verify_token"),
        hub_challenge: str = Query(default="", alias="hub.challenge"),
    ) -> Response:
        try:
            challenge = verify_whatsapp_webhook(
                mode=hub_mode,
                verify_token=hub_verify_token,
                challenge=hub_challenge,
                expected_verify_token=getattr(cfg, "whatsapp_webhook_verify_token", ""),
            )
            return Response(content=challenge, media_type="text/plain")
        except ValueError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc

    @app.post("/v1/channels/whatsapp/webhook")
    def whatsapp_webhook(payload: Dict[str, Any]) -> dict:
        try:
            events = normalize_whatsapp_webhook_payload(payload)
            processed: List[Dict[str, Any]] = []
            deliveries: List[Dict[str, Any]] = []
            for event in events:
                inbound = WhatsAppInboundRequest(
                    phone_number=str(event.get("phone_number") or ""),
                    message=str(event.get("message") or ""),
                    message_id=str(event.get("message_id") or ""),
                    profile_name=str(event.get("profile_name") or ""),
                    image_url=str(event.get("image_url") or ""),
                    link_url=str(event.get("link_url") or ""),
                    media_type=str(event.get("media_type") or ""),
                )
                response = whatsapp_inbound(inbound)
                delivery = whatsapp_sender.send_text_message(
                    phone_number=response.phone_number,
                    message=response.assistant_message,
                )
                processed.append(
                    {
                        "message_id": response.input_message_id,
                        "conversation_id": response.conversation_id,
                        "turn_id": response.turn_id,
                        "user_id": response.user_id,
                    }
                )
                deliveries.append(
                    {
                        "message_id": response.input_message_id,
                        "phone_number": response.phone_number,
                        **delivery.as_dict(),
                    }
                )
            return {
                "received_event_count": len(events),
                "processed_event_count": len(processed),
                "processed": processed,
                "deliveries": deliveries,
            }
        except (ValueError, SupabaseError, RuntimeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/v1/channels/whatsapp/reminders", response_model=WhatsAppReminderResponse)
    def whatsapp_reminder_preview(payload: WhatsAppReminderRequest) -> WhatsAppReminderResponse:
        try:
            normalized_phone = _normalize_whatsapp_phone_number(payload.phone_number) if str(payload.phone_number or "").strip() else ""
            external_user_id = _resolve_whatsapp_external_user_id(
                phone_number=normalized_phone,
                user_id=payload.user_id,
                onboarding_gateway=onboarding_gateway if normalized_phone else None,
                repo=repo if normalized_phone else None,
            ) if (normalized_phone or str(payload.user_id or "").strip()) else ""
            conversation_id = str(payload.conversation_id or "").strip()
            previous_context: Dict[str, Any] = {}
            conversation: Dict[str, Any] = {}
            latest_conversation: Dict[str, Any] = {}

            if conversation_id:
                conversation = repo.get_conversation(conversation_id)
                if not conversation:
                    raise ValueError("Conversation not found.")
                previous_context = dict(conversation.get("session_context_json") or {})
                if not external_user_id:
                    user_row = repo.get_user_by_id(str(conversation.get("user_id") or ""))
                    external_user_id = str((user_row or {}).get("external_user_id") or "").strip()
            elif external_user_id:
                user_row = repo.get_or_create_user(external_user_id)
                latest_conversation = repo.get_latest_conversation_for_user(str(user_row.get("id") or ""))
                if latest_conversation:
                    conversation_id = str(latest_conversation.get("id") or "")
                    previous_context = dict(latest_conversation.get("session_context_json") or {})
            trigger = evaluate_reengagement_trigger(
                previous_context=previous_context,
                conversation_updated_at=str((latest_conversation or conversation or {}).get("updated_at") or ""),
                reminder_type=payload.reminder_type,
            ) if (latest_conversation or conversation or previous_context) else {
                "eligible": True,
                "reason": "no_conversation_context",
                "cooldown_hours": 72,
            }

            reminder = build_whatsapp_reengagement_message(
                previous_context=previous_context,
                reminder_type=payload.reminder_type,
            )
            return WhatsAppReminderResponse(
                user_id=external_user_id,
                conversation_id=conversation_id,
                channel="whatsapp",
                reminder_type=str(reminder["reminder_type"]),
                assistant_message=str(reminder["assistant_message"]),
                follow_up_suggestions=list(reminder["follow_up_suggestions"]),
                metadata={
                    **dict(reminder.get("metadata") or {}),
                    "phone_number": normalized_phone,
                    "has_conversation_context": bool(previous_context),
                    "trigger": trigger,
                },
            )
        except (ValueError, SupabaseError, RuntimeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/v1/channels/whatsapp/deep-links", response_model=WhatsAppDeepLinkResponse)
    def whatsapp_deep_link(payload: WhatsAppDeepLinkRequest) -> WhatsAppDeepLinkResponse:
        try:
            normalized_phone = _normalize_whatsapp_phone_number(payload.phone_number) if str(payload.phone_number or "").strip() else ""
            external_user_id = _resolve_whatsapp_external_user_id(
                phone_number=normalized_phone,
                user_id=payload.user_id,
                onboarding_gateway=onboarding_gateway if normalized_phone else None,
                repo=repo if normalized_phone else None,
            ) if (normalized_phone or str(payload.user_id or "").strip()) else ""
            conversation_id = str(payload.conversation_id or "").strip()
            previous_context: Dict[str, Any] = {}

            if conversation_id:
                conversation = repo.get_conversation(conversation_id)
                if not conversation:
                    raise ValueError("Conversation not found.")
                previous_context = dict(conversation.get("session_context_json") or {})
                if not external_user_id:
                    user_row = repo.get_user_by_id(str(conversation.get("user_id") or ""))
                    external_user_id = str((user_row or {}).get("external_user_id") or "").strip()
            elif external_user_id:
                user_row = repo.get_or_create_user(external_user_id)
                latest_conversation = repo.get_latest_conversation_for_user(str(user_row.get("id") or ""))
                if latest_conversation:
                    conversation_id = str(latest_conversation.get("id") or "")
                    previous_context = dict(latest_conversation.get("session_context_json") or {})

            deep_link = build_whatsapp_deep_link(
                base_app_url=_base_app_url_from_rest_url(cfg.supabase_rest_url),
                user_id=external_user_id,
                conversation_id=conversation_id,
                task=payload.task,
                previous_context=previous_context,
            )
            return WhatsAppDeepLinkResponse(
                user_id=external_user_id,
                conversation_id=conversation_id,
                channel="whatsapp",
                task=str(deep_link["task"]),
                assistant_message=str(deep_link["assistant_message"]),
                deep_link_url=str(deep_link["deep_link_url"]),
                metadata={
                    **dict(deep_link.get("metadata") or {}),
                    "phone_number": normalized_phone,
                },
            )
        except (ValueError, SupabaseError, RuntimeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/v1/conversations/{conversation_id}/turns/start", response_model=TurnJobStartResponse)
    def start_turn_job(conversation_id: str, payload: CreateTurnRequest) -> TurnJobStartResponse:
        job_id = str(uuid4())
        with _TURN_JOB_LOCK:
            _TURN_JOBS[job_id] = {
                "conversation_id": conversation_id,
                "status": "running",
                "stages": [],
                "error": "",
                "result": None,
                "created_at": _now_iso(),
            }

        def append_stage(stage: str, detail: str = "", message: str = "") -> None:
            event = {"timestamp": _now_iso(), "stage": stage, "detail": detail, "message": message}
            with _TURN_JOB_LOCK:
                job = _TURN_JOBS.get(job_id)
                if job is None:
                    return
                stages: List[Dict[str, str]] = list(job.get("stages") or [])
                stages.append(event)
                job["stages"] = stages

        def run_job() -> None:
            append_stage("turn_execution", "started")
            try:
                out = orchestrator.process_turn(
                    conversation_id=conversation_id,
                    external_user_id=payload.user_id,
                    message=payload.message,
                    channel=payload.channel,
                    image_data=payload.image_data or "",
                    stage_callback=append_stage,
                )
                append_stage("turn_execution", "completed")
                with _TURN_JOB_LOCK:
                    job = _TURN_JOBS.get(job_id)
                    if job is None:
                        return
                    job["status"] = "completed"
                    job["result"] = out
            except Exception as exc:  # noqa: BLE001
                append_stage("turn_execution", "failed")
                with _TURN_JOB_LOCK:
                    job = _TURN_JOBS.get(job_id)
                    if job is None:
                        return
                    job["status"] = "failed"
                    job["error"] = str(exc)

        Thread(target=run_job, daemon=True).start()
        return TurnJobStartResponse(conversation_id=conversation_id, job_id=job_id, status="running")

    @app.get("/v1/conversations/{conversation_id}/turns/{job_id}/status", response_model=TurnJobStatusResponse)
    def get_turn_job_status(conversation_id: str, job_id: str) -> TurnJobStatusResponse:
        with _TURN_JOB_LOCK:
            job = dict(_TURN_JOBS.get(job_id) or {})
        if not job:
            raise HTTPException(status_code=404, detail="Turn job not found.")
        if job.get("conversation_id") != conversation_id:
            raise HTTPException(status_code=404, detail="Turn job not found for this conversation.")
        return TurnJobStatusResponse(
            conversation_id=conversation_id,
            job_id=job_id,
            status=str(job.get("status", "running")),
            stages=list(job.get("stages") or []),
            error=str(job.get("error") or ""),
            result=job.get("result"),
        )

    class TryonRequest(BaseModel):
        user_id: str
        product_image_url: str

    @app.post("/v1/tryon")
    def virtual_tryon(payload: TryonRequest) -> dict:
        reason_code = ""
        try:
            person_image_path = onboarding_gateway.get_person_image_path(payload.user_id)
            if not person_image_path:
                reason_code = "missing_person_image"
                raise ValueError(graceful_policy_message(reason_code))
            result = tryon_service.generate_tryon(
                person_image_path=person_image_path,
                product_image_url=payload.product_image_url,
            )
            if result.get("success"):
                quality = tryon_quality_gate.evaluate(
                    person_image_path=person_image_path,
                    tryon_result=result,
                )
                result["quality_gate"] = quality
                if not quality.get("passed"):
                    reason_code = str(quality.get("reason_code") or "quality_gate_failed")
                    raise ValueError(
                        graceful_policy_message(
                            reason_code,
                            default=str(quality.get("message") or "Generated try-on output failed quality checks."),
                        )
                    )
                log_policy_event(
                    policy_event_type="virtual_tryon_guardrail",
                    input_class="virtual_tryon_request",
                    reason_code="quality_gate_passed",
                    decision="allowed",
                    user_id=payload.user_id,
                    source_channel="web",
                    metadata_json={"quality_gate": quality},
                )
            return result
        except (ValueError, FileNotFoundError, RuntimeError) as exc:
            log_policy_event(
                policy_event_type="virtual_tryon_guardrail",
                input_class="virtual_tryon_request",
                reason_code=reason_code or (
                    "missing_person_image"
                    if "No full-body onboarding image found" in str(exc)
                    else "tryon_request_failed"
                ),
                user_id=payload.user_id,
                source_channel="web",
                metadata_json={"error": str(exc)},
            )
            raise HTTPException(
                status_code=400,
                detail=graceful_policy_message(reason_code or "tryon_request_failed", default=str(exc)),
            ) from exc

    @app.post("/v1/conversations/{conversation_id}/feedback")
    def submit_feedback(conversation_id: str, payload: FeedbackRequest) -> dict:
        try:
            conv = repo.get_conversation(conversation_id)
            if not conv:
                raise HTTPException(status_code=404, detail="Conversation not found.")
            user_id = conv["user_id"]
            external_uid = str((repo.get_user_by_id(str(user_id)) or {}).get("external_user_id") or "").strip()

            target_turn = None
            if payload.turn_id:
                target_turn = repo.get_turn(payload.turn_id)
                if not target_turn:
                    log_policy_event(
                        policy_event_type="feedback_guardrail",
                        input_class="feedback_submission",
                        reason_code="turn_not_found",
                        user_id=external_uid,
                        conversation_id=conversation_id,
                        turn_id=payload.turn_id,
                        metadata_json={"outfit_rank": payload.outfit_rank},
                    )
                    raise HTTPException(status_code=404, detail=graceful_policy_message("turn_not_found"))
                if str(target_turn.get("conversation_id") or "") != conversation_id:
                    log_policy_event(
                        policy_event_type="feedback_guardrail",
                        input_class="feedback_submission",
                        reason_code="turn_conversation_mismatch",
                        user_id=external_uid,
                        conversation_id=conversation_id,
                        turn_id=payload.turn_id,
                        metadata_json={"outfit_rank": payload.outfit_rank},
                    )
                    raise HTTPException(status_code=400, detail=graceful_policy_message("turn_conversation_mismatch"))
            else:
                target_turn = repo.get_latest_turn(conversation_id)
            turn_id = target_turn["id"] if target_turn else None

            # Resolve garment IDs from the outfit at the given rank on the selected turn.
            item_ids = list(payload.item_ids) if payload.item_ids else []
            recommended_item_ids: list[str] = []
            if target_turn:
                resolved = target_turn.get("resolved_context_json") or {}
                final_recs = resolved.get("final_recommendations") or resolved.get("recommendations") or []
                for rec in final_recs:
                    if rec.get("rank") == payload.outfit_rank:
                        recommended_item_ids = [str(pid) for pid in (rec.get("item_ids") or []) if str(pid).strip()]
                        break

            if item_ids and recommended_item_ids:
                invalid_item_ids = [gid for gid in item_ids if gid not in recommended_item_ids]
                if invalid_item_ids:
                    log_policy_event(
                        policy_event_type="feedback_guardrail",
                        input_class="feedback_submission",
                        reason_code="item_outside_selected_outfit",
                        user_id=external_uid,
                        conversation_id=conversation_id,
                        turn_id=turn_id or payload.turn_id,
                        metadata_json={
                            "outfit_rank": payload.outfit_rank,
                            "invalid_item_ids": invalid_item_ids,
                        },
                    )
                    raise HTTPException(status_code=400, detail=graceful_policy_message("item_outside_selected_outfit"))

            if not item_ids:
                item_ids = list(recommended_item_ids)

            if not item_ids:
                log_policy_event(
                    policy_event_type="feedback_guardrail",
                    input_class="feedback_submission",
                    reason_code="unresolved_feedback_items",
                    user_id=external_uid,
                    conversation_id=conversation_id,
                    turn_id=turn_id or payload.turn_id,
                    metadata_json={"outfit_rank": payload.outfit_rank},
                )
                raise HTTPException(status_code=400, detail=graceful_policy_message("unresolved_feedback_items"))

            reward = 1 if payload.event_type == "like" else -1
            count = 0
            for gid in item_ids:
                repo.create_feedback_event(
                    user_id=user_id,
                    conversation_id=conversation_id,
                    turn_id=turn_id,
                    outfit_rank=payload.outfit_rank,
                    garment_id=gid,
                    event_type=payload.event_type,
                    reward_value=reward,
                    notes=payload.notes,
                )
                if external_uid:
                    repo.create_catalog_interaction(
                        user_id=external_uid,
                        conversation_id=conversation_id,
                        turn_id=turn_id,
                        product_id=gid,
                        interaction_type="save" if payload.event_type == "like" else "dismiss",
                        source_channel="web",
                        source_surface="outfit_feedback",
                        metadata_json={
                            "outfit_rank": payload.outfit_rank,
                            "feedback_event_type": payload.event_type,
                        },
                    )
                count += 1

            conversation = repo.get_conversation(conversation_id) or {}
            previous_context = dict(conversation.get("session_context_json") or {})
            repo.update_conversation_context(
                conversation_id=conversation_id,
                session_context={
                    **previous_context,
                    "last_feedback_summary": {
                        "event_type": payload.event_type,
                        "item_ids": list(item_ids),
                        "item_count": len(item_ids),
                        "outfit_rank": payload.outfit_rank,
                        "target_turn_id": str(turn_id or ""),
                    },
                },
            )

            # Comfort learning: detect high-intent signals from likes
            if payload.event_type == "like":
                if external_uid:
                    comfort = ComfortLearningService(client)
                    for gid in item_ids:
                        if gid and gid != "unknown":
                            comfort.detect_high_intent_signal(
                                user_id=external_uid,
                                garment_id=gid,
                                conversation_id=conversation_id,
                                turn_id=turn_id,
                            )

            return {"ok": True, "count": count, "turn_id": turn_id or ""}
        except HTTPException:
            raise
        except (ValueError, SupabaseError, RuntimeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    # -- UI listing endpoints --------------------------------------------------

    @app.get("/v1/users/{user_id}/conversations", response_model=ConversationListResponse)
    def list_user_conversations(user_id: str) -> ConversationListResponse:
        try:
            user = repo.get_or_create_user(user_id)
            internal_uid = str(user["id"])
            rows = repo.list_conversations_for_user(internal_uid)
            items: list[ConversationListItem] = []
            for row in rows:
                conv_id = str(row.get("id") or "")
                first_turn = repo.get_latest_turn(conv_id)
                ctx = dict(row.get("session_context_json") or {})
                preview = ""
                if first_turn:
                    preview = str(first_turn.get("user_message") or "")[:80]
                items.append(
                    ConversationListItem(
                        conversation_id=conv_id,
                        status=str(row.get("status") or ""),
                        preview=preview,
                        occasion=str(ctx.get("occasion") or ""),
                        created_at=str(row.get("created_at") or ""),
                        updated_at=str(row.get("updated_at") or ""),
                    )
                )
            return ConversationListResponse(user_id=user_id, conversations=items)
        except (ValueError, SupabaseError, RuntimeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/v1/conversations/{conversation_id}/turns", response_model=TurnListResponse)
    def list_conversation_turns(conversation_id: str) -> TurnListResponse:
        try:
            rows = repo.list_turns_for_conversation(conversation_id)
            items: list[TurnListItem] = []
            for row in rows:
                items.append(
                    TurnListItem(
                        turn_id=str(row.get("id") or ""),
                        user_message=str(row.get("user_message") or ""),
                        assistant_message=str(row.get("assistant_message") or ""),
                        resolved_context=row.get("resolved_context_json"),
                        created_at=str(row.get("created_at") or ""),
                    )
                )
            return TurnListResponse(conversation_id=conversation_id, turns=items)
        except (ValueError, SupabaseError, RuntimeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/v1/users/{user_id}/results", response_model=ResultListResponse)
    def list_user_results(user_id: str) -> ResultListResponse:
        try:
            user = repo.get_or_create_user(user_id)
            internal_uid = str(user["id"])
            rows = repo.list_recent_results_for_user(internal_uid)
            items: list[ResultListItem] = []
            for row in rows:
                ctx = dict(row.get("resolved_context_json") or {})
                recs = ctx.get("final_recommendations") or ctx.get("recommendations") or []
                first_img = ""
                for rec in recs:
                    for item in (rec.get("items") or []):
                        if item.get("image_url"):
                            first_img = str(item["image_url"])
                            break
                    if first_img:
                        break
                items.append(
                    ResultListItem(
                        turn_id=str(row.get("id") or ""),
                        conversation_id=str(row.get("conversation_id") or ""),
                        user_message=str(row.get("user_message") or ""),
                        assistant_message=str(row.get("assistant_message") or "")[:200],
                        occasion=str(ctx.get("occasion") or ""),
                        intent=str(ctx.get("intent") or ctx.get("response_type") or ""),
                        source=str(ctx.get("source_preference") or ""),
                        outfit_count=len(recs),
                        first_outfit_image=first_img,
                        created_at=str(row.get("created_at") or ""),
                    )
                )
            return ResultListResponse(user_id=user_id, results=items)
        except (ValueError, SupabaseError, RuntimeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/v1/analytics/referrals", response_model=ReferralEventResponse)
    def create_referral_event(payload: ReferralEventRequest) -> ReferralEventResponse:
        try:
            repo.get_or_create_user(payload.user_id)
            row = repo.create_dependency_event(
                user_id=payload.user_id,
                event_type="referral",
                source_channel=payload.channel,
                primary_intent="referral",
                metadata_json={
                    "referral_type": payload.referral_type,
                    "target": payload.target,
                    **dict(payload.metadata or {}),
                },
            )
            return ReferralEventResponse(
                success=True,
                event_id=str(row.get("id") or ""),
                user_id=payload.user_id,
                referral_type=payload.referral_type,
            )
        except (ValueError, SupabaseError, RuntimeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/v1/analytics/dependency-report", response_model=DependencyReportResponse)
    def dependency_report() -> DependencyReportResponse:
        try:
            return DependencyReportResponse(report=dependency_reporting.build_report())
        except (ValueError, SupabaseError, RuntimeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return app
