"""
Auth Service — business logic for registration, login, token management.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    ConflictException,
    InvalidCredentialsException,
    InvalidTokenException,
    NotFoundException,
)
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    get_refresh_token_expiry,
    hash_password,
    hash_token,
    verify_password,
)
from app.models.models import User, UserRole
from app.repositories.auth_repository import AuthRepository
from app.repositories.user_repository import UserRepository
from app.schemas.auth import AccessTokenResponse, TokenResponse
from app.schemas.user import UserRegisterRequest


class AuthService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.user_repo = UserRepository(db)
        self.auth_repo = AuthRepository(db)

    async def register(self, data: UserRegisterRequest) -> User:
        # Check duplicate email
        existing = await self.user_repo.get_by_email(data.email)
        if existing:
            raise ConflictException("A user with this email already exists")

        hashed_pw = hash_password(data.password)
        user = await self.user_repo.create(
            email=data.email,
            hashed_password=hashed_pw,
            display_name=data.display_name,
            role=data.role,
        )
        return user

    async def login(self, email: str, password: str) -> TokenResponse:
        user = await self.user_repo.get_by_email(email)
        if not user or not verify_password(password, user.hashed_password):
            raise InvalidCredentialsException()
        if not user.is_active:
            raise InvalidCredentialsException()

        # Handle streak + XP for login (Learners only)
        if user.role == UserRole.learner:
            streak_result = await self.user_repo.update_streak(user)
            
            # Only award login XP if they haven't already logged in today
            if not streak_result.get("already_logged_in_today"):
                from app.models.models import PointEventType
                from app.core.config import settings
                await self.user_repo.add_xp(
                    user_id=user.id,
                    user_name=user.display_name,
                    amount=settings.XP_LOGIN,
                    event_type=PointEventType.login,
                    description="Daily login bonus",
                )
                # Award streak bonus if applicable
                if streak_result.get("streak_bonus_awarded"):
                    from app.core.config import settings
                    await self.user_repo.add_xp(
                        user_id=user.id,
                        user_name=user.display_name,
                        amount=settings.XP_STREAK_BONUS,
                        event_type=PointEventType.streak_bonus,
                        description=f"Streak bonus! {user.streak_count} day streak",
                    )
                
                # Refresh user to get updated XP for level calculation
                await self.db.refresh(user)

            await self.user_repo.update_level(user)

        # Build tokens
        token_data = {"sub": str(user.id), "email": user.email, "role": user.role}
        access_token = create_access_token(token_data)
        refresh_token = create_refresh_token(token_data)

        # Store hashed refresh token
        await self.auth_repo.create_refresh_token(
            user_id=user.id,
            token_hash=hash_token(refresh_token),
            expires_at=get_refresh_token_expiry(),
        )

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
        )

    async def refresh_access_token(self, refresh_token: str) -> AccessTokenResponse:
        # Decode token
        try:
            payload = decode_refresh_token(refresh_token)
        except Exception:
            raise InvalidTokenException("Invalid or expired refresh token")

        # Verify in DB
        token_hash = hash_token(refresh_token)
        stored = await self.auth_repo.get_by_hash(token_hash)
        if not stored:
            raise InvalidTokenException("Refresh token not found")
        if not await self.auth_repo.is_valid(stored):
            raise InvalidTokenException("Refresh token has been revoked or expired")

        # Rotate: revoke old, issue new
        await self.auth_repo.revoke_token(stored)

        user_id = uuid.UUID(payload["sub"])
        user = await self.user_repo.get_by_id(user_id)
        if not user or not user.is_active:
            raise InvalidTokenException("User not found or inactive")

        # Issue new refresh token (rotation)
        token_data = {"sub": str(user.id), "email": user.email, "role": user.role}
        new_access_token = create_access_token(token_data)
        new_refresh_token = create_refresh_token(token_data)

        await self.auth_repo.create_refresh_token(
            user_id=user.id,
            token_hash=hash_token(new_refresh_token),
            expires_at=get_refresh_token_expiry(),
        )

        # Return new access token (and the new refresh token in header or body)
        # For now, return both so the frontend can update stored tokens
        return AccessTokenResponse(access_token=new_access_token)

    async def logout(self, refresh_token: str) -> None:
        token_hash = hash_token(refresh_token)
        stored = await self.auth_repo.get_by_hash(token_hash)
        if stored:
            await self.auth_repo.revoke_token(stored)
        # No error if token not found — idempotent logout

    async def logout_all_devices(self, user_id: uuid.UUID) -> None:
        await self.auth_repo.revoke_all_for_user(user_id)
