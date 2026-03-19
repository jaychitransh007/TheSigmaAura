from datetime import date
from typing import Any, Dict, List, Literal, Optional

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

ImageCategory = Literal["full_body", "headshot"]
WardrobeSource = Literal["onboarding", "chat", "manual", "inferred"]

FIXED_OTP = "123456"
AnalysisAgentName = Literal[
    "body_type_analysis",
    "color_analysis_headshot",
    "other_details_analysis",
]


class SendOtpRequest(BaseModel):
    mobile: str = Field(min_length=10, max_length=15, pattern=r"^\+?\d{10,15}$")


class SendOtpResponse(BaseModel):
    success: bool
    message: str


class VerifyOtpRequest(BaseModel):
    mobile: str = Field(min_length=10, max_length=15)
    otp: str = Field(min_length=6, max_length=6)
    acquisition_source: str = Field(default="unknown", max_length=80)
    acquisition_campaign: str = Field(default="", max_length=120)
    referral_code: str = Field(default="", max_length=120)
    icp_tag: str = Field(default="", max_length=120)


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
    acquisition_source: str = "unknown"
    acquisition_campaign: str = ""
    referral_code: str = ""
    icp_tag: str = ""
    profile_complete: bool = False
    images_uploaded: List[str] = Field(default_factory=list)
    style_preference_complete: bool = False
    onboarding_complete: bool = False
    wardrobe_item_count: int = 0


class WardrobeItemResponse(BaseModel):
    id: str = ""
    user_id: str
    source: WardrobeSource
    title: str = ""
    description: str = ""
    image_url: str = ""
    image_path: str = ""
    garment_category: str = ""
    garment_subtype: str = ""
    primary_color: str = ""
    secondary_color: str = ""
    pattern_type: str = ""
    formality_level: str = ""
    occasion_fit: str = ""
    brand: str = ""
    notes: str = ""
    metadata_json: Dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True
    created_at: str = ""
    updated_at: str = ""


class WardrobeItemListResponse(BaseModel):
    user_id: str
    count: int = 0
    items: List[WardrobeItemResponse] = Field(default_factory=list)


class StyleArchetypeImage(BaseModel):
    id: str
    gender: Literal["male", "female"]
    primaryArchetype: str
    secondaryArchetype: Optional[str] = None
    imageType: Literal["pure", "blend", "context"]
    intensity: Literal["restrained", "moderate", "bold"]
    context: Literal["neutral", "casual", "elevated"]
    imageUrl: str
    position: Optional[int] = None


class StyleArchetypeSessionResponse(BaseModel):
    user_id: str
    gender: Literal["male", "female"]
    layer1: List[StyleArchetypeImage] = Field(default_factory=list)
    pool: List[StyleArchetypeImage] = Field(default_factory=list)
    adjacency: Dict[str, Dict[str, str]] = Field(default_factory=dict)
    minSelections: int = 3
    maxSelections: int = 5


class StyleSelectionEventRequest(BaseModel):
    image: Dict[str, Any]
    layer: Literal[1, 2, 3]
    position: Optional[int] = None
    selectionOrder: int = Field(ge=1, le=5)


class StylePreferenceCompleteRequest(BaseModel):
    user_id: str = Field(min_length=1)
    shown_images: List[Dict[str, Any]] = Field(default_factory=list, min_length=8)
    selections: List[StyleSelectionEventRequest] = Field(min_length=3, max_length=5)


class StylePreferenceResponse(BaseModel):
    user_id: str
    saved: bool
    style_preference: dict = Field(default_factory=dict)


class AnalysisStartRequest(BaseModel):
    user_id: str = Field(min_length=1)


class AnalysisAgentRerunRequest(BaseModel):
    user_id: str = Field(min_length=1)
    agent_name: AnalysisAgentName


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
