"""
Roadmap Repository — all DB operations for roadmaps and nodes.
Uses Recursive CTE for efficient tree traversal (Adjacency List pattern).
"""

import uuid
from typing import Any

from sqlalchemy import delete, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.models import Roadmap, RoadmapNode


class RoadmapRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ── Roadmap CRUD ───────────────────────────────────────────────────────────
    async def create(
        self,
        title: str,
        description: str | None,
        created_by: uuid.UUID,
    ) -> Roadmap:
        roadmap = Roadmap(title=title, description=description, created_by=created_by)
        self.db.add(roadmap)
        await self.db.flush()
        await self.db.refresh(roadmap)
        return roadmap

    async def get_by_id(self, roadmap_id: uuid.UUID) -> Roadmap | None:
        result = await self.db.execute(
            select(Roadmap).where(
                Roadmap.id == roadmap_id, Roadmap.is_deleted == False
            )
        )
        return result.scalar_one_or_none()

    async def get_all(
        self,
        skip: int = 0,
        limit: int = 20,
        published_only: bool = True,
    ) -> tuple[list[Roadmap], int]:
        base = select(Roadmap).where(Roadmap.is_deleted == False)
        count_base = select(func.count(Roadmap.id)).where(Roadmap.is_deleted == False)

        if published_only:
            base = base.where(Roadmap.is_published == True)
            count_base = count_base.where(Roadmap.is_published == True)

        total = (await self.db.execute(count_base)).scalar_one()
        result = await self.db.execute(
            base.order_by(Roadmap.created_at.desc()).offset(skip).limit(limit)
        )
        return result.scalars().all(), total

    async def update(self, roadmap: Roadmap, **kwargs) -> Roadmap:
        for key, value in kwargs.items():
            if hasattr(roadmap, key):
                setattr(roadmap, key, value)
        self.db.add(roadmap)
        await self.db.flush()
        await self.db.refresh(roadmap)
        return roadmap

    async def soft_delete(self, roadmap: Roadmap) -> None:
        roadmap.is_deleted = True
        self.db.add(roadmap)
        await self.db.flush()

    async def count_nodes(self, roadmap_id: uuid.UUID) -> int:
        result = await self.db.execute(
            select(func.count(RoadmapNode.id)).where(
                RoadmapNode.roadmap_id == roadmap_id
            )
        )
        return result.scalar_one()

    # ── Node CRUD ──────────────────────────────────────────────────────────────
    async def create_node(
        self,
        roadmap_id: uuid.UUID,
        title: str,
        description: str | None = None,
        parent_id: uuid.UUID | None = None,
        resources: list | None = None,
        position_x: float = 0.0,
        position_y: float = 0.0,
        order_index: int = 0,
    ) -> RoadmapNode:
        node = RoadmapNode(
            roadmap_id=roadmap_id,
            title=title,
            description=description,
            parent_id=parent_id,
            resources=resources or [],
            position_x=position_x,
            position_y=position_y,
            order_index=order_index,
        )
        self.db.add(node)
        await self.db.flush()
        await self.db.refresh(node)
        return node

    async def get_node_by_id(self, node_id: uuid.UUID) -> RoadmapNode | None:
        result = await self.db.execute(
            select(RoadmapNode).where(RoadmapNode.id == node_id)
        )
        return result.scalar_one_or_none()

    async def update_node(self, node: RoadmapNode, **kwargs) -> RoadmapNode:
        for key, value in kwargs.items():
            if hasattr(node, key) and value is not None:
                setattr(node, key, value)
        self.db.add(node)
        await self.db.flush()
        await self.db.refresh(node)
        return node

    async def delete_node(self, node: RoadmapNode) -> None:
        await self.db.delete(node)
        await self.db.flush()

    async def get_root_nodes(self, roadmap_id: uuid.UUID) -> list[RoadmapNode]:
        """Get all top-level nodes (parent_id IS NULL) for a roadmap."""
        result = await self.db.execute(
            select(RoadmapNode)
            .where(
                RoadmapNode.roadmap_id == roadmap_id,
                RoadmapNode.parent_id == None,
            )
            .order_by(RoadmapNode.order_index)
        )
        return result.scalars().all()

    # ── Tree Fetch (dialect-aware) ─────────────────────────────────────────────
    async def get_full_tree(self, roadmap_id: uuid.UUID) -> list[dict[str, Any]]:
        """
        Fetch ALL nodes for a roadmap in one query.

        Strategy by dialect:
        - PostgreSQL (production): Optimised Recursive CTE with ARRAY path ordering.
          Single round-trip, handles unlimited depth efficiently.
        - SQLite (tests): ORM SELECT + Python DFS depth tagging.
          SQLite stores UUID(as_uuid=True) as BLOB bytes; raw text() queries cannot
          bind UUID params correctly — the ORM handles type coercion automatically.
        """
        from app.core.config import settings

        if settings.DATABASE_URL.startswith("sqlite"):
            return await self._get_full_tree_sqlite(roadmap_id)

        # PostgreSQL: Recursive CTE with ARRAY path for correct ordering
        cte_sql = text("""
            WITH RECURSIVE node_tree AS (
                SELECT
                    id, roadmap_id, parent_id, title, description, resources,
                    position_x, position_y, order_index, created_at, updated_at,
                    0 AS depth,
                    ARRAY[order_index] AS path
                FROM roadmap_nodes
                WHERE roadmap_id = :roadmap_id AND parent_id IS NULL

                UNION ALL

                SELECT
                    n.id, n.roadmap_id, n.parent_id, n.title, n.description,
                    n.resources, n.position_x, n.position_y, n.order_index,
                    n.created_at, n.updated_at,
                    nt.depth + 1,
                    nt.path || n.order_index
                FROM roadmap_nodes n
                INNER JOIN node_tree nt ON n.parent_id = nt.id
            )
            SELECT * FROM node_tree ORDER BY path, order_index
        """)

        result = await self.db.execute(cte_sql, {"roadmap_id": str(roadmap_id)})
        rows = result.mappings().all()

        return [
            {
                "id": str(row["id"]),
                "roadmap_id": str(row["roadmap_id"]),
                "parent_id": str(row["parent_id"]) if row["parent_id"] else None,
                "title": row["title"],
                "description": row["description"],
                "resources": row["resources"],
                "position_x": row["position_x"],
                "position_y": row["position_y"],
                "order_index": row["order_index"],
                "depth": row["depth"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
            for row in rows
        ]

    async def _get_full_tree_sqlite(self, roadmap_id: uuid.UUID) -> list[dict[str, Any]]:
        """
        SQLite-compatible tree fetch via ORM + Python-side DFS traversal.
        Used exclusively in tests — avoids UUID BLOB binding problems in raw SQL.
        """
        result = await self.db.execute(
            select(RoadmapNode)
            .where(RoadmapNode.roadmap_id == roadmap_id)
            .order_by(RoadmapNode.order_index)
        )
        all_nodes = result.scalars().all()

        # Build parent_id -> [children] map for DFS
        children_map: dict[str | None, list[RoadmapNode]] = {}
        for node in all_nodes:
            pid = str(node.parent_id) if node.parent_id else None
            children_map.setdefault(pid, []).append(node)

        flat: list[dict[str, Any]] = []

        def _dfs(parent_key: str | None, depth: int) -> None:
            for node in children_map.get(parent_key, []):
                flat.append(
                    {
                        "id": str(node.id),
                        "roadmap_id": str(node.roadmap_id),
                        "parent_id": str(node.parent_id) if node.parent_id else None,
                        "title": node.title,
                        "description": node.description,
                        "resources": node.resources,
                        "position_x": node.position_x,
                        "position_y": node.position_y,
                        "order_index": node.order_index,
                        "depth": depth,
                        "created_at": node.created_at,
                        "updated_at": node.updated_at,
                    }
                )
                _dfs(str(node.id), depth + 1)

        _dfs(None, 0)
        return flat
