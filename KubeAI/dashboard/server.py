"""KubeAI Dashboard server — the kubectl-proxy analogue for serving the control-plane UI."""

from __future__ import annotations

import asyncio
import json
import os
import pathlib
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from KubeAI.api.state_store import StateStore
from KubeAI.dashboard.deps import bootstrap_runtime, get_control_plane
from KubeAI.dashboard.ws_manager import manager
from KubeAI.dashboard.api import overview, agents, tasks, memory, blueprints, monitoring

BASE = pathlib.Path(__file__).parent


def _make_ws_payload(cp) -> dict:
    """Build a WebSocket state snapshot from ControlPlaneAPI."""
    agents_list = cp.list_agents()
    tasks_list = cp.list_tasks(limit=200)

    # Collect pool info if available
    pool_models = []
    pool_mcps = []
    llm_pool = getattr(cp, "_llm_pool", None)
    if llm_pool is not None:
        for m in llm_pool.list_models():
            pool_models.append({
                "model_id": m.model_id,
                "provider": m.provider,
                "tier": m.tier.value,
                "load": m.load,
                "healthy": m.healthy,
                "cost_per_1k": m.cost_per_1k_tokens,
                "has_key": bool(m.api_key),
                "base_url": m.base_url,
            })
    try:
        from KubeAI.dashboard.deps import get_runtime
        rt = get_runtime()
        for s in rt.mcp_pool.list_servers():
            pool_mcps.append({
                "server_id": s.server_id,
                "endpoint": s.endpoint,
                "capabilities": sorted(s.capabilities),
                "healthy": s.healthy,
                "description": s.description,
                "transport": s.transport,
                "timeout_s": s.timeout_s,
                "tags": sorted(s.tags),
            })
    except Exception:
        pass

    # Collect cluster snapshots
    clusters_snapshot = []
    try:
        from KubeAI.dashboard.deps import get_cluster_registry
        clusters_snapshot = get_cluster_registry().snapshot()
    except Exception:
        pass

    return {
        "agents": [
            {
                "id": a.agent_id,
                "blueprint": a.metadata.get("blueprint", a.name),
                "state": a.state.upper(),
                "model_id": a.metadata.get("model", "unknown"),
                "tier": a.metadata.get("tier", "unknown"),
                "load": a.load,
                "healthy": a.healthy,
                "capabilities": list(a.capabilities),
                "mcp_servers": list(a.metadata.get("mcp_servers", [])),
            }
            for a in agents_list
        ],
        "tasks": [
            {
                "id": t.task_id,
                "description": t.description,
                "status": t.status.upper(),
                "blueprint": t.blueprint,
                "agent_id": t.agent_id,
                "latency_ms": t.latency_ms,
                "result_text": t.result_text,
                "stages": cp._task_stages.get(t.task_id, []),  # noqa: SLF001
            }
            for t in tasks_list
        ],
        "metrics": cp.metrics_snapshot(),
        "pool_models": pool_models,
        "pool_mcps": pool_mcps,
        "clusters": clusters_snapshot,
    }


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage startup wiring and background broadcast loop.

    Bootstraps the full runtime on startup (NO demo data),
    loads persisted state, then periodically pushes live state
    to all connected dashboard clients via WebSocket.
    """
    runtime = bootstrap_runtime()
    from KubeAI.dashboard.deps import get_cluster_registry
    get_cluster_registry()  # initialise registry with default cluster
    cp = runtime.control_plane

    # Default to a clean runtime start so stale runtime state is never shown.
    # Only clear agents/tasks (runtime state), NOT models/MCPs (infrastructure config).
    # Set KUBEAI_CLEAN_START=0 to preserve in-memory state on startup.
    if os.environ.get("KUBEAI_CLEAN_START", "1").strip() != "0":
        with cp._lock:  # noqa: SLF001
            cp._agents.clear()  # noqa: SLF001
            cp._tasks.clear()  # noqa: SLF001
            cp._task_stages.clear()  # noqa: SLF001

    state_store = StateStore()
    if os.environ.get("KUBEAI_RESTORE_STATE", "").strip() == "1":
        state_store.load(cp)
    state_store.start_periodic_checkpoint(cp)

    async def _push_loop() -> None:
        while True:
            await asyncio.sleep(2)
            await manager.broadcast({"type": "state_update", "data": _make_ws_payload(cp)})

    task = asyncio.create_task(_push_loop())
    yield
    task.cancel()


app = FastAPI(title="KubeAI Dashboard", lifespan=lifespan)

# CORS for React dev server (Vite on localhost:5173)
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(overview.router, prefix="/api")
app.include_router(agents.router, prefix="/api")
app.include_router(tasks.router, prefix="/api")
app.include_router(memory.router, prefix="/api")
app.include_router(blueprints.router, prefix="/api")
app.include_router(monitoring.router, prefix="/api")

# ── Config & Skills API routers ────────────────────────────────────────────
from KubeAI.dashboard.api.config import router as config_router, skills_router
app.include_router(config_router)
app.include_router(skills_router)

# ── Cluster API router ─────────────────────────────────────────────────────
from KubeAI.dashboard.api import cluster as cluster_api
app.include_router(cluster_api.router, prefix="/api")

# ── Orchestrator API router ─────────────────────────────────────────────────
from KubeAI.dashboard.api import orchestrator as orchestrator_api
app.include_router(orchestrator_api.router, prefix="/api")

# ── Benchmarks API router ────────────────────────────────────────────────────
from KubeAI.dashboard.api import benchmarks as benchmarks_api
app.include_router(benchmarks_api.router, prefix="/api")


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    """WebSocket endpoint for real-time dashboard state streaming."""
    await manager.connect(ws)
    cp = get_control_plane()
    await ws.send_text(json.dumps({"type": "state_update", "data": _make_ws_payload(cp)}))
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(ws)


static_dir = BASE / "static"
if static_dir.exists():
    from fastapi.staticfiles import StaticFiles
    app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")


def serve(host: str = "0.0.0.0", port: int = 8080) -> None:
    """Start the KubeAI dashboard server."""
    import uvicorn
    uvicorn.run(app, host=host, port=port)
