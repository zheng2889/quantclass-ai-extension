"""Tests for tag endpoints (TC-T01 ~ TC-T04)."""

import pytest


class TestTags:
    """Tag management tests."""

    def test_list_tags_default(self, test_client):
        """TC-T03: List tags returns default system tags."""
        resp = test_client.get("/api/tags/")
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 0
        assert "items" in body["data"]
        assert "categories" in body["data"]
        # Should have system tags from init_db
        tag_names = [t["name"] for t in body["data"]["items"]]
        assert "量化策略" in tag_names
        assert "Python" in tag_names

    def test_list_tags_by_category(self, test_client):
        """TC-T04: Filter tags by category."""
        resp = test_client.get("/api/tags/", params={"category": "system"})
        assert resp.status_code == 200
        body = resp.json()
        for item in body["data"]["items"]:
            assert item["category"] == "system"

    def test_create_tag(self, test_client):
        """Create a custom tag."""
        resp = test_client.post("/api/tags/", json={
            "name": "测试标签",
            "category": "custom"
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 0
        assert body["data"]["name"] == "测试标签"

    def test_create_duplicate_tag(self, test_client):
        """Creating duplicate tag returns existing tag."""
        test_client.post("/api/tags/", json={"name": "Duplicate"})
        resp = test_client.post("/api/tags/", json={"name": "Duplicate"})
        assert resp.status_code == 200
        assert resp.json()["data"]["name"] == "Duplicate"

    def test_get_tag(self, test_client):
        """Get tag by ID."""
        resp = test_client.get("/api/tags/1")
        assert resp.status_code == 200
        assert resp.json()["data"]["id"] == 1

    def test_get_nonexistent_tag(self, test_client):
        """Get non-existent tag returns 1002."""
        resp = test_client.get("/api/tags/99999")
        assert resp.json()["code"] == 1002

    def test_delete_tag(self, test_client):
        """Delete a tag."""
        create_resp = test_client.post("/api/tags/", json={"name": "ToDelete"})
        tag_id = create_resp.json()["data"]["id"]

        resp = test_client.delete(f"/api/tags/{tag_id}")
        assert resp.status_code == 200
        assert resp.json()["data"]["deleted"] is True
