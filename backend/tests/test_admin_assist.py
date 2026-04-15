"""Tests for admin and assist endpoints."""

import pytest


def _get_admin_token(test_client) -> str:
    """Helper: log in as admin and return token."""
    resp = test_client.post("/api/auth/login", json={
        "username": "admin",
        "password": "admin123"
    })
    return resp.json()["data"]["token"]


class TestAdmin:
    """Admin endpoint tests."""

    def test_get_stats(self, test_client):
        """Get system stats returns all sections."""
        token = _get_admin_token(test_client)
        resp = test_client.get(
            "/api/admin/stats",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 0
        data = body["data"]
        assert "database" in data
        assert "llm_usage" in data
        assert "storage" in data
        assert "config" in data
        assert data["database"]["bookmarks"] >= 0
        assert data["database"]["tags"] >= 0

    def test_reindex(self, test_client):
        """Reindex FTS returns success."""
        token = _get_admin_token(test_client)
        resp = test_client.post(
            "/api/admin/reindex",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 0
        assert body["data"]["success"] is True

    def test_get_llm_logs(self, test_client):
        """Get LLM logs returns list."""
        token = _get_admin_token(test_client)
        resp = test_client.get(
            "/api/admin/logs/llm",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 0
        assert "logs" in body["data"]
        assert isinstance(body["data"]["logs"], list)


class TestAssist:
    """Assist endpoint validation tests (no LLM calls)."""

    def test_polish_empty_text(self, test_client):
        """TC-A02: Empty text returns validation error."""
        resp = test_client.post("/api/assist/polish", json={
            "text": ""
        })
        assert resp.status_code == 422

    def test_format_empty_text(self, test_client):
        """Empty text format returns validation error."""
        resp = test_client.post("/api/assist/format", json={
            "text": ""
        })
        assert resp.status_code == 422

    def test_check_code_empty(self, test_client):
        """Empty code check returns validation error."""
        resp = test_client.post("/api/assist/check-code", json={
            "code": ""
        })
        assert resp.status_code == 422

    def test_compare_too_few_items(self, test_client):
        """Compare with less than 2 items returns validation error."""
        resp = test_client.post("/api/assist/compare", json={
            "items": [{"bookmark_id": "1", "title": "A", "summary": "test"}]
        })
        assert resp.status_code == 422
