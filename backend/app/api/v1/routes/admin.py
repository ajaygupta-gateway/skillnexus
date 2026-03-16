"""Admin routes — assignments, analytics dashboard, skill gap analysis."""

import uuid

from fastapi import APIRouter, Query

from app.api.deps import AdminOrManager, AdminUser, DB
from app.schemas.analytics import (
    DashboardResponse,
    EmployeeProgressRow,
    RoadmapAnalyticsSummary,
    SkillGapEntry,
    UserAnalyticsResponse,
)
from app.schemas.base import MessageResponse
from app.schemas.progress import (
    AssignmentCreateRequest,
    AssignmentResponse,
    AssignmentUpdateRequest,
)
from app.services.progress_service import ProgressService

router = APIRouter(prefix="/admin", tags=["Administration"])


# ── Assignments ────────────────────────────────────────────────────────────────
@router.post("/assignments", response_model=list[AssignmentResponse], status_code=201)
async def create_assignments(
    data: AssignmentCreateRequest,
    current_user: AdminUser,
    db: DB,
):
    """
    Admin: Assign a roadmap to one or more users.
    Optionally enable strict_mode (requires quiz pass before marking done).
    """
    service = ProgressService(db)
    return await service.create_assignment(data, current_user)


@router.get("/assignments", response_model=dict)
async def list_assignments(
    _: AdminOrManager,
    db: DB,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    roadmap_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
):
    """Admin/Manager: List all assignments with optional filters."""
    service = ProgressService(db)
    return await service.get_assignments(
        page=page, page_size=page_size, roadmap_id=roadmap_id, user_id=user_id
    )


@router.patch("/assignments/{assignment_id}", response_model=AssignmentResponse)
async def update_assignment(
    assignment_id: uuid.UUID,
    data: AssignmentUpdateRequest,
    current_user: AdminUser,
    db: DB,
):
    """Admin: Update assignment (status, strict_mode toggle)."""
    service = ProgressService(db)
    return await service.update_assignment(assignment_id, data)


@router.delete("/assignments/{assignment_id}", response_model=MessageResponse)
async def delete_assignment(
    assignment_id: uuid.UUID,
    current_user: AdminUser,
    db: DB,
):
    """Admin: Remove a roadmap assignment from a user."""
    service = ProgressService(db)
    await service.delete_assignment(assignment_id)
    return MessageResponse(message="Assignment removed successfully")


# ── Analytics ──────────────────────────────────────────────────────────────────
@router.get("/analytics/dashboard", response_model=DashboardResponse)
async def get_dashboard(
    _: AdminOrManager,
    db: DB,
):
    """
    Admin/Manager: Get overview dashboard with:
    - Total learners, roadmaps, assignments
    - Active users this week
    - Per-roadmap completion stats
    """
    from sqlalchemy import func, select
    from app.models.models import Roadmap, User, UserRoadmapAssignment, PointTransaction
    from datetime import UTC, datetime, timedelta

    # Aggregate stats
    total_learners = (
        await db.execute(select(func.count(User.id)).where(User.is_active == True))
    ).scalar_one()

    total_roadmaps = (
        await db.execute(
            select(func.count(Roadmap.id)).where(Roadmap.is_deleted == False)
        )
    ).scalar_one()

    total_assignments = (
        await db.execute(select(func.count(UserRoadmapAssignment.id)))
    ).scalar_one()

    # Active this week: users who earned XP in last 7 days
    since = datetime.now(UTC) - timedelta(days=7)
    active_this_week = (
        await db.execute(
            select(func.count(func.distinct(PointTransaction.user_id))).where(
                PointTransaction.created_at >= since
            )
        )
    ).scalar_one()

    # Per-roadmap stats
    roadmaps_result = await db.execute(
        select(Roadmap).where(Roadmap.is_deleted == False, Roadmap.is_published == True)
    )
    roadmaps = roadmaps_result.scalars().all()

    roadmap_summaries = []
    for rm in roadmaps:
        assigned_count = (
            await db.execute(
                select(func.count(UserRoadmapAssignment.id)).where(
                    UserRoadmapAssignment.roadmap_id == rm.id
                )
            )
        ).scalar_one()

        avg_completion = (
            await db.execute(
                select(func.avg(UserRoadmapAssignment.completion_percentage)).where(
                    UserRoadmapAssignment.roadmap_id == rm.id
                )
            )
        ).scalar_one() or 0.0

        completed_count = (
            await db.execute(
                select(func.count(UserRoadmapAssignment.id)).where(
                    UserRoadmapAssignment.roadmap_id == rm.id,
                    UserRoadmapAssignment.completion_percentage >= 100.0,
                )
            )
        ).scalar_one()

        in_progress_count = assigned_count - completed_count

        last_activity = (
            await db.execute(
                select(func.max(UserRoadmapAssignment.last_active_at)).where(
                    UserRoadmapAssignment.roadmap_id == rm.id
                )
            )
        ).scalar_one()

        roadmap_summaries.append(
            RoadmapAnalyticsSummary(
                roadmap_id=rm.id,
                roadmap_title=rm.title,
                total_assigned=assigned_count,
                completed=completed_count,
                in_progress=in_progress_count,
                average_completion=round(float(avg_completion), 2),
                last_activity=last_activity,
            )
        )

    return DashboardResponse(
        total_learners=total_learners,
        total_roadmaps=total_roadmaps,
        total_assignments=total_assignments,
        active_this_week=active_this_week,
        roadmap_summaries=roadmap_summaries,
    )


