"""
Tests for Roadmap CRUD and node management.
"""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_roadmap_as_admin(client: AsyncClient, admin_token: str):
    response = await client.post(
        "/api/v1/roadmaps",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"title": "Python Developer 2026", "description": "Comprehensive Python path"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "Python Developer 2026"
    assert data["is_published"] is False
    return data["id"]


@pytest.mark.asyncio
async def test_create_roadmap_as_learner_forbidden(client: AsyncClient, learner_token: str):
    response = await client.post(
        "/api/v1/roadmaps",
        headers={"Authorization": f"Bearer {learner_token}"},
        json={"title": "Unauthorized Roadmap"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_list_roadmaps(client: AsyncClient, admin_token: str, learner_token: str):
    # Create and publish a roadmap first
    create_resp = await client.post(
        "/api/v1/roadmaps",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"title": "Public Roadmap"},
    )
    roadmap_id = create_resp.json()["id"]

    # Learner shouldn't see unpublished
    list_resp = await client.get(
        "/api/v1/roadmaps",
        headers={"Authorization": f"Bearer {learner_token}"},
    )
    assert list_resp.status_code == 200

    # Add a node to allow publishing
    await client.post(
        f"/api/v1/roadmaps/{roadmap_id}/nodes",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"title": "First Node"},
    )

    # Publish
    await client.post(
        f"/api/v1/roadmaps/{roadmap_id}/publish",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    # Now learner should see it
    list_resp2 = await client.get(
        "/api/v1/roadmaps",
        headers={"Authorization": f"Bearer {learner_token}"},
    )
    titles = [r["title"] for r in list_resp2.json()["items"]]
    assert "Public Roadmap" in titles


@pytest.mark.asyncio
async def test_add_nodes_to_roadmap(client: AsyncClient, admin_token: str):
    # Create roadmap
    create_resp = await client.post(
        "/api/v1/roadmaps",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"title": "Test Roadmap with Nodes"},
    )
    roadmap_id = create_resp.json()["id"]

    # Add root node
    root_resp = await client.post(
        f"/api/v1/roadmaps/{roadmap_id}/nodes",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"title": "JavaScript Basics", "description": "Core JS concepts"},
    )
    assert root_resp.status_code == 201
    root_node_id = root_resp.json()["id"]
    assert root_resp.json()["parent_id"] is None

    # Add child node
    child_resp = await client.post(
        f"/api/v1/roadmaps/{roadmap_id}/nodes",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"title": "Variables & Types", "parent_id": root_node_id},
    )
    assert child_resp.status_code == 201
    assert child_resp.json()["parent_id"] == root_node_id


@pytest.mark.asyncio
async def test_get_roadmap_with_tree(client: AsyncClient, admin_token: str):
    """Verify that the roadmap returns a properly nested tree structure."""
    # Create roadmap with nodes
    create_resp = await client.post(
        "/api/v1/roadmaps",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"title": "Tree Test Roadmap"},
    )
    roadmap_id = create_resp.json()["id"]

    root_resp = await client.post(
        f"/api/v1/roadmaps/{roadmap_id}/nodes",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"title": "Root Node"},
    )
    root_id = root_resp.json()["id"]

    await client.post(
        f"/api/v1/roadmaps/{roadmap_id}/nodes",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"title": "Child Node 1", "parent_id": root_id},
    )
    await client.post(
        f"/api/v1/roadmaps/{roadmap_id}/nodes",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"title": "Child Node 2", "parent_id": root_id},
    )

    # Get roadmap detail
    detail_resp = await client.get(
        f"/api/v1/roadmaps/{roadmap_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert detail_resp.status_code == 200
    data = detail_resp.json()
    assert data["node_count"] == 3


@pytest.mark.asyncio
async def test_publish_empty_roadmap_fails(client: AsyncClient, admin_token: str):
    create_resp = await client.post(
        "/api/v1/roadmaps",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"title": "Empty Roadmap"},
    )
    roadmap_id = create_resp.json()["id"]

    publish_resp = await client.post(
        f"/api/v1/roadmaps/{roadmap_id}/publish",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert publish_resp.status_code == 400  # Cannot publish empty roadmap


@pytest.mark.asyncio
async def test_delete_node_cascades(client: AsyncClient, admin_token: str):
    create_resp = await client.post(
        "/api/v1/roadmaps",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"title": "Cascade Test Roadmap"},
    )
    roadmap_id = create_resp.json()["id"]

    root_resp = await client.post(
        f"/api/v1/roadmaps/{roadmap_id}/nodes",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"title": "Parent"},
    )
    root_id = root_resp.json()["id"]

    await client.post(
        f"/api/v1/roadmaps/{roadmap_id}/nodes",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"title": "Child", "parent_id": root_id},
    )

    # Delete parent — should cascade to child
    del_resp = await client.delete(
        f"/api/v1/roadmaps/{roadmap_id}/nodes/{root_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert del_resp.status_code == 200

    # Verify roadmap now has 0 nodes
    detail_resp = await client.get(
        f"/api/v1/roadmaps/{roadmap_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert detail_resp.json()["node_count"] == 0
