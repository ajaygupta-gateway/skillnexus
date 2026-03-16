"""Roadmap routes — CRUD for roadmaps and nodes, plus AI generator."""

import uuid

from fastapi import APIRouter, Query

from app.api.deps import AdminUser, CurrentUser, DB, OptionalUser
from app.schemas.base import MessageResponse
from app.schemas.roadmap import (
    GenerateRoadmapRequest,
    NodeCreateRequest,
    NodeResponse,
    NodeUpdateRequest,
    RoadmapCreateRequest,
    RoadmapDetailResponse,
    RoadmapListResponse,
    RoadmapUpdateRequest,
)
from app.services.ai_roadmap_generator import AIRoadmapGeneratorService
from app.services.roadmap_service import RoadmapService

router = APIRouter(prefix="/roadmaps", tags=["Roadmaps"])


# ── Roadmap CRUD ───────────────────────────────────────────────────────────────
@router.post("", response_model=RoadmapDetailResponse, status_code=201)
async def create_roadmap(
    data: RoadmapCreateRequest,
    current_user: AdminUser,
    db: DB,
):
    """Admin: Create a new roadmap."""
    service = RoadmapService(db)
    roadmap = await service.create_roadmap(data, current_user)
    return await service.get_roadmap_detail(roadmap.id, current_user)


@router.get("", response_model=dict)
async def list_roadmaps(
    current_user: OptionalUser,
    db: DB,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """List roadmaps. Admins see unpublished; learners see published only."""
    service = RoadmapService(db)
    return await service.get_roadmaps(page=page, page_size=page_size, current_user=current_user)


@router.get("/{roadmap_id}", response_model=RoadmapDetailResponse)
async def get_roadmap(
    roadmap_id: uuid.UUID,
    current_user: OptionalUser,
    db: DB,
    include_progress: bool = Query(False),
):
    """Get full roadmap with nested node tree. Optionally include user progress overlays."""
    service = RoadmapService(db)
    return await service.get_roadmap_detail(
        roadmap_id,
        current_user=current_user,
        include_user_progress=include_progress and current_user is not None,
    )


@router.patch("/{roadmap_id}", response_model=RoadmapDetailResponse)
async def update_roadmap(
    roadmap_id: uuid.UUID,
    data: RoadmapUpdateRequest,
    current_user: AdminUser,
    db: DB,
):
    """Admin: Update roadmap metadata."""
    service = RoadmapService(db)
    await service.update_roadmap(roadmap_id, data, current_user)
    return await service.get_roadmap_detail(roadmap_id, current_user)


@router.delete("/{roadmap_id}", response_model=MessageResponse)
async def delete_roadmap(
    roadmap_id: uuid.UUID,
    current_user: AdminUser,
    db: DB,
):
    """Admin: Soft-delete a roadmap (unpublish and hide)."""
    service = RoadmapService(db)
    await service.delete_roadmap(roadmap_id, current_user)
    return MessageResponse(message="Roadmap deleted successfully")


@router.post("/{roadmap_id}/publish", response_model=RoadmapDetailResponse)
async def publish_roadmap(
    roadmap_id: uuid.UUID,
    current_user: AdminUser,
    db: DB,
):
    """Admin: Publish a roadmap (makes it visible to learners)."""
    service = RoadmapService(db)
    await service.publish_roadmap(roadmap_id)
    return await service.get_roadmap_detail(roadmap_id, current_user)


# ── Node CRUD ──────────────────────────────────────────────────────────────────
@router.post("/{roadmap_id}/nodes", response_model=NodeResponse, status_code=201)
async def add_node(
    roadmap_id: uuid.UUID,
    data: NodeCreateRequest,
    current_user: AdminUser,
    db: DB,
):
    """Admin: Add a node to a roadmap (with optional parent_id for hierarchy)."""
    service = RoadmapService(db)
    node = await service.add_node(roadmap_id, data)
    return NodeResponse(
        id=node.id,
        roadmap_id=node.roadmap_id,
        parent_id=node.parent_id,
        title=node.title,
        description=node.description,
        resources=node.resources,
        position_x=node.position_x,
        position_y=node.position_y,
        order_index=node.order_index,
        created_at=node.created_at,
        updated_at=node.updated_at,
    )


@router.patch("/{roadmap_id}/nodes/{node_id}", response_model=NodeResponse)
async def update_node(
    roadmap_id: uuid.UUID,
    node_id: uuid.UUID,
    data: NodeUpdateRequest,
    current_user: AdminUser,
    db: DB,
):
    """Admin: Update node content, resources, or position."""
    service = RoadmapService(db)
    node = await service.update_node(roadmap_id, node_id, data)
    return NodeResponse(
        id=node.id,
        roadmap_id=node.roadmap_id,
        parent_id=node.parent_id,
        title=node.title,
        description=node.description,
        resources=node.resources,
        position_x=node.position_x,
        position_y=node.position_y,
        order_index=node.order_index,
        created_at=node.created_at,
        updated_at=node.updated_at,
    )


@router.delete("/{roadmap_id}/nodes/{node_id}", response_model=MessageResponse)
async def delete_node(
    roadmap_id: uuid.UUID,
    node_id: uuid.UUID,
    current_user: AdminUser,
    db: DB,
):
    """Admin: Delete a node (cascades to all children)."""
    service = RoadmapService(db)
    await service.delete_node(roadmap_id, node_id)
    return MessageResponse(message="Node deleted successfully")


# ── AI Roadmap Generator (Bonus) ───────────────────────────────────────────────
@router.post("/generate", response_model=RoadmapDetailResponse, status_code=201)
async def generate_roadmap_with_ai(
    data: GenerateRoadmapRequest,
    current_user: AdminUser,
    db: DB,
):
    """
    Admin Bonus: Generate a complete roadmap using AI.
    Provide a natural language prompt like: 'Create a roadmap for Senior Java Developer'
    """
    service = AIRoadmapGeneratorService(db)
    return await service.generate_and_save(data, current_user)


# ── Roadmap Requests ───────────────────────────────────────────────────────────
from app.models.models import RoadmapRequest
from app.schemas.roadmap import RoadmapRequestCreate, RoadmapRequestResponse

@router.post("/request", response_model=RoadmapRequestResponse, status_code=201)
async def request_roadmap(
    data: RoadmapRequestCreate,
    current_user: CurrentUser,
    db: DB,
):
    """Learner: Request a new learning roadmap by title."""
    req = RoadmapRequest(
        user_id=current_user.id,
        title=data.title,
    )
    db.add(req)
    await db.flush()
    await db.refresh(req)

    return RoadmapRequestResponse(
        id=req.id,
        user_id=req.user_id,
        title=req.title,
        status=req.status,
        created_at=req.created_at,
        user_name=current_user.display_name,
        user_email=current_user.email,
    )
