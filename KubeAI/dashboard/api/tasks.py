"""Tasks API — the kubectl apply Job / kubectl get jobs analogue for task submission and tracking."""
from fastapi import APIRouter
from pydantic import BaseModel
from ..state import RuntimeState

router = APIRouter()


class TaskSubmitRequest(BaseModel):
    """Request body for task submission — analogous to a Job manifest."""

    description: str
    blueprint: str | None = None

    def __repr__(self) -> str:
        return f"TaskSubmitRequest(description={self.description[:40]!r}, blueprint={self.blueprint!r})"


@router.get("/tasks")
def list_tasks() -> list[dict]:
    """List all tasks in the cluster.

    Analogous to 'kubectl get jobs' — returns the full task history including
    queued, running, completed, and failed tasks.
    """
    state = RuntimeState()
    return state.snapshot()["tasks"]


@router.post("/tasks/submit")
def submit_task(body: TaskSubmitRequest) -> dict:
    """Submit a new task to the KubeAI scheduler.

    Analogous to 'kubectl apply -f job.yaml' — creates a new Task record,
    queues it for routing, and returns the initial task state.
    """
    state = RuntimeState()
    rec = state.add_task(description=body.description, blueprint=body.blueprint)
    return vars(rec)
