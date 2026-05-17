import logging
from pathlib import Path
from threading import Thread

from fastapi import APIRouter, File, Form, HTTPException, Query, Response, UploadFile
from fastapi.responses import FileResponse

from platform_core.metrics import (
    observe_onboarding_endpoint,
    observe_onboarding_image_bytes,
)
from platform_core.supabase_rest import SupabaseError

from .schemas import (
    AnalysisAgentRerunRequest,
    AnalysisStartRequest,
    AnalysisStartResponse,
    AnalysisStatusResponse,
    EnsureProfileRequest,
    ImageCategory,
    ImageUploadResponse,
    OnboardingStatusResponse,
    ProfilePartialRequest,
    ProfileRequest,
    ProfileResponse,
    SendOtpRequest,
    SendOtpResponse,
    RiskToleranceRequest,
    RiskToleranceResponse,
    VerifyOtpRequest,
    VerifyOtpResponse,
    WardrobeItemListResponse,
    WardrobeItemResponse,
    WardrobeItemUpdateRequest,
    WardrobeSummaryResponse,
)
from .service import OnboardingService
from .analysis import UserAnalysisService


logger = logging.getLogger("aura.onboarding")


def _log_endpoint(
    *, endpoint: str, status: str, channel: str, user_id: str = "", **extra: object,
) -> None:
    """Emit one structured log per onboarding-endpoint outcome.

    Mirrors the Prometheus counter so dashboards can aggregate while
    debugging walks per-user via grep. `extra` carries route-specific
    fields (e.g. category for image_upload). Best-effort — logging
    should never break the request path."""
    try:
        logger.info(
            "onboarding_endpoint",
            extra={
                "event": "onboarding_endpoint",
                "endpoint": endpoint,
                "status": status,
                "channel": channel,
                "user_id": user_id,
                **extra,
            },
        )
    except Exception:  # noqa: BLE001
        pass


def _repo_root() -> Path:
    here = Path(__file__).resolve()
    for base in [here.parent] + list(here.parents):
        if (base / "data").exists() and (base / "modules").exists():
            return base
    return Path.cwd()


def _resolve_local_image_file(path_value: str) -> Path | None:
    raw = str(path_value or "").strip()
    if not raw:
        return None
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = (_repo_root() / candidate).resolve()
    else:
        candidate = candidate.resolve()

    allowed_roots = [
        (_repo_root() / "data" / "onboarding" / "images").resolve(),
        (_repo_root() / "data" / "tryon" / "images").resolve(),
    ]
    for allowed_root in allowed_roots:
        try:
            candidate.relative_to(allowed_root)
            return candidate
        except ValueError:
            continue
    return None


