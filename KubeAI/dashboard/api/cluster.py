"""Cluster API — multi-cluster Kubernetes-like routing.

Each cluster is an isolated Runtime with its own agent pool, task queue,
LLM pool, and MCP pool. Clusters can be created on demand and managed
independently via this API.

  GET  /api/clusters                    → list all clusters (high-level)
  POST /api/clusters                    → create a new cluster
  DELETE /api/clusters/{name}           → delete a cluster
  GET  /api/clusters/{cluster}/status   → cluster health + pool snapshot
  GET  /api/clusters/{cluster}/agents   → agents in this cluster
  POST /api/clusters/{cluster}/tasks    → submit task to this cluster
  GET  /api/clusters/{cluster}/tasks    → list tasks in this cluster
  GET  /api/clusters/{cluster}/tasks/{id} → single task detail
  GET  /api/clusters/{cluster}/pools    → pool models + MCPs for this cluster
  POST /api/clusters/{cluster}/pools/models → register model in this cluster
  POST /api/clusters/{cluster}/pools/mcps   → register MCP in this cluster

  GET  /api/pools                       → pools for the default cluster
  POST /api/pools/models                → register model in default cluster
  POST /api/pools/mcps                  → register MCP in default cluster
  DELETE /api/pools/models/{model_id}   → remove model from default cluster
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from KubeAI.api.control_plane import ControlPlaneAPI
from KubeAI.dashboard.deps import (
    ClusterConfig,
    ClusterRegistry,
    Runtime,
    get_cluster_registry,
    get_cluster_runtime,
    get_control_plane,
    get_runtime,
)
from KubeAI.orchestrator.llm_pool import ModelEntry, ModelTier
from KubeAI.orchestrator.mcp_pool import MCPServer

router = APIRouter()


# ── Cluster management ─────────────────────────────────────────────────────

@router.get("/clusters")
def list_clusters(
    reg: ClusterRegistry = Depends(get_cluster_registry),
) -> list[dict[str, Any]]:
    """List all clusters with high-level status snapshot."""
    return reg.snapshot()


class CreateClusterRequest(BaseModel):
    name: str
    description: str = ""
    num_workers: int = 4
    inherit_models: bool = True
    inherit_mcps: bool = True
    inherit_blueprints: bool = True


@router.post("/clusters")
def create_cluster(
    body: CreateClusterRequest,
    reg: ClusterRegistry = Depends(get_cluster_registry),
) -> dict[str, Any]:
    """Create a new isolated cluster runtime."""
    if reg.exists(body.name):
        raise HTTPException(status_code=409, detail=f"Cluster {body.name!r} already exists")
    if not body.name.replace("-", "").replace("_", "").isalnum():
        raise HTTPException(status_code=400, detail="Cluster name must be alphanumeric (hyphens/underscores allowed)")

    config = ClusterConfig(
        name=body.name,
        description=body.description,
        num_workers=body.num_workers,
        inherit_models=body.inherit_models,
        inherit_mcps=body.inherit_mcps,
        inherit_blueprints=body.inherit_blueprints,
    )
    reg.create(config)
    return {
        "status": "created",
        "name": body.name,
        "description": body.description,
        "num_workers": body.num_workers,
    }


@router.delete("/clusters/{cluster}")
def delete_cluster(
    cluster: str,
    reg: ClusterRegistry = Depends(get_cluster_registry),
) -> dict[str, Any]:
    """Delete a cluster. The 'default' cluster cannot be deleted."""
    if cluster == "default":
        raise HTTPException(status_code=403, detail="Cannot delete the default cluster")
    if not reg.delete(cluster):
        raise HTTPException(status_code=404, detail=f"Cluster {cluster!r} not found")
    return {"status": "deleted", "name": cluster}


@router.get("/clusters/{cluster}/status")
def cluster_status(
    cluster: str,
    reg: ClusterRegistry = Depends(get_cluster_registry),
) -> dict[str, Any]:
    """Detailed status for a single cluster."""
    try:
        rt = reg.get(cluster)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Cluster {cluster!r} not found")

    cp = rt.control_plane
    agents = cp.list_agents()
    tasks = cp.list_tasks(limit=1000)
    models = [
        {"model_id": m.model_id, "tier": m.tier.value, "healthy": m.healthy, "load": m.load}
        for m in rt.llm_pool.list_models()
    ]
    mcps = [
        {"server_id": s.server_id, "healthy": s.healthy, "capabilities": sorted(s.capabilities)}
        for s in rt.mcp_pool.list_servers()
    ]
    blueprints = [
        {"name": b.name, "tier": b.tier.value, "description": b.description}
        for b in rt.registry.list_blueprints()
    ]
    return {
        "name": cluster,
        "status": "healthy",
        "agents": {
            "total": len(agents),
            "running": sum(1 for a in agents if a.state == "running"),
            "idle": sum(1 for a in agents if a.state == "idle"),
        },
        "tasks": {
            "total": len(tasks),
            "queued": sum(1 for t in tasks if t.status == "queued"),
            "complete": sum(1 for t in tasks if t.status == "success"),
            "failed": sum(1 for t in tasks if t.status == "failed"),
        },
        "models": models,
        "mcps": mcps,
        "blueprints": blueprints,
    }


# ── Cluster agents ─────────────────────────────────────────────────────────

@router.get("/clusters/{cluster}/agents")
def list_cluster_agents(
    cluster: str,
    reg: ClusterRegistry = Depends(get_cluster_registry),
) -> list[dict[str, Any]]:
    """List agents in a specific cluster."""
    try:
        rt = reg.get(cluster)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Cluster {cluster!r} not found")
    agents = rt.control_plane.list_agents()
    return [
        {
            "id": a.agent_id,
            "name": a.name,
            "blueprint": a.metadata.get("blueprint", a.name),
            "state": a.state.upper(),
            "model_id": a.metadata.get("model", "unknown"),
            "tier": a.metadata.get("tier", "unknown"),
            "load": a.load,
            "healthy": a.healthy,
            "capabilities": list(a.capabilities),
            "cluster": cluster,
        }
        for a in agents
    ]


# ── Cluster task submission ────────────────────────────────────────────────

@router.post("/clusters/{cluster}/tasks")
async def submit_cluster_task(
    cluster: str,
    description: str = Form(...),
    blueprint: str = Form(None),
    file: UploadFile = File(None),
    url: str = Form(None),
    reg: ClusterRegistry = Depends(get_cluster_registry),
) -> dict[str, Any]:
    """Submit a task to a named cluster with optional file data and URL."""
    try:
        rt = reg.get(cluster)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Cluster {cluster!r} not found")

    data: str | None = None
    if file is not None:
        raw = await file.read()
        data = raw.decode("utf-8", errors="replace")

    result = rt.control_plane.submit_task(
        description=description,
        blueprint=blueprint or None,
        data=data,
        data_url=url or None,
    )
    result["cluster"] = cluster
    return result


@router.get("/clusters/{cluster}/tasks")
def list_cluster_tasks(
    cluster: str,
    limit: int = 100,
    reg: ClusterRegistry = Depends(get_cluster_registry),
) -> list[dict[str, Any]]:
    """List tasks in a specific cluster."""
    try:
        rt = reg.get(cluster)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Cluster {cluster!r} not found")

    cp = rt.control_plane
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
        for t in cp.list_tasks(limit=limit)
    ]


@router.get("/clusters/{cluster}/tasks/{task_id}")
def get_cluster_task(
    cluster: str,
    task_id: str,
    reg: ClusterRegistry = Depends(get_cluster_registry),
) -> dict[str, Any]:
    """Get a single task with full stage history and result."""
    try:
        rt = reg.get(cluster)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Cluster {cluster!r} not found")

    cp = rt.control_plane
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


# ── Per-cluster pool management ────────────────────────────────────────────

@router.get("/clusters/{cluster}/pools")
def cluster_pools(
    cluster: str,
    reg: ClusterRegistry = Depends(get_cluster_registry),
) -> dict[str, Any]:
    """List LLM models and MCP servers registered in a specific cluster."""
    try:
        rt = reg.get(cluster)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Cluster {cluster!r} not found")
    return {
        "models": [
            {
                "model_id": m.model_id, "provider": m.provider, "tier": m.tier.value,
                "cost_per_1k": m.cost_per_1k_tokens, "load": m.load, "healthy": m.healthy,
            }
            for m in rt.llm_pool.list_models()
        ],
        "mcps": [
            {
                "server_id": s.server_id, "endpoint": s.endpoint,
                "capabilities": sorted(s.capabilities), "healthy": s.healthy,
            }
            for s in rt.mcp_pool.list_servers()
        ],
    }


class RegisterModelRequest(BaseModel):
    model_id: str
    provider: str
    tier: str = "capable"
    cost_per_1k_tokens: float = 0.003
    description: str = ""
    is_local: bool = False


class RegisterMCPRequest(BaseModel):
    server_id: str
    endpoint: str
    capabilities: list[str]
    description: str = ""


@router.post("/clusters/{cluster}/pools/models")
def register_cluster_model(
    cluster: str,
    body: RegisterModelRequest,
    reg: ClusterRegistry = Depends(get_cluster_registry),
) -> dict[str, Any]:
    """Register an LLM model in a specific cluster's pool."""
    try:
        rt = reg.get(cluster)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Cluster {cluster!r} not found")
    try:
        tier = ModelTier(body.tier)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid tier {body.tier!r}")
    rt.llm_pool.register(ModelEntry(
        model_id=body.model_id, provider=body.provider, tier=tier,
        cost_per_1k_tokens=body.cost_per_1k_tokens,
        description=body.description, is_local=body.is_local,
    ))
    return {"status": "registered", "model_id": body.model_id, "cluster": cluster}


