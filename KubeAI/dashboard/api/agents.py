"""Agents API — the kubectl get pods / kubectl delete pod analogue for agent lifecycle management."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from KubeAI.api.control_plane import ControlPlaneAPI
from KubeAI.dashboard.deps import get_control_plane

router = APIRouter()


@router.get("/agents")
def list_agents(cp: ControlPlaneAPI = Depends(get_control_plane)) -> list[dict]:
    """List all agent instances in the cluster.

    Analogous to 'kubectl get pods' — returns the current state of all
    agent Pods managed by the KubeAI scheduler.
    """
    return [
        {
            "id": a.agent_id,
            "name": a.name,
            "blueprint": a.metadata.get("blueprint", a.name.split("-")[0]),
            "state": a.state.upper(),
            "model_id": a.metadata.get("model", "unknown"),
            "tier": a.metadata.get("tier", "unknown"),
            "healthy": a.healthy,
            "load": a.load,
            "capabilities": list(a.capabilities),
            "mcp_servers": list(a.capabilities),
        }
        for a in cp.list_agents()
    ]


@router.post("/agents/{agent_id}/terminate")
def terminate_agent(
    agent_id: str,
    cp: ControlPlaneAPI = Depends(get_control_plane),
) -> dict:
    """Terminate a specific agent instance.

    Analogous to 'kubectl delete pod <name>' — gracefully terminates the
    agent and marks it as TERMINATED in the state store.
    """
    success = cp.terminate_agent(agent_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id!r} not found")
    return {"terminated": agent_id, "success": True}
