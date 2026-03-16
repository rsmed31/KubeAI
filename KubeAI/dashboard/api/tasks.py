"""Tasks API — the kubectl apply Job / kubectl get jobs analogue for task submission and tracking."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from KubeAI.api.control_plane import ControlPlaneAPI
from KubeAI.dashboard.deps import get_control_plane

router = APIRouter()


class TaskSubmitRequest(BaseModel):
    """Request body for task submission — analogous to a Job manifest."""

    description: str
    blueprint: str | None = None

    def __repr__(self) -> str:
        return f"TaskSubmitRequest(description={self.description[:40]!r}, blueprint={self.blueprint!r})"


@router.get("/tasks")
def list_tasks(cp: ControlPlaneAPI = Depends(get_control_plane)) -> list[dict]:
    """List all tasks in the cluster.

    Analogous to 'kubectl get jobs' — returns the full task history including
    queued, running, completed, and failed tasks.
    """
    return [
        {
            "id": t.task_id,
            "description": t.task_id,   # description not stored in TaskRecord; use id as proxy
            "status": t.status.upper(),
            "blueprint": t.blueprint,
            "agent_id": t.agent_id,
            "latency_ms": t.latency_ms,
            "eval_score": t.eval_score,
            "timestamp": t.timestamp,
        }
        for t in cp.list_tasks(limit=200)
    ]


@router.post("/tasks/submit")
def submit_task(
    body: TaskSubmitRequest,
    cp: ControlPlaneAPI = Depends(get_control_plane),
) -> dict:
    """Submit a new task to the KubeAI scheduler.

    Analogous to 'kubectl apply -f job.yaml' — creates a new Task record,
    queues it for routing, and returns the initial task state.
    """
    return cp.submit_task(description=body.description, blueprint=body.blueprint)
