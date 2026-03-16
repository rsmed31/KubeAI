"""Dashboard dependency injection — the service-account analogue: one control-plane handle shared by all route handlers."""

from __future__ import annotations

import random
import time
import uuid

from KubeAI.api.control_plane import AgentRecord, ControlPlaneAPI, TaskRecord

# ── Singleton ──────────────────────────────────────────────────────────────
_control_plane = ControlPlaneAPI()


def get_control_plane() -> ControlPlaneAPI:
    """FastAPI dependency: returns the shared ControlPlaneAPI instance."""
    return _control_plane


# ── Demo seeder ────────────────────────────────────────────────────────────

def seed_demo_data(cp: ControlPlaneAPI | None = None) -> None:
    """Populate the control plane with realistic demo state on first startup."""
    cp = cp or _control_plane

    blueprints = ["research_agent", "coding_agent", "data_agent", "writing_agent"]
    models = [
        ("claude-haiku-4", "fast"),
        ("claude-sonnet-4", "capable"),
        ("claude-opus-4", "best"),
    ]
    states = ["running", "running", "idle", "running", "idle", "running"]
    now = time.time()

    # Register demo agents directly into the internal store to avoid the
    # A2AAgentCard dependency at startup.
    for i, state in enumerate(states):
        agent_id = f"agent-{uuid.uuid4().hex[:8]}"
        model_id, tier = models[i % len(models)]
        bp = blueprints[i % len(blueprints)]
        record = AgentRecord(
            agent_id=agent_id,
            name=f"{bp}-{agent_id[-4:]}",
            description=f"Demo {bp} instance",
            state=state,
            healthy=True,
            load=round(random.uniform(0.1, 0.7), 2),
            capabilities=("web_search",) if i % 2 == 0 else ("code_exec",),
            metadata={"blueprint": bp, "model": model_id, "tier": tier},
        )
        cp._agents[agent_id] = record  # noqa: SLF001

    # Record demo task completions
    task_descs = [
        ("Summarize Q3 earnings report", "research_agent", "complete", 2300.0, 0.012, 0.91),
        ("Debug authentication middleware", "coding_agent", "complete", 5100.0, 0.031, 0.87),
        ("Analyse customer churn data", "data_agent", "complete", 3800.0, 0.019, 0.94),
        ("Write product changelog", "writing_agent", "complete", 1700.0, 0.008, 0.89),
        ("Research competitor pricing", "research_agent", "complete", 4200.0, 0.024, 0.92),
    ]
    for desc, bp, status, latency, cost, score in task_descs:
        cp.record_task_result(
            task_id=f"task-{uuid.uuid4().hex[:8]}",
            blueprint=bp,
            status=status,
            latency_ms=latency,
            token_cost=cost,
            eval_score=score,
            agent_id=None,
        )

    # Add two in-flight tasks
    for desc, bp in [("Generate test suite for API", "coding_agent"), ("Draft support docs", "writing_agent")]:
        cp.submit_task(description=desc, blueprint=bp)
