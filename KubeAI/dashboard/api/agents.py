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
    tasks = cp.list_tasks(limit=2000)
    task_metrics: dict[str, dict[str, float | int]] = {}
    for task in tasks:
        if not task.agent_id:
            continue
        metrics = task_metrics.setdefault(
            task.agent_id,
            {"total": 0, "success": 0, "failed": 0, "latency_sum": 0.0},
        )
        metrics["total"] = int(metrics["total"]) + 1
        if task.status == "success":
            metrics["success"] = int(metrics["success"]) + 1
        if task.status == "failed":
            metrics["failed"] = int(metrics["failed"]) + 1
        metrics["latency_sum"] = float(metrics["latency_sum"]) + float(task.latency_ms)

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
            "mcp_servers": list(a.metadata.get("mcp_servers", [])),
            "memory": {
                "enabled": True,
                "namespace": a.agent_id,
            },
            "metrics": {
                "tasks_total": int(task_metrics.get(a.agent_id, {}).get("total", 0)),
                "tasks_success": int(task_metrics.get(a.agent_id, {}).get("success", 0)),
                "tasks_failed": int(task_metrics.get(a.agent_id, {}).get("failed", 0)),
                "avg_latency_ms": (
                    float(task_metrics[a.agent_id]["latency_sum"]) / float(task_metrics[a.agent_id]["total"])
                    if a.agent_id in task_metrics and float(task_metrics[a.agent_id]["total"]) > 0
                    else 0.0
                ),
            },
            "metadata": dict(a.metadata),
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


@router.delete("/agents/{agent_id}")
def terminate_agent_delete(
    agent_id: str,
    cp: ControlPlaneAPI = Depends(get_control_plane),
) -> dict:
    """Backward-compatible terminate endpoint used by some dashboard clients."""
    success = cp.terminate_agent(agent_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id!r} not found")
    return {"terminated": agent_id, "success": True}
