import uuid
from datetime import datetime

from pydantic import EmailStr, Field, field_validator

from app.models.models import UserRole
from app.schemas.base import BaseSchema, UUIDMixin


# ── Request Schemas ────────────────────────────────────────────────────────────
class UserRegisterRequest(BaseSchema):
    email: EmailStr
    password: str = Field(min_length=8, max_length=100)
    display_name: str = Field(min_length=2, max_length=100)
    role: UserRole = UserRole.learner

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        return v


class UserLoginRequest(BaseSchema):
    email: EmailStr
    password: str


class UserUpdateRequest(BaseSchema):
    display_name: str | None = Field(None, min_length=2, max_length=100)
    current_role_title: str | None = Field(None, max_length=150)


# ── Response Schemas ───────────────────────────────────────────────────────────
class UserPublicResponse(UUIDMixin, BaseSchema):
    email: str
    display_name: str
    role: str
    current_role_title: str | None
    xp_balance: int
    level: int
    streak_count: int
    is_active: bool
    created_at: datetime


class UserMeResponse(UserPublicResponse):
    last_login_date: datetime | None


class LeaderboardEntry(BaseSchema):
    rank: int
    user_id: uuid.UUID
    display_name: str
    xp_earned: int
    level: int


class LeaderboardResponse(BaseSchema):
    period: str  # "this_week" | "all_time"
    entries: list[LeaderboardEntry]


class PointTransactionResponse(UUIDMixin, BaseSchema):
    user_id: uuid.UUID
    amount: int
    event_type: str
    description: str | None
    reference_id: str | None
    created_at: datetime