@router.post("/clusters/{cluster}/pools/mcps")
def register_cluster_mcp(
    cluster: str,
    body: RegisterMCPRequest,
    reg: ClusterRegistry = Depends(get_cluster_registry),
) -> dict[str, Any]:
    """Register an MCP server in a specific cluster's pool."""
    try:
        rt = reg.get(cluster)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Cluster {cluster!r} not found")
    rt.mcp_pool.register(MCPServer(
        server_id=body.server_id, endpoint=body.endpoint,
        capabilities=frozenset(body.capabilities), description=body.description,
    ))
    return {"status": "registered", "server_id": body.server_id, "cluster": cluster}


# ── Default-cluster pool management (backward compat) ─────────────────────

@router.get("/pools")
def list_pools(runtime: Runtime = Depends(get_runtime)) -> dict[str, Any]:
    """List pools for the default cluster."""
    return {
        "models": [
            {
                "model_id": m.model_id, "provider": m.provider, "tier": m.tier.value,
                "cost_per_1k": m.cost_per_1k_tokens, "load": m.load,
                "healthy": m.healthy, "description": m.description, "is_local": m.is_local,
            }
            for m in runtime.llm_pool.list_models()
        ],
        "mcps": [
            {
                "server_id": s.server_id, "endpoint": s.endpoint,
                "capabilities": sorted(s.capabilities), "healthy": s.healthy, "description": s.description,
            }
            for s in runtime.mcp_pool.list_servers()
        ],
    }


