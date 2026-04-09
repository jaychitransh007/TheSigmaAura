from datetime import datetime, timezone
import re
from threading import Lock, Thread
from typing import Any, Dict, List
from uuid import uuid4

from catalog.admin_api import create_catalog_admin_router
from catalog.ui import get_catalog_admin_html
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from platform_core.api_schemas import (
    ConversationListItem,
    ConversationListResponse,
    ConversationResponse,
    ConversationStateResponse,
    CreateConversationRequest,
    CreateTurnRequest,
    DependencyReportResponse,
    FeedbackRequest,
    RenameConversationRequest,
    ResolveConversationRequest,
    ResolveConversationResponse,
    ResultListItem,
    ResultListResponse,
    TurnJobStartResponse,
    TurnJobStatusResponse,
    TurnListItem,
    TurnListResponse,
    TurnResponse,
)
from platform_core.config import load_config
from platform_core.fallback_messages import graceful_policy_message
from platform_core.repositories import ConversationRepository
from platform_core.image_moderation import ImageModerationService, image_block_message
from platform_core.restricted_categories import detect_restricted_category
from platform_core.supabase_rest import SupabaseError, SupabaseRestClient
from platform_core.ui import get_web_ui_html

from pydantic import BaseModel

from .intent_registry import Intent
from .orchestrator import AgenticOrchestrator
from .services.comfort_learning import ComfortLearningService
from .services.dependency_reporting import DependencyReportingService
from .services.onboarding_gateway import ApplicationUserGateway
from .services.tryon_quality_gate import TryonQualityGate
from .services.tryon_service import TryonService


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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

    @app.get("/onboard/processing", response_class=RedirectResponse, include_in_schema=False)
    def onboard_processing(user: str = "") -> RedirectResponse:
        return RedirectResponse(url=f"/?user={user}&view=profile")

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
            resolved_view = "profile"
            html = get_web_ui_html(
                user_id=user,
                active_view=resolved_view,
                source=str(source or "").strip().lower(),
                focus=str(focus or "").strip().lower(),
                conversation_id=str(conversation_id or "").strip(),
            )
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

    @app.post("/v1/images/convert")
    def convert_image(payload: dict) -> dict:
        """Convert HEIC/HEIF/AVIF image data URL to JPEG.

        OpenAI's vision API only accepts JPEG/PNG/GIF/WebP. iPhones
        default to HEIC and modern web tooling defaults to AVIF —
        both fail wardrobe enrichment with `400 - The image data you
        provided does not represent a valid image`. The frontend can
        call this route before posting an upload turn to convert
        unsupported formats up front. The wardrobe save path also
        runs the same conversion as a defense-in-depth fallback.
        """
        from user.service import _convert_to_jpeg_if_needed
        import base64 as b64
        raw = str(payload.get("image_data") or "").strip()
        if not raw.startswith("data:") or ";base64," not in raw:
            raise HTTPException(status_code=400, detail="Invalid image data URL")
        header, encoded = raw.split(",", 1)
        mime = header.split(";")[0].split(":", 1)[1] if ":" in header else ""
        # Allowlist of formats we know how to convert to JPEG. Anything
        # outside this set is passed through unchanged so the frontend
        # doesn't accidentally re-encode JPEGs that are already valid.
        if mime not in ("image/heic", "image/heif", "image/avif", ""):
            return {"image_data": raw, "converted": False}
        try:
            file_bytes = b64.b64decode(encoded)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid base64 data")
        # Pick a filename extension matching the mime so the converter's
        # extension-based dispatch fires correctly.
        if mime == "image/avif":
            filename = "upload.avif"
        elif mime == "image/heif":
            filename = "upload.heif"
        else:
            filename = "upload.heic"
        converted, new_ct, _ = _convert_to_jpeg_if_needed(file_bytes, filename)
        if new_ct:
            jpeg_b64 = b64.b64encode(converted).decode("ascii")
            return {"image_data": f"data:image/jpeg;base64,{jpeg_b64}", "converted": True}
        return {"image_data": raw, "converted": False}

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

    @app.patch("/v1/conversations/{conversation_id}")
    def rename_conversation(conversation_id: str, payload: RenameConversationRequest):
        try:
            row = repo.rename_conversation(conversation_id, payload.title)
            if not row:
                raise HTTPException(status_code=404, detail="Conversation not found")
            return {"ok": True, "conversation_id": conversation_id, "title": payload.title}
        except HTTPException:
            raise
        except (ValueError, SupabaseError, RuntimeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.delete("/v1/conversations/{conversation_id}")
    def delete_conversation(conversation_id: str):
        try:
            row = repo.archive_conversation(conversation_id)
            if not row:
                raise HTTPException(status_code=404, detail="Conversation not found")
            return {"ok": True, "conversation_id": conversation_id}
        except HTTPException:
            raise
        except (ValueError, SupabaseError, RuntimeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

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
                    input_class=Intent.GARMENT_EVALUATION,
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
                input_class=Intent.GARMENT_EVALUATION,
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
                        input_class=Intent.FEEDBACK_SUBMISSION,
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
                        input_class=Intent.FEEDBACK_SUBMISSION,
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
                        input_class=Intent.FEEDBACK_SUBMISSION,
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
                    input_class=Intent.FEEDBACK_SUBMISSION,
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

            # Update the turn trace with the user's feedback signal so
            # we can correlate pipeline shape with user satisfaction in
            # a single-table query on turn_traces.
            if turn_id:
                try:
                    repo.update_turn_trace_user_response(
                        turn_id=str(turn_id),
                        user_response={
                            "feedback_type": payload.event_type,
                            "feedback_notes": payload.notes[:200] if payload.notes else "",
                            "feedback_item_ids": list(item_ids),
                            "feedback_outfit_rank": payload.outfit_rank,
                        },
                    )
                except Exception:
                    pass  # best-effort; never break the feedback flow

            return {"ok": True, "count": count, "turn_id": turn_id or ""}
        except HTTPException:
            raise
        except (ValueError, SupabaseError, RuntimeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/v1/products/{product_id}/wishlist")
    def wishlist_product(product_id: str, user_id: str = "", conversation_id: str = ""):
        try:
            if not user_id:
                raise HTTPException(status_code=400, detail="user_id is required")
            repo.create_catalog_interaction(
                user_id=user_id,
                product_id=product_id,
                interaction_type="save",
                conversation_id=conversation_id or None,
                source_channel="web",
                source_surface="product_wishlist",
            )
            return {"ok": True, "product_id": product_id}
        except HTTPException:
            raise
        except (ValueError, SupabaseError, RuntimeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    # -- Saved looks (server-side persistence) ---------------------------------

    class SavedLookCreateRequest(BaseModel):
        user_id: str
        conversation_id: str = ""
        turn_id: str = ""
        outfit_rank: int = 1
        title: str = ""
        item_ids: List[str] = []
        snapshot_json: Dict[str, Any] = {}
        notes: str = ""

    @app.post("/v1/users/{user_id}/saved-looks")
    def create_saved_look(user_id: str, payload: SavedLookCreateRequest):
        try:
            user = repo.get_or_create_user(user_id)
            internal_uid = str(user["id"])
            row = repo.create_saved_look(
                user_id=internal_uid,
                conversation_id=payload.conversation_id or None,
                turn_id=payload.turn_id or None,
                outfit_rank=payload.outfit_rank,
                title=payload.title,
                item_ids=payload.item_ids,
                snapshot_json=payload.snapshot_json,
                notes=payload.notes,
            )
            return {"ok": True, "saved_look": row}
        except (ValueError, SupabaseError, RuntimeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/v1/users/{user_id}/saved-looks")
    def list_saved_looks(user_id: str, limit: int = 50):
        try:
            user = repo.get_or_create_user(user_id)
            internal_uid = str(user["id"])
            rows = repo.list_saved_looks_for_user(internal_uid, limit=limit)
            return {"user_id": user_id, "saved_looks": rows or []}
        except (ValueError, SupabaseError, RuntimeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.delete("/v1/users/{user_id}/saved-looks/{saved_look_id}")
    def delete_saved_look(user_id: str, saved_look_id: str):
        try:
            row = repo.archive_saved_look(saved_look_id)
            if not row:
                raise HTTPException(status_code=404, detail="saved look not found")
            return {"ok": True}
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
            rows = repo.list_conversations_for_user(internal_uid, status="active")
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
                        title=str(row.get("title") or ""),
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
                outfits = ctx.get("outfits") or []
                first_img = ""
                # Prefer tryon_image for preview
                for outfit in outfits:
                    tryon = str(outfit.get("tryon_image") or "").strip()
                    if tryon:
                        first_img = tryon
                        break
                # Fallback: first garment image
                if not first_img:
                    for outfit in outfits:
                        for item in (outfit.get("items") or []):
                            img = str(item.get("image_url") or "").strip()
                            if img:
                                first_img = img
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
                        outfit_count=len(outfits),
                        first_outfit_image=first_img,
                        created_at=str(row.get("created_at") or ""),
                    )
                )
            return ResultListResponse(user_id=user_id, results=items)
        except (ValueError, SupabaseError, RuntimeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/v1/analytics/dependency-report", response_model=DependencyReportResponse)
    def dependency_report() -> DependencyReportResponse:
        try:
            return DependencyReportResponse(report=dependency_reporting.build_report())
        except (ValueError, SupabaseError, RuntimeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return app
