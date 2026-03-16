"""
Progress Service — node status updates, XP awards, and assignment management.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    BadRequestException,
    ConflictException,
    NotFoundException,
    NotAssignedException,
    QuizRequiredException,
)
from app.models.models import (
    NodeStatus,
    PointEventType,
    User,
    UserRoadmapAssignment,
)
from app.repositories.progress_repository import ProgressRepository
from app.repositories.roadmap_repository import RoadmapRepository
from app.repositories.user_repository import UserRepository
from app.schemas.progress import (
    AssignmentCreateRequest,
    AssignmentResponse,
    AssignmentUpdateRequest,
    NodeProgressResponse,
    RoadmapProgressSummary,
)


class ProgressService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = ProgressRepository(db)
        self.roadmap_repo = RoadmapRepository(db)
        self.user_repo = UserRepository(db)

    # ── Assignments ────────────────────────────────────────────────────────────
    async def create_assignment(
        self,
        data: AssignmentCreateRequest,
        assigned_by: User,
    ) -> list[AssignmentResponse]:
        # Validate roadmap exists
        roadmap = await self.roadmap_repo.get_by_id(data.roadmap_id)
        if not roadmap:
            raise NotFoundException("Roadmap")

        created = []
        for user_id in data.user_ids:
            # Check if assignment already exists
            existing = await self.repo.get_assignment(user_id, data.roadmap_id)
            if existing:
                raise ConflictException(
                    f"User {user_id} is already assigned to this roadmap"
                )

            assignment = await self.repo.create_assignment(
                user_id=user_id,
                roadmap_id=data.roadmap_id,
                assigned_by=assigned_by.id,
                strict_mode=data.strict_mode,
            )
            created.append(
                AssignmentResponse(
                    id=assignment.id,
                    user_id=assignment.user_id,
                    roadmap_id=assignment.roadmap_id,
                    assigned_by=assignment.assigned_by,
                    status=assignment.status,
                    completion_percentage=assignment.completion_percentage,
                    strict_mode=assignment.strict_mode,
                    assigned_at=assignment.assigned_at,
                    last_active_at=assignment.last_active_at,
                    roadmap_title=roadmap.title,
                )
            )
        return created

    async def enroll_roadmap(
        self,
        user_id: uuid.UUID,
        roadmap_id: uuid.UUID,
    ) -> AssignmentResponse:
        """Self-enroll to a roadmap. First node automatically set to in_progress (unlocked)."""
        roadmap = await self.roadmap_repo.get_by_id(roadmap_id)
        if not roadmap:
            raise NotFoundException("Roadmap")

        existing = await self.repo.get_assignment(user_id, roadmap_id)
        if existing:
            # Already assigned, return as is
            return AssignmentResponse(
                id=existing.id, user_id=existing.user_id, roadmap_id=existing.roadmap_id,
                assigned_by=existing.assigned_by, status=existing.status,
                completion_percentage=existing.completion_percentage, strict_mode=existing.strict_mode,
                assigned_at=existing.assigned_at, last_active_at=existing.last_active_at,
                roadmap_title=roadmap.title,
            )

        assignment = await self.repo.create_assignment(
            user_id=user_id,
            roadmap_id=roadmap_id,
            assigned_by=user_id,
            strict_mode=False,
        )
        
        # Initialize first node as in_progress (unlocked)
        flat_nodes = await self.roadmap_repo.get_full_tree(roadmap_id)
        if flat_nodes:
            # Get first root node (no parent), sorted by order_index
            root_nodes = sorted(
                [n for n in flat_nodes if n.get('parent_id') is None],
                key=lambda n: n.get('order_index', 0)
            )
            if root_nodes:
                first_node = root_nodes[0]
                # ID from get_full_tree is a string, convert to UUID
                first_node_id = uuid.UUID(first_node['id']) if isinstance(first_node['id'], str) else first_node['id']
                await self.repo.upsert_node_progress(
                    user_id=user_id,
                    node_id=first_node_id,
                    roadmap_id=roadmap_id,
                    status=NodeStatus.in_progress,
                )
        
        return AssignmentResponse(
            id=assignment.id, user_id=assignment.user_id, roadmap_id=assignment.roadmap_id,
            assigned_by=assignment.assigned_by, status=assignment.status,
            completion_percentage=assignment.completion_percentage, strict_mode=assignment.strict_mode,
            assigned_at=assignment.assigned_at, last_active_at=assignment.last_active_at,
            roadmap_title=roadmap.title,
        )

    async def get_assignments(
        self,
        page: int = 1,
        page_size: int = 20,
        roadmap_id: uuid.UUID | None = None,
        user_id: uuid.UUID | None = None,
    ) -> dict:
        skip = (page - 1) * page_size
        assignments, total = await self.repo.get_all_assignments(
            skip=skip, limit=page_size, roadmap_id=roadmap_id, user_id=user_id
        )
        pages = (total + page_size - 1) // page_size

        user_cache: dict[uuid.UUID, str | None] = {}
        roadmap_cache: dict[uuid.UUID, str | None] = {}

        items: list[AssignmentResponse] = []
        for a in assignments:
            if a.user_id not in user_cache:
                user = await self.user_repo.get_by_id(a.user_id)
                user_cache[a.user_id] = user.display_name if user else None

            if a.roadmap_id not in roadmap_cache:
                roadmap = await self.roadmap_repo.get_by_id(a.roadmap_id)
                roadmap_cache[a.roadmap_id] = roadmap.title if roadmap else None

            items.append(
                AssignmentResponse(
                    id=a.id,
                    user_id=a.user_id,
                    roadmap_id=a.roadmap_id,
                    assigned_by=a.assigned_by,
                    status=a.status,
                    completion_percentage=a.completion_percentage,
                    strict_mode=a.strict_mode,
                    assigned_at=a.assigned_at,
                    last_active_at=a.last_active_at,
                    user_display_name=user_cache[a.user_id],
                    roadmap_title=roadmap_cache[a.roadmap_id],
                )
            )
        return {"items": items, "total": total, "page": page, "page_size": page_size, "pages": pages}

    async def update_assignment(
        self, assignment_id: uuid.UUID, data: AssignmentUpdateRequest
    ) -> AssignmentResponse:
        assignment = await self.repo.get_assignment_by_id(assignment_id)
        if not assignment:
            raise NotFoundException("Assignment")

        updates = data.model_dump(exclude_none=True)
        assignment = await self.repo.update_assignment(assignment, **updates)
        return AssignmentResponse(
            id=assignment.id,
            user_id=assignment.user_id,
            roadmap_id=assignment.roadmap_id,
            assigned_by=assignment.assigned_by,
            status=assignment.status,
            completion_percentage=assignment.completion_percentage,
            strict_mode=assignment.strict_mode,
            assigned_at=assignment.assigned_at,
            last_active_at=assignment.last_active_at,
        )

    async def delete_assignment(self, assignment_id: uuid.UUID) -> None:
        assignment = await self.repo.get_assignment_by_id(assignment_id)
        if not assignment:
            raise NotFoundException("Assignment")
        await self.repo.delete_assignment(assignment)

    # ── Node Progress ──────────────────────────────────────────────────────────
    async def get_roadmap_progress(
        self, user_id: uuid.UUID, roadmap_id: uuid.UUID
    ) -> RoadmapProgressSummary:
        roadmap = await self.roadmap_repo.get_by_id(roadmap_id)
        if not roadmap:
            raise NotFoundException("Roadmap")

        # Verify the user is actually enrolled / assigned to this roadmap
        assignment = await self.repo.get_assignment(user_id, roadmap_id)
        if not assignment:
            raise NotAssignedException()

        progress_records = await self.repo.get_roadmap_progress(user_id, roadmap_id)
        total_nodes = await self.roadmap_repo.count_nodes(roadmap_id)

        done = sum(1 for p in progress_records if p.status == NodeStatus.done)
        in_progress = sum(
            1 for p in progress_records if p.status == NodeStatus.in_progress
        )
        percentage = round((done / total_nodes * 100), 2) if total_nodes > 0 else 0.0

        node_statuses = [
            NodeProgressResponse(
                id=p.id,
                user_id=p.user_id,
                node_id=p.node_id,
                roadmap_id=p.roadmap_id,
                status=p.status,
                quiz_passed=p.quiz_passed,
                completed_at=p.completed_at,
                updated_at=p.updated_at,
            )
            for p in progress_records
        ]

        return RoadmapProgressSummary(
            roadmap_id=roadmap_id,
            roadmap_title=roadmap.title,
            total_nodes=total_nodes,
            completed_nodes=done,
            in_progress_nodes=in_progress,
            completion_percentage=percentage,
            node_statuses=node_statuses,
        )

    async def update_node_progress(
        self,
        user_id: uuid.UUID,
        roadmap_id: uuid.UUID,
        node_id: uuid.UUID,
        new_status: str,
        bypass_quiz: bool = False,
    ) -> NodeProgressResponse:
        # Security: must be assigned to this roadmap
        assignment = await self.repo.get_assignment(user_id, roadmap_id)
        if not assignment:
            raise NotAssignedException()

        # Validate the node belongs to this roadmap
        node = await self.roadmap_repo.get_node_by_id(node_id)
        if not node or node.roadmap_id != roadmap_id:
            raise NotFoundException("Node")

        status = NodeStatus(new_status)
        
        # Check if user is allowed to move to this node (only when trying to unlock from locked state)
        existing_progress = await self.repo.get_node_progress(user_id, node_id)
        is_currently_locked = not existing_progress or existing_progress.status == NodeStatus.locked

        if status == NodeStatus.in_progress and is_currently_locked and not bypass_quiz:
            # User is trying to unlock a node. Determine what needs to be satisfied.
            if node.parent_id:
                parent_node = await self.roadmap_repo.get_node_by_id(node.parent_id)

                # Check whether the parent is a "section header" (has other children).
                # We detect this by finding sibling nodes that share the same parent_id.
                from sqlalchemy import select as sa_select
                from app.models.models import RoadmapNode as RNModel
                siblings_result = await self.db.execute(
                    sa_select(RNModel).where(
                        RNModel.roadmap_id == roadmap_id,
                        RNModel.parent_id == node.parent_id,
                        RNModel.id != node_id,
                    )
                )
                siblings = siblings_result.scalars().all()

                if siblings:
                    # Parent has multiple children → it's a section header.
                    # First child: only require parent to be in_progress (enrolled).
                    # Subsequent children: require previous sibling done+quiz_passed.
                    prev_siblings = [
                        s for s in siblings
                        if (s.order_index or 0) < (node.order_index or 0)
                    ]
                    if not prev_siblings:
                        # First child of section: parent in_progress is enough
                        parent_progress = await self.repo.get_node_progress(user_id, node.parent_id)
                        if not parent_progress or parent_progress.status not in (
                            NodeStatus.in_progress, NodeStatus.done
                        ):
                            raise BadRequestException(
                                "You must start this section before accessing its first topic"
                            )
                    else:
                        # Subsequent child: previous sibling must be done + quiz_passed
                        prev_sibling = max(prev_siblings, key=lambda s: s.order_index or 0)
                        prev_progress = await self.repo.get_node_progress(user_id, prev_sibling.id)
                        if not prev_progress or prev_progress.status != NodeStatus.done:
                            raise BadRequestException(
                                "You must complete the previous topic before unlocking this one"
                            )
                        if not prev_progress.quiz_passed:
                            raise QuizRequiredException()
                else:
                    # Only child (or parent is a leaf node itself).
                    # Require parent to be done + quiz_passed.
                    parent_progress = await self.repo.get_node_progress(user_id, node.parent_id)
                    if not parent_progress or parent_progress.status != NodeStatus.done:
                        raise BadRequestException(
                            "You must complete the previous node before unlocking this one"
                        )
                    if not parent_progress.quiz_passed:
                        raise QuizRequiredException()
            # For root nodes, always allow unlocking if enrolled

        # Strict Mode: cannot mark done without quiz_passed (only if transitioning to done)
        if status == NodeStatus.done and assignment.strict_mode:
            if not existing_progress or not existing_progress.quiz_passed:
                if not bypass_quiz:
                    raise QuizRequiredException()

        is_newly_done = False
        if not existing_progress or existing_progress.status != NodeStatus.done:
            is_newly_done = status == NodeStatus.done

        progress = await self.repo.upsert_node_progress(
            user_id=user_id,
            node_id=node_id,
            roadmap_id=roadmap_id,
            status=status,
            quiz_passed=bypass_quiz if status == NodeStatus.done else False,
        )

        # Award XP only when ALL root nodes (parent_id is None) are completed.
        # Ensure it is awarded only once upon the final root node completion.
        if is_newly_done and node.parent_id is None:
            from app.core.config import settings
            from sqlalchemy import select as sa_select, func as sa_func
            from app.models.models import RoadmapNode as _RNModel
            from app.models.models import UserNodeProgress as _UNPModel
            from app.models.schemas.enums import NodeStatus as _NS

            # Count total root nodes
            root_count_result = await self.db.execute(
                sa_select(sa_func.count(_RNModel.id)).where(
                    _RNModel.roadmap_id == roadmap_id,
                    _RNModel.parent_id.is_(None),
                )
            )
            root_count = root_count_result.scalar_one() or 1

            # Count completed root nodes for this user
            done_root_result = await self.db.execute(
                sa_select(sa_func.count(_RNModel.id)).join(
                    _UNPModel, _RNModel.id == _UNPModel.node_id
                ).where(
                    _RNModel.roadmap_id == roadmap_id,
                    _RNModel.parent_id.is_(None),
                    _UNPModel.user_id == user_id,
                    _UNPModel.status == _NS.done
                )
            )
            done_root_count = done_root_result.scalar_one() or 0

            if done_root_count == root_count:
                user = await self.user_repo.get_by_id(user_id)
                if user:
                    await self.user_repo.add_xp(
                        user_id=user_id,
                        user_name=user.display_name,
                        amount=settings.XP_NODE_COMPLETE,
                        event_type=PointEventType.roadmap_complete,
                        description=f"Completed all foundations of roadmap!",
                        reference_id=str(roadmap_id),
                    )
                    await self.user_repo.update_level(user)

        # Recalculate assignment completion percentage
        await self.repo.recalculate_completion(user_id, roadmap_id)

        return NodeProgressResponse(
            id=progress.id,
            user_id=progress.user_id,
            node_id=progress.node_id,
            roadmap_id=progress.roadmap_id,
            status=progress.status,
            quiz_passed=progress.quiz_passed,
            completed_at=progress.completed_at,
            updated_at=progress.updated_at,
        )

    async def get_node_progress(
        self, user_id: uuid.UUID, roadmap_id: uuid.UUID, node_id: uuid.UUID
    ) -> NodeProgressResponse | None:
        progress = await self.repo.get_node_progress(user_id, node_id)
        if not progress:
            return None
        return NodeProgressResponse(
            id=progress.id,
            user_id=progress.user_id,
            node_id=progress.node_id,
            roadmap_id=progress.roadmap_id,
            status=progress.status,
            quiz_passed=progress.quiz_passed,
            completed_at=progress.completed_at,
            updated_at=progress.updated_at,
        )