@router.get("/analytics/skill-gaps", response_model=list[SkillGapEntry])
async def get_skill_gaps(
    roadmap_id: uuid.UUID,
    _: AdminOrManager,
    db: DB,
):
    """
    Admin/Manager: Per-node skill gap analysis.
    Shows what % of assigned users haven't started or completed each node.
    Example use: '50% of Frontend Team hasn't started the TypeScript node.'
    """
    from app.repositories.progress_repository import ProgressRepository
    from app.repositories.roadmap_repository import RoadmapRepository
    from app.core.exceptions import NotFoundException

    repo = ProgressRepository(db)
    roadmap_repo = RoadmapRepository(db)

    roadmap = await roadmap_repo.get_by_id(roadmap_id)
    if not roadmap:
        raise NotFoundException("Roadmap")

    gaps_data = await repo.get_skill_gaps(roadmap_id)
    return [
        SkillGapEntry(
            node_id=g["node_id"],
            node_title=g["node_title"],
            roadmap_id=g["roadmap_id"],
            roadmap_title=roadmap.title,
            total_assigned=g["total_assigned"],
            not_started=g["not_started"],
            in_progress=g["in_progress"],
            completed=g["completed"],
            not_started_percentage=g["not_started_percentage"],
        )
        for g in gaps_data
    ]


@router.get("/analytics/users/{user_id}", response_model=UserAnalyticsResponse)
async def get_user_analytics(
    user_id: uuid.UUID,
    _: AdminOrManager,
    db: DB,
):
    """Admin/Manager: Complete learner report — all assignments + per-node progress."""
    from app.core.exceptions import NotFoundException
    from app.repositories.user_repository import UserRepository
    from app.repositories.progress_repository import ProgressRepository

    user_repo = UserRepository(db)
    progress_repo = ProgressRepository(db)

    user = await user_repo.get_by_id(user_id)
    if not user:
        raise NotFoundException("User")

    assignments, _ = await progress_repo.get_all_assignments(user_id=user_id, limit=100)

    from app.repositories.roadmap_repository import RoadmapRepository
    roadmap_repo = RoadmapRepository(db)

    rows = []
    for a in assignments:
        roadmap = await roadmap_repo.get_by_id(a.roadmap_id)
        rows.append(
            EmployeeProgressRow(
                user_id=user.id,
                display_name=user.display_name,
                email=user.email,
                assigned_roadmap=roadmap.title if roadmap else "Unknown",
                roadmap_id=a.roadmap_id,
                completion_percentage=a.completion_percentage,
                status=a.status,
                last_active_at=a.last_active_at,
                assigned_at=a.assigned_at,
            )
        )

    return UserAnalyticsResponse(
        user_id=user.id,
        display_name=user.display_name,
        email=user.email,
        xp_balance=user.xp_balance,
        level=user.level,
        streak_count=user.streak_count,
        assignments=rows,
    )


# ── Roadmap Requests ───────────────────────────────────────────────────────────
from app.models.models import RoadmapRequest

@router.get("/roadmap-requests", response_model=list[dict])
async def get_roadmap_requests(
    _: AdminOrManager,
    db: DB,
):
    """Admin/Manager: Get all pending user roadmap requests."""
    from sqlalchemy import select
    from app.models.models import User
    
    # Query requests joining with users to get email
    stmt = select(RoadmapRequest, User).join(User, RoadmapRequest.user_id == User.id).where(
        RoadmapRequest.status == "pending"
    ).order_by(RoadmapRequest.created_at.desc())
    
    results = await db.execute(stmt)
    
    response = []
    for req, user in results:
        response.append({
            "id": req.id,
            "user_id": req.user_id,
            "title": req.title,
            "status": req.status,
            "created_at": req.created_at,
            "user_email": user.email,
            "user_name": user.display_name,
        })
        
    return response

@router.patch("/roadmap-requests/{request_id}", response_model=MessageResponse)
async def update_roadmap_request(
    request_id: uuid.UUID,
    data: dict,
    _: AdminOrManager,
    db: DB,
):
    """Admin/Manager: Update status of a roadmap request (e.g. fulfilled or rejected)."""
    from app.core.exceptions import NotFoundException
    
    req = await db.get(RoadmapRequest, request_id)
    if not req:
        raise NotFoundException("Roadmap Request")
        
    if "status" in data:
        req.status = data["status"]
        
    await db.commit()
    return MessageResponse(message="Request updated successfully")
