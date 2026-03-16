"""Unit tests for ControlPlaneAPI: control-plane read models, events, and Prometheus metrics integration."""

from __future__ import annotations

from typing import Any

import pytest

from KubeAI.api import ControlPlaneAPI
from KubeAI.orchestrator.a2a_pool import A2AAgentCard


def _card(
    agent_id: str,
    *,
    name: str = "research-agent",
    description: str = "research assistant",
    state_capability: str = "rag_retrieval",
    blueprint: str | None = "research_agent",
) -> A2AAgentCard:
    metadata: dict[str, Any] = {}
    if blueprint is not None:
        metadata["blueprint"] = blueprint
    return A2AAgentCard(
        agent_id=agent_id,
        name=name,
        endpoint=f"http://agents/{agent_id}",
        capabilities=frozenset({state_capability}),
        description=description,
        metadata=metadata,
    )


def _metric_value(
    snapshot: dict[str, list[dict[str, object]]],
    bucket: str,
    name: str,
    labels: dict[str, str],
) -> float:
    for item in snapshot[bucket]:
        if item["name"] == name and item["labels"] == labels:
            return float(item["value"]) if "value" in item else float(item.get("sum", 0.0))
    return 0.0


def _hist_entry(
    snapshot: dict[str, list[dict[str, object]]],
    name: str,
    labels: dict[str, str],
) -> dict[str, object] | None:
    for item in snapshot["histograms"]:
        if item["name"] == name and item["labels"] == labels:
            return item
    return None


class TestControlPlaneAgents:
    def test_register_agent_updates_metrics_and_events(self) -> None:
        api = ControlPlaneAPI()

        record = api.register_agent(_card("agent-1"))

        assert record.agent_id == "agent-1"
        assert len(api.list_agents()) == 1

        snapshot = api.metrics_snapshot()
        assert (
            _metric_value(
                snapshot,
                "counters",
                "KubeAI_agent_spawns_total",
                {"blueprint": "research_agent"},
            )
            == 1.0
        )
        assert (
            _metric_value(
                snapshot,
                "gauges",
                "KubeAI_agent_pool_size",
                {"blueprint": "research_agent", "state": "running"},
            )
            == 1.0
        )

        events = api.list_events(limit=10)
        assert len(events) == 1
        assert events[0]["event_type"] == "agent.registered"

    def test_update_agent_state_refreshes_pool_size(self) -> None:
        api = ControlPlaneAPI()
        api.register_agent(_card("agent-1"))

        updated = api.update_agent_state("agent-1", state="failed", healthy=False, load=0.95)

        assert updated.state == "failed"
        assert updated.healthy is False
        assert updated.load == pytest.approx(0.95)

        snapshot = api.metrics_snapshot()
        assert (
            _metric_value(
                snapshot,
                "gauges",
                "KubeAI_agent_pool_size",
                {"blueprint": "research_agent", "state": "running"},
            )
            == 0.0
        )
        assert (
            _metric_value(
                snapshot,
                "gauges",
                "KubeAI_agent_pool_size",
                {"blueprint": "research_agent", "state": "failed"},
            )
            == 1.0
        )

    def test_get_unknown_agent_raises(self) -> None:
        api = ControlPlaneAPI()

        with pytest.raises(KeyError, match="not registered"):
            api.get_agent("missing")

        with pytest.raises(KeyError, match="not registered"):
            api.update_agent_state("missing", state="running")


