"""Tests for health check endpoints (TC-H01, TC-H02)."""

import pytest


class TestHealthCheck:
    """Health check endpoint tests."""

    def test_health_check_ok(self, test_client):
        """TC-H01: Normal health check returns healthy."""
        resp = test_client.get("/api/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 0
        assert body["data"]["status"] == "healthy"
        assert body["data"]["sqlite"] == "connected"
        assert body["data"]["version"] == "0.1.0"

    def test_health_ready(self, test_client):
        """Readiness probe returns ready."""
        resp = test_client.get("/api/health/ready")
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 0
        assert body["data"]["ready"] is True

    def test_root_endpoint(self, test_client):
        """Root endpoint returns service info."""
        resp = test_client.get("/")
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 0
        assert body["data"]["service"] == "QuantClass Backend"

    def test_simple_health(self, test_client):
        """Root health check endpoint."""
        resp = test_client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["status"] == "healthy"
