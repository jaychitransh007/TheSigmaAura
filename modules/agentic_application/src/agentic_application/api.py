from datetime import datetime, timezone
import logging
import re
from threading import Lock, Thread
from typing import Any, Dict, List, Optional
from uuid import uuid4

_log = logging.getLogger(__name__)

from catalog.admin_api import create_catalog_admin_router
from catalog.ui import get_catalog_admin_html
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from platform_core.request_context import (
    set_request_id,
    reset_request_id,
)

from platform_core.api_schemas import (
    ConversationListItem,
    ConversationListResponse,
    ConversationResponse,
    ConversationStateResponse,
    CreateConversationRequest,
    BootstrapBatchRequest,
    BootstrapBatchResponse,
    BootstrapCompleteRequest,
    CreateTurnRequest,
    EnrichmentBatchPollItem,
    EnrichmentPollResponse,
    EnrichmentSubmitResponse,
    LookupOrCreateTenantRequest,
    ProductWebhookCreateOrUpdateRequest,
    ProductWebhookDeleteResult,
    ProductWebhookResult,
    TenantListResponse,
    TenantStatusResponse,
    UpdateThemeOverridesRequest,
    DependencyReportResponse,
    FeedbackRequest,
    IntentHistoryGroup,
    IntentHistoryResponse,
    IntentHistoryThemeBlock,
    IntentHistoryTurn,
    MergeUsersRequest,
    MergeUsersResponse,
    RecentSignal,
    RecentSignalsResponse,
    RenameConversationRequest,
    ResolveConversationRequest,
    ResolveConversationResponse,
    ResultListItem,
    ResultListResponse,
    TryonGalleryItem,
    TryonGalleryResponse,
    TurnJobStartResponse,
    TurnJobStatusResponse,
    TurnListItem,
    TurnListResponse,
    TurnResponse,
    WishlistItem,
    WishlistResponse,
)
from platform_core.config import load_config
from platform_core.fallback_messages import graceful_policy_message
from platform_core.repositories import ConversationRepository
from platform_core.tenants import TenantRepository, resolve_tenant_id_or_default

from .services.catalog_bootstrap_service import CatalogBootstrapService
from .services.catalog_product_sync_service import CatalogProductSyncService
from .services.catalog_vision_enrichment_service import (
    CatalogVisionEnrichmentService,
)
from platform_core.image_moderation import ImageModerationService, image_block_message
from platform_core.restricted_categories import detect_restricted_category
from platform_core.supabase_rest import SupabaseError, SupabaseRestClient
from platform_core.ui import get_web_ui_html

from pydantic import BaseModel

from .intent_registry import Intent
from .orchestrator import AgenticOrchestrator, _build_candidate_item
from .schemas import RetrievedProduct
from .services.comfort_learning import ComfortLearningService
from .services.dependency_reporting import DependencyReportingService
from .services.onboarding_gateway import ApplicationUserGateway
from .services.tryon_quality_gate import TryonQualityGate
from .services.tryon_service import TryonService


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


_TURN_JOB_LOCK = Lock()
_TURN_JOBS: Dict[str, Dict[str, Any]] = {}


# ---------------------------------------------------------------------------
# Historical outfit-card hydration
# ---------------------------------------------------------------------------
#
# Four recommendation handlers persisted turns without writing the rendered
# OutfitCard(s) into resolved_context_json. The card objects were only
# returned in the live HTTP response, so when a user later opens that
# conversation in the chat history sidebar, loadConversation → renderOutfits
# reads resolved_context.outfits → empty → no cards.
#
# The Phase 14 backend patches (_build_wardrobe_first_occasion_response,
# _build_wardrobe_first_pairing_response, _build_catalog_anchor_pairing_response)
# fixed the forward path so new turns persist outfits correctly. This
# helper covers the historical gap: for any turn that reaches /turns
# missing an `outfits` array, it reconstructs a synthetic OutfitCard on
# the fly from the signals that ARE persisted (recommendations[].item_ids +
# handler_payload) and splices it into the response.
#
# Reconstructed cards carry the title, reasoning, items, source labels,
# and (if available) the virtual try-on image. The polar chart metrics
# (body_harmony_pct, archetype percentages, etc.) were never persisted,
# so the chart renders empty for historical cards — still better than
# zero cards. The helper is best-effort: if no item IDs are findable
# for a turn, it leaves that turn untouched (non-recommendation paths
# like onboarding gates and clarifications).


def _wardrobe_row_to_item_dict(row: Dict[str, Any]) -> Dict[str, Any]:
    """Convert a user_wardrobe_items row into the item-dict shape the
    frontend buildOutfitCard expects. Mirrors
    AgenticOrchestrator._wardrobe_item_to_outfit_item."""
    return {
        "product_id": str(row.get("id") or ""),
        "title": str(row.get("title") or ""),
        "image_url": str(row.get("image_url") or row.get("image_path") or ""),
        "price": "",
        "product_url": "",
        "garment_category": str(row.get("garment_category") or ""),
        "garment_subtype": str(row.get("garment_subtype") or ""),
        "primary_color": str(row.get("primary_color") or ""),
        "formality_level": str(row.get("formality_level") or ""),
        "occasion_fit": str(row.get("occasion_fit") or ""),
        "pattern_type": str(row.get("pattern_type") or ""),
        "source": "wardrobe",
    }


def _catalog_row_to_item_dict(row: Dict[str, Any]) -> Dict[str, Any]:
    """Convert a catalog_enriched row into the item-dict shape the
    frontend buildOutfitCard expects. Mirrors the catalog side of
    orchestrator._build_candidate_item."""
    image_url = str(
        row.get("images__0__src")
        or row.get("images_0_src")
        or row.get("primary_image_url")
        or row.get("image_url")
        or ""
    )
    return {
        "product_id": str(row.get("product_id") or ""),
        "title": str(row.get("title") or ""),
        "image_url": image_url,
        "price": str(row.get("price") or ""),
        "product_url": str(row.get("url") or row.get("product_url") or ""),
        "garment_category": str(row.get("garment_category") or ""),
        "garment_subtype": str(row.get("garment_subtype") or ""),
        "primary_color": str(row.get("primary_color") or ""),
        "formality_level": str(row.get("formality_level") or ""),
        "occasion_fit": str(row.get("occasion_fit") or ""),
        "pattern_type": str(row.get("pattern_type") or ""),
        "source": "catalog",
    }


def _empty_outfit_skeleton() -> Dict[str, Any]:
    """Zero-valued OutfitCard fields for metrics that were never persisted.
    The frontend radar gracefully drops null/zero values, so an empty
    skeleton renders an empty chart rather than crashing.

    R7 (May 5 2026): six dims now (added formality + statement; renamed
    inter_item_coherence_pct → pairing_pct).
    """
    return {
        "body_harmony_pct": 0,
        "color_suitability_pct": 0,
        "occasion_pct": None,
        "pairing_pct": None,
        "formality_pct": 0,
        "statement_pct": 0,
        "fashion_score_pct": 0,
    }


