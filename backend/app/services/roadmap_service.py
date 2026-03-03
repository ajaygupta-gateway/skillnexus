"""
Roadmap Service — business logic for roadmap and node management.
Converts adjacency list DB results into nested tree structures.
"""

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestException, ForbiddenException, NotFoundException
from app.models.models import Roadmap, RoadmapNode, User, UserRole
from app.repositories.roadmap_repository import RoadmapRepository
from app.schemas.roadmap import (
    NodeCreateRequest,
    NodeTreeResponse,
    NodeUpdateRequest,
    RoadmapCreateRequest,
    RoadmapDetailResponse,
    RoadmapListResponse,
    RoadmapUpdateRequest,
)


def _build_tree(flat_nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Convert a flat adjacency list (from CTE) into a nested tree structure.
    Time complexity: O(n) using a lookup map.
    """
    node_map: dict[str, dict] = {}
    roots: list[dict] = []

    # First pass: create all node dicts with empty children lists
    for node in flat_nodes:
        node_dict = {**node, "children": []}
        node_map[node["id"]] = node_dict

    # Second pass: attach each node to its parent (or root list)
    for node_id, node_dict in node_map.items():
        parent_id = node_dict.get("parent_id")
        if parent_id and parent_id in node_map:
            node_map[parent_id]["children"].append(node_dict)
        else:
            roots.append(node_dict)

    return roots


class RoadmapService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = RoadmapRepository(db)

    # ── Roadmap ────────────────────────────────────────────────────────────────
    async def create_roadmap(
        self, data: RoadmapCreateRequest, current_user: User
    ) -> Roadmap:
        return await self.repo.create(
            title=data.title,
            description=data.description,
            created_by=current_user.id,
        )

    async def get_roadmaps(
        self,
        page: int = 1,
        page_size: int = 20,
        current_user: User | None = None,
    ) -> dict:
        is_admin = current_user and current_user.role == UserRole.admin
        # Admins see unpublished too; learners only see published
        published_only = not is_admin

        skip = (page - 1) * page_size
        roadmaps, total = await self.repo.get_all(
            skip=skip, limit=page_size, published_only=published_only
        )

        items = []
        for rm in roadmaps:
            node_count = await self.repo.count_nodes(rm.id)
            items.append(
                RoadmapListResponse(
                    id=rm.id,
                    title=rm.title,
                    description=rm.description,
                    is_published=rm.is_published,
                    created_at=rm.created_at,
                    updated_at=rm.updated_at,
                    node_count=node_count,
                )
            )

        pages = (total + page_size - 1) // page_size
        return {"items": items, "total": total, "page": page, "page_size": page_size, "pages": pages}

    async def get_roadmap_detail(
        self,
        roadmap_id: uuid.UUID,
        current_user: User | None = None,
        include_user_progress: bool = False,
    ) -> RoadmapDetailResponse:
        roadmap = await self.repo.get_by_id(roadmap_id)
        if not roadmap:
            raise NotFoundException("Roadmap")

        # Fetch all nodes via Recursive CTE
        flat_nodes = await self.repo.get_full_tree(roadmap_id)
        node_count = len(flat_nodes)

        # Inject user progress status per node if requested
        if include_user_progress and current_user:
            from app.repositories.progress_repository import ProgressRepository
            prog_repo = ProgressRepository(self.db)
            progress_records = await prog_repo.get_roadmap_progress(
                current_user.id, roadmap_id
            )
            progress_map = {str(p.node_id): p.status for p in progress_records}
            for node in flat_nodes:
                node["user_status"] = progress_map.get(node["id"])

        # Build nested tree
        tree = _build_tree(flat_nodes)

        # Convert to Pydantic models
        def dict_to_node_tree(d: dict) -> NodeTreeResponse:
            return NodeTreeResponse(
                id=d["id"],
                roadmap_id=d["roadmap_id"],
                parent_id=d.get("parent_id"),
                title=d["title"],
                description=d.get("description"),
                resources=d.get("resources") or [],
                position_x=d.get("position_x", 0.0),
                position_y=d.get("position_y", 0.0),
                order_index=d.get("order_index", 0),
                created_at=d["created_at"],
                updated_at=d["updated_at"],
                user_status=d.get("user_status"),
                children=[dict_to_node_tree(c) for c in d.get("children", [])],
            )

        node_trees = [dict_to_node_tree(root) for root in tree]

        return RoadmapDetailResponse(
            id=roadmap.id,
            title=roadmap.title,
            description=roadmap.description,
            is_published=roadmap.is_published,
            created_at=roadmap.created_at,
            updated_at=roadmap.updated_at,
            node_count=node_count,
            nodes=node_trees,
        )

    async def update_roadmap(
        self,
        roadmap_id: uuid.UUID,
        data: RoadmapUpdateRequest,
        current_user: User,
    ) -> Roadmap:
        roadmap = await self.repo.get_by_id(roadmap_id)
        if not roadmap:
            raise NotFoundException("Roadmap")

        updates = data.model_dump(exclude_none=True)
        return await self.repo.update(roadmap, **updates)

    async def delete_roadmap(self, roadmap_id: uuid.UUID, current_user: User) -> None:
        roadmap = await self.repo.get_by_id(roadmap_id)
        if not roadmap:
            raise NotFoundException("Roadmap")
        await self.repo.soft_delete(roadmap)

    async def publish_roadmap(self, roadmap_id: uuid.UUID) -> Roadmap:
        roadmap = await self.repo.get_by_id(roadmap_id)
        if not roadmap:
            raise NotFoundException("Roadmap")

        node_count = await self.repo.count_nodes(roadmap_id)
        if node_count == 0:
            raise BadRequestException("Cannot publish a roadmap with no nodes")

        return await self.repo.update(roadmap, is_published=True)

    # ── Nodes ──────────────────────────────────────────────────────────────────
    async def add_node(
        self,
        roadmap_id: uuid.UUID,
        data: NodeCreateRequest,
    ) -> RoadmapNode:
        roadmap = await self.repo.get_by_id(roadmap_id)
        if not roadmap:
            raise NotFoundException("Roadmap")

        # Validate parent belongs to same roadmap
        if data.parent_id:
            parent = await self.repo.get_node_by_id(data.parent_id)
            if not parent or parent.roadmap_id != roadmap_id:
                raise BadRequestException("Parent node does not belong to this roadmap")

        resources_data = [r.model_dump() for r in data.resources] if data.resources else []

        return await self.repo.create_node(
            roadmap_id=roadmap_id,
            title=data.title,
            description=data.description,
            parent_id=data.parent_id,
            resources=resources_data,
            position_x=data.position_x,
            position_y=data.position_y,
            order_index=data.order_index,
        )

    async def update_node(
        self,
        roadmap_id: uuid.UUID,
        node_id: uuid.UUID,
        data: NodeUpdateRequest,
    ) -> RoadmapNode:
        node = await self.repo.get_node_by_id(node_id)
        if not node or node.roadmap_id != roadmap_id:
            raise NotFoundException("Node")

        updates = data.model_dump(exclude_none=True)
        if "resources" in updates and updates["resources"] is not None:
            updates["resources"] = [r.model_dump() if hasattr(r, 'model_dump') else r for r in updates["resources"]]

        return await self.repo.update_node(node, **updates)

    async def delete_node(
        self,
        roadmap_id: uuid.UUID,
        node_id: uuid.UUID,
    ) -> None:
        node = await self.repo.get_node_by_id(node_id)
        if not node or node.roadmap_id != roadmap_id:
            raise NotFoundException("Node")
        await self.repo.delete_node(node)
