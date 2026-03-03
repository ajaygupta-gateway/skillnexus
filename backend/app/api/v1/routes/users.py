"""User routes — profile, leaderboard, admin user management."""

import uuid

from fastapi import APIRouter, Query

from app.api.deps import AdminOrManager, AdminUser, CurrentUser, DB
from app.repositories.user_repository import UserRepository
from app.schemas.base import MessageResponse, PaginatedResponse
from app.schemas.user import (
    LeaderboardResponse,
    PointTransactionResponse,
    UserMeResponse,
    UserPublicResponse,
    UserUpdateRequest,
)

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("/me", response_model=UserMeResponse)
async def get_my_profile(current_user: CurrentUser):
    """Get the authenticated user's full profile including XP and streak."""
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


@router.patch("/me", response_model=UserMeResponse)
async def update_my_profile(data: UserUpdateRequest, current_user: CurrentUser, db: DB):
    """Update authenticated user's display name or current role title."""
    repo = UserRepository(db)
    updates = data.model_dump(exclude_none=True)
    user = await repo.update(current_user, **updates)
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


@router.get("/leaderboard", response_model=LeaderboardResponse)
async def get_leaderboard(
    db: DB,
    limit: int = Query(10, ge=1, le=50),
):
    """Get top learners this week by XP earned."""
    repo = UserRepository(db)
    entries_data = await repo.get_weekly_leaderboard(limit=limit)
    from app.schemas.user import LeaderboardEntry
    entries = [LeaderboardEntry(**e) for e in entries_data]
    return LeaderboardResponse(period="this_week", entries=entries)


@router.get("/me/transactions", response_model=list[PointTransactionResponse])
async def get_my_transactions(
    current_user: CurrentUser,
    db: DB,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    """Get the authenticated user's XP transaction history."""
    repo = UserRepository(db)
    transactions = await repo.get_point_transactions(current_user.id, skip=skip, limit=limit)
    return [
        PointTransactionResponse(
            id=t.id,
            user_id=t.user_id,
            amount=t.amount,
            event_type=t.event_type,
            description=t.description,
            reference_id=t.reference_id,
            created_at=t.created_at,
        )
        for t in transactions
    ]


# ── Admin endpoints ────────────────────────────────────────────────────────────
@router.get("", response_model=dict)
async def list_users(
    _: AdminOrManager,
    db: DB,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """Admin/Manager: list all users (paginated)."""
    repo = UserRepository(db)
    skip = (page - 1) * page_size
    users, total = await repo.get_all(skip=skip, limit=page_size)

    items = [
        UserPublicResponse(
            id=u.id,
            email=u.email,
            display_name=u.display_name,
            role=u.role,
            current_role_title=u.current_role_title,
            xp_balance=u.xp_balance,
            level=u.level,
            streak_count=u.streak_count,
            is_active=u.is_active,
            created_at=u.created_at,
        )
        for u in users
    ]
    pages = (total + page_size - 1) // page_size
    return {"items": [i.model_dump() for i in items], "total": total, "page": page, "page_size": page_size, "pages": pages}


@router.get("/{user_id}", response_model=UserPublicResponse)
async def get_user(user_id: uuid.UUID, _: AdminOrManager, db: DB):
    """Admin/Manager: view any user's public profile."""
    from app.core.exceptions import NotFoundException
    repo = UserRepository(db)
    user = await repo.get_by_id(user_id)
    if not user:
        raise NotFoundException("User")
    return UserPublicResponse(
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
    )
