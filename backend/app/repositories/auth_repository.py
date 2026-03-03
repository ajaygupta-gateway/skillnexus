"""
Auth Repository — manages refresh tokens (stateful).
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import RefreshToken


class AuthRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_refresh_token(
        self,
        user_id: uuid.UUID,
        token_hash: str,
        expires_at: datetime,
    ) -> RefreshToken:
        token = RefreshToken(
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at,
        )
        self.db.add(token)
        await self.db.flush()
        return token

    async def get_by_hash(self, token_hash: str) -> RefreshToken | None:
        result = await self.db.execute(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        )
        return result.scalar_one_or_none()

    async def revoke_token(self, token: RefreshToken) -> None:
        token.revoked = True
        self.db.add(token)
        await self.db.flush()

    async def revoke_all_for_user(self, user_id: uuid.UUID) -> None:
        await self.db.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user_id, RefreshToken.revoked == False)
            .values(revoked=True)
        )
        await self.db.flush()

    async def is_valid(self, token: RefreshToken) -> bool:
        """Check that token is not revoked and not expired."""
        now = datetime.now(UTC)
        return (
            not token.revoked
            and token.expires_at.replace(tzinfo=UTC) > now
        )

    async def cleanup_expired(self) -> None:
        """Remove expired tokens (call periodically from a background task)."""
        now = datetime.now(UTC)
        from sqlalchemy import delete
        await self.db.execute(
            delete(RefreshToken).where(RefreshToken.expires_at < now)
        )
        await self.db.flush()
