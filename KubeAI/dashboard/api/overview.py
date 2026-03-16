"""Overview API — the kubectl cluster-info analogue: high-level cluster health summary."""
import time
from fastapi import APIRouter
from ..state import RuntimeState

router = APIRouter()

_start_time = time.time()


@router.get("/overview")
def get_overview() -> dict:
    """Return a high-level overview of the KubeAI cluster state.

    Analogous to 'kubectl cluster-info' — provides a quick health snapshot
    of all running agents, active tasks, and overall system health.
    """
    state = RuntimeState()
    snap = state.snapshot()

    agents = snap["agents"]
    tasks = snap["tasks"]

    running = sum(1 for a in agents if a["state"] == "RUNNING")
    idle = sum(1 for a in agents if a["state"] == "IDLE")
    terminated = sum(1 for a in agents if a["state"] == "TERMINATED")

    task_queued = sum(1 for t in tasks if t["status"] == "QUEUED")
    task_running = sum(1 for t in tasks if t["status"] in ("RUNNING", "ROUTING", "ASSIGNED"))
    task_complete = sum(1 for t in tasks if t["status"] == "COMPLETE")
    task_failed = sum(1 for t in tasks if t["status"] == "FAILED")

    active_agents = running + idle
    health = "healthy" if active_agents > 0 and task_failed == 0 else "degraded"

    return {
        "agents": {
            "total": len(agents),
            "running": running,
            "idle": idle,
            "terminated": terminated,
        },
        "tasks": {
            "total": len(tasks),
            "queued": task_queued,
            "running": task_running,
            "complete": task_complete,
            "failed": task_failed,
        },
        "uptime_s": time.time() - _start_time,
        "health": health,
    }
