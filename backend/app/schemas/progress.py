import uuid
from datetime import datetime

from pydantic import Field

from app.schemas.base import BaseSchema, UUIDMixin


# ── Progress ───────────────────────────────────────────────────────────────────
class NodeProgressUpdateRequest(BaseSchema):
    status: str = Field(pattern="^(in_progress|done)$")


class NodeProgressResponse(UUIDMixin, BaseSchema):
    user_id: uuid.UUID
    node_id: uuid.UUID
    roadmap_id: uuid.UUID
    status: str
    quiz_passed: bool
    completed_at: datetime | None
    updated_at: datetime


class RoadmapProgressSummary(BaseSchema):
    roadmap_id: uuid.UUID
    roadmap_title: str
    total_nodes: int
    completed_nodes: int
    in_progress_nodes: int
    completion_percentage: float
    node_statuses: list[NodeProgressResponse]


# ── Assignment ─────────────────────────────────────────────────────────────────
class AssignmentCreateRequest(BaseSchema):
    user_ids: list[uuid.UUID] = Field(min_length=1)
    roadmap_id: uuid.UUID
    strict_mode: bool = False


class AssignmentUpdateRequest(BaseSchema):
    status: str | None = Field(None, pattern="^(active|completed|archived)$")
    strict_mode: bool | None = None


class AssignmentResponse(UUIDMixin, BaseSchema):
    user_id: uuid.UUID
    roadmap_id: uuid.UUID
    assigned_by: uuid.UUID | None
    status: str
    completion_percentage: float
    strict_mode: bool
    assigned_at: datetime
    last_active_at: datetime | None

    # Enriched fields
    user_display_name: str | None = None
    roadmap_title: str | None = None
