"""
Tests for progress tracking, XP awards, and security (assignment enforcement).
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Roadmap, RoadmapNode, UserRoadmapAssignment


async def _setup_roadmap_with_node(
    client: AsyncClient, admin_token: str, db: AsyncSession
) -> tuple[str, str]:
    """Helper: create a published roadmap with one node, return (roadmap_id, node_id)."""
    # Create roadmap
    rm_resp = await client.post(
        "/api/v1/roadmaps",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"title": "Test Roadmap"},
    )
    roadmap_id = rm_resp.json()["id"]

    # Add node
    node_resp = await client.post(
        f"/api/v1/roadmaps/{roadmap_id}/nodes",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"title": "Test Node"},
    )
    node_id = node_resp.json()["id"]

    # Publish
    await client.post(
        f"/api/v1/roadmaps/{roadmap_id}/publish",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    return roadmap_id, node_id


@pytest.mark.asyncio
async def test_update_node_progress_not_assigned(
    client: AsyncClient, learner_token: str, admin_token: str, db_session: AsyncSession
):
    """Security: user cannot mark progress on unassigned roadmap."""
    roadmap_id, node_id = await _setup_roadmap_with_node(client, admin_token, db_session)

    response = await client.post(
        f"/api/v1/progress/roadmaps/{roadmap_id}/nodes/{node_id}",
        headers={"Authorization": f"Bearer {learner_token}"},
        json={"status": "done"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_update_node_progress_assigned(
    client: AsyncClient,
    learner_token: str,
    admin_token: str,
    learner_user,
    db_session: AsyncSession,
):
    """User can mark progress after being assigned."""
    roadmap_id, node_id = await _setup_roadmap_with_node(client, admin_token, db_session)

    # Assign roadmap to learner
    await client.post(
        "/api/v1/admin/assignments",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"user_ids": [str(learner_user.id)], "roadmap_id": roadmap_id},
    )

    # Now mark as in_progress
    response = await client.post(
        f"/api/v1/progress/roadmaps/{roadmap_id}/nodes/{node_id}",
        headers={"Authorization": f"Bearer {learner_token}"},
        json={"status": "in_progress"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "in_progress"


@pytest.mark.asyncio
async def test_xp_awarded_on_node_completion(
    client: AsyncClient,
    learner_token: str,
    admin_token: str,
    learner_user,
    db_session: AsyncSession,
):
    """XP should be awarded when a node is marked done for the first time."""
    roadmap_id, node_id = await _setup_roadmap_with_node(client, admin_token, db_session)

    # Assign roadmap to learner
    await client.post(
        "/api/v1/admin/assignments",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"user_ids": [str(learner_user.id)], "roadmap_id": roadmap_id},
    )

    # Get initial XP
    me_before = await client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {learner_token}"},
    )
    initial_xp = me_before.json()["xp_balance"]

    # Mark node as done
    await client.post(
        f"/api/v1/progress/roadmaps/{roadmap_id}/nodes/{node_id}",
        headers={"Authorization": f"Bearer {learner_token}"},
        json={"status": "done"},
    )

    # Check XP increased
    me_after = await client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {learner_token}"},
    )
    # XP should have increased (login XP + node completion XP)
    assert me_after.json()["xp_balance"] > initial_xp


@pytest.mark.asyncio
async def test_strict_mode_blocks_done_without_quiz(
    client: AsyncClient,
    learner_token: str,
    admin_token: str,
    learner_user,
    db_session: AsyncSession,
):
    """Strict Mode: cannot mark done without passing quiz."""
    roadmap_id, node_id = await _setup_roadmap_with_node(client, admin_token, db_session)

    # Assign with strict_mode=True
    await client.post(
        "/api/v1/admin/assignments",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "user_ids": [str(learner_user.id)],
            "roadmap_id": roadmap_id,
            "strict_mode": True,
        },
    )

    # Try to mark done without quiz
    response = await client.post(
        f"/api/v1/progress/roadmaps/{roadmap_id}/nodes/{node_id}",
        headers={"Authorization": f"Bearer {learner_token}"},
        json={"status": "done"},
    )
    assert response.status_code == 403  # QuizRequiredException


@pytest.mark.asyncio
async def test_get_roadmap_progress(
    client: AsyncClient,
    learner_token: str,
    admin_token: str,
    learner_user,
    db_session: AsyncSession,
):
    """Progress summary should correctly reflect completion status."""
    roadmap_id, node_id = await _setup_roadmap_with_node(client, admin_token, db_session)

    # Assign roadmap
    await client.post(
        "/api/v1/admin/assignments",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"user_ids": [str(learner_user.id)], "roadmap_id": roadmap_id},
    )

    # Get progress before any updates
    prog_resp = await client.get(
        f"/api/v1/progress/roadmaps/{roadmap_id}",
        headers={"Authorization": f"Bearer {learner_token}"},
    )
    assert prog_resp.status_code == 200
    data = prog_resp.json()
    assert data["total_nodes"] == 1
    assert data["completed_nodes"] == 0


@pytest.mark.asyncio
async def test_leaderboard(
    client: AsyncClient,
    learner_token: str,
):
    """Leaderboard should return top users."""
    response = await client.get(
        "/api/v1/users/leaderboard",
        headers={"Authorization": f"Bearer {learner_token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "entries" in data
    assert data["period"] == "this_week"
