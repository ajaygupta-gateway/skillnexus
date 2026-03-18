"""
User Repository — handles all DB queries related to users and points.
"""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import PointEventType, PointTransaction, User, UserRole


class UserRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        result = await self.db.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> User | None:
        result = await self.db.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def create(
        self,
        email: str,
        hashed_password: str,
        display_name: str,
        role: UserRole = UserRole.learner,
    ) -> User:
        user = User(
            email=email,
            hashed_password=hashed_password,
            display_name=display_name,
            role=role,
        )
        self.db.add(user)
        await self.db.flush()
        await self.db.refresh(user)
        return user

    async def update(self, user: User, **kwargs) -> User:
        for key, value in kwargs.items():
            if hasattr(user, key) and value is not None:
                setattr(user, key, value)
        self.db.add(user)
        await self.db.flush()
        await self.db.refresh(user)
        return user

    async def get_all(self, skip: int = 0, limit: int = 20) -> tuple[list[User], int]:
        count_stmt = select(func.count(User.id))
        total = (await self.db.execute(count_stmt)).scalar_one()

        stmt = select(User).order_by(User.created_at.desc()).offset(skip).limit(limit)
        result = await self.db.execute(stmt)
        return result.scalars().all(), total

    # ── Gamification ──────────────────────────────────────────────────────────
    async def add_xp(
        self,
        user_id: uuid.UUID,
        user_name: str,
        amount: int,
        event_type: PointEventType,
        description: str | None = None,
        reference_id: str | None = None,
    ) -> PointTransaction:
        """Append a XP event to ledger. xp_balance is a column_property — no separate update needed."""
        transaction = PointTransaction(
            user_id=user_id,
            user_name=user_name,
            amount=amount,
            event_type=event_type,
            description=description,
            reference_id=reference_id,
        )
        self.db.add(transaction)
        await self.db.flush()
        return transaction

    async def update_level(self, user: User) -> None:
        """
        Recalculate level from actual XP earned (every 500 XP = 1 level).
        
        We do NOT access user.xp_balance directly because it is a column_property
        (scalar subquery) that async SQLAlchemy cannot lazy-load — doing so raises
        MissingGreenlet. Instead we issue an explicit async SUM query.
        """
        result = await self.db.execute(
            select(func.coalesce(func.sum(PointTransaction.amount), 0))
            .where(PointTransaction.user_id == user.id)
        )
        total_xp: int = result.scalar_one()
        new_level = max(1, (total_xp // 500) + 1)
        if user.level != new_level:
            await self.db.execute(
                update(User).where(User.id == user.id).values(level=new_level)
            )
            await self.db.flush()

    async def update_streak(self, user: User) -> dict:
        """
        Check last login date and update streak.
        Returns dict with streak_updated and streak_bonus_awarded.
        """
        from app.core.config import settings

        now = datetime.now(UTC)
        streak_bonus_awarded = False
        already_logged_in_today = False

        if user.last_login_date:
            last = user.last_login_date.replace(tzinfo=UTC)
            days_diff = (now.date() - last.date()).days

            if days_diff == 0:
                # Already logged in today
                already_logged_in_today = True
            elif days_diff == 1:
                # Consecutive day — increment streak
                user.streak_count += 1
                if user.streak_count > 0 and user.streak_count % settings.STREAK_THRESHOLD_DAYS == 0:
                    streak_bonus_awarded = True
            else:
                # Streak broken or first login after a while
                user.streak_count = 1
        else:
            user.streak_count = 1

        user.last_login_date = now
        self.db.add(user)
        await self.db.flush()
        return {
            "streak_bonus_awarded": streak_bonus_awarded,
            "already_logged_in_today": already_logged_in_today,
        }

    # ── Leaderboard ───────────────────────────────────────────────────────────
    async def get_weekly_leaderboard(self, limit: int = 10) -> list[dict]:
        """Top N users by XP earned in the last 7 days."""
        since = datetime.now(UTC) - timedelta(days=7)
        stmt = (
            select(
                User.id,
                User.display_name,
                User.level,
                func.sum(PointTransaction.amount).label("xp_earned"),
            )
            .join(PointTransaction, PointTransaction.user_id == User.id)
            .where(PointTransaction.created_at >= since)
            .group_by(User.id, User.display_name, User.level)
            .order_by(func.sum(PointTransaction.amount).desc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        rows = result.all()
        return [
            {
                "rank": i + 1,
                "user_id": row.id,
                "display_name": row.display_name,
                "xp_earned": row.xp_earned or 0,
                "level": row.level,
            }
            for i, row in enumerate(rows)
        ]

    async def get_point_transactions(
        self, user_id: uuid.UUID, skip: int = 0, limit: int = 50
    ) -> list[PointTransaction]:
        stmt = (
            select(PointTransaction)
            .where(PointTransaction.user_id == user_id)
            .order_by(PointTransaction.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return result.scalars().all()
