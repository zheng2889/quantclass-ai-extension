"""Tests for authentication system."""

import pytest


class TestAuthLogin:
    """Login endpoint tests."""

    def test_login_success(self, test_client):
        """Login with correct credentials returns token."""
        resp = test_client.post("/api/auth/login", json={
            "username": "admin",
            "password": "admin123"
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 0
        data = body["data"]
        assert "token" in data
        assert data["user"]["username"] == "admin"
        assert data["user"]["role"] == "admin"

    def test_login_wrong_password(self, test_client):
        """Login with wrong password returns 401."""
        resp = test_client.post("/api/auth/login", json={
            "username": "admin",
            "password": "wrongpass"
        })
        assert resp.status_code == 401

    def test_login_nonexistent_user(self, test_client):
        """Login with non-existent user returns 401."""
        resp = test_client.post("/api/auth/login", json={
            "username": "nobody",
            "password": "admin123"
        })
        assert resp.status_code == 401

    def test_login_empty_fields(self, test_client):
        """Login with empty fields returns 422."""
        resp = test_client.post("/api/auth/login", json={
            "username": "",
            "password": ""
        })
        assert resp.status_code == 422


def _get_admin_token(test_client) -> str:
    """Helper: log in as admin and return token."""
    resp = test_client.post("/api/auth/login", json={
        "username": "admin",
        "password": "admin123"
    })
    return resp.json()["data"]["token"]


class TestAuthMe:
    """GET /api/auth/me tests."""

    def test_me_with_valid_token(self, test_client):
        """Access /me with valid token returns user info."""
        token = _get_admin_token(test_client)
        resp = test_client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 0
        assert body["data"]["username"] == "admin"
        assert body["data"]["role"] == "admin"

    def test_me_without_token(self, test_client):
        """Access /me without token returns 401/403."""
        resp = test_client.get("/api/auth/me")
        assert resp.status_code in (401, 403)

    def test_me_with_invalid_token(self, test_client):
        """Access /me with invalid token returns 401."""
        resp = test_client.get(
            "/api/auth/me",
            headers={"Authorization": "Bearer invalid.token.here"}
        )
        assert resp.status_code == 401


class TestChangePassword:
    """POST /api/auth/change-password tests."""

    def test_change_password_success(self, test_client):
        """Change password with correct old password succeeds."""
        token = _get_admin_token(test_client)
        resp = test_client.post(
            "/api/auth/change-password",
            json={"old_password": "admin123", "new_password": "newpass123"},
            headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 200
        assert resp.json()["code"] == 0

        # Can login with new password
        resp2 = test_client.post("/api/auth/login", json={
            "username": "admin",
            "password": "newpass123"
        })
        assert resp2.status_code == 200

        # Restore original password for other tests
        token2 = resp2.json()["data"]["token"]
        test_client.post(
            "/api/auth/change-password",
            json={"old_password": "newpass123", "new_password": "admin123"},
            headers={"Authorization": f"Bearer {token2}"}
        )

    def test_change_password_wrong_old(self, test_client):
        """Change password with wrong old password returns 400."""
        token = _get_admin_token(test_client)
        resp = test_client.post(
            "/api/auth/change-password",
            json={"old_password": "wrongpass", "new_password": "newpass123"},
            headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 400

    def test_change_password_too_short(self, test_client):
        """New password shorter than 6 chars returns 422."""
        token = _get_admin_token(test_client)
        resp = test_client.post(
            "/api/auth/change-password",
            json={"old_password": "admin123", "new_password": "short"},
            headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 422


class TestAdminProtection:
    """Admin endpoints require admin auth."""

    def test_stats_without_token(self, test_client):
        """GET /api/admin/stats without token returns 401/403."""
        resp = test_client.get("/api/admin/stats")
        assert resp.status_code in (401, 403)

    def test_stats_with_admin_token(self, test_client):
        """GET /api/admin/stats with admin token returns 200."""
        token = _get_admin_token(test_client)
        resp = test_client.get(
            "/api/admin/stats",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 200
        assert resp.json()["code"] == 0

    def test_reindex_without_token(self, test_client):
        """POST /api/admin/reindex without token returns 401/403."""
        resp = test_client.post("/api/admin/reindex")
        assert resp.status_code in (401, 403)

    def test_reindex_with_admin_token(self, test_client):
        """POST /api/admin/reindex with admin token returns 200."""
        token = _get_admin_token(test_client)
        resp = test_client.post(
            "/api/admin/reindex",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 200

    def test_llm_logs_without_token(self, test_client):
        """GET /api/admin/logs/llm without token returns 401/403."""
        resp = test_client.get("/api/admin/logs/llm")
        assert resp.status_code in (401, 403)

    def test_llm_logs_with_admin_token(self, test_client):
        """GET /api/admin/logs/llm with admin token returns 200."""
        token = _get_admin_token(test_client)
        resp = test_client.get(
            "/api/admin/logs/llm",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 200