def _hydrate_missing_outfits(
    *,
    client: SupabaseRestClient,
    repo: ConversationRepository,
    user_id: str,
    turns: List[Dict[str, Any]],
) -> None:
    """For every turn whose resolved_context_json is missing an `outfits`
    array, reconstruct synthetic outfit cards from persisted signals and
    mutate the turn in place.

    Best-effort — turns without recoverable item IDs (clarifications,
    onboarding gates, errors) are left untouched.
    """
    # Collect the set of turns that need hydration and the union of item
    # IDs they reference, so wardrobe + catalog lookups can be batched.
    all_ids: set = set()
    pending: List[tuple] = []  # (turn_row, recommendations_list, per_rec_ids)
    for turn in turns:
        rc = turn.get("resolved_context_json") or {}
        if rc.get("outfits"):
            continue
        recs = rc.get("recommendations") or []
        if not recs:
            continue
        per_rec_ids: List[List[str]] = []
        for rec in recs:
            ids = [str(x).strip() for x in (rec.get("item_ids") or []) if str(x).strip()]
            per_rec_ids.append(ids)
            all_ids.update(ids)
        if not any(per_rec_ids):
            continue
        pending.append((turn, recs, per_rec_ids))

    if not pending or not all_ids:
        return

    # Batch-fetch this user's wardrobe (already scoped by user_id, cheap)
    try:
        wardrobe_rows = client.select_many(
            "user_wardrobe_items",
            filters={"user_id": f"eq.{user_id}"},
        ) or []
    except Exception:
        wardrobe_rows = []
    wardrobe_by_id = {str(r.get("id") or ""): r for r in wardrobe_rows}

    # Any ID not matched against the wardrobe is assumed to be a catalog
    # product_id. Batch-fetch those from catalog_enriched.
    catalog_ids_to_fetch = [i for i in all_ids if i and i not in wardrobe_by_id]
    catalog_by_id: Dict[str, Dict[str, Any]] = {}
    if catalog_ids_to_fetch:
        try:
            ids_csv = ",".join(catalog_ids_to_fetch)
            catalog_rows = client.select_many(
                "catalog_enriched",
                filters={"product_id": f"in.({ids_csv})"},
            ) or []
            catalog_by_id = {str(r.get("product_id") or ""): r for r in catalog_rows}
        except Exception:
            catalog_by_id = {}

    from urllib.parse import quote

    # Reconstruct one outfit per persisted recommendation.
    for turn, recs, per_rec_ids in pending:
        outfits: List[Dict[str, Any]] = []
        for rec, ids in zip(recs, per_rec_ids):
            items: List[Dict[str, Any]] = []
            for item_id in ids:
                if item_id in wardrobe_by_id:
                    items.append(_wardrobe_row_to_item_dict(wardrobe_by_id[item_id]))
                elif item_id in catalog_by_id:
                    items.append(_catalog_row_to_item_dict(catalog_by_id[item_id]))
            if not items:
                continue

            # Try-on image: look up by the same sorted garment-ID set the
            # live renderer used. If found, rewrite the stored file_path
            # to the local-images serving route so the browser can load it.
            tryon_image_url = ""
            try:
                tryon_row = repo.find_tryon_image_by_garments(user_id, ids)
                if tryon_row:
                    fp = str(tryon_row.get("file_path") or "").strip()
                    if fp and not fp.startswith(("http://", "https://", "/v1/")):
                        tryon_image_url = "/v1/onboarding/images/local?path=" + quote(fp, safe="/._-")
                    else:
                        tryon_image_url = fp
            except Exception:
                tryon_image_url = ""

            outfit_dict: Dict[str, Any] = {
                "rank": int(rec.get("rank") or (len(outfits) + 1)),
                "title": str(rec.get("title") or "Styled Look"),
                "reasoning": str(rec.get("reasoning") or ""),
                "items": items,
                "tryon_image": tryon_image_url,
                "_reconstructed": True,
            }
            outfit_dict.update(_empty_outfit_skeleton())
            outfits.append(outfit_dict)

        if not outfits:
            continue

        # Mutate the turn row in place so the downstream TurnListItem
        # serializer picks up the reconstructed outfits.
        next_rc = dict(turn.get("resolved_context_json") or {})
        next_rc["outfits"] = outfits
        next_rc["_outfits_hydrated"] = True
        turn["resolved_context_json"] = next_rc


# May 1, 2026 — Theme Taxonomy: in-process dedup for the unmapped-
# signal telemetry. We don't want every read of the Outfits tab to
# spam tool_traces with the same signals over and over; this set
# remembers what we've already logged in the current process. Process
# restart re-logs (fine for ops). For multi-process deployments the
# rate limit applies per worker — still bounded.
_THEME_UNMAPPED_LOGGED: set[str] = set()


