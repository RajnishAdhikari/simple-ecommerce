import re
import os
from typing import Optional
from urllib.parse import urlparse

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator


USERNAME_PATTERN = r"^[A-Za-z0-9_]{3,30}$"
SAFE_TEXT_PATTERN = re.compile(r"^[^\x00-\x1f\x7f<>]*$")


def normalize_optional_text(value):
    if value is None:
        return None
    if not isinstance(value, str):
        return value

    cleaned = " ".join(value.strip().split())
    if not cleaned:
        return None
    if not SAFE_TEXT_PATTERN.fullmatch(cleaned):
        raise ValueError("must not contain HTML tags or control characters")
    return cleaned


def normalize_required_text(value):
    cleaned = normalize_optional_text(value)
    if cleaned is None:
        raise ValueError("value is required")
    return cleaned


def normalize_text_list(value):
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("must be a list")
    if len(value) > 24:
        raise ValueError("must contain 24 or fewer values")

    normalized = []
    seen = set()
    for item in value:
        cleaned = normalize_required_text(item)
        if len(cleaned) > 120:
            raise ValueError("list values must be 120 characters or fewer")
        key = cleaned.lower()
        if key not in seen:
            normalized.append(cleaned)
            seen.add(key)

    return normalized


class RegisterRequest(BaseModel):
    email: EmailStr
    username: str = Field(min_length=3, max_length=30, pattern=USERNAME_PATTERN)
    full_name: str = Field(min_length=2, max_length=100)
    password: str = Field(min_length=10, max_length=72)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=72)


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict


class AddCartItemRequest(BaseModel):
    product_id: int
    quantity: int = Field(default=1, ge=1, le=20)
    size: Optional[str] = Field(default=None, max_length=30)
    color: Optional[str] = Field(default=None, max_length=30)


class UpdateCartItemRequest(BaseModel):
    quantity: int = Field(ge=1, le=20)


class CheckoutRequest(BaseModel):
    shipping_address: str = Field(min_length=6, max_length=255)


class TrackViewRequest(BaseModel):
    product_id: int


class ProductContentRequest(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    category: Optional[str] = Field(default=None, max_length=120)
    product_type: Optional[str] = Field(default=None, max_length=120)
    brand: Optional[str] = Field(default=None, max_length=120)
    description: Optional[str] = Field(default=None, max_length=900)
    price: Optional[float] = Field(default=None, gt=0, le=999999)
    original_price: Optional[float] = Field(default=None, gt=0, le=999999)
    currency: str = Field(default="USD", min_length=3, max_length=3, pattern=r"^[A-Z]{3}$")
    colors: list[str] = Field(default_factory=list)
    sizes: list[str] = Field(default_factory=list)
    material: Optional[str] = Field(default=None, max_length=180)
    pattern: Optional[str] = Field(default=None, max_length=120)
    condition: Optional[str] = Field(default=None, max_length=80)
    age_group: Optional[str] = Field(default=None, max_length=80)
    gender: Optional[str] = Field(default=None, max_length=80)
    size_type: Optional[str] = Field(default=None, max_length=80)
    size_system: Optional[str] = Field(default=None, max_length=80)
    dimensions: Optional[str] = Field(default=None, max_length=180)
    weight: Optional[str] = Field(default=None, max_length=120)
    origin: Optional[str] = Field(default=None, max_length=120)
    handmade: Optional[bool] = None
    ingredients: Optional[str] = Field(default=None, max_length=500)
    dietary_info: Optional[str] = Field(default=None, max_length=220)
    shelf_life: Optional[str] = Field(default=None, max_length=160)
    storage_instructions: Optional[str] = Field(default=None, max_length=260)
    fit: Optional[str] = Field(default=None, max_length=180)
    care_instructions: Optional[str] = Field(default=None, max_length=260)
    craft_method: Optional[str] = Field(default=None, max_length=220)
    package_contents: list[str] = Field(default_factory=list)
    warranty: Optional[str] = Field(default=None, max_length=180)
    compatibility: Optional[str] = Field(default=None, max_length=220)
    usage: Optional[str] = Field(default=None, max_length=260)
    availability: Optional[str] = Field(default=None, max_length=160)
    features: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    details: dict[str, str] = Field(default_factory=dict)

    @field_validator(
        "name",
        "category",
        "product_type",
        "brand",
        "description",
        "material",
        "pattern",
        "condition",
        "age_group",
        "gender",
        "size_type",
        "size_system",
        "dimensions",
        "weight",
        "origin",
        "ingredients",
        "dietary_info",
        "shelf_life",
        "storage_instructions",
        "fit",
        "care_instructions",
        "craft_method",
        "warranty",
        "compatibility",
        "usage",
        "availability",
        mode="before",
    )
    @classmethod
    def normalize_text_fields(cls, value):
        return normalize_optional_text(value)

    @field_validator("colors", "sizes", "package_contents", "features", "tags", mode="before")
    @classmethod
    def normalize_list_fields(cls, value):
        return normalize_text_list(value)

    @field_validator("details", mode="before")
    @classmethod
    def normalize_custom_details(cls, value):
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise ValueError("must be an object")
        if len(value) > 24:
            raise ValueError("must contain 24 or fewer entries")

        normalized = {}
        for raw_key, raw_value in value.items():
            key = normalize_required_text(str(raw_key))
            detail_value = normalize_required_text(str(raw_value))
            if len(key) > 50:
                raise ValueError("detail keys must be 50 characters or fewer")
            if len(detail_value) > 220:
                raise ValueError("detail values must be 220 characters or fewer")
            normalized[key] = detail_value

        return normalized

    @model_validator(mode="after")
    def validate_price_range(self):
        if self.original_price is not None and self.price is not None and self.original_price < self.price:
            raise ValueError("original_price must be greater than or equal to price")
        return self


class AdminProductCreateRequest(ProductContentRequest):
    category: str = Field(min_length=2, max_length=120)
    price: float = Field(gt=0, le=999999)
    image: Optional[str] = Field(default=None, max_length=500, pattern=r"^https?://[^\s]+$")
    rating: float = Field(default=0.0, ge=0, le=5)
    reviews: int = Field(default=0, ge=0, le=10000000)
    badge: Optional[str] = Field(default=None, max_length=80)
    is_new: bool = False

    @field_validator("badge", mode="before")
    @classmethod
    def normalize_badge(cls, value):
        return normalize_optional_text(value)

    @field_validator("image")
    @classmethod
    def validate_image_host(cls, value):
        if value is None:
            return value

        allowed_hosts = {
            host.strip().lower()
            for host in os.getenv("IMAGE_ALLOWED_HOSTS", "images.unsplash.com").split(",")
            if host.strip()
        }
        hostname = (urlparse(value).hostname or "").lower()
        if not allowed_hosts or hostname not in allowed_hosts:
            raise ValueError("image host is not allowed")
        return value
