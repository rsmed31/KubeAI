"""Agents API — the kubectl get pods / kubectl delete pod analogue for agent lifecycle management."""
from fastapi import APIRouter, HTTPException
from ..state import RuntimeState

router = APIRouter()


@router.get("/agents")
def list_agents() -> list[dict]:
    """List all agent instances in the cluster.

    Analogous to 'kubectl get pods' — returns the current state of all
    agent Pods managed by the KubeAI scheduler.
    """
    state = RuntimeState()
    return state.snapshot()["agents"]


@router.post("/agents/{agent_id}/terminate")
def terminate_agent(agent_id: str) -> dict:
    """Terminate a specific agent instance.

    Analogous to 'kubectl delete pod <name>' — gracefully terminates the
    agent and marks it as TERMINATED in the state store.
    """
    state = RuntimeState()
    success = state.terminate_agent(agent_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id!r} not found")
    return {"terminated": agent_id, "success": True}