def create_app() -> FastAPI:
    cfg = load_config()
    client = SupabaseRestClient(
        rest_url=cfg.supabase_rest_url,
        service_role_key=cfg.supabase_service_role_key,
        timeout_seconds=cfg.request_timeout_seconds,
    )
    repo = ConversationRepository(client)
    onboarding_gateway = ApplicationUserGateway(client)
    # F.2.0 (2026-05-18): tenant lookup, used to resolve shop_domain
    # from incoming requests to the partition key threaded into
    # process_turn → CombinedContext → catalog_search_agent.
    tenant_repo = TenantRepository(client)
    # F.2.2 (2026-05-18): install-time catalog sync. Idempotent per-
    # product upsert; embedding generation only on cache miss.
    bootstrap_service = CatalogBootstrapService(client)
    # F.2.2b (2026-05-18): vision attribute enrichment via OpenAI
    # Batch API. Submitted opportunistically at bootstrap-complete;
    # polled either manually or via the F.3 daily cron.
    vision_enrichment_service = CatalogVisionEnrichmentService(client)
    # F.4 (2026-05-18): per-product sync from Shopify products/*
    # webhooks. Delegates inserts/updates to the bootstrap service so
    # the embedding/upsert logic lives in one place.
    product_sync_service = CatalogProductSyncService(
        client,
        bootstrap_service=bootstrap_service,
    )
    orchestrator = AgenticOrchestrator(repo=repo, onboarding_gateway=onboarding_gateway, config=cfg)
    image_moderation = ImageModerationService()
    dependency_reporting = DependencyReportingService(client)

    tryon_service = TryonService()
    tryon_quality_gate = TryonQualityGate()

    app = FastAPI(title="Sigma Aura Agentic Application", version="3.0.0")

    # Item 6 (May 1, 2026): OpenTelemetry distributed tracing. No-op
    # when OTEL_EXPORTER_OTLP_ENDPOINT is unset; ships spans to the
    # configured collector when set. Honours W3C Trace Context for
    # join-up with frontend RUM and downstream services.
    try:
        from platform_core.otel_setup import configure_otel, instrument_fastapi
        configure_otel("aura-agentic-application")
        instrument_fastapi(app)
    except Exception:  # noqa: BLE001 — never fail app construction on tracing setup
        pass

    # Item 2 (May 1, 2026): request_id correlation. Read incoming
    # X-Request-Id (so upstream proxies / load balancers can supply
    # one), generate when absent, echo on the response, and stash on
    # a ContextVar so logs and observability rows can pick it up
    # without explicit threading. The middleware lives on every route
    # automatically — including /healthz and /metrics.
    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        incoming = request.headers.get("x-request-id") or request.headers.get("X-Request-Id")
        request_id = incoming if incoming else uuid4().hex
        token = set_request_id(request_id)
        try:
            response = await call_next(request)
            response.headers["x-request-id"] = request_id
            return response
        finally:
            reset_request_id(token)

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
            if resolved_view == "chat":
                resolved_view = "home"
            if not resolved_view:
                focus_map = {
                    "chat": "home",
                    "home": "home",
                    "planner": "home",
                    "tryon": "home",
                    "profile": "profile",
                    "wardrobe": "wardrobe",
                    "results": "results",
                    "outfits": "outfits",
                    "checks": "checks",
                }
                resolved_view = focus_map.get(str(focus or "").strip().lower(), "home")
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
        """Liveness probe — fast, no external calls. Restart-decision input."""
        return {"ok": True}

    @app.get("/readyz")
    def readyz() -> Response:
        """Readiness probe — verifies Supabase + OpenAI + Gemini reachability.

        Item 3 (May 1, 2026): traffic-routing decision input. Returns 503
        when any upstream is unreachable so an unhealthy instance is taken
        out of the load balancer rotation immediately. Three checks run
        in parallel with a 2s per-check timeout.
        """
        import os as _os
        from platform_core.readiness import run_all_checks
        report = run_all_checks(
            supabase_rest_url=cfg.supabase_rest_url,
            supabase_service_role_key=cfg.supabase_service_role_key,
            openai_api_key=_os.getenv("OPENAI_API_KEY", "").strip(),
            gemini_api_key=_os.getenv("GEMINI_API_KEY", "").strip(),
        )
        status_code = 200 if report["ready"] else 503
        return Response(
            content=__import__("json").dumps(report),
            status_code=status_code,
            media_type="application/json",
        )

    @app.get("/version")
    def version() -> dict:
        """Build / deploy identifiers — fed by AURA_COMMIT_SHA and AURA_DEPLOYED_AT
        environment variables set by the deploy pipeline."""
        from platform_core.readiness import version_info
        return version_info()

    @app.get("/metrics", include_in_schema=False)
    def metrics() -> Response:
        """Item 5 (May 1, 2026): Prometheus exposition for scrape collection.

        Returns the canonical text-format metrics every Prometheus-compatible
        scraper (Prometheus itself, Datadog Agent, Grafana Alloy, OpenTelemetry
        Collector) ingests without further configuration.
        """
        from platform_core.metrics import generate_latest, CONTENT_TYPE_LATEST
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

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

    @app.post("/v1/users/merge", response_model=MergeUsersResponse)
    def merge_users(payload: MergeUsersRequest) -> MergeUsersResponse:
        """Merge an anonymous external_user_id into an authenticated one.

        D.S.3b — Shopify Customer Account integration. The Vibe app
        calls this once after a customer logs in: alias is the
        localStorage UUID the customer chatted under while anonymous;
        canonical is `shopify:{customer_id}` derived from
        logged_in_customer_id on the storefront. The repo method
        reassigns conversations / catalog_interaction_history /
        confidence_history / policy_event_log /
        dependency_validation_events from alias to canonical.

        Idempotent. If alias doesn't exist the merge is a no-op; if
        canonical doesn't exist it gets created. Note: this endpoint
        does NOT touch onboarding_profiles — the Vibe app calls
        POST /v1/onboarding/profile/ensure separately after merge so
        the downstream image-upload / profile-patch endpoints don't
        404. Keeping the two endpoints distinct lets other callers
        merge users without paying the onboarding-profile cost.
        """
        # Lazy import keeps the metrics module out of the import graph
        # for environments that don't run the FastAPI app.
        from platform_core.metrics import observe_user_merge

        if payload.canonical_external_user_id == payload.alias_external_user_id:
            # Customer was already keyed off this identity — nothing
            # to merge. Still ensure the user row exists so
            # subsequent turns don't 404.
            try:
                repo.get_or_create_user(payload.canonical_external_user_id)
            except (SupabaseError, RuntimeError) as exc:
                observe_user_merge(status="failed")
                raise HTTPException(status_code=502, detail=str(exc)) from exc
            observe_user_merge(status="noop")
            return MergeUsersResponse(
                canonical_external_user_id=payload.canonical_external_user_id,
                merged=False,
                message="canonical equals alias — no-op",
            )
        try:
            repo.merge_external_user_identity(
                canonical_external_user_id=payload.canonical_external_user_id,
                alias_external_user_id=payload.alias_external_user_id,
            )
        except (SupabaseError, RuntimeError) as exc:
            observe_user_merge(status="failed")
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        observe_user_merge(status="success")
        return MergeUsersResponse(
            canonical_external_user_id=payload.canonical_external_user_id,
            merged=True,
            message="merged",
        )

    # ── F.2.2 catalog bootstrap (install-time sync) ──────────────────
    #
    # Vibe-app walks the merchant's Shopify Admin GraphQL catalog,
    # batches products into 25-50 per call, and POSTs each batch to
    # bootstrap-batch. Engine checks (tenant_id, shopify_product_id)
    # in catalog_enriched before any LLM call — re-installs and
    # daily syncs skip everything that's already enriched.
    #
    # When pagination exhausts, vibe-app POSTs bootstrap-complete
    # which flips tenants.bootstrap_status to 'ready' and writes
    # the final product_count for the merchant-admin progress UI.

    @app.post(
        "/v1/tenants/lookup-or-create",
        response_model=TenantStatusResponse,
    )
    def lookup_or_create_tenant(payload: LookupOrCreateTenantRequest) -> TenantStatusResponse:
        """Idempotently resolve a Shopify shop domain to its tenant row.

        First call (post-install): creates `tenants` row with a fresh
        opaque tenant_id, status='pending'. Subsequent calls return
        the existing row unchanged. Vibe-app hits this on every
        merchant-admin load so the home screen has a `tenant_id` to
        thread into bootstrap calls.
        """
        from platform_core.metrics import observe_tenant_lookup
        try:
            # Probe first so we can attribute "created" vs "existing" to
            # the counter. get_or_create itself does the same select
            # internally; the extra query is acceptable on a low-volume
            # endpoint (one call per admin home load + install).
            # Inside the try block so a DB failure on this probe
            # registers as outcome="error" instead of escaping unobserved.
            existing = tenant_repo.get_by_shop_domain(payload.shopify_shop_domain)
            row = tenant_repo.get_or_create(
                shop_domain=payload.shopify_shop_domain,
                shopify_shop_gid=payload.shopify_shop_gid or None,
            )
            observe_tenant_lookup(outcome="existing" if existing else "created")
            return TenantStatusResponse(
                tenant_id=str(row.get("tenant_id") or ""),
                shopify_shop_domain=str(row.get("shopify_shop_domain") or ""),
                bootstrap_status=str(row.get("bootstrap_status") or ""),
                product_count=int(row.get("product_count") or 0),
                bootstrap_completed_at=str(row.get("bootstrap_completed_at") or ""),
                last_sync_at=str(row.get("last_sync_at") or ""),
                theme_overrides=row.get("theme_overrides") or None,
            )
        except (ValueError, SupabaseError, RuntimeError) as exc:
            observe_tenant_lookup(outcome="error")
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.patch(
        "/v1/tenants/{tenant_id}/theme-overrides",
        response_model=TenantStatusResponse,
    )
    def patch_theme_overrides(
        tenant_id: str,
        payload: UpdateThemeOverridesRequest,
    ) -> TenantStatusResponse:
        """Replace the tenant's captured theme settings.

        Called from vibe-app on install + on every `themes/update`
        webhook. Empty payload is OK and clears the overrides
        (Vibe will fall back to Confident Luxe defaults).
        """
        from platform_core.metrics import observe_theme_overrides_patch
        try:
            if not tenant_repo.get_by_tenant_id(tenant_id):
                observe_theme_overrides_patch(outcome="error")
                raise HTTPException(
                    status_code=404,
                    detail=f"tenant_id {tenant_id} not found",
                )
            overrides = payload.model_dump()
            tenant_repo.set_theme_overrides(tenant_id, overrides)
            row = tenant_repo.get_by_tenant_id(tenant_id) or {}
            observe_theme_overrides_patch(outcome="applied")
            return TenantStatusResponse(
                tenant_id=str(row.get("tenant_id") or ""),
                shopify_shop_domain=str(row.get("shopify_shop_domain") or ""),
                bootstrap_status=str(row.get("bootstrap_status") or ""),
                product_count=int(row.get("product_count") or 0),
                bootstrap_completed_at=str(row.get("bootstrap_completed_at") or ""),
                last_sync_at=str(row.get("last_sync_at") or ""),
                theme_overrides=row.get("theme_overrides") or None,
            )
        except HTTPException:
            raise
        except (ValueError, SupabaseError, RuntimeError) as exc:
            observe_theme_overrides_patch(outcome="error")
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post(
        "/v1/tenants/{tenant_id}/bootstrap-batch",
        response_model=BootstrapBatchResponse,
    )
    def bootstrap_batch(
        tenant_id: str,
        payload: BootstrapBatchRequest,
    ) -> BootstrapBatchResponse:
        try:
            # Validate the tenant exists — refusing to ingest data
            # against a tenant_id the install flow hasn't created
            # surfaces config bugs early.
            tenant_row = tenant_repo.get_by_tenant_id(tenant_id)
            if not tenant_row:
                raise HTTPException(
                    status_code=404,
                    detail=f"tenant_id {tenant_id} not found; install flow must run first",
                )

            # Only flip to 'syncing' on a tenant that's still in the
            # install flow (pending/failed). For a tenant already at
            # 'ready' (daily-sync cron re-using this endpoint), leave
            # the status alone — otherwise the merchant-admin home
            # would show "syncing" forever every time the cron fires.
            current_status = str(tenant_row.get("bootstrap_status") or "")
            if current_status in ("pending", "failed"):
                tenant_repo.set_bootstrap_status(tenant_id, "syncing")

            result = bootstrap_service.process_products(
                tenant_id=tenant_id,
                products=[p.model_dump() for p in payload.products],
                revive_soft_deleted=bool(payload.revive_soft_deleted),
            )
            created = int(result.get("created", 0))
            updated = int(result.get("updated", 0))
            failed = int(result.get("failed", 0))
            page_size = len(payload.products)
            tick_status = "empty" if page_size == 0 else (
                "failed" if failed > 0 and (created + updated) == 0 else "ok"
            )
            _log.info(
                "bootstrap_batch: tenant=%s revive=%s products_in=%d created=%d updated=%d failed=%d status=%s",
                tenant_id, bool(payload.revive_soft_deleted),
                page_size, created, updated, failed, tick_status,
            )
            try:
                from platform_core.metrics import observe_bootstrap_batch
                observe_bootstrap_batch(
                    status=tick_status,
                    created=created, updated=updated, failed=failed,
                )
            except Exception:  # noqa: BLE001 — metrics never break pipeline
                pass
            return BootstrapBatchResponse(
                created=created,
                updated=updated,
                failed=failed,
                errors=list(result.get("errors", []) or []),
            )
        except HTTPException:
            raise
        except (ValueError, SupabaseError, RuntimeError) as exc:
            _log.warning(
                "bootstrap_batch: tenant=%s failed err=%s",
                tenant_id, exc,
            )
            try:
                from platform_core.metrics import observe_bootstrap_batch
                observe_bootstrap_batch(status="failed")
            except Exception:  # noqa: BLE001
                pass
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/v1/tenants/{tenant_id}/bootstrap-complete")
    def bootstrap_complete(
        tenant_id: str,
        payload: BootstrapCompleteRequest,
    ) -> Dict[str, Any]:
        from platform_core.metrics import observe_catalog_linkage
        try:
            if not tenant_repo.get_by_tenant_id(tenant_id):
                raise HTTPException(
                    status_code=404,
                    detail=f"tenant_id {tenant_id} not found",
                )
            tenant_repo.set_bootstrap_status(
                tenant_id,
                "ready",
                product_count=int(payload.product_count or 0),
            )
            # Observe how many catalog rows for this tenant have a
            # populated `shopify_product_id`. Tenants with <99% linkage
            # are at risk of firing duplicate-row vision enrichment
            # when webhooks / cron next touches the unlinked products
            # (~$0.003 per row, gated by the cost-bearing invariant
            # only after the freshly-inserted duplicates have already
            # paid the cost). Best-effort — never fail the bootstrap.
            #
            # Two `count()` calls (DB-side aggregation via PostgREST's
            # ``Prefer: count=exact`` Content-Range header) instead of
            # the original ``select_many(limit=50000)``. Memory-bounded
            # regardless of catalog size and deterministic for tenants
            # exceeding the prior cap.
            try:
                total = client.count(
                    "catalog_enriched",
                    filters={"tenant_id": f"eq.{tenant_id}"},
                )
                linked = client.count(
                    "catalog_enriched",
                    filters={
                        "tenant_id": f"eq.{tenant_id}",
                        "shopify_product_id": "not.is.null",
                    },
                )
                observe_catalog_linkage(
                    tenant_id=tenant_id,
                    total_rows=total,
                    linked_rows=linked,
                )
            except Exception as link_exc:  # noqa: BLE001
                _log.warning(
                    "bootstrap_complete: linkage observe failed tenant=%s err=%s",
                    tenant_id,
                    link_exc,
                )
            # F.2.2b: best-effort vision-enrichment submit. Bootstrap
            # is "complete" the moment text embeddings land — vision
            # attributes are an async overlay that arrives within the
            # Batch API's 24h SLA. Failure to submit here doesn't
            # fail the bootstrap (caller's status is already flipped
            # to 'ready'); the daily cron will retry. We catch
            # everything so an OpenAI outage can't roll back the
            # ready-state flip.
            enrich_submitted = False
            enrich_batch_id = ""
            enrich_row_count = 0
            enrich_reason = ""
            try:
                submit = vision_enrichment_service.submit_pending_for_tenant(
                    tenant_id
                )
                enrich_submitted = submit.submitted
                enrich_batch_id = submit.openai_batch_id
                enrich_row_count = submit.row_count
                enrich_reason = submit.reason
            except Exception as exc:  # noqa: BLE001
                enrich_reason = f"submit error: {type(exc).__name__}: {exc}"
                _log.warning(
                    "bootstrap_complete: vision enrichment submit failed tenant=%s err=%s",
                    tenant_id,
                    exc,
                )
            return {
                "ok": True,
                "tenant_id": tenant_id,
                "enrichment": {
                    "submitted": enrich_submitted,
                    "openai_batch_id": enrich_batch_id,
                    "row_count": enrich_row_count,
                    "reason": enrich_reason,
                },
            }
        except HTTPException:
            raise
        except (ValueError, SupabaseError, RuntimeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    # F.2.2b vision enrichment endpoints. The submit endpoint is a
    # manual trigger (bootstrap_complete already auto-submits, but
    # operators may want to retry for a tenant that had OpenAI down
    # during install). The poll endpoint is what the F.3 daily cron
    # calls to ingest completed batches.

    @app.post(
        "/v1/tenants/{tenant_id}/enrichment/submit",
        response_model=EnrichmentSubmitResponse,
    )
    def enrichment_submit(tenant_id: str) -> EnrichmentSubmitResponse:
        try:
            if not tenant_repo.get_by_tenant_id(tenant_id):
                raise HTTPException(
                    status_code=404,
                    detail=f"tenant_id {tenant_id} not found",
                )
            result = vision_enrichment_service.submit_pending_for_tenant(
                tenant_id
            )
            return EnrichmentSubmitResponse(
                submitted=result.submitted,
                openai_batch_id=result.openai_batch_id,
                row_count=result.row_count,
                reason=result.reason,
            )
        except HTTPException:
            raise
        except (ValueError, SupabaseError, RuntimeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post(
        "/v1/tenants/{tenant_id}/enrichment/poll",
        response_model=EnrichmentPollResponse,
    )
    def enrichment_poll(tenant_id: str) -> EnrichmentPollResponse:
        try:
            if not tenant_repo.get_by_tenant_id(tenant_id):
                raise HTTPException(
                    status_code=404,
                    detail=f"tenant_id {tenant_id} not found",
                )
            results = vision_enrichment_service.poll_and_ingest(
                tenant_id=tenant_id
            )
            return EnrichmentPollResponse(
                batches=[
                    EnrichmentBatchPollItem(
                        openai_batch_id=r.openai_batch_id,
                        final_status=r.final_status,
                        rows_ingested=r.rows_ingested,
                        rows_failed=r.rows_failed,
                    )
                    for r in results
                ]
            )
        except HTTPException:
            raise
        except (ValueError, SupabaseError, RuntimeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    # F.4 product webhook endpoints. Vibe-app forwards the raw
    # Shopify webhook payload here after HMAC verification — this
    # service owns the translation to our internal product shape and
    # the catalog_enriched / catalog_item_embeddings updates.

    @app.post(
        "/v1/tenants/{tenant_id}/products/webhook-upsert",
        response_model=ProductWebhookResult,
    )
    def product_webhook_upsert(
        tenant_id: str,
        request: ProductWebhookCreateOrUpdateRequest,
    ) -> ProductWebhookResult:
        try:
            if not tenant_repo.get_by_tenant_id(tenant_id):
                raise HTTPException(
                    status_code=404,
                    detail=f"tenant_id {tenant_id} not found",
                )
            result = product_sync_service.apply_create_or_update(
                tenant_id=tenant_id,
                product_payload=request.payload or {},
                topic=request.topic or "",
            )
            return ProductWebhookResult(
                created=int(result.get("created", 0)),
                updated=int(result.get("updated", 0)),
                failed=int(result.get("failed", 0)),
                shopify_product_id=str(result.get("shopify_product_id", "")),
                available_for_sale=bool(result.get("available_for_sale", True)),
                reason=str(result.get("reason", "")),
            )
        except HTTPException:
            raise
        except (ValueError, SupabaseError, RuntimeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post(
        "/v1/tenants/{tenant_id}/products/webhook-delete",
        response_model=ProductWebhookDeleteResult,
    )
    def product_webhook_delete(
        tenant_id: str,
        request: ProductWebhookCreateOrUpdateRequest,
    ) -> ProductWebhookDeleteResult:
        try:
            if not tenant_repo.get_by_tenant_id(tenant_id):
                raise HTTPException(
                    status_code=404,
                    detail=f"tenant_id {tenant_id} not found",
                )
            # Shopify products/delete payload is `{id: <numeric>}`.
            # Normalise to gid format the rest of the engine uses.
            payload = request.payload or {}
            pid_raw = payload.get("id")
            if isinstance(pid_raw, (int, float)):
                shopify_pid = f"gid://shopify/Product/{int(pid_raw)}"
            else:
                shopify_pid = str(pid_raw or "").strip()
            result = product_sync_service.apply_delete(
                tenant_id=tenant_id,
                shopify_product_id=shopify_pid,
            )
            return ProductWebhookDeleteResult(
                deleted=bool(result.get("deleted", False)),
                shopify_product_id=str(result.get("shopify_product_id", "")),
                reason=str(result.get("reason", "")),
            )
        except HTTPException:
            raise
        except (ValueError, SupabaseError, RuntimeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post(
        "/v1/enrichment/poll-all",
        response_model=EnrichmentPollResponse,
    )
    def enrichment_poll_all() -> EnrichmentPollResponse:
        """Poll EVERY tenant's in-flight enrichment batches.

        Called by the F.3 daily cron. Safe to call manually too —
        idempotent and fast when there are no in-flight batches.
        """
        try:
            results = vision_enrichment_service.poll_and_ingest()
            return EnrichmentPollResponse(
                batches=[
                    EnrichmentBatchPollItem(
                        openai_batch_id=r.openai_batch_id,
                        final_status=r.final_status,
                        rows_ingested=r.rows_ingested,
                        rows_failed=r.rows_failed,
                    )
                    for r in results
                ]
            )
        except (ValueError, SupabaseError, RuntimeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/v1/enrichment/submit-pending-all")
    def enrichment_submit_pending_all() -> Dict[str, Any]:
        """Submit-pending across every ready tenant.

        Closes the F.3 review gap: the F.4 product webhooks insert
        rows with row_status='pending_enrichment' but no surface
        triggered a submit for them (bootstrap_complete only fires
        at install time). Without this call, webhook-added products
        would stay text-only forever. The daily cron now invokes
        this BEFORE poll-all so freshly-inserted rows enter the
        Batch API queue and get ingested on the next day's poll.

        Idempotent: each tenant's submit short-circuits if a batch
        is already in-flight.
        """
        submitted_count = 0
        no_op_count = 0
        errors: List[Dict[str, str]] = []
        try:
            tenants = tenant_repo.list_all(bootstrap_status="ready")
        except (ValueError, SupabaseError, RuntimeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        for tenant in tenants:
            tid = str(tenant.get("tenant_id") or "")
            if not tid:
                continue
            try:
                result = vision_enrichment_service.submit_pending_for_tenant(tid)
                if result.submitted:
                    submitted_count += 1
                else:
                    no_op_count += 1
            except Exception as exc:  # noqa: BLE001
                errors.append({"tenant_id": tid, "error": str(exc)})
                _log.warning(
                    "enrichment_submit_pending_all: tenant=%s err=%s", tid, exc,
                )
        return {
            "tenants_seen": len(tenants),
            "submitted": submitted_count,
            "no_op": no_op_count,
            "errors": errors,
        }

    @app.get(
        "/v1/tenants",
        response_model=TenantListResponse,
    )
    def list_tenants() -> TenantListResponse:
        """Enumerate installed shops. Used by the F.3 daily-sync
        cron in vibe-app to iterate over tenants without holding a
        per-shop session. Filtered to 'ready' tenants only — pending/
        failed/syncing don't yet have data to incrementally sync.
        """
        try:
            rows = tenant_repo.list_all(bootstrap_status="ready")
            return TenantListResponse(
                tenants=[
                    TenantStatusResponse(
                        tenant_id=str(r.get("tenant_id") or ""),
                        shopify_shop_domain=str(r.get("shopify_shop_domain") or ""),
                        bootstrap_status=str(r.get("bootstrap_status") or ""),
                        product_count=int(r.get("product_count") or 0),
                        bootstrap_completed_at=str(r.get("bootstrap_completed_at") or ""),
                        last_sync_at=str(r.get("last_sync_at") or ""),
                        theme_overrides=r.get("theme_overrides") or None,
                    )
                    for r in rows
                ]
            )
        except (ValueError, SupabaseError, RuntimeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get(
        "/v1/tenants/{tenant_id}",
        response_model=TenantStatusResponse,
    )
    def get_tenant(tenant_id: str) -> TenantStatusResponse:
        try:
            row = tenant_repo.get_by_tenant_id(tenant_id)
            if not row:
                raise HTTPException(
                    status_code=404,
                    detail=f"tenant_id {tenant_id} not found",
                )
            return TenantStatusResponse(
                tenant_id=str(row.get("tenant_id") or ""),
                shopify_shop_domain=str(row.get("shopify_shop_domain") or ""),
                bootstrap_status=str(row.get("bootstrap_status") or ""),
                product_count=int(row.get("product_count") or 0),
                bootstrap_completed_at=str(row.get("bootstrap_completed_at") or ""),
                last_sync_at=str(row.get("last_sync_at") or ""),
                theme_overrides=row.get("theme_overrides") or None,
            )
        except HTTPException:
            raise
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
            tenant_id = resolve_tenant_id_or_default(
                tenant_repo,
                shop_domain=payload.shop_domain,
                channel=payload.channel,
            )
            out = orchestrator.process_turn(
                conversation_id=conversation_id,
                external_user_id=payload.user_id,
                message=payload.message,
                channel=payload.channel,
                image_data=payload.image_data or "",
                wardrobe_item_id=payload.wardrobe_item_id or "",
                wishlist_product_id=payload.wishlist_product_id or "",
                seed_product_id=payload.seed_product_id or "",
                tenant_id=tenant_id,
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

        # Resolve tenant_id outside the job thread so a missing-tenant
        # error fails the start-request synchronously (better signal
        # to the client than an opaque background failure).
        tenant_id = resolve_tenant_id_or_default(
            tenant_repo,
            shop_domain=payload.shop_domain,
            channel=payload.channel,
        )

        def run_job() -> None:
            append_stage("turn_execution", "started")
            try:
                out = orchestrator.process_turn(
                    conversation_id=conversation_id,
                    external_user_id=payload.user_id,
                    message=payload.message,
                    channel=payload.channel,
                    image_data=payload.image_data or "",
                    wardrobe_item_id=payload.wardrobe_item_id or "",
                    wishlist_product_id=payload.wishlist_product_id or "",
                    seed_product_id=payload.seed_product_id or "",
                    tenant_id=tenant_id,
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

    class TryonOutfitGarmentRequest(BaseModel):
        # `role` is what Gemini's prompt uses to compose the outfit
        # ("top", "bottom", "dress", "jacket", …). Defaults to a
        # generic value so a single-garment caller works without
        # bothering with the role; the multi-garment branch in
        # TryonService.generate_tryon_outfit only switches prompt
        # variant when `len(garments) >= 2`.
        role: str = "garment"
        image_url: str

    class TryonOutfitRequest(BaseModel):
        user_id: str
        garments: List[TryonOutfitGarmentRequest]

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
                    input_class=Intent.PAIRING_REQUEST,
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
                input_class=Intent.PAIRING_REQUEST,
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

    @app.post("/v1/tryon-outfit")
    def virtual_tryon_outfit(payload: TryonOutfitRequest) -> dict:
        """Multi-garment on-demand try-on.

        Mirrors `POST /v1/tryon` but accepts a list of garments so the
        client (e.g. Vibe Conversation's outfit-mode card) can render
        a whole outfit on the customer in one round trip. The
        orchestrator already runs this same code path automatically
        at outfit-generation time and persists the result; this
        endpoint exists for the cases where that auto-render didn't
        fire (flag off at the time, person photo arrived late, Gemini
        timed out, etc.) and the customer wants a fresh render from
        the storefront / chat surface.

        Inline base64 response — no persistence in this path. Caching
        per (user, garment_ids) lands as V.5 of the Phase V plan.
        """
        reason_code = ""
        try:
            person_image_path = onboarding_gateway.get_person_image_path(payload.user_id)
            if not person_image_path:
                reason_code = "missing_person_image"
                raise ValueError(graceful_policy_message(reason_code))
            if not payload.garments:
                reason_code = "tryon_request_failed"
                raise ValueError("No garments provided.")
            garment_urls: List[tuple[str, str]] = [
                ((g.role or "garment").strip() or "garment", g.image_url.strip())
                for g in payload.garments
                if g.image_url and g.image_url.strip()
            ]
            if not garment_urls:
                reason_code = "tryon_request_failed"
                raise ValueError("No garment image URLs provided.")
            result = tryon_service.generate_tryon_outfit(
                person_image_path=person_image_path,
                garment_urls=garment_urls,
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
                    input_class=Intent.PAIRING_REQUEST,
                    reason_code="quality_gate_passed",
                    decision="allowed",
                    user_id=payload.user_id,
                    source_channel="web",
                    metadata_json={"quality_gate": quality, "garment_count": len(garment_urls)},
                )
            return result
        except (ValueError, FileNotFoundError, RuntimeError) as exc:
            log_policy_event(
                policy_event_type="virtual_tryon_guardrail",
                input_class=Intent.PAIRING_REQUEST,
                reason_code=reason_code or (
                    "missing_person_image"
                    if "No full-body onboarding image found" in str(exc)
                    else "tryon_request_failed"
                ),
                user_id=payload.user_id,
                source_channel="web",
                metadata_json={"error": str(exc), "garment_count": len(payload.garments or [])},
            )
            raise HTTPException(
                status_code=400,
                detail=graceful_policy_message(reason_code or "tryon_request_failed", default=str(exc)),
            ) from exc

    @app.get("/v1/catalog/products/by-shopify-id/{shopify_product_numeric_id}")
    def lookup_catalog_product_by_shopify_id(
        shopify_product_numeric_id: str,
        tenant_id: str = "",
    ) -> dict:
        """Catalog row lookup by Shopify numeric product id, scoped to tenant.

        Phase W gateway — the customer clicks "Virtual Try On" on a
        storefront PDP, lands in Vibe with `?productId=<id>`, and
        the Vibe-app loader hits this to fetch the catalog row for
        the entry product without firing a planner / composer turn.
        Returns the row shaped as an OutfitItem dict (same fields
        the existing turn pipeline emits via _build_candidate_item),
        so the client can wrap it as a synthetic single-item Outfit
        and render the seeded PDP card immediately. No LLM cost on
        entry; LLM only fires when the customer asks a follow-up.

        Shopify's product.id liquid variable returns just the numeric
        portion (e.g. "12345"); catalog_enriched.shopify_product_id
        stores the full GraphQL GID (`gid://shopify/Product/12345`).
        We construct the GID here and match by that — same shape the
        B.8 capture script wrote.

        Numeric ids collide across stores when two tenants happened
        to ingest the same id, so tenant_id is REQUIRED to scope the
        lookup; without it the route would leak rows between
        merchants. Empty tenant_id → 400; missing row → 404.
        """
        if not shopify_product_numeric_id or not shopify_product_numeric_id.strip():
            raise HTTPException(status_code=400, detail="Missing product id")
        if not tenant_id or not tenant_id.strip():
            raise HTTPException(status_code=400, detail="Missing tenant_id")
        gid = f"gid://shopify/Product/{shopify_product_numeric_id.strip()}"
        try:
            enriched = repo.client.select_one(
                "catalog_enriched",
                filters={
                    "shopify_product_id": f"eq.{gid}",
                    "tenant_id": f"eq.{tenant_id.strip()}",
                },
            )
        except SupabaseError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        if not enriched:
            raise HTTPException(
                status_code=404,
                detail=f"Product with id '{shopify_product_numeric_id}' not found in tenant '{tenant_id}'.",
            )

        # Build the OutfitItem the same way the turn pipeline does so
        # the client gets an identically-shaped dict — catalog_description
        # sanitization, image_url normalization, tag-attribute fanout,
        # synthesized description fallback, all of it. Wrap the
        # enriched dict in a minimal RetrievedProduct; populate BOTH
        # `metadata` and `enriched_data` so downstream consumers find
        # the PascalCase attribute keys (GarmentCategory, etc.)
        # regardless of which bucket they read from — the same shape
        # the orchestrator's seed-product anchor branch uses.
        seed_product = RetrievedProduct(
            product_id=str(enriched.get("product_id") or ""),
            similarity=1.0,
            metadata=dict(enriched),
            enriched_data=dict(enriched),
        )
        item = _build_candidate_item(seed_product, role="")
        return {"ok": True, "item": item}

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

            # When there are no item_ids (e.g. outfit check with no catalog
            # products), record a single feedback event at the outfit level
            # using the conversation_id as the garment_id placeholder.
            if not item_ids:
                item_ids = [f"outfit:{conversation_id}:{payload.outfit_rank}"]

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
            # Read-time hydration: reconstruct outfit cards for historical
            # turns that were persisted before the Phase 14 "persist outfits
            # in resolved_context" patch. Best-effort; no-op when the turn
            # already has outfits or when no item IDs are recoverable.
            try:
                conversation = repo.get_conversation(conversation_id)
            except Exception:
                conversation = None
            user_id = ""
            if conversation:
                user_id = str(conversation.get("user_id") or "")
            if user_id and rows:
                try:
                    _hydrate_missing_outfits(
                        client=client,
                        repo=repo,
                        user_id=user_id,
                        turns=rows,
                    )
                except Exception:
                    # Hydration is best-effort — a failure here must not
                    # break the endpoint. The turn rows will just render
                    # without their outfit cards (same as before the fix).
                    pass
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

    # -- Wishlist tab -----------------------------------------------------------

    @app.get("/v1/users/{user_id}/wishlist", response_model=WishlistResponse)
    def list_wishlist(user_id: str) -> WishlistResponse:
        """Return wishlisted catalog products for the Wishlist tab."""
        try:
            items = repo.list_wishlist_products(user_id)
            return WishlistResponse(
                user_id=user_id,
                items=[WishlistItem(**item) for item in items],
            )
        except (ValueError, SupabaseError, RuntimeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    # -- Trial Room tab --------------------------------------------------------

    @app.get("/v1/users/{user_id}/tryon-gallery", response_model=TryonGalleryResponse)
    def list_tryon_gallery(user_id: str) -> TryonGalleryResponse:
        """Return try-on renders for the Trial Room gallery tab."""
        try:
            from urllib.parse import quote
            rows = repo.list_tryon_gallery(user_id)
            items = []
            for row in rows:
                fp = str(row.get("file_path") or "").strip()
                # Rewrite local data/ paths to the serving route
                if fp and not fp.startswith(("http://", "https://", "/v1/")):
                    image_url = "/v1/onboarding/images/local?path=" + quote(fp, safe="/._-")
                else:
                    image_url = fp
                items.append(TryonGalleryItem(
                    id=row.get("id") or "",
                    image_url=image_url,
                    garment_ids=row.get("garment_ids") or [],
                    garment_source=row.get("garment_source") or "",
                    created_at=row.get("created_at") or "",
                ))
            return TryonGalleryResponse(user_id=user_id, items=items)
        except (ValueError, SupabaseError, RuntimeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/v1/analytics/dependency-report", response_model=DependencyReportResponse)
    def dependency_report() -> DependencyReportResponse:
        try:
            return DependencyReportResponse(report=dependency_reporting.build_report())
        except (ValueError, SupabaseError, RuntimeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    # -- Intent-organized history (Phase 15) -----------------------------------

    @app.get("/v1/users/{user_id}/intent-history", response_model=IntentHistoryResponse)
    def list_intent_history(user_id: str, types: str = "") -> IntentHistoryResponse:
        """Return styling history grouped by intent session.

        Groups turns by (conversation_id, primary_intent, occasion). Each
        group is a self-contained intent session with its own PDP cards,
        context summary, and try-on images. The frontend renders each
        group as a swipeable PDP carousel.

        Optional ``types`` query param filters to specific intents
        (comma-separated, e.g. ``?types=occasion_recommendation,pairing_request``).
        """
        try:
            from collections import OrderedDict
            from urllib.parse import quote

            user = repo.get_or_create_user(user_id)
            internal_uid = str(user["id"])
            rows = repo.list_recent_results_for_user(internal_uid, limit=100)

            if not rows:
                return IntentHistoryResponse(user_id=user_id, groups=[])

            # Hydrate missing outfits (same as /turns endpoint)
            try:
                _hydrate_missing_outfits(
                    client=client,
                    repo=repo,
                    user_id=internal_uid,
                    turns=rows,
                )
            except Exception:
                pass

            # Load liked/disliked outfit keys
            liked_keys: set = set()
            disliked_keys: set = set()
            try:
                liked_keys = repo.list_liked_outfit_keys(internal_uid)
            except Exception:
                pass
            try:
                disliked_keys = repo.list_disliked_outfit_keys(internal_uid)
            except Exception:
                pass

            # Parse the types filter
            allowed_types = set()
            if types:
                allowed_types = {t.strip().lower() for t in types.split(",") if t.strip()}

            # Group by (conversation_id, primary_intent, occasion)
            groups: OrderedDict[str, dict] = OrderedDict()
            for row in rows:
                ctx = dict(row.get("resolved_context_json") or {})
                metadata = dict(ctx.get("response_metadata") or {})
                raw_intent = str(
                    metadata.get("primary_intent")
                    or ctx.get("intent")
                    or ctx.get("handler", "").split("_")[0]
                    or ""
                ).strip().lower()
                occasion = str(ctx.get("occasion") or "").strip().lower()
                conv_id = str(row.get("conversation_id") or "")
                source = str(
                    metadata.get("answer_source")
                    or ctx.get("style_goal")
                    or ctx.get("source_preference")
                    or ""
                )

                # PR V2 (May 5 2026): outfit_check + garment_evaluation
                # intents removed from the product. Skip historical rows
                # tagged with those intents — their persisted shape
                # included visual_evaluator-only fields (verdicts,
                # archetype tier pcts, deeper notes) that the post-V2
                # frontend can't render cleanly. Skipping is safer than
                # rendering them as half-baked recommendation cards.
                if raw_intent in ("outfit_check", "garment_evaluation"):
                    continue
                intent = raw_intent

                if allowed_types and intent not in allowed_types:
                    continue

                # Skip turns with no outfits (clarification responses).
                all_outfits = ctx.get("outfits") or []
                if not all_outfits:
                    continue

                # Require some kind of preview image (tryon_image or product
                # image). Cards without any preview can't be rendered.
                has_preview = any(
                    str(o.get("tryon_image") or "").strip()
                    or any(str(it.get("image_url") or "").strip() for it in (o.get("items") or []))
                    for o in all_outfits
                )
                if not has_preview:
                    continue

                group_key = f"{intent}:{occasion}" if occasion else f"{intent}:{conv_id}"

                # Extract outfits for this turn, filtering out disliked/hidden ones
                # and tagging liked ones
                turn_id_str = str(row.get("id") or "")
                outfits = []
                for o in all_outfits:
                    rank_val = int(o.get("rank") or 0)
                    if (turn_id_str, rank_val) in disliked_keys:
                        continue
                    if (turn_id_str, rank_val) in liked_keys:
                        o["_liked"] = True
                    outfits.append(o)
                first_img = ""
                for o in outfits:
                    tryon = str(o.get("tryon_image") or "").strip()
                    if tryon:
                        first_img = tryon
                        break
                if not first_img:
                    for o in outfits:
                        for item in (o.get("items") or []):
                            img = str(item.get("image_url") or "").strip()
                            if img:
                                first_img = img
                                break
                        if first_img:
                            break

                turn_item = IntentHistoryTurn(
                    turn_id=str(row.get("id") or ""),
                    conversation_id=conv_id,
                    user_message=str(row.get("user_message") or ""),
                    assistant_summary=str(row.get("assistant_message") or "")[:300],
                    outfits=outfits,
                    outfit_count=len(outfits),
                    first_outfit_image=first_img,
                    created_at=str(row.get("created_at") or ""),
                )

                if group_key not in groups:
                    # Build a human-readable context summary
                    occasion_label = occasion.replace("_", " ").strip() if occasion else ""
                    intent_label = intent.replace("_", " ").strip() if intent else "styled look"
                    summary_parts = []
                    if occasion_label:
                        summary_parts.append(occasion_label)
                    if source and source not in ("auto", ""):
                        summary_parts.append(source.replace("_", " "))
                    context_summary = " · ".join(summary_parts) if summary_parts else intent_label

                    # May 1, 2026 — Theme Taxonomy: collapse the long
                    # tail of occasion strings into 8 canonical themes.
                    from .services.theme_taxonomy import map_to_theme, is_unmapped
                    theme_key = map_to_theme(occasion, intent)
                    # Telemetry: signals that have content but matched
                    # zero keywords are the keyword-list's growth edge.
                    # Dedup per-process so we log each unique unmapped
                    # signal once until restart.
                    if is_unmapped(occasion) and occasion not in _THEME_UNMAPPED_LOGGED:
                        _THEME_UNMAPPED_LOGGED.add(occasion)
                        try:
                            repo.log_tool_trace(
                                conversation_id=conv_id,
                                turn_id=str(row.get("id") or ""),
                                tool_name="theme_unmapped",
                                input_json={"occasion_signal": occasion, "intent": intent},
                                output_json={"theme_key": theme_key},
                            )
                        except Exception:
                            pass

                    groups[group_key] = {
                        "group_key": group_key,
                        "conversation_id": conv_id,
                        "intent": intent,
                        "occasion": occasion,
                        "source": source,
                        "context_summary": context_summary,
                        "turn_count": 0,
                        "total_outfit_count": 0,
                        "first_image": "",
                        "created_at": str(row.get("created_at") or ""),
                        "updated_at": str(row.get("created_at") or ""),
                        "turns": [],
                        "theme_key": theme_key,
                    }

                g = groups[group_key]
                g["turns"].append(turn_item)
                g["turn_count"] += 1
                g["total_outfit_count"] += len(outfits)
                if not g["first_image"] and first_img:
                    g["first_image"] = first_img
                g["updated_at"] = str(row.get("created_at") or g["updated_at"])

            # Formality fallback: sessions that did not match any
            # occasion keyword get bucketed by the rater's
            # ``formality_pct`` averaged across the session's outfits
            # — so a stylist-only "what goes with this skirt?" still
            # lands in a meaningful bucket (Smart Looks / Easy
            # Everyday / Off-Duty) instead of a generic catch-all.
            from .services.theme_taxonomy import map_formality_to_bucket

            def _avg_formality(turns_list) -> Optional[float]:
                vals: List[float] = []
                for t in turns_list:
                    for o in (t.outfits or []):
                        v = o.get("formality_pct") if isinstance(o, dict) else None
                        if isinstance(v, (int, float)) and v >= 0:
                            vals.append(float(v))
                return sum(vals) / len(vals) if vals else None

            result_groups: List[IntentHistoryGroup] = []
            for g in groups.values():
                if g["theme_key"] == "style_sessions":
                    g["theme_key"] = map_formality_to_bucket(_avg_formality(g["turns"]))
                result_groups.append(IntentHistoryGroup(**g))

            # Fold flat groups into theme blocks. Themes ordered by
            # most-recent activity so whatever the user is currently
            # planning floats to the top; ties broken by canonical
            # theme order. Empty themes are dropped.
            from .services.theme_taxonomy import (
                THEMES, theme_label, theme_description, theme_order,
            )
            from collections import defaultdict
            theme_to_groups: Dict[str, List[IntentHistoryGroup]] = defaultdict(list)
            theme_to_recent: Dict[str, str] = {}
            for g in result_groups:
                tk = g.theme_key or "style_sessions"
                theme_to_groups[tk].append(g)
                if g.updated_at and (tk not in theme_to_recent or g.updated_at > theme_to_recent[tk]):
                    theme_to_recent[tk] = g.updated_at

            theme_blocks: List[IntentHistoryThemeBlock] = []
            for tk, gs in theme_to_groups.items():
                gs_sorted = sorted(gs, key=lambda x: x.updated_at or "", reverse=True)
                theme_blocks.append(
                    IntentHistoryThemeBlock(
                        theme_key=tk,
                        theme_label=theme_label(tk),
                        theme_description=theme_description(tk),
                        group_count=len(gs_sorted),
                        total_outfit_count=sum(g.total_outfit_count for g in gs_sorted),
                        most_recent_at=theme_to_recent.get(tk, ""),
                        groups=gs_sorted,
                    )
                )
            # Recency-first sort, fallback to canonical order on ties.
            theme_blocks.sort(
                key=lambda b: (b.most_recent_at or "", -theme_order(b.theme_key)),
                reverse=True,
            )

            return IntentHistoryResponse(
                user_id=user_id,
                groups=result_groups,  # back-compat
                themes=theme_blocks,
            )
        except (ValueError, SupabaseError, RuntimeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    # -- Recent signals timeline (profile Phase 14 Step 5) ---------------------

    @app.get("/v1/users/{user_id}/recent-signals", response_model=RecentSignalsResponse)
    def list_recent_signals(user_id: str, limit: int = 5) -> RecentSignalsResponse:
        """Return the deterministic profile signals timeline.

        Reads from `user_comfort_learning`, `feedback_events`, and
        `catalog_interaction_history` and shapes the rows into a small
        list of stylist-voice copy strings. No LLM call. Newest first.
        """
        try:
            from .services.recent_signals import build_recent_signals

            user = repo.get_or_create_user(user_id)
            internal_uid = str(user["id"])

            comfort_rows = repo.get_comfort_signals(internal_uid)
            feedback_rows = repo.list_feedback_events_for_user(internal_uid, limit=50)
            catalog_rows = repo.list_catalog_interactions(internal_uid, limit=50)

            signals = build_recent_signals(
                comfort_rows=comfort_rows or [],
                feedback_rows=feedback_rows or [],
                catalog_rows=catalog_rows or [],
                limit=max(1, min(20, int(limit))),
            )
            return RecentSignalsResponse(
                user_id=user_id,
                signals=[RecentSignal(**s) for s in signals],
            )
        except (ValueError, SupabaseError, RuntimeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return app
