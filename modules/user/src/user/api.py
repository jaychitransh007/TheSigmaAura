from pathlib import Path
from threading import Thread

from fastapi import APIRouter, File, Form, HTTPException, Response, UploadFile
from fastapi.responses import FileResponse

from platform_core.supabase_rest import SupabaseError

from .schemas import (
    AnalysisAgentRerunRequest,
    AnalysisStartRequest,
    AnalysisStartResponse,
    AnalysisStatusResponse,
    ImageCategory,
    ImageUploadResponse,
    OnboardingStatusResponse,
    ProfileRequest,
    ProfileResponse,
    SendOtpRequest,
    SendOtpResponse,
    StyleArchetypeSessionResponse,
    StylePreferenceCompleteRequest,
    StylePreferenceResponse,
    VerifyOtpRequest,
    VerifyOtpResponse,
    WardrobeItemListResponse,
    WardrobeItemResponse,
)
from .service import OnboardingService
from .analysis import UserAnalysisService
from .style_archetype import resolve_style_asset_file


def create_onboarding_router(service: OnboardingService, analysis_service: UserAnalysisService) -> APIRouter:
    router = APIRouter(prefix="/v1/onboarding", tags=["onboarding"])

    @router.get("/style-assets/choices/{filename}", include_in_schema=False)
    def get_style_archetype_asset(filename: str) -> FileResponse:
        asset_path = resolve_style_asset_file(filename)
        if asset_path is None:
            raise HTTPException(status_code=404, detail="Style archetype image not found.")
        return FileResponse(path=Path(asset_path), media_type="image/png")

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
    ) -> ImageUploadResponse:
        if not file.content_type or not file.content_type.startswith("image/"):
            raise HTTPException(status_code=400, detail="File must be an image")
        data = file.file.read()
        if len(data) > 10 * 1024 * 1024:
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
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except (SupabaseError, RuntimeError) as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        if result is None:
            raise HTTPException(status_code=404, detail="User not found")
        encrypted_filename, file_path = result
        return ImageUploadResponse(
            user_id=user_id,
            category=category,
            saved=True,
            encrypted_filename=encrypted_filename,
            file_path=file_path,
        )

    @router.get("/status/{user_id}", response_model=OnboardingStatusResponse)
    def get_status(user_id: str) -> OnboardingStatusResponse:
        try:
            status = service.get_status(user_id)
        except (SupabaseError, RuntimeError) as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return OnboardingStatusResponse(**status)

    @router.get("/style/session/{user_id}", response_model=StyleArchetypeSessionResponse)
    def get_style_session(user_id: str) -> StyleArchetypeSessionResponse:
        try:
            session = service.get_style_archetype_session(user_id)
        except (SupabaseError, RuntimeError, ValueError) as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        if not session:
            raise HTTPException(status_code=404, detail="User not found.")
        return StyleArchetypeSessionResponse(**session)

    @router.get("/wardrobe/{user_id}", response_model=WardrobeItemListResponse)
    def get_wardrobe_items(user_id: str) -> WardrobeItemListResponse:
        try:
            out = service.list_wardrobe_items(user_id)
        except (SupabaseError, RuntimeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return WardrobeItemListResponse(**out)

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

    @router.post("/style/complete", response_model=StylePreferenceResponse)
    def save_style_preference(payload: StylePreferenceCompleteRequest) -> StylePreferenceResponse:
        try:
            out = service.save_style_preference(
                user_id=payload.user_id,
                shown_images=payload.shown_images,
                selections=[item.model_dump() for item in payload.selections],
            )
        except (SupabaseError, RuntimeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if not out:
            raise HTTPException(status_code=404, detail="User not found.")
        return StylePreferenceResponse(user_id=payload.user_id, saved=True, style_preference=out)

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

        if str(run.get("status")) == "pending":
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
            message="Analysis started" if str(run.get("status") or "pending") == "pending" else "Analysis already in progress or complete",
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
    def get_analysis_status(user_id: str) -> AnalysisStatusResponse:
        try:
            status = analysis_service.get_analysis_status(user_id)
        except (SupabaseError, RuntimeError, ValueError) as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return AnalysisStatusResponse(**status)

    return router
