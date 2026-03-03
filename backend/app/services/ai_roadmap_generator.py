"""
AI Roadmap Generator Service — Bonus Feature.

Admin provides a text prompt like:
  "Create a roadmap for Senior Java Developer"

LLM generates a structured node hierarchy which is then saved to the DB.
"""

import uuid

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import LLMException, NotFoundException
from app.models.models import User
from app.repositories.roadmap_repository import RoadmapRepository
from app.schemas.roadmap import GenerateRoadmapRequest, RoadmapDetailResponse
from app.services.llm_factory import get_structured_llm
from app.services.roadmap_service import RoadmapService


# ── Structured LLM output schema ──────────────────────────────────────────────
class _GeneratedResourceSchema(BaseModel):
    title: str = Field(description="Resource title")
    url: str = Field(description="URL link")
    type: str = Field(description="Type of resource: docs, article, or video")

class _GeneratedNodeSchema(BaseModel):
    title: str = Field(description="Node title, e.g. 'Java Fundamentals'")
    description: str = Field(description="2-3 sentence description of this learning topic")
    parent_title: str | None = Field(
        None,
        description=(
            "Title of the parent node (must exactly match another node's title). "
            "Set to null for root-level nodes."
        ),
    )
    order_index: int = Field(0, description="Position among siblings (0-indexed)")
    resources: list[_GeneratedResourceSchema] = Field(
        default_factory=list,
        description="List of helpful links/resources for this node",
    )


class _GeneratedRoadmapSchema(BaseModel):
    title: str = Field(description="Roadmap title, e.g. 'Senior Java Developer 2026'")
    description: str = Field(description="Overview of what this roadmap covers")
    nodes: list[_GeneratedNodeSchema] = Field(
        description="All nodes in the roadmap (5-30 nodes recommended)",
    )


class AIRoadmapGeneratorService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.roadmap_repo = RoadmapRepository(db)
        self.roadmap_service = RoadmapService(db)

    async def generate_and_save(
        self,
        data: GenerateRoadmapRequest,
        current_user: User,
    ) -> RoadmapDetailResponse:
        prompt = (
            f"Create a comprehensive learning roadmap based on this request:\n"
            f"'{data.prompt}'\n\n"
            f"Guidelines:\n"
            f"- Generate 8-20 nodes organized in a logical learning progression\n"
            f"- Use parent_title to establish hierarchy (e.g., 'Java Basics' → 'OOP in Java')\n"
            f"- Root nodes (no parent) should be major topic areas\n"
            f"- Leaf nodes should be specific, learnable skills\n"
            f"- Maximum depth: 3-4 levels\n"
            f"- Include practical resources where possible\n"
            f"- Order nodes logically (prerequisites first)\n"
            f"- Match the roadmap.sh style: structured, opinionated learning path"
        )

        try:
            structured_llm = get_structured_llm(_GeneratedRoadmapSchema)
            generated: _GeneratedRoadmapSchema = await structured_llm.ainvoke(prompt)
        except Exception as e:
            raise LLMException(f"Roadmap generation failed: {str(e)}")

        # ── Save generated roadmap to DB ───────────────────────────────────────
        roadmap = await self.roadmap_repo.create(
            title=generated.title,
            description=generated.description,
            created_by=current_user.id,
        )

        if data.publish_immediately:
            await self.roadmap_repo.update(roadmap, is_published=True)

        # ── Save nodes respecting parent hierarchy ─────────────────────────────
        # Two passes: first create all nodes, then link parents by title
        title_to_id: dict[str, uuid.UUID] = {}
        nodes_with_parents: list[tuple[_GeneratedNodeSchema, uuid.UUID]] = []

        for node_data in generated.nodes:
            parent_id = None
            if node_data.parent_title and node_data.parent_title in title_to_id:
                parent_id = title_to_id[node_data.parent_title]

            # Clean resources — ensure they're dicts not Pydantic models
            resources = node_data.resources or []
            resources_clean = [
                r if isinstance(r, dict) else r.model_dump() for r in resources
            ]

            node = await self.roadmap_repo.create_node(
                roadmap_id=roadmap.id,
                title=node_data.title,
                description=node_data.description,
                parent_id=parent_id,
                resources=resources_clean,
                order_index=node_data.order_index,
            )
            title_to_id[node_data.title] = node.id

        # Return the full roadmap detail with tree
        return await self.roadmap_service.get_roadmap_detail(roadmap.id, current_user)
