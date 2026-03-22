"""Integration tests — config and skills API routes via FastAPI TestClient.

The config router's internal helper functions (_get_config_store and
_get_skill_registry) delegate to get_runtime().  We monkey-patch those helpers
at the module level so the routes talk to fresh in-memory instances instead of
booting the full runtime.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from KubeAI.config.skill import SkillRegistry
from KubeAI.config.store import ConfigStore
import KubeAI.dashboard.api.config as config_module
from KubeAI.dashboard.api.config import router as config_router
from KubeAI.dashboard.api.config import skills_router


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def config_store() -> ConfigStore:
    return ConfigStore(dsn="")


@pytest.fixture()
def skill_registry() -> SkillRegistry:
    return SkillRegistry(dsn="")


@pytest.fixture()
def client(config_store: ConfigStore, skill_registry: SkillRegistry) -> TestClient:
    """Build a minimal FastAPI app with config + skills routers and patched deps."""
    app = FastAPI()
    app.include_router(config_router)
    app.include_router(skills_router)

    # Patch the module-level helper functions so they return our test instances
    # rather than bootstrapping the full production runtime.
    config_module._get_config_store = lambda: config_store      # noqa: SLF001
    config_module._get_skill_registry = lambda: skill_registry  # noqa: SLF001

    return TestClient(app, raise_server_exceptions=True)


# ---------------------------------------------------------------------------
# Config route tests
# ---------------------------------------------------------------------------

class TestConfigRoutes:

    def test_get_config_returns_200_with_dict(self, client: TestClient) -> None:
        """GET /api/config must return 200 and a non-empty dict."""
        response = client.get("/api/config")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)
        # Defaults are always loaded
        assert len(data) > 0

    def test_put_config_persists_value(self, client: TestClient) -> None:
        """PUT /api/config/{key} stores the value and returns the expected shape."""
        response = client.put(
            "/api/config/integration.test_key",
            json={"value": "test_value", "category": "integration"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["key"] == "integration.test_key"
        assert body["value"] == "test_value"
        assert body["status"] == "updated"

    def test_get_config_by_key_returns_stored_value(self, client: TestClient) -> None:
        """GET /api/config/{key} returns the value that was previously PUT."""
        client.put(
            "/api/config/roundtrip.key",
            json={"value": 42, "category": "test"},
        )
        response = client.get("/api/config/roundtrip.key")
        assert response.status_code == 200
        body = response.json()
        assert body["key"] == "roundtrip.key"
        assert body["value"] == 42

    def test_get_config_missing_key_returns_404(self, client: TestClient) -> None:
        """GET /api/config/{key} returns 404 for unknown keys."""
        response = client.get("/api/config/totally.nonexistent.key")
        assert response.status_code == 404

    def test_put_config_boolean_value(self, client: TestClient) -> None:
        """PUT /api/config/{key} handles boolean values correctly."""
        client.put(
            "/api/config/feature.enabled",
            json={"value": True, "category": "features"},
        )
        response = client.get("/api/config/feature.enabled")
        assert response.status_code == 200
        assert response.json()["value"] is True

    def test_put_config_dict_value(self, client: TestClient) -> None:
        """PUT /api/config/{key} handles nested dict values."""
        payload = {"chunk_size": 256, "overlap": 32}
        client.put(
            "/api/config/rag.chunking_strategy",
            json={"value": payload, "category": "rag"},
        )
        response = client.get("/api/config/rag.chunking_strategy")
        assert response.status_code == 200
        assert response.json()["value"] == payload

    def test_delete_config_removes_key(self, client: TestClient) -> None:
        """DELETE /api/config/{key} removes the key and subsequent GET returns 404."""
        client.put(
            "/api/config/to.delete",
            json={"value": "bye", "category": "test"},
        )
        del_response = client.delete("/api/config/to.delete")
        assert del_response.status_code == 200
        assert del_response.json()["status"] == "deleted"

        get_response = client.get("/api/config/to.delete")
        assert get_response.status_code == 404

    def test_delete_config_missing_key_returns_404(self, client: TestClient) -> None:
        """DELETE on a non-existent key returns 404."""
        response = client.delete("/api/config/does.not.exist")
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Skills route tests
# ---------------------------------------------------------------------------

class TestSkillsRoutes:

    def test_get_skills_returns_list(self, client: TestClient) -> None:
        """GET /api/skills returns 200 and an empty list initially."""
        response = client.get("/api/skills")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_post_skill_creates_skill(self, client: TestClient) -> None:
        """POST /api/skills creates a skill and returns it with all required fields."""
        response = client.post(
            "/api/skills",
            json={
                "name": "code_review",
                "description": "Reviews Python code",
                "system_prompt": "You are a strict code reviewer.",
                "mcp_tools": ["linter"],
                "tags": ["code", "quality"],
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["name"] == "code_review"
        assert body["description"] == "Reviews Python code"
        assert body["system_prompt"] == "You are a strict code reviewer."
        assert "code" in body["tags"]
        assert "skill_id" in body
        assert body["enabled"] is True

    def test_post_skill_appears_in_list(self, client: TestClient) -> None:
        """A created skill is visible in GET /api/skills."""
        client.post("/api/skills", json={"name": "listed_skill"})
        response = client.get("/api/skills")
        names = [s["name"] for s in response.json()]
        assert "listed_skill" in names

    def test_get_skill_by_id_returns_correct_skill(self, client: TestClient) -> None:
        """GET /api/skills/{skill_id} returns the exact skill that was created."""
        create_resp = client.post("/api/skills", json={"name": "fetch_me", "description": "desc"})
        skill_id = create_resp.json()["skill_id"]

        response = client.get(f"/api/skills/{skill_id}")
        assert response.status_code == 200
        assert response.json()["skill_id"] == skill_id
        assert response.json()["name"] == "fetch_me"

    def test_get_skill_missing_id_returns_404(self, client: TestClient) -> None:
        """GET /api/skills/{skill_id} returns 404 for an unknown id."""
        response = client.get("/api/skills/nonexistent-id")
        assert response.status_code == 404

    def test_put_skill_updates_fields(self, client: TestClient) -> None:
        """PUT /api/skills/{skill_id} updates the specified fields."""
        create_resp = client.post("/api/skills", json={"name": "old_name"})
        skill_id = create_resp.json()["skill_id"]

        update_resp = client.put(
            f"/api/skills/{skill_id}",
            json={"name": "new_name", "tags": ["updated"]},
        )
        assert update_resp.status_code == 200
        body = update_resp.json()
        assert body["name"] == "new_name"
        assert "updated" in body["tags"]

    def test_delete_skill_removes_it(self, client: TestClient) -> None:
        """DELETE /api/skills/{skill_id} removes the skill from the registry."""
        create_resp = client.post("/api/skills", json={"name": "to_delete"})
        skill_id = create_resp.json()["skill_id"]

        del_resp = client.delete(f"/api/skills/{skill_id}")
        assert del_resp.status_code == 200
        assert del_resp.json()["status"] == "deleted"

        get_resp = client.get(f"/api/skills/{skill_id}")
        assert get_resp.status_code == 404

    def test_delete_skill_missing_id_returns_404(self, client: TestClient) -> None:
        """DELETE on an unknown skill_id returns 404."""
        response = client.delete("/api/skills/no-such-skill")
        assert response.status_code == 404
