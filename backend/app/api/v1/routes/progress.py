"""Progress routes — node status updates and assignment progress."""

import uuid

from fastapi import APIRouter

from app.api.deps import CurrentUser, DB
from app.schemas.base import MessageResponse
from app.schemas.progress import (
    AssignmentResponse,
    NodeProgressResponse,
    NodeProgressUpdateRequest,
    RoadmapProgressSummary,
)
from app.services.progress_service import ProgressService

router = APIRouter(prefix="/progress", tags=["Progress"])


@router.get("/roadmaps/{roadmap_id}", response_model=RoadmapProgressSummary)
async def get_roadmap_progress(
    roadmap_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
):
    """Get the authenticated user's progress summary for a roadmap."""
    service = ProgressService(db)
    return await service.get_roadmap_progress(current_user.id, roadmap_id)


@router.post("/roadmaps/{roadmap_id}/enroll", response_model=AssignmentResponse)
async def enroll_roadmap(
    roadmap_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
):
    """Self-enroll in a roadmap. Sets first node to in_progress."""
    service = ProgressService(db)
    return await service.enroll_roadmap(current_user.id, roadmap_id)


@router.post(
    "/roadmaps/{roadmap_id}/nodes/{node_id}",
    response_model=NodeProgressResponse,
)
async def update_node_progress(
    roadmap_id: uuid.UUID,
    node_id: uuid.UUID,
    data: NodeProgressUpdateRequest,
    current_user: CurrentUser,
    db: DB,
):
    """
    Update node status: 'in_progress' or 'done'.

    Security: User must be assigned to this roadmap.
    Strict Mode: 'done' only allowed if quiz has been passed.
    """
    service = ProgressService(db)
    return await service.update_node_progress(
        user_id=current_user.id,
        roadmap_id=roadmap_id,
        node_id=node_id,
        new_status=data.status,
        bypass_quiz=data.bypass_quiz,
    )


@router.get(
    "/roadmaps/{roadmap_id}/nodes/{node_id}",
    response_model=NodeProgressResponse | None,
)
async def get_node_progress(
    roadmap_id: uuid.UUID,
    node_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
):
    """Get progress status for a specific node."""
    service = ProgressService(db)
    return await service.get_node_progress(current_user.id, roadmap_id, node_id)