@router.post("/pools/models")
def register_model(
    body: RegisterModelRequest,
    runtime: Runtime = Depends(get_runtime),
) -> dict[str, Any]:
    try:
        tier = ModelTier(body.tier)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid tier {body.tier!r}")
    runtime.llm_pool.register(ModelEntry(
        model_id=body.model_id, provider=body.provider, tier=tier,
        cost_per_1k_tokens=body.cost_per_1k_tokens,
        description=body.description, is_local=body.is_local,
    ))
    return {"status": "registered", "model_id": body.model_id, "tier": tier.value}


@router.post("/pools/mcps")
def register_mcp(
    body: RegisterMCPRequest,
    runtime: Runtime = Depends(get_runtime),
) -> dict[str, Any]:
    runtime.mcp_pool.register(MCPServer(
        server_id=body.server_id, endpoint=body.endpoint,
        capabilities=frozenset(body.capabilities), description=body.description,
    ))
    return {"status": "registered", "server_id": body.server_id}


@router.delete("/pools/models/{model_id}")
def remove_model(
    model_id: str,
    runtime: Runtime = Depends(get_runtime),
) -> dict[str, Any]:
    with runtime.llm_pool._lock:  # noqa: SLF001
        if model_id not in runtime.llm_pool._models:  # noqa: SLF001
            raise HTTPException(status_code=404, detail=f"Model {model_id!r} not found")
        del runtime.llm_pool._models[model_id]  # noqa: SLF001
    return {"status": "removed", "model_id": model_id}
