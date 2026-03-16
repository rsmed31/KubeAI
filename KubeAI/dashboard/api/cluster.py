"""Cluster API — Kubernetes-like routing API: submit tasks to a named cluster, route through the full stack, stream output.

Each 'cluster' is a named domain/namespace that has its own pool of agents.
The API accepts tasks, data, and URLs, routes them through the full KubeAI
stack automatically, and returns live progress + final output.

Analogous to a Kubernetes cluster API server endpoint:
  POST /api/clusters/{cluster}/tasks  →  submit a task
  GET  /api/clusters/{cluster}/tasks  →  list tasks
  GET  /api/clusters/{cluster}/status →  cluster health
  GET  /api/clusters             →  list all clusters
  GET  /api/pools                →  list all pool models + MCPs
  POST /api/pools/models         →  register a new model
  POST /api/pools/mcps           →  register a new MCP server
"""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from KubeAI.api.control_plane import ControlPlaneAPI
from KubeAI.dashboard.deps import Runtime, get_control_plane, get_runtime
from KubeAI.orchestrator.llm_pool import ModelEntry, ModelTier
from KubeAI.orchestrator.mcp_pool import MCPServer

router = APIRouter()


# ── Cluster task submission ────────────────────────────────────────────────

@router.post("/clusters/{cluster}/tasks")
async def submit_cluster_task(
    cluster: str,
    description: str = Form(...),
    blueprint: str = Form(None),
    file: UploadFile = File(None),
    url: str = Form(None),
    cp: ControlPlaneAPI = Depends(get_control_plane),
) -> dict[str, Any]:
    """Submit a task to a named cluster with optional file data and URL.

    Analogous to kubectl apply -f job.yaml --context=<cluster>.
    The task is routed through the full KubeAI stack automatically:
    intent analysis → blueprint routing → model assignment → agent spawn → execution.
    """
    data: str | None = None
    if file is not None:
        raw = await file.read()
        data = raw.decode("utf-8", errors="replace")

    result = cp.submit_task(
        description=description,
        blueprint=blueprint or None,
        data=data,
        data_url=url or None,
    )
    # Tag the task with its cluster context
    result["cluster"] = cluster
    return result


@router.get("/clusters/{cluster}/tasks")
def list_cluster_tasks(
    cluster: str,
    limit: int = 50,
    cp: ControlPlaneAPI = Depends(get_control_plane),
) -> list[dict[str, Any]]:
    """List tasks in a cluster with full stage and result data."""
    tasks = cp.list_tasks(limit=limit)
    return [
        {
            "id": t.task_id,
            "description": t.description,
            "status": t.status.upper(),
            "blueprint": t.blueprint,
            "agent_id": t.agent_id,
            "latency_ms": t.latency_ms,
            "result_text": t.result_text,
            "stages": cp._task_stages.get(t.task_id, []),  # noqa: SLF001
            "cluster": cluster,
        }
        for t in tasks
    ]


@router.get("/clusters/{cluster}/tasks/{task_id}")
def get_cluster_task(
    cluster: str,
    task_id: str,
    cp: ControlPlaneAPI = Depends(get_control_plane),
) -> dict[str, Any]:
    """Get a single task by ID with full stage history and result."""
    with cp._lock:  # noqa: SLF001
        task = cp._tasks.get(task_id)  # noqa: SLF001
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id!r} not found")
    return {
        "id": task.task_id,
        "description": task.description,
        "status": task.status.upper(),
        "blueprint": task.blueprint,
        "agent_id": task.agent_id,
        "latency_ms": task.latency_ms,
        "result_text": task.result_text,
        "stages": cp._task_stages.get(task_id, []),  # noqa: SLF001
        "cluster": cluster,
    }


@router.get("/clusters/{cluster}/status")
def cluster_status(
    cluster: str,
    cp: ControlPlaneAPI = Depends(get_control_plane),
) -> dict[str, Any]:
    """Return cluster health summary."""
    overview = cp.get_overview()
    overview["cluster"] = cluster
    overview["healthy"] = True
    return overview


@router.get("/clusters")
def list_clusters(cp: ControlPlaneAPI = Depends(get_control_plane)) -> list[dict[str, Any]]:
    """List all available clusters (currently a single default cluster)."""
    return [
        {
            "name": "default",
            "status": "healthy",
            "agents": len(cp.list_agents()),
            "tasks": len(cp.list_tasks(limit=1000)),
        }
    ]


# ── Pool management ────────────────────────────────────────────────────────

@router.get("/pools")
def list_pools(runtime: Runtime = Depends(get_runtime)) -> dict[str, Any]:
    """List all registered LLM models and MCP servers in both pools."""
    models = [
        {
            "model_id": m.model_id,
            "provider": m.provider,
            "tier": m.tier.value,
            "cost_per_1k": m.cost_per_1k_tokens,
            "load": m.load,
            "healthy": m.healthy,
            "description": m.description,
            "is_local": m.is_local,
        }
        for m in runtime.llm_pool.list_models()
    ]
    mcps = [
        {
            "server_id": s.server_id,
            "endpoint": s.endpoint,
            "capabilities": sorted(s.capabilities),
            "healthy": s.healthy,
            "description": s.description,
        }
        for s in runtime.mcp_pool.list_servers()
    ]
    return {"models": models, "mcps": mcps}


class RegisterModelRequest(BaseModel):
    model_id: str
    provider: str
    tier: str = "capable"
    cost_per_1k_tokens: float = 0.003
    description: str = ""
    is_local: bool = False


@router.post("/pools/models")
def register_model(
    body: RegisterModelRequest,
    runtime: Runtime = Depends(get_runtime),
) -> dict[str, Any]:
    """Register a new LLM model in the pool."""
    try:
        tier = ModelTier(body.tier)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid tier {body.tier!r}. Use: fast, capable, best")

    entry = ModelEntry(
        model_id=body.model_id,
        provider=body.provider,
        tier=tier,
        cost_per_1k_tokens=body.cost_per_1k_tokens,
        description=body.description,
        is_local=body.is_local,
    )
    runtime.llm_pool.register(entry)
    return {"status": "registered", "model_id": body.model_id, "tier": tier.value}


class RegisterMCPRequest(BaseModel):
    server_id: str
    endpoint: str
    capabilities: list[str]
    description: str = ""


@router.post("/pools/mcps")
def register_mcp(
    body: RegisterMCPRequest,
    runtime: Runtime = Depends(get_runtime),
) -> dict[str, Any]:
    """Register a new MCP server in the pool."""
    server = MCPServer(
        server_id=body.server_id,
        endpoint=body.endpoint,
        capabilities=frozenset(body.capabilities),
        description=body.description,
    )
    runtime.mcp_pool.register(server)
    return {"status": "registered", "server_id": body.server_id, "capabilities": body.capabilities}


@router.delete("/pools/models/{model_id}")
def remove_model(
    model_id: str,
    runtime: Runtime = Depends(get_runtime),
) -> dict[str, Any]:
    """Remove a model from the pool."""
    with runtime.llm_pool._lock:  # noqa: SLF001
        if model_id not in runtime.llm_pool._models:  # noqa: SLF001
            raise HTTPException(status_code=404, detail=f"Model {model_id!r} not found")
        del runtime.llm_pool._models[model_id]  # noqa: SLF001
    return {"status": "removed", "model_id": model_id}
