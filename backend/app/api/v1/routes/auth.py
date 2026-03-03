"""Auth routes — register, login, refresh, logout."""

from fastapi import APIRouter

from app.api.deps import CurrentUser, DB
from app.schemas.auth import (
    AccessTokenResponse,
    LogoutRequest,
    RefreshTokenRequest,
    TokenResponse,
)
from app.schemas.base import MessageResponse
from app.schemas.user import UserLoginRequest, UserMeResponse, UserRegisterRequest
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", response_model=UserMeResponse, status_code=201)
async def register(data: UserRegisterRequest, db: DB):
    """Register a new user account."""
    service = AuthService(db)
    user = await service.register(data)
    return UserMeResponse(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        role=user.role,
        current_role_title=user.current_role_title,
        xp_balance=user.xp_balance,
        level=user.level,
        streak_count=user.streak_count,
        is_active=user.is_active,
        created_at=user.created_at,
        last_login_date=user.last_login_date,
    )


@router.post("/login", response_model=TokenResponse)
async def login(data: UserLoginRequest, db: DB):
    """Login with email and password. Returns access + refresh tokens."""
    service = AuthService(db)
    return await service.login(data.email, data.password)


@router.post("/refresh", response_model=AccessTokenResponse)
async def refresh_token(data: RefreshTokenRequest, db: DB):
    """Refresh access token using a valid refresh token (token is rotated)."""
    service = AuthService(db)
    return await service.refresh_access_token(data.refresh_token)


@router.post("/logout", response_model=MessageResponse)
async def logout(data: LogoutRequest, db: DB):
    """Logout: revoke the provided refresh token."""
    service = AuthService(db)
    await service.logout(data.refresh_token)
    return MessageResponse(message="Logged out successfully")


@router.post("/logout-all", response_model=MessageResponse)
async def logout_all_devices(current_user: CurrentUser, db: DB):
    """Logout from all devices: revoke ALL refresh tokens for the current user."""
    service = AuthService(db)
    await service.logout_all_devices(current_user.id)
    return MessageResponse(message="Logged out from all devices")


@router.get("/me", response_model=UserMeResponse)
async def get_me(current_user: CurrentUser):
    """Get the current authenticated user's profile."""
    return UserMeResponse(
        id=current_user.id,
        email=current_user.email,
        display_name=current_user.display_name,
        role=current_user.role,
        current_role_title=current_user.current_role_title,
        xp_balance=current_user.xp_balance,
        level=current_user.level,
        streak_count=current_user.streak_count,
        is_active=current_user.is_active,
        created_at=current_user.created_at,
        last_login_date=current_user.last_login_date,
    )