def create_onboarding_router(service: OnboardingService, analysis_service: UserAnalysisService) -> APIRouter:
    router = APIRouter(prefix="/v1/onboarding", tags=["onboarding"])

    # May 2026: /style-assets/choices/{filename}, /style/session/{user_id},
    # and /style/complete endpoints removed alongside the image-picker
    # onboarding step. New flow uses /risk-tolerance with a single
    # 3-option choice — see save_risk_tolerance below.

    @router.get("/images/local", include_in_schema=False)
    def get_local_image(path: str = Query(..., min_length=1)) -> FileResponse:
        image_path = _resolve_local_image_file(path)
        if image_path is None or not image_path.exists() or not image_path.is_file():
            raise HTTPException(status_code=404, detail="Local image not found.")
        return FileResponse(path=image_path)

    @router.post("/send-otp", response_model=SendOtpResponse)
    def send_otp(payload: SendOtpRequest) -> SendOtpResponse:
        ok, msg = service.send_otp(payload.mobile)
        return SendOtpResponse(success=ok, message=msg)

    @router.post("/verify-otp", response_model=VerifyOtpResponse)
    def verify_otp(payload: VerifyOtpRequest) -> VerifyOtpResponse:
        try:
            ok, user_id, msg = service.verify_otp(
                payload.mobile,
                payload.otp,
                acquisition_source=payload.acquisition_source,
                acquisition_campaign=payload.acquisition_campaign,
                referral_code=payload.referral_code,
                icp_tag=payload.icp_tag,
            )
        except (SupabaseError, RuntimeError) as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        if not ok:
            raise HTTPException(status_code=401, detail=msg)
        return VerifyOtpResponse(verified=True, user_id=user_id, message=msg)

    @router.post("/profile/ensure", response_model=ProfileResponse)
    def ensure_profile(
        payload: EnsureProfileRequest,
        channel: str = Query("web", description="Caller channel label for metrics (web / vibe_storefront)."),
    ) -> ProfileResponse:
        """Idempotent onboarding-profile row creation for OTP-less flows
        (Vibe Shopify storefront).

        Vibe customers don't go through OTP — they're anonymous via a
        localStorage session id (D.S.3a). Without this endpoint the
        downstream PATCH /profile/partial and POST /images/{cat} calls
        404 because the row doesn't exist. Idempotent — repeated calls
        are no-ops past the first.
        """
        try:
            out = service.ensure_profile(payload.user_id)
        except (SupabaseError, RuntimeError) as exc:
            observe_onboarding_endpoint(endpoint="profile_ensure", status="failed", channel=channel)
            _log_endpoint(endpoint="profile_ensure", status="failed", channel=channel, user_id=payload.user_id, error=str(exc))
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        # Surface the no-repo case as a 503 instead of a success-shaped
        # response — it means the engine isn't fully wired to Supabase,
        # which the caller can't recover from and ops needs to see.
        reason = out.get("reason", "")
        if reason == "no_repo":
            observe_onboarding_endpoint(endpoint="profile_ensure", status="failed", channel=channel)
            _log_endpoint(endpoint="profile_ensure", status="failed", channel=channel, user_id=payload.user_id, error="no_repo")
            raise HTTPException(status_code=503, detail="Onboarding repository not initialized.")
        created = bool(out.get("created"))
        observe_onboarding_endpoint(endpoint="profile_ensure", status="success", channel=channel)
        _log_endpoint(endpoint="profile_ensure", status="success", channel=channel, user_id=payload.user_id, created=created)
        return ProfileResponse(
            user_id=payload.user_id,
            saved=True,
            message="Profile created" if created else "Profile already exists",
        )

    @router.post("/profile", response_model=ProfileResponse)
    def save_profile(payload: ProfileRequest) -> ProfileResponse:
        try:
            ok = service.save_profile(
                user_id=payload.user_id,
                name=payload.name,
                date_of_birth=str(payload.date_of_birth),
                gender=payload.gender,
                height_cm=payload.height_cm,
                waist_cm=payload.waist_cm,
                profession=payload.profession,
            )
        except (SupabaseError, RuntimeError) as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        if not ok:
            raise HTTPException(status_code=404, detail="User not found. Complete OTP verification first.")
        return ProfileResponse(user_id=payload.user_id, saved=True, message="Profile saved")

    @router.patch("/profile/partial", response_model=ProfileResponse)
    def patch_profile(
        payload: ProfilePartialRequest,
        channel: str = Query("web", description="Caller channel label for metrics (web / vibe_storefront)."),
    ) -> ProfileResponse:
        """Update individual profile fields. Only provided (non-null) fields are saved."""
        fields = {}
        if payload.name is not None:
            fields["name"] = payload.name
        if payload.date_of_birth is not None:
            fields["date_of_birth"] = str(payload.date_of_birth)
        if payload.gender is not None:
            fields["gender"] = payload.gender
        if payload.height_cm is not None:
            fields["height_cm"] = payload.height_cm
        if payload.waist_cm is not None:
            fields["waist_cm"] = payload.waist_cm
        if payload.profession is not None:
            fields["profession"] = payload.profession
        if not fields:
            observe_onboarding_endpoint(endpoint="profile_partial", status="success", channel=channel)
            _log_endpoint(endpoint="profile_partial", status="success", channel=channel, user_id=payload.user_id, fields_count=0)
            return ProfileResponse(user_id=payload.user_id, saved=False, message="No fields to update")
        try:
            ok = service.patch_profile(payload.user_id, **fields)
        except (SupabaseError, RuntimeError) as exc:
            observe_onboarding_endpoint(endpoint="profile_partial", status="failed", channel=channel)
            _log_endpoint(endpoint="profile_partial", status="failed", channel=channel, user_id=payload.user_id, error=str(exc), fields=sorted(fields.keys()))
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        if not ok:
            observe_onboarding_endpoint(endpoint="profile_partial", status="not_found", channel=channel)
            _log_endpoint(endpoint="profile_partial", status="not_found", channel=channel, user_id=payload.user_id, fields=sorted(fields.keys()))
            raise HTTPException(status_code=404, detail="User not found.")
        observe_onboarding_endpoint(endpoint="profile_partial", status="success", channel=channel)
        _log_endpoint(endpoint="profile_partial", status="success", channel=channel, user_id=payload.user_id, fields=sorted(fields.keys()))
        return ProfileResponse(user_id=payload.user_id, saved=True, message="Profile updated")

    @router.post("/images/normalize")
    def normalize_image(file: UploadFile = File(...)) -> Response:
        if not file.content_type or not file.content_type.startswith("image/"):
            raise HTTPException(status_code=400, detail="File must be an image")
        data = file.file.read()
        if len(data) > 15 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="Image must be under 15MB")
        try:
            normalized_data, normalized_type, normalized_name = service.normalize_image_for_crop(
                file_data=data,
                filename=file.filename or "image.jpg",
                content_type=file.content_type,
            )
        except (SupabaseError, RuntimeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        headers = {"X-Normalized-Filename": normalized_name}
        return Response(content=normalized_data, media_type=normalized_type, headers=headers)

    @router.post("/images/{category}", response_model=ImageUploadResponse)
    def upload_image(
        category: ImageCategory,
        user_id: str = Form(...),
        file: UploadFile = File(...),
        channel: str = Query("web", description="Caller channel label for metrics (web / vibe_storefront)."),
    ) -> ImageUploadResponse:
        category_label = str(getattr(category, "value", category) or "")
        if not file.content_type or not file.content_type.startswith("image/"):
            observe_onboarding_endpoint(endpoint="image_upload", status="bad_request", channel=channel)
            _log_endpoint(endpoint="image_upload", status="bad_request", channel=channel, user_id=user_id, category=category_label, error="not_an_image")
            raise HTTPException(status_code=400, detail="File must be an image")
        data = file.file.read()
        size_bytes = len(data)
        if size_bytes > 10 * 1024 * 1024:
            observe_onboarding_endpoint(endpoint="image_upload", status="bad_request", channel=channel)
            _log_endpoint(endpoint="image_upload", status="bad_request", channel=channel, user_id=user_id, category=category_label, size_bytes=size_bytes, error="too_large")
            raise HTTPException(status_code=400, detail="Image must be under 10MB")
        try:
            result = service.save_image(
                user_id=user_id,
                category=category,
                file_data=data,
                filename=file.filename or "image.jpg",
                content_type=file.content_type or "image/jpeg",
            )
        except ValueError as exc:
            observe_onboarding_endpoint(endpoint="image_upload", status="bad_request", channel=channel)
            _log_endpoint(endpoint="image_upload", status="bad_request", channel=channel, user_id=user_id, category=category_label, size_bytes=size_bytes, error=str(exc))
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except (SupabaseError, RuntimeError) as exc:
            observe_onboarding_endpoint(endpoint="image_upload", status="failed", channel=channel)
            _log_endpoint(endpoint="image_upload", status="failed", channel=channel, user_id=user_id, category=category_label, size_bytes=size_bytes, error=str(exc))
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        if result is None:
            observe_onboarding_endpoint(endpoint="image_upload", status="not_found", channel=channel)
            _log_endpoint(endpoint="image_upload", status="not_found", channel=channel, user_id=user_id, category=category_label, size_bytes=size_bytes)
            raise HTTPException(status_code=404, detail="User not found")
        encrypted_filename, file_path = result
        # Histogram on the success path only — failed uploads have
        # already been bucketed via the counter and we don't want to
        # mix "successfully ingested by the engine" with "rejected
        # too_large" in the size distribution.
        observe_onboarding_image_bytes(category=category_label, size_bytes=size_bytes, channel=channel)
        observe_onboarding_endpoint(endpoint="image_upload", status="success", channel=channel)
        _log_endpoint(endpoint="image_upload", status="success", channel=channel, user_id=user_id, category=category_label, size_bytes=size_bytes)
        return ImageUploadResponse(
            user_id=user_id,
            category=category,
            saved=True,
            encrypted_filename=encrypted_filename,
            file_path=file_path,
        )

    @router.get("/status/{user_id}", response_model=OnboardingStatusResponse)
    def get_status(
        user_id: str,
        channel: str = Query("web", description="Caller channel label for metrics (web / vibe_storefront)."),
    ) -> OnboardingStatusResponse:
        try:
            status = service.get_status(user_id)
        except (SupabaseError, RuntimeError) as exc:
            observe_onboarding_endpoint(endpoint="status_read", status="failed", channel=channel)
            _log_endpoint(endpoint="status_read", status="failed", channel=channel, user_id=user_id, error=str(exc))
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        # service.get_status returns a 200 with empty fields for users
        # with no row (instead of raising 404), so the metric is just
        # success/failed; row presence flows through the log on
        # `has_row` for grepping individual customer sessions. The Vibe
        # client (getOnboardingStatus) maps "empty gender" → hasProfile=
        # false on its end, so we don't need a separate metric label
        # here.
        has_row = bool(status.get("mobile") or status.get("gender") or status.get("name"))
        observe_onboarding_endpoint(endpoint="status_read", status="success", channel=channel)
        _log_endpoint(endpoint="status_read", status="success", channel=channel, user_id=user_id, has_row=has_row)
        return OnboardingStatusResponse(**status)

    @router.get("/wardrobe/{user_id}", response_model=WardrobeItemListResponse)
    def get_wardrobe_items(
        user_id: str,
        channel: str = Query("web", description="Caller channel label for metrics (web / vibe_storefront)."),
    ) -> WardrobeItemListResponse:
        try:
            out = service.list_wardrobe_items(user_id)
        except (SupabaseError, RuntimeError, ValueError) as exc:
            observe_onboarding_endpoint(endpoint="wardrobe_list", status="bad_request", channel=channel)
            _log_endpoint(endpoint="wardrobe_list", status="bad_request", channel=channel, user_id=user_id, error=str(exc))
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        item_count = len(out.get("items") or [])
        observe_onboarding_endpoint(endpoint="wardrobe_list", status="success", channel=channel)
        _log_endpoint(endpoint="wardrobe_list", status="success", channel=channel, user_id=user_id, item_count=item_count)
        return WardrobeItemListResponse(**out)

    @router.get("/wardrobe/{user_id}/summary", response_model=WardrobeSummaryResponse)
    def get_wardrobe_summary(user_id: str) -> WardrobeSummaryResponse:
        try:
            out = service.get_wardrobe_summary(user_id)
        except (SupabaseError, RuntimeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return WardrobeSummaryResponse(**out)

    @router.post("/wardrobe/items", response_model=WardrobeItemResponse)
    def save_wardrobe_item(
        user_id: str = Form(...),
        title: str = Form(""),
        description: str = Form(""),
        garment_category: str = Form(""),
        garment_subtype: str = Form(""),
        primary_color: str = Form(""),
        secondary_color: str = Form(""),
        pattern_type: str = Form(""),
        formality_level: str = Form(""),
        occasion_fit: str = Form(""),
        brand: str = Form(""),
        notes: str = Form(""),
        file: UploadFile = File(...),
    ) -> WardrobeItemResponse:
        if not file.content_type or not file.content_type.startswith("image/"):
            raise HTTPException(status_code=400, detail="File must be an image")
        data = file.file.read()
        if len(data) > 10 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="Image must be under 10MB")
        try:
            out = service.save_wardrobe_item(
                user_id=user_id,
                file_data=data,
                filename=file.filename or "wardrobe.jpg",
                content_type=file.content_type,
                source="onboarding",
                title=title,
                description=description,
                garment_category=garment_category,
                garment_subtype=garment_subtype,
                primary_color=primary_color,
                secondary_color=secondary_color,
                pattern_type=pattern_type,
                formality_level=formality_level,
                occasion_fit=occasion_fit,
                brand=brand,
                notes=notes,
            )
        except (SupabaseError, RuntimeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if not out:
            raise HTTPException(status_code=404, detail="User not found.")
        return WardrobeItemResponse(**out)

    @router.patch("/wardrobe/items/{wardrobe_item_id}", response_model=WardrobeItemResponse)
    def update_wardrobe_item(wardrobe_item_id: str, payload: WardrobeItemUpdateRequest) -> WardrobeItemResponse:
        try:
            out = service.update_wardrobe_item(
                user_id=payload.user_id,
                wardrobe_item_id=wardrobe_item_id,
                title=payload.title,
                description=payload.description,
                garment_category=payload.garment_category,
                garment_subtype=payload.garment_subtype,
                primary_color=payload.primary_color,
                secondary_color=payload.secondary_color,
                pattern_type=payload.pattern_type,
                formality_level=payload.formality_level,
                occasion_fit=payload.occasion_fit,
                brand=payload.brand,
                notes=payload.notes,
            )
        except (SupabaseError, RuntimeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if not out:
            raise HTTPException(status_code=404, detail="Wardrobe item not found.")
        return WardrobeItemResponse(**out)

    @router.delete("/wardrobe/items/{wardrobe_item_id}")
    def delete_wardrobe_item(wardrobe_item_id: str, user_id: str) -> dict:
        try:
            ok = service.delete_wardrobe_item(user_id=user_id, wardrobe_item_id=wardrobe_item_id)
        except (SupabaseError, RuntimeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if not ok:
            raise HTTPException(status_code=404, detail="Wardrobe item not found.")
        return {"ok": True, "wardrobe_item_id": wardrobe_item_id}

    @router.post("/risk-tolerance", response_model=RiskToleranceResponse)
    def save_risk_tolerance(payload: RiskToleranceRequest) -> RiskToleranceResponse:
        """May 2026: single-step risk-tolerance capture, replaces the
        multi-layer image-picker /style/complete flow."""
        try:
            out = service.save_risk_tolerance(
                user_id=payload.user_id,
                risk_tolerance=payload.risk_tolerance,
            )
        except (SupabaseError, RuntimeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if not out:
            raise HTTPException(status_code=404, detail="User not found.")
        return RiskToleranceResponse(user_id=payload.user_id, saved=True, risk_tolerance=out["risk_tolerance"])

    @router.post("/analysis/start", response_model=AnalysisStartResponse)
    def start_analysis(payload: AnalysisStartRequest) -> AnalysisStartResponse:
        try:
            status = service.get_status(payload.user_id)
        except (SupabaseError, RuntimeError) as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        if not status.get("onboarding_complete"):
            raise HTTPException(status_code=400, detail="Complete onboarding before starting analysis.")

        try:
            run = analysis_service.ensure_analysis_started(payload.user_id)
        except (SupabaseError, RuntimeError, ValueError) as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

        if str(run.get("status")) in ("pending", "running"):
            def run_job() -> None:
                try:
                    # Uses run_remaining_and_finalize so phases 1/2 outputs
                    # (color + other_details) are reused if already completed.
                    analysis_service.run_remaining_and_finalize(payload.user_id)
                except Exception as exc:  # noqa: BLE001
                    analysis_service.fail_analysis(payload.user_id, str(exc))

            Thread(target=run_job, daemon=True).start()

        return AnalysisStartResponse(
            user_id=payload.user_id,
            analysis_run_id=str(run.get("id") or ""),
            status=str(run.get("status") or "pending"),
            message="Analysis started" if str(run.get("status") or "pending") == "pending" else "Analysis already in progress or complete",
        )

    @router.post("/analysis/start-phase1", response_model=AnalysisStartResponse)
    def start_phase1(
        payload: AnalysisStartRequest,
        channel: str = Query("web", description="Caller channel label for metrics (web / vibe_storefront)."),
    ) -> AnalysisStartResponse:
        """Phase 1: start color analysis agent right after image upload.

        Requires gender (already collected) + headshot image.
        Age is passed as empty — color analysis is age-independent.
        """
        try:
            status = service.get_status(payload.user_id)
        except (SupabaseError, RuntimeError) as exc:
            observe_onboarding_endpoint(endpoint="analysis_start_phase1", status="failed", channel=channel)
            _log_endpoint(endpoint="analysis_start_phase1", status="failed", channel=channel, user_id=payload.user_id, error=str(exc))
            raise HTTPException(status_code=502, detail=str(exc)) from exc

        gender = status.get("gender") or ""
        if not gender:
            observe_onboarding_endpoint(endpoint="analysis_start_phase1", status="bad_request", channel=channel)
            _log_endpoint(endpoint="analysis_start_phase1", status="bad_request", channel=channel, user_id=payload.user_id, error="missing_gender")
            raise HTTPException(status_code=400, detail="Gender is required for color analysis.")

        ctx = {"gender": gender, "age": "", "height": "", "waist": ""}

        def run_job() -> None:
            try:
                analysis_service.run_single_agent(
                    payload.user_id,
                    "color_analysis_headshot",
                    prompt_context_override=ctx,
                )
            except Exception:
                pass  # best-effort — full analysis will re-run this if it failed

        Thread(target=run_job, daemon=True).start()
        observe_onboarding_endpoint(endpoint="analysis_start_phase1", status="success", channel=channel)
        _log_endpoint(endpoint="analysis_start_phase1", status="success", channel=channel, user_id=payload.user_id)
        return AnalysisStartResponse(
            user_id=payload.user_id,
            analysis_run_id="",
            status="phase1_started",
            message="Color analysis started.",
        )

    @router.post("/analysis/start-phase2", response_model=AnalysisStartResponse)
    def start_phase2(
        payload: AnalysisStartRequest,
        channel: str = Query("web", description="Caller channel label for metrics (web / vibe_storefront)."),
    ) -> AnalysisStartResponse:
        """Phase 2: start other_details agent after DOB is provided.

        Requires gender + date_of_birth + both images.
        """
        try:
            status = service.get_status(payload.user_id)
        except (SupabaseError, RuntimeError) as exc:
            observe_onboarding_endpoint(endpoint="analysis_start_phase2", status="failed", channel=channel)
            _log_endpoint(endpoint="analysis_start_phase2", status="failed", channel=channel, user_id=payload.user_id, error=str(exc))
            raise HTTPException(status_code=502, detail=str(exc)) from exc

        gender = status.get("gender") or ""
        dob = status.get("date_of_birth") or ""
        if not dob:
            observe_onboarding_endpoint(endpoint="analysis_start_phase2", status="bad_request", channel=channel)
            _log_endpoint(endpoint="analysis_start_phase2", status="bad_request", channel=channel, user_id=payload.user_id, error="missing_dob")
            raise HTTPException(status_code=400, detail="Date of birth is required for this phase.")

        age = analysis_service._calculate_age(dob)
        ctx = {"gender": gender, "age": age, "height": "", "waist": ""}

        def run_job() -> None:
            try:
                analysis_service.run_single_agent(
                    payload.user_id,
                    "other_details_analysis",
                    prompt_context_override=ctx,
                )
            except Exception:
                pass  # best-effort

        Thread(target=run_job, daemon=True).start()
        observe_onboarding_endpoint(endpoint="analysis_start_phase2", status="success", channel=channel)
        _log_endpoint(endpoint="analysis_start_phase2", status="success", channel=channel, user_id=payload.user_id)
        return AnalysisStartResponse(
            user_id=payload.user_id,
            analysis_run_id="",
            status="phase2_started",
            message="Other details analysis started.",
        )

    @router.post("/analysis/rerun", response_model=AnalysisStartResponse)
    def rerun_analysis(payload: AnalysisStartRequest) -> AnalysisStartResponse:
        try:
            status = service.get_status(payload.user_id)
        except (SupabaseError, RuntimeError) as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        if not status.get("onboarding_complete"):
            raise HTTPException(status_code=400, detail="Complete onboarding before re-running analysis.")

        try:
            run = analysis_service.force_analysis_restart(payload.user_id)
        except (SupabaseError, RuntimeError, ValueError) as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

        def run_job() -> None:
            try:
                analysis_service.run_analysis(payload.user_id)
            except Exception as exc:  # noqa: BLE001
                analysis_service.fail_analysis(payload.user_id, str(exc))

        Thread(target=run_job, daemon=True).start()

        return AnalysisStartResponse(
            user_id=payload.user_id,
            analysis_run_id=str(run.get("id") or ""),
            status=str(run.get("status") or "pending"),
            message="Analysis re-run started",
        )

    @router.post("/analysis/rerun-agent", response_model=AnalysisStartResponse)
    def rerun_analysis_agent(payload: AnalysisAgentRerunRequest) -> AnalysisStartResponse:
        try:
            status = service.get_status(payload.user_id)
        except (SupabaseError, RuntimeError) as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        if not status.get("onboarding_complete"):
            raise HTTPException(status_code=400, detail="Complete onboarding before re-running analysis.")

        try:
            run = analysis_service.force_agent_restart(payload.user_id, payload.agent_name)
        except (SupabaseError, RuntimeError, ValueError) as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

        def run_job() -> None:
            try:
                analysis_service.run_agent_rerun(
                    payload.user_id,
                    payload.agent_name,
                    run_id=str(run.get("id") or ""),
                )
            except Exception as exc:  # noqa: BLE001
                analysis_service.fail_analysis(payload.user_id, str(exc))

        Thread(target=run_job, daemon=True).start()

        return AnalysisStartResponse(
            user_id=payload.user_id,
            analysis_run_id=str(run.get("id") or ""),
            status=str(run.get("status") or "pending"),
            message=f"{payload.agent_name} re-run started",
        )

    @router.get("/analysis/{user_id}", response_model=AnalysisStatusResponse)
    def get_analysis_status(
        user_id: str,
        channel: str = Query("web", description="Caller channel label for metrics (web / vibe_storefront)."),
    ) -> AnalysisStatusResponse:
        try:
            status = analysis_service.get_analysis_status(user_id)
        except (SupabaseError, RuntimeError, ValueError) as exc:
            observe_onboarding_endpoint(endpoint="analysis_status_read", status="failed", channel=channel)
            _log_endpoint(endpoint="analysis_status_read", status="failed", channel=channel, user_id=user_id, error=str(exc))
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        # Carry the run's phase status in the log so percentile latency
        # (time-to-completion) can be computed from log-derived events
        # without joining to analysis_runs. The Prometheus counter only
        # tracks request volume.
        observe_onboarding_endpoint(endpoint="analysis_status_read", status="success", channel=channel)
        _log_endpoint(
            endpoint="analysis_status_read",
            status="success",
            channel=channel,
            user_id=user_id,
            analysis_status=str(status.get("status") or ""),
        )
        return AnalysisStatusResponse(**status)

    return router
