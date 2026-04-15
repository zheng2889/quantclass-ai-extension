"""Tests for /api/config endpoints."""

import pytest


class TestGetConfig:
    """GET /api/config returns sanitized config without raw API keys."""

    def test_get_config_basic(self, test_client):
        resp = test_client.get("/api/config")
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 0

        data = body["data"]
        assert "host" in data
        assert "port" in data
        assert "default_model" in data
        assert "default_provider" in data
        assert "providers" in data

    def test_get_config_providers_include_user_providers(self, test_client):
        resp = test_client.get("/api/config")
        providers = resp.json()["data"]["providers"]
        assert "openai" in providers
        assert "anthropic" in providers

    def test_get_config_does_not_leak_api_keys(self, test_client):
        """Response must never include raw api_key values."""
        resp = test_client.get("/api/config")
        body = resp.json()
        # Walk the entire response and assert no "api_key" field anywhere
        def _no_api_key(obj):
            if isinstance(obj, dict):
                assert "api_key" not in obj, f"api_key leaked in response: {obj}"
                for v in obj.values():
                    _no_api_key(v)
            elif isinstance(obj, list):
                for item in obj:
                    _no_api_key(item)

        _no_api_key(body)

    def test_get_config_reports_has_api_key_flag(self, test_client):
        """Each provider should have a boolean has_api_key flag."""
        resp = test_client.get("/api/config")
        providers = resp.json()["data"]["providers"]
        for pid, p in providers.items():
            assert "has_api_key" in p
            assert isinstance(p["has_api_key"], bool)

    def test_get_config_exposes_base_url_per_provider(self, test_client):
        """Every provider must expose a non-empty base_url string."""
        resp = test_client.get("/api/config")
        providers = resp.json()["data"]["providers"]
        assert len(providers) > 0
        for pid, p in providers.items():
            assert "base_url" in p, f"{pid} missing base_url"
            assert isinstance(p["base_url"], str), f"{pid}.base_url must be str"
            assert p["base_url"].startswith(("http://", "https://")), (
                f"{pid}.base_url looks malformed: {p['base_url']}"
            )


class TestUpdateConfig:
    """PUT /api/config applies partial updates."""

    def test_update_default_model(self, test_client):
        resp = test_client.put(
            "/api/config",
            json={"default_model": "gpt-5"}
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 0
        assert body["data"]["default_model"] == "gpt-5"

        # Verify persistence via GET
        resp2 = test_client.get("/api/config")
        assert resp2.json()["data"]["default_model"] == "gpt-5"

    def test_update_default_provider(self, test_client):
        resp = test_client.put(
            "/api/config",
            json={"default_provider": "openai"}
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["default_provider"] == "openai"

    def test_update_unknown_provider_rejected(self, test_client):
        resp = test_client.put(
            "/api/config",
            json={"default_provider": "totally_fake_provider"}
        )
        body = resp.json()
        assert body["code"] != 0  # Error
        assert "Unknown provider" in body["message"]

    def test_update_user_provider_api_key(self, test_client):
        """Updating an openai api_key should be accepted and not leak on GET."""
        resp = test_client.put(
            "/api/config",
            json={
                "providers": {
                    "openai": {"api_key": "sk-test-123456"}
                }
            }
        )
        assert resp.status_code == 200
        assert resp.json()["code"] == 0

        # GET should report has_api_key=True but not echo the key
        resp2 = test_client.get("/api/config")
        openai_cfg = resp2.json()["data"]["providers"]["openai"]
        assert openai_cfg["has_api_key"] is True
        assert "api_key" not in openai_cfg

    def test_update_unknown_provider_in_providers_dict_ignored(self, test_client):
        """Partial update referencing a non-existent provider should not 500."""
        resp = test_client.put(
            "/api/config",
            json={
                "providers": {
                    "ghost_provider": {"api_key": "x"}
                }
            }
        )
        assert resp.status_code == 200
        assert resp.json()["code"] == 0

    def test_update_user_provider_base_url_round_trip(self, test_client):
        """PUT /api/config with a custom base_url on a user provider must
        persist and be visible on the next GET."""
        custom = "https://proxy.internal.example.com/openai/v1"
        resp = test_client.put(
            "/api/config",
            json={
                "providers": {
                    "openai": {"base_url": custom}
                }
            }
        )
        assert resp.status_code == 200
        assert resp.json()["code"] == 0

        resp2 = test_client.get("/api/config")
        openai_cfg = resp2.json()["data"]["providers"]["openai"]
        assert openai_cfg["base_url"] == custom
        assert "api_key" not in openai_cfg

    def test_update_base_url_and_api_key_together(self, test_client):
        """Settings tab sends {base_url, api_key} in a single providers
        entry when both are changed. Both updates must land in one PUT."""
        resp = test_client.put(
            "/api/config",
            json={
                "providers": {
                    "moonshot": {
                        "base_url": "https://custom-kimi.example.com/v1",
                        "api_key": "sk-moonshot-round5-test",
                    }
                }
            }
        )
        assert resp.status_code == 200
        assert resp.json()["code"] == 0

        resp2 = test_client.get("/api/config")
        moonshot_cfg = resp2.json()["data"]["providers"]["moonshot"]
        assert moonshot_cfg["base_url"] == "https://custom-kimi.example.com/v1"
        assert moonshot_cfg["has_api_key"] is True

    def test_update_omitting_base_url_preserves_existing(self, test_client):
        """Omitting base_url from the payload must not wipe the existing URL."""
        custom = "https://pinned-openai.example.com/v1"
        test_client.put(
            "/api/config",
            json={"providers": {"openai": {"base_url": custom}}},
        )

        resp = test_client.put(
            "/api/config",
            json={
                "providers": {
                    "openai": {"api_key": "sk-keep-url-intact"}
                }
            }
        )
        assert resp.status_code == 200
        assert resp.json()["code"] == 0

        resp2 = test_client.get("/api/config")
        openai_cfg = resp2.json()["data"]["providers"]["openai"]
        assert openai_cfg["base_url"] == custom, (
            f"base_url was clobbered: expected {custom}, got {openai_cfg['base_url']}"
        )
