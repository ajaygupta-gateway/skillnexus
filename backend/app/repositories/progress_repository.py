"""
Progress Repository — tracks node-level progress and roadmap assignments.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import (
    AssignmentStatus,
    NodeStatus,
    RoadmapNode,
    UserNodeProgress,
    UserRoadmapAssignment,
)


class ProgressRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ── Assignment ─────────────────────────────────────────────────────────────
    async def create_assignment(
        self,
        user_id: uuid.UUID,
        roadmap_id: uuid.UUID,
        assigned_by: uuid.UUID | None = None,
        strict_mode: bool = False,
    ) -> UserRoadmapAssignment:
        assignment = UserRoadmapAssignment(
            user_id=user_id,
            roadmap_id=roadmap_id,
            assigned_by=assigned_by,
            strict_mode=strict_mode,
        )
        self.db.add(assignment)
        await self.db.flush()
        await self.db.refresh(assignment)
        return assignment

    async def get_assignment(
        self, user_id: uuid.UUID, roadmap_id: uuid.UUID
    ) -> UserRoadmapAssignment | None:
        result = await self.db.execute(
            select(UserRoadmapAssignment).where(
                UserRoadmapAssignment.user_id == user_id,
                UserRoadmapAssignment.roadmap_id == roadmap_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_assignment_by_id(
        self, assignment_id: uuid.UUID
    ) -> UserRoadmapAssignment | None:
        result = await self.db.execute(
            select(UserRoadmapAssignment).where(
                UserRoadmapAssignment.id == assignment_id
            )
        )
        return result.scalar_one_or_none()

    async def get_all_assignments(
        self,
        skip: int = 0,
        limit: int = 20,
        roadmap_id: uuid.UUID | None = None,
        user_id: uuid.UUID | None = None,
    ) -> tuple[list[UserRoadmapAssignment], int]:
        base = select(UserRoadmapAssignment)
        count_base = select(func.count(UserRoadmapAssignment.id))

        if roadmap_id:
            base = base.where(UserRoadmapAssignment.roadmap_id == roadmap_id)
            count_base = count_base.where(
                UserRoadmapAssignment.roadmap_id == roadmap_id
            )
        if user_id:
            base = base.where(UserRoadmapAssignment.user_id == user_id)
            count_base = count_base.where(UserRoadmapAssignment.user_id == user_id)

        total = (await self.db.execute(count_base)).scalar_one()
        result = await self.db.execute(
            base.order_by(UserRoadmapAssignment.assigned_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return result.scalars().all(), total

    async def update_assignment(
        self, assignment: UserRoadmapAssignment, **kwargs
    ) -> UserRoadmapAssignment:
        for key, value in kwargs.items():
            if hasattr(assignment, key) and value is not None:
                setattr(assignment, key, value)
        self.db.add(assignment)
        await self.db.flush()
        await self.db.refresh(assignment)
        return assignment

    async def delete_assignment(self, assignment: UserRoadmapAssignment) -> None:
        await self.db.delete(assignment)
        await self.db.flush()

    # ── Node Progress ──────────────────────────────────────────────────────────
    async def get_node_progress(
        self, user_id: uuid.UUID, node_id: uuid.UUID
    ) -> UserNodeProgress | None:
        result = await self.db.execute(
            select(UserNodeProgress).where(
                UserNodeProgress.user_id == user_id,
                UserNodeProgress.node_id == node_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_roadmap_progress(
        self, user_id: uuid.UUID, roadmap_id: uuid.UUID
    ) -> list[UserNodeProgress]:
        result = await self.db.execute(
            select(UserNodeProgress).where(
                UserNodeProgress.user_id == user_id,
                UserNodeProgress.roadmap_id == roadmap_id,
            )
        )
        return result.scalars().all()

    async def upsert_node_progress(
        self,
        user_id: uuid.UUID,
        node_id: uuid.UUID,
        roadmap_id: uuid.UUID,
        status: NodeStatus,
        quiz_passed: bool = False,
    ) -> UserNodeProgress:
        existing = await self.get_node_progress(user_id, node_id)
        now = datetime.now(UTC)

        if existing:
            existing.status = status
            if quiz_passed:
                existing.quiz_passed = True
            if status == NodeStatus.done and not existing.completed_at:
                existing.completed_at = now
            self.db.add(existing)
            await self.db.flush()
            await self.db.refresh(existing)
            return existing
        else:
            progress = UserNodeProgress(
                user_id=user_id,
                node_id=node_id,
                roadmap_id=roadmap_id,
                status=status,
                quiz_passed=quiz_passed,
                completed_at=now if status == NodeStatus.done else None,
            )
            self.db.add(progress)
            await self.db.flush()
            await self.db.refresh(progress)
            return progress

    async def mark_quiz_passed(
        self, user_id: uuid.UUID, node_id: uuid.UUID, roadmap_id: uuid.UUID
    ) -> UserNodeProgress:
        progress = await self.get_node_progress(user_id, node_id)
        if progress:
            progress.quiz_passed = True
            self.db.add(progress)
        else:
            progress = UserNodeProgress(
                user_id=user_id,
                node_id=node_id,
                roadmap_id=roadmap_id,
                status=NodeStatus.in_progress,
                quiz_passed=True,
            )
            self.db.add(progress)
        await self.db.flush()
        await self.db.refresh(progress)
        return progress

    async def recalculate_completion(
        self, user_id: uuid.UUID, roadmap_id: uuid.UUID
    ) -> float:
        """Recalculate and persist the completion percentage on the assignment."""
        # Count total nodes in roadmap
        total_result = await self.db.execute(
            select(func.count(RoadmapNode.id)).where(
                RoadmapNode.roadmap_id == roadmap_id
            )
        )
        total_nodes = total_result.scalar_one()
        if total_nodes == 0:
            return 0.0

        # Count done nodes for this user
        done_result = await self.db.execute(
            select(func.count(UserNodeProgress.id)).where(
                UserNodeProgress.user_id == user_id,
                UserNodeProgress.roadmap_id == roadmap_id,
                UserNodeProgress.status == NodeStatus.done,
            )
        )
        done_nodes = done_result.scalar_one()
        percentage = round((done_nodes / total_nodes) * 100, 2)

        # Update the assignment
        now = datetime.now(UTC)
        await self.db.execute(
            update(UserRoadmapAssignment)
            .where(
                UserRoadmapAssignment.user_id == user_id,
                UserRoadmapAssignment.roadmap_id == roadmap_id,
            )
            .values(completion_percentage=percentage, last_active_at=now)
        )
        await self.db.flush()
        return percentage

    # ── Analytics ──────────────────────────────────────────────────────────────
    async def get_all_user_assignments_with_details(
        self, skip: int = 0, limit: int = 50
    ) -> list[dict]:
        """For admin dashboard: all assignments with user + roadmap info."""
        from app.models.models import Roadmap, User

        stmt = (
            select(
                UserRoadmapAssignment,
                User.display_name,
                User.email,
                Roadmap.title.label("roadmap_title"),
            )
            .join(User, UserRoadmapAssignment.user_id == User.id)
            .join(Roadmap, UserRoadmapAssignment.roadmap_id == Roadmap.id)
            .order_by(UserRoadmapAssignment.assigned_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        rows = result.all()
        return [
            {
                "assignment": row[0],
                "display_name": row[1],
                "email": row[2],
                "roadmap_title": row[3],
            }
            for row in rows
        ]

    async def get_skill_gaps(self, roadmap_id: uuid.UUID) -> list[dict]:
        """
        Per-node breakdown: how many assigned users have/haven't completed each node.
        """
        from app.models.models import Roadmap, User

        # Total assigned to this roadmap
        total_stmt = select(func.count(UserRoadmapAssignment.id)).where(
            UserRoadmapAssignment.roadmap_id == roadmap_id,
            UserRoadmapAssignment.status == AssignmentStatus.active,
        )
        total = (await self.db.execute(total_stmt)).scalar_one()
        if total == 0:
            return []

        # Per-node completion counts
        nodes_stmt = select(RoadmapNode).where(RoadmapNode.roadmap_id == roadmap_id)
        nodes = (await self.db.execute(nodes_stmt)).scalars().all()

        gaps = []
        for node in nodes:
            done_stmt = select(func.count(UserNodeProgress.id)).where(
                UserNodeProgress.node_id == node.id,
                UserNodeProgress.status == NodeStatus.done,
            )
            in_progress_stmt = select(func.count(UserNodeProgress.id)).where(
                UserNodeProgress.node_id == node.id,
                UserNodeProgress.status == NodeStatus.in_progress,
            )
            done_count = (await self.db.execute(done_stmt)).scalar_one()
            in_progress_count = (await self.db.execute(in_progress_stmt)).scalar_one()
            not_started = total - done_count - in_progress_count

            gaps.append(
                {
                    "node_id": node.id,
                    "node_title": node.title,
                    "roadmap_id": roadmap_id,
                    "total_assigned": total,
                    "not_started": max(0, not_started),
                    "in_progress": in_progress_count,
                    "completed": done_count,
                    "not_started_percentage": round(
                        (max(0, not_started) / total) * 100, 2
                    ),
                }
            )
        return gaps
