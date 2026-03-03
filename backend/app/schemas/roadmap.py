import uuid
from datetime import datetime
from typing import Any

from pydantic import Field, HttpUrl, field_validator

from app.schemas.base import BaseSchema, UUIDMixin


# ── Resource (link inside a node) ──────────────────────────────────────────────
class NodeResource(BaseSchema):
    title: str = Field(min_length=1, max_length=200)
    url: str = Field(min_length=1)
    type: str = Field(default="article")  # article | video | docs | course


# ── Node Schemas ───────────────────────────────────────────────────────────────
class NodeCreateRequest(BaseSchema):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None
    parent_id: uuid.UUID | None = None
    resources: list[NodeResource] = Field(default_factory=list)
    position_x: float = 0.0
    position_y: float = 0.0
    order_index: int = 0


class NodeUpdateRequest(BaseSchema):
    title: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = None
    resources: list[NodeResource] | None = None
    position_x: float | None = None
    position_y: float | None = None
    order_index: int | None = None
    parent_id: uuid.UUID | None = None


class NodeResponse(UUIDMixin, BaseSchema):
    roadmap_id: uuid.UUID
    parent_id: uuid.UUID | None
    title: str
    description: str | None
    resources: list[dict] | None
    position_x: float
    position_y: float
    order_index: int
    created_at: datetime
    updated_at: datetime


class NodeTreeResponse(NodeResponse):
    """Node with its children nested recursively (built from adjacency list via CTE)."""
    children: list["NodeTreeResponse"] = Field(default_factory=list)
    # User-specific progress (injected by service layer when user is authenticated)
    user_status: str | None = None  # locked | in_progress | done


NodeTreeResponse.model_rebuild()  # Required for self-referential models in Pydantic v2


# ── Roadmap Schemas ────────────────────────────────────────────────────────────
class RoadmapCreateRequest(BaseSchema):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None


class RoadmapUpdateRequest(BaseSchema):
    title: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = None
    is_published: bool | None = None


class RoadmapListResponse(UUIDMixin, BaseSchema):
    title: str
    description: str | None
    is_published: bool
    created_at: datetime
    updated_at: datetime
    node_count: int = 0
    creator_name: str | None = None


class RoadmapDetailResponse(RoadmapListResponse):
    """Full roadmap with nested node tree."""
    nodes: list[NodeTreeResponse] = Field(default_factory=list)


# ── AI Roadmap Generator ───────────────────────────────────────────────────────
class GenerateRoadmapRequest(BaseSchema):
    prompt: str = Field(
        min_length=10,
        max_length=500,
        description='e.g. "Create a roadmap for Senior Java Developer"',
    )
    publish_immediately: bool = False
