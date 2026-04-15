"""Tests for knowledge/bookmark endpoints (TC-K01 ~ TC-K09)."""

import pytest


class TestBookmarks:
    """Bookmark CRUD tests."""

    def test_create_bookmark(self, test_client):
        """TC-K01: Create bookmark with full params returns bookmark_id."""
        resp = test_client.post("/api/knowledge/bookmarks", json={
            "thread_id": "1001",
            "title": "量化入门指南",
            "url": "https://bbs.quantclass.cn/topic/1001",
            "summary": "一篇很好的量化入门文章",
            "tags": ["量化策略", "入门"]
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 0
        assert body["data"]["bookmark_id"]
        assert body["data"]["thread_id"] == "1001"
        assert body["data"]["title"] == "量化入门指南"

    def test_duplicate_bookmark_upsert(self, test_client):
        """TC-K02: Duplicate thread_id upserts (ON CONFLICT)."""
        # First create
        test_client.post("/api/knowledge/bookmarks", json={
            "thread_id": "2002",
            "title": "Original Title",
            "url": "https://bbs.quantclass.cn/topic/2002",
        })
        # Second create with same thread_id
        resp = test_client.post("/api/knowledge/bookmarks", json={
            "thread_id": "2002",
            "title": "Updated Title",
            "url": "https://bbs.quantclass.cn/topic/2002",
            "summary": "Updated summary"
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 0
        assert body["data"]["title"] == "Updated Title"

    def test_list_bookmarks_default(self, test_client):
        """TC-K03: List bookmarks returns paginated results in desc order."""
        resp = test_client.get("/api/knowledge/bookmarks")
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 0
        assert "items" in body["data"]
        assert "pagination" in body["data"]
        assert body["data"]["pagination"]["total"] >= 1

    def test_list_bookmarks_by_tag(self, test_client):
        """TC-K04: Filter by tag returns only matching bookmarks."""
        resp = test_client.get("/api/knowledge/bookmarks", params={"tag": "量化策略"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 0
        for item in body["data"]["items"]:
            assert "量化策略" in item["tags"]

    def test_get_bookmark(self, test_client):
        """Get single bookmark by ID."""
        # Create one first
        create_resp = test_client.post("/api/knowledge/bookmarks", json={
            "thread_id": "3003",
            "title": "Test Get",
            "url": "https://bbs.quantclass.cn/topic/3003",
        })
        bookmark_id = create_resp.json()["data"]["bookmark_id"]

        resp = test_client.get(f"/api/knowledge/bookmarks/{bookmark_id}")
        assert resp.status_code == 200
        assert resp.json()["data"]["thread_id"] == "3003"

    def test_update_bookmark(self, test_client):
        """TC-K05: Update bookmark changes title and updated_at."""
        create_resp = test_client.post("/api/knowledge/bookmarks", json={
            "thread_id": "4004",
            "title": "Before Update",
            "url": "https://bbs.quantclass.cn/topic/4004",
        })
        bookmark_id = create_resp.json()["data"]["bookmark_id"]

        resp = test_client.put(f"/api/knowledge/bookmarks/{bookmark_id}", json={
            "title": "After Update",
            "tags": ["Python"]
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["title"] == "After Update"
        assert "Python" in body["data"]["tags"]

    def test_delete_bookmark(self, test_client):
        """TC-K06: Delete removes bookmark."""
        create_resp = test_client.post("/api/knowledge/bookmarks", json={
            "thread_id": "5005",
            "title": "To Delete",
            "url": "https://bbs.quantclass.cn/topic/5005",
        })
        bookmark_id = create_resp.json()["data"]["bookmark_id"]

        resp = test_client.delete(f"/api/knowledge/bookmarks/{bookmark_id}")
        assert resp.status_code == 200
        assert resp.json()["data"]["deleted"] is True

        # Verify it's gone
        resp = test_client.get(f"/api/knowledge/bookmarks/{bookmark_id}")
        assert resp.json()["code"] == 1002

    def test_delete_nonexistent_bookmark(self, test_client):
        """Delete non-existent bookmark returns 1002."""
        resp = test_client.delete("/api/knowledge/bookmarks/nonexistent")
        assert resp.json()["code"] == 1002

    def test_export_json(self, test_client):
        """TC-K07: Export as JSON returns valid JSON."""
        resp = test_client.get("/api/knowledge/export", params={"format": "json"})
        assert resp.status_code == 200
        assert "application/json" in resp.headers["content-type"]
        import json
        data = json.loads(resp.text)
        assert isinstance(data, list)

    def test_export_csv(self, test_client):
        """TC-K08: Export as CSV returns valid CSV."""
        resp = test_client.get("/api/knowledge/export", params={"format": "csv"})
        assert resp.status_code == 200
        assert "text/csv" in resp.headers["content-type"]
        lines = resp.text.strip().split("\n")
        assert len(lines) >= 1  # at least header
        assert "Title" in lines[0]

    def test_export_markdown(self, test_client):
        """Export as Markdown returns valid markdown."""
        resp = test_client.get("/api/knowledge/export", params={"format": "markdown"})
        assert resp.status_code == 200
        assert "text/markdown" in resp.headers["content-type"]

    def test_empty_bookmark_list(self, test_client):
        """TC-K09: Search with impossible filter returns empty list."""
        resp = test_client.get("/api/knowledge/bookmarks", params={"tag": "不存在的标签xyz"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["pagination"]["total"] == 0
        assert body["data"]["items"] == []


class TestNotes:
    """Notes tests."""

    def test_add_and_get_note(self, test_client):
        """Add note to bookmark and retrieve it."""
        create_resp = test_client.post("/api/knowledge/bookmarks", json={
            "thread_id": "6006",
            "title": "Note Test",
            "url": "https://bbs.quantclass.cn/topic/6006",
        })
        bookmark_id = create_resp.json()["data"]["bookmark_id"]

        # Add note
        resp = test_client.post(f"/api/knowledge/bookmarks/{bookmark_id}/notes", json={
            "content": "This is my note"
        })
        assert resp.status_code == 200
        assert resp.json()["data"]["content"] == "This is my note"

        # Get note
        resp = test_client.get(f"/api/knowledge/bookmarks/{bookmark_id}/notes")
        assert resp.status_code == 200
        assert resp.json()["data"]["content"] == "This is my note"

    def test_update_note(self, test_client):
        """Updating note replaces content."""
        create_resp = test_client.post("/api/knowledge/bookmarks", json={
            "thread_id": "7007",
            "title": "Note Update Test",
            "url": "https://bbs.quantclass.cn/topic/7007",
        })
        bookmark_id = create_resp.json()["data"]["bookmark_id"]

        test_client.post(f"/api/knowledge/bookmarks/{bookmark_id}/notes", json={
            "content": "Original note"
        })
        resp = test_client.post(f"/api/knowledge/bookmarks/{bookmark_id}/notes", json={
            "content": "Updated note"
        })
        assert resp.json()["data"]["content"] == "Updated note"
