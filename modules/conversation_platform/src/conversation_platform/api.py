from datetime import datetime, timezone
from threading import Lock, Thread
from typing import Any, Dict, List
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, Response

from .config import load_config
from .orchestrator import ConversationOrchestrator
from .repositories import ConversationRepository
from .schemas import (
    ConversationResponse,
    ConversationStateResponse,
    CreateConversationRequest,
    CreateTurnRequest,
    FeedbackRequest,
    FeedbackResponse,
    RecommendationRunResponse,
    TurnJobStartResponse,
    TurnJobStatusResponse,
    TurnResponse,
)
from .supabase_rest import SupabaseError, SupabaseRestClient
from .ui import get_web_ui_html


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _map_supabase_error(exc: Exception) -> str:
    msg = str(exc)
    if (
        "feedback_events_event_type_check" in msg
        and "feedback_events" in msg
        and "violates check constraint" in msg
    ):
        return (
            "Feedback event type is not supported by current DB schema. "
            "Apply latest Supabase migrations and retry."
        )
    return msg


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
    orchestrator = ConversationOrchestrator(repo=repo, catalog_csv_path=cfg.catalog_csv_path)

    app = FastAPI(title="Sigma Aura Conversation Platform", version="1.0.0")

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    def home() -> HTMLResponse:
        html = get_web_ui_html()
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
                image_refs=payload.image_refs,
                strictness=payload.strictness,
                hard_filter_profile=payload.hard_filter_profile,
                max_results=payload.max_results,
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
                    image_refs=payload.image_refs,
                    strictness=payload.strictness,
                    hard_filter_profile=payload.hard_filter_profile,
                    max_results=payload.max_results,
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
        return TurnJobStartResponse(
            conversation_id=conversation_id,
            job_id=job_id,
            status="running",
        )

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

    @app.get("/v1/recommendations/{run_id}", response_model=RecommendationRunResponse)
    def get_recommendation_run(run_id: str) -> RecommendationRunResponse:
        try:
            out = orchestrator.get_recommendation_run(run_id=run_id)
            return RecommendationRunResponse(**out)
        except (ValueError, SupabaseError, RuntimeError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/v1/feedback", response_model=FeedbackResponse)
    def create_feedback(payload: FeedbackRequest) -> FeedbackResponse:
        try:
            out = orchestrator.record_feedback(
                external_user_id=payload.user_id,
                conversation_id=payload.conversation_id,
                recommendation_run_id=payload.recommendation_run_id,
                garment_id=payload.garment_id,
                event_type=payload.event_type,
                notes=payload.notes,
            )
            return FeedbackResponse(**out)
        except (ValueError, SupabaseError, RuntimeError) as exc:
            raise HTTPException(status_code=400, detail=_map_supabase_error(exc)) from exc

    return app
