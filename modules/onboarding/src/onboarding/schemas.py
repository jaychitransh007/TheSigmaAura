from datetime import date
from typing import List, Literal

from pydantic import BaseModel, Field


Gender = Literal["male", "female", "non_binary", "prefer_not_to_say"]

Profession = Literal[
    "software_engineer",
    "doctor",
    "lawyer",
    "teacher",
    "designer",
    "architect",
    "business_finance",
    "marketing",
    "artist",
    "student",
    "entrepreneur",
    "homemaker",
    "other",
]

ImageCategory = Literal["full_body", "headshot", "veins"]

FIXED_OTP = "123456"


class SendOtpRequest(BaseModel):
    mobile: str = Field(min_length=10, max_length=15, pattern=r"^\+?\d{10,15}$")


class SendOtpResponse(BaseModel):
    success: bool
    message: str


class VerifyOtpRequest(BaseModel):
    mobile: str = Field(min_length=10, max_length=15)
    otp: str = Field(min_length=6, max_length=6)


class VerifyOtpResponse(BaseModel):
    verified: bool
    user_id: str = ""
    message: str = ""


class ProfileRequest(BaseModel):
    user_id: str = Field(min_length=1)
    name: str = Field(min_length=1, max_length=100)
    date_of_birth: date
    gender: Gender
    height_cm: float = Field(ge=50, le=300)
    waist_cm: float = Field(ge=30, le=200)
    profession: Profession


class ProfileResponse(BaseModel):
    user_id: str
    saved: bool
    message: str = ""


class ImageUploadResponse(BaseModel):
    user_id: str
    category: ImageCategory
    saved: bool
    encrypted_filename: str = ""
    file_path: str = ""
    message: str = ""


class OnboardingStatusResponse(BaseModel):
    user_id: str
    mobile: str = ""
    profile_complete: bool = False
    images_uploaded: List[str] = Field(default_factory=list)
    onboarding_complete: bool = False


class AnalysisStartRequest(BaseModel):
    user_id: str = Field(min_length=1)


class AnalysisStartResponse(BaseModel):
    user_id: str
    analysis_run_id: str = ""
    status: str
    message: str = ""


class AnalysisStatusResponse(BaseModel):
    user_id: str
    analysis_run_id: str = ""
    status: str
    error_message: str = ""
    profile: dict = Field(default_factory=dict)
    agent_outputs: dict = Field(default_factory=dict)
    attributes: dict = Field(default_factory=dict)
    grouped_attributes: dict = Field(default_factory=dict)
    derived_interpretations: dict = Field(default_factory=dict)
