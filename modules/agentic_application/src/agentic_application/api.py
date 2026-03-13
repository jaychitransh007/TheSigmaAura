from datetime import datetime, timezone
from threading import Lock, Thread
from typing import Any, Dict, List
from uuid import uuid4

from catalog.admin_api import create_catalog_admin_router
from catalog.ui import get_catalog_admin_html
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, Response

from platform_core.api_schemas import (
    ConversationResponse,
    ConversationStateResponse,
    CreateConversationRequest,
    CreateTurnRequest,
    TurnJobStartResponse,
    TurnJobStatusResponse,
    TurnResponse,
)
from platform_core.config import load_config
from platform_core.repositories import ConversationRepository
from platform_core.supabase_rest import SupabaseError, SupabaseRestClient
from platform_core.ui import get_web_ui_html

from pydantic import BaseModel

from .orchestrator import AgenticOrchestrator
from .services.onboarding_gateway import ApplicationOnboardingGateway
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
    onboarding_gateway = ApplicationOnboardingGateway(client)
    orchestrator = AgenticOrchestrator(repo=repo, onboarding_gateway=onboarding_gateway, config=cfg)

    tryon_service = TryonService()

    app = FastAPI(title="Sigma Aura Agentic Application", version="3.0.0")

    app.include_router(onboarding_gateway.create_router())
    app.include_router(create_catalog_admin_router())

    @app.get("/onboard", response_class=HTMLResponse, include_in_schema=False)
    def onboard() -> HTMLResponse:
        return HTMLResponse(
            content=onboarding_gateway.render_onboarding_html(),
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
    def home(user: str = "") -> HTMLResponse:
        status = onboarding_gateway.get_onboarding_status(user) if user else {"onboarding_complete": False}
        analysis_status = onboarding_gateway.get_analysis_status(user) if user else {"status": "not_started"}
        if not status.get("onboarding_complete"):
            html = onboarding_gateway.render_onboarding_html()
        elif analysis_status.get("status") != "completed":
            html = onboarding_gateway.render_processing_html(user_id=user)
        else:
            html = get_web_ui_html(user_id=user)
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

        def append_stage(stage: str, detail: str = "") -> None:
            event = {"timestamp": _now_iso(), "stage": stage, "detail": detail}
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
        try:
            person_image_path = onboarding_gateway.get_person_image_path(payload.user_id)
            if not person_image_path:
                raise ValueError("No full-body onboarding image found for this user.")
            result = tryon_service.generate_tryon(
                person_image_path=person_image_path,
                product_image_url=payload.product_image_url,
            )
            return result
        except (ValueError, FileNotFoundError, RuntimeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return app
