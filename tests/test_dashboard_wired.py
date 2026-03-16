"""Integration tests verifying dashboard routes read from ControlPlaneAPI, not demo RuntimeState."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from KubeAI.api.control_plane import AgentRecord
from KubeAI.dashboard.server import app
from KubeAI.dashboard.deps import get_control_plane


@pytest.fixture(scope="module")
def client() -> TestClient:
    """TestClient with minimal seeded control-plane data."""
    cp = get_control_plane()
    # Seed one agent record so agent-dependent tests have data
    agent_id = f"agent-{uuid.uuid4().hex[:8]}"
    cp._agents[agent_id] = AgentRecord(  # noqa: SLF001
        agent_id=agent_id,
        name="wired-test-agent",
        description="Test agent",
        state="idle",
        healthy=True,
        load=0.0,
        capabilities=(),
        metadata={"blueprint": "general_agent", "model": "claude-haiku-4-5-20251001", "tier": "fast"},
    )
    return TestClient(app)


class TestOverviewWired:
    def test_returns_expected_keys(self, client: TestClient) -> None:
        r = client.get("/api/overview")
        assert r.status_code == 200
        data = r.json()
        assert "agents" in data
        assert "tasks" in data
        assert "health" in data
        assert "uptime_s" in data

    def test_agents_section_has_counts(self, client: TestClient) -> None:
        r = client.get("/api/overview")
        agents = r.json()["agents"]
        assert "total" in agents
        assert "running" in agents
        assert agents["total"] >= 0


class TestAgentsWired:
    def test_returns_list(self, client: TestClient) -> None:
        r = client.get("/api/agents")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_agents_have_required_fields(self, client: TestClient) -> None:
        r = client.get("/api/agents")
        data = r.json()
        if data:
            agent = data[0]
            assert "id" in agent
            assert "state" in agent
            assert "blueprint" in agent

    def test_terminate_nonexistent_returns_404(self, client: TestClient) -> None:
        r = client.post("/api/agents/nonexistent-ghost/terminate")
        assert r.status_code == 404


class TestTasksWired:
    def test_returns_list(self, client: TestClient) -> None:
        r = client.get("/api/tasks")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_submit_creates_task(self, client: TestClient) -> None:
        r = client.post("/api/tasks/submit", json={"description": "test task from wired test"})
        assert r.status_code == 200
        data = r.json()
        assert "task_id" in data
        assert data["status"] == "queued"

    def test_submit_with_blueprint(self, client: TestClient) -> None:
        r = client.post(
            "/api/tasks/submit",
            json={"description": "blueprint task", "blueprint": "coding_agent"},
        )
        assert r.status_code == 200
        assert r.json()["blueprint"] == "coding_agent"


class TestMemoryWired:
    def test_returns_three_tiers(self, client: TestClient) -> None:
        r = client.get("/api/memory")
        assert r.status_code == 200
        data = r.json()
        assert "working" in data
        assert "short_term" in data
        assert "long_term" in data


class TestMonitoringWired:
    def test_metrics_returns_dict(self, client: TestClient) -> None:
        r = client.get("/api/monitoring/metrics")
        assert r.status_code == 200
        assert isinstance(r.json(), dict)

    def test_prometheus_endpoint_returns_text(self, client: TestClient) -> None:
        r = client.get("/api/monitoring/metrics/prometheus")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/plain")
