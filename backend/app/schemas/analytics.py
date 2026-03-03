import uuid
from datetime import datetime

from pydantic import Field

from app.schemas.base import BaseSchema, UUIDMixin


# ── Analytics ──────────────────────────────────────────────────────────────────
class EmployeeProgressRow(BaseSchema):
    user_id: uuid.UUID
    display_name: str
    email: str
    assigned_roadmap: str
    roadmap_id: uuid.UUID
    completion_percentage: float
    status: str
    last_active_at: datetime | None
    assigned_at: datetime


class SkillGapEntry(BaseSchema):
    node_id: uuid.UUID
    node_title: str
    roadmap_id: uuid.UUID
    roadmap_title: str
    total_assigned: int
    not_started: int
    in_progress: int
    completed: int
    not_started_percentage: float


class RoadmapAnalyticsSummary(BaseSchema):
    roadmap_id: uuid.UUID
    roadmap_title: str
    total_assigned: int
    completed: int
    in_progress: int
    average_completion: float
    last_activity: datetime | None


class DashboardResponse(BaseSchema):
    total_learners: int
    total_roadmaps: int
    total_assignments: int
    active_this_week: int
    roadmap_summaries: list[RoadmapAnalyticsSummary]


class UserAnalyticsResponse(BaseSchema):
    user_id: uuid.UUID
    display_name: str
    email: str
    xp_balance: int
    level: int
    streak_count: int
    assignments: list[EmployeeProgressRow]
