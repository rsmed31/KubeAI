"""Overview API — the kubectl cluster-info analogue: high-level cluster health summary."""

from __future__ import annotations

import time

from fastapi import APIRouter, Depends

from KubeAI.api.control_plane import ControlPlaneAPI
from KubeAI.dashboard.deps import get_control_plane

router = APIRouter()

_start_time = time.time()


@router.get("/overview")
def get_overview(cp: ControlPlaneAPI = Depends(get_control_plane)) -> dict:
    """Return a high-level overview of the KubeAI cluster state.

    Analogous to 'kubectl cluster-info' — provides a quick health snapshot
    of all running agents, active tasks, and overall system health.
    """
    data = cp.get_overview()
    agents_list = cp.list_agents()
    tasks_list = cp.list_tasks(limit=1000)

    running = sum(1 for a in agents_list if a.state == "running")
    idle = sum(1 for a in agents_list if a.state == "idle")
    terminated = sum(1 for a in agents_list if a.state == "terminated")

    task_queued = sum(1 for t in tasks_list if t.status == "queued")
    task_running = sum(1 for t in tasks_list if t.status in ("running", "routing", "assigned"))
    task_complete = sum(1 for t in tasks_list if t.status == "complete")
    task_failed = sum(1 for t in tasks_list if t.status == "failed")

    active = running + idle
    health = "healthy" if active > 0 else "degraded"

    return {
        "agents": {
            "total": len(agents_list),
            "running": running,
            "idle": idle,
            "terminated": terminated,
        },
        "tasks": {
            "total": len(tasks_list),
            "queued": task_queued,
            "running": task_running,
            "complete": task_complete,
            "failed": task_failed,
        },
        "uptime_s": time.time() - _start_time,
        "health": health,
        "avg_latency_ms": data.get("avg_latency_ms", 0.0),
        "avg_eval_score": data.get("avg_eval_score", 0.0),
    }
