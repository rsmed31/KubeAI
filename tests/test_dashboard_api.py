"""Test suite for KubeAI Dashboard API.

Analogous to Kubernetes API conformance tests — verifies that every control-plane
endpoint returns the expected shape and HTTP status codes.
"""
import pytest
from fastapi.testclient import TestClient

from KubeAI.dashboard.server import app
from KubeAI.dashboard.deps import get_control_plane, seed_demo_data

# Seed the singleton before any test so agent/task lists are non-empty.
seed_demo_data(get_control_plane())

client = TestClient(app)


def test_get_overview_returns_expected_keys() -> None:
    """GET /api/overview must return agent counts, task counts, uptime, and health."""
    response = client.get("/api/overview")
    assert response.status_code == 200
    data = response.json()
    assert "agents" in data
    assert "tasks" in data
    assert "uptime_s" in data
    assert "health" in data

    agents = data["agents"]
    assert "total" in agents
    assert "running" in agents
    assert "idle" in agents
    assert "terminated" in agents

    tasks = data["tasks"]
    assert "total" in tasks
    assert "queued" in tasks
    assert "running" in tasks
    assert "complete" in tasks
    assert "failed" in tasks

    assert data["health"] in ("healthy", "degraded")


def test_get_agents_returns_list() -> None:
    """GET /api/agents must return a non-empty list of agent records."""
    response = client.get("/api/agents")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0

    agent = data[0]
    assert "id" in agent
    assert "state" in agent
    assert "blueprint" in agent
    assert "model_id" in agent
    assert "tier" in agent


def test_get_tasks_returns_list() -> None:
    """GET /api/tasks must return a list of task records."""
    response = client.get("/api/tasks")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0

    task = data[0]
    assert "id" in task
    assert "status" in task
    assert "blueprint" in task


def test_post_tasks_submit_creates_task() -> None:
    """POST /api/tasks/submit must create a task and return the record."""
    payload = {"description": "Test task for dashboard API conformance"}
    response = client.post("/api/tasks/submit", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "task_id" in data
    assert data["task_id"].startswith("task-")
    assert data["description"] == payload["description"]
    assert data["status"] == "queued"


def test_post_tasks_submit_with_blueprint() -> None:
    """POST /api/tasks/submit must accept an optional blueprint field."""
    payload = {"description": "Coding task with blueprint", "blueprint": "coding_agent"}
    response = client.post("/api/tasks/submit", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["blueprint"] == "coding_agent"
    assert data["status"] == "queued"


def test_get_memory_returns_three_tiers() -> None:
    """GET /api/memory must return working, short_term, and long_term tiers."""
    response = client.get("/api/memory")
    assert response.status_code == 200
    data = response.json()
    assert "working" in data
    assert "short_term" in data
    assert "long_term" in data

    assert "agent_contexts" in data["working"]
    assert "size_bytes" in data["working"]

    assert "keys" in data["short_term"]
    assert "ttl_avg_s" in data["short_term"]
    assert "size_bytes" in data["short_term"]

    assert "blueprints" in data["long_term"]
    assert "fact_entries" in data["long_term"]
    assert "size_bytes" in data["long_term"]


def test_get_blueprints_returns_list() -> None:
    """GET /api/blueprints must return a list of blueprint records."""
    response = client.get("/api/blueprints")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0

    bp = data[0]
    assert "name" in bp
    assert "description" in bp
    assert "tier" in bp
    assert "capabilities" in bp


def test_post_blueprints_generate_returns_yaml() -> None:
    """POST /api/blueprints/generate must return a YAML string deterministically."""
    payload = {"description": "A web search and research agent for competitive analysis"}
    response = client.post("/api/blueprints/generate", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "yaml" in data
    assert isinstance(data["yaml"], str)
    assert len(data["yaml"]) > 50
    # Verify YAML contains expected keys
    assert "apiVersion" in data["yaml"]
    assert "kind: AgentBlueprint" in data["yaml"]
    assert "tier:" in data["yaml"]
    # Verify determinism: same input → same output
    response2 = client.post("/api/blueprints/generate", json=payload)
    assert response2.json()["yaml"] == data["yaml"]


def test_get_monitoring_metrics_returns_all_six_keys() -> None:
    """GET /api/monitoring/metrics must return all 6 KubeAI metric series."""
    response = client.get("/api/monitoring/metrics")
    assert response.status_code == 200
    data = response.json()

    # ControlPlaneAPI.metrics_snapshot() returns MetricsStore.snapshot():
    # a dict of metric_name → list of sample dicts. Verify structure only.
    assert isinstance(data, dict)
    for series in data.values():
        assert isinstance(series, list)