class TestControlPlaneTasks:
    def test_record_task_result_updates_metrics_and_task_feed(self) -> None:
        api = ControlPlaneAPI()

        task = api.record_task_result(
            task_id="task-1",
            blueprint="coding_agent",
            status="complete",
            latency_ms=123.5,
            token_cost=0.012,
            eval_score=0.89,
            agent_id="agent-77",
        )

        assert task.task_id == "task-1"
        assert task.status == "complete"

        snapshot = api.metrics_snapshot()
        assert (
            _metric_value(
                snapshot,
                "counters",
                "KubeAI_tasks_total",
                {"blueprint": "coding_agent", "status": "complete"},
            )
            == 1.0
        )
        assert (
            _metric_value(
                snapshot,
                "counters",
                "KubeAI_token_cost_total",
                {"blueprint": "coding_agent", "provider": "unknown"},
            )
            == pytest.approx(0.012)
        )

        latency_hist = _hist_entry(
            snapshot,
            "KubeAI_task_latency_ms",
            {"blueprint": "coding_agent"},
        )
        assert latency_hist is not None
        assert int(latency_hist["count"]) == 1
        assert float(latency_hist["sum"]) == pytest.approx(123.5)

        eval_hist = _hist_entry(snapshot, "KubeAI_eval_score", {"blueprint": "coding_agent"})
        assert eval_hist is not None
        assert float(eval_hist["sum"]) == pytest.approx(0.89)

        tasks = api.list_tasks(limit=5)
        assert len(tasks) == 1
        assert tasks[0].agent_id == "agent-77"

    def test_list_tasks_honors_limit(self) -> None:
        api = ControlPlaneAPI()

        for i in range(5):
            api.record_task_result(
                task_id=f"task-{i}",
                blueprint="research_agent",
                status="complete",
                latency_ms=float(i + 1),
                token_cost=0.001,
            )

        tasks = api.list_tasks(limit=2)
        assert [task.task_id for task in tasks] == ["task-3", "task-4"]


class TestControlPlaneOverviewAndEvents:
    def test_overview_reports_active_agents_and_averages(self) -> None:
        api = ControlPlaneAPI()

        api.register_agent(_card("agent-1", blueprint="coding_agent"), state="running")
        api.register_agent(_card("agent-2", blueprint="coding_agent"), state="idle")
        api.register_agent(_card("agent-3", blueprint="coding_agent"), state="terminated")

        api.record_task_result(
            task_id="task-1",
            blueprint="coding_agent",
            status="complete",
            latency_ms=100.0,
            token_cost=0.01,
            eval_score=0.8,
        )
        api.record_task_result(
            task_id="task-2",
            blueprint="coding_agent",
            status="complete",
            latency_ms=300.0,
            token_cost=0.02,
            eval_score=1.0,
        )

        overview = api.get_overview()

        assert overview["agents_total"] == 3
        assert overview["active_agents"] == 2
        assert overview["tasks_total"] == 2
        assert overview["avg_latency_ms"] == pytest.approx(200.0)
        assert overview["avg_eval_score"] == pytest.approx(0.9)
        assert isinstance(overview["latest_event_id"], str)

    def test_event_filters_and_cursor_work(self) -> None:
        api = ControlPlaneAPI()

        api.register_agent(_card("agent-1"))
        api.record_task_result(
            task_id="task-1",
            blueprint="research_agent",
            status="complete",
            latency_ms=10.0,
            token_cost=0.001,
        )
        api.record_task_result(
            task_id="task-2",
            blueprint="research_agent",
            status="complete",
            latency_ms=20.0,
            token_cost=0.001,
        )

        all_events = api.list_events(limit=10)
        task_events = api.list_events(limit=10, event_type="task.recorded")
        after_first = api.list_events(limit=10, after_event_id=all_events[0]["event_id"])

        assert len(all_events) == 3
        assert len(task_events) == 2
        assert all(event["event_type"] == "task.recorded" for event in task_events)
        assert len(after_first) == 2

    def test_blueprint_inferred_from_agent_name_when_metadata_missing(self) -> None:
        api = ControlPlaneAPI()
        card = _card(
            "agent-9",
            name="writing-agent-1",
            blueprint=None,
            description="writer",
        )

        api.register_agent(card)

        snapshot = api.metrics_snapshot()
        assert (
            _metric_value(
                snapshot,
                "counters",
                "KubeAI_agent_spawns_total",
                {"blueprint": "writing"},
            )
            == 1.0
        )

    def test_metrics_text_contains_prometheus_samples(self) -> None:
        api = ControlPlaneAPI()
        api.record_task_result(
            task_id="task-1",
            blueprint="research_agent",
            status="complete",
            latency_ms=10.0,
            token_cost=0.001,
        )

        text = api.metrics_text()

        assert 'KubeAI_tasks_total{blueprint="research_agent",status="complete"} 1.0' in text
        assert 'KubeAI_task_latency_ms_count{blueprint="research_agent"} 1.0' in text
