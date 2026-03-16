"""KubeAI Dashboard server — the kubectl-proxy analogue for serving the control-plane UI."""

from __future__ import annotations

import asyncio
import json
import pathlib
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from KubeAI.api.state_store import StateStore
from KubeAI.dashboard.deps import get_control_plane, seed_demo_data
from KubeAI.dashboard.ws_manager import manager
from KubeAI.dashboard.api import overview, agents, tasks, memory, blueprints, monitoring

BASE = pathlib.Path(__file__).parent


def _make_ws_payload(cp) -> dict:
    """Build a WebSocket state snapshot from ControlPlaneAPI."""
    agents_list = cp.list_agents()
    tasks_list = cp.list_tasks(limit=200)
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
                "mcp_servers": list(a.capabilities),
            }
            for a in agents_list
        ],
        "tasks": [
            {
                "id": t.task_id,
                "status": t.status.upper(),
                "blueprint": t.blueprint,
                "agent_id": t.agent_id,
                "latency_ms": t.latency_ms,
            }
            for t in tasks_list
        ],
        "metrics": cp.metrics_snapshot(),
    }


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage startup seeding and background broadcast loop lifecycle.

    Analogous to the kube-controller-manager's reconciliation loop —
    seeds demo state on startup then periodically pushes updated state
    to all connected dashboard clients.
    """
    cp = get_control_plane()
    state_store = StateStore()
    state_store.load(cp)
    seed_demo_data(cp)
    state_store.start_periodic_checkpoint(cp)

    async def _push_loop() -> None:
        while True:
            await asyncio.sleep(2)
            await manager.broadcast({"type": "state_update", "data": _make_ws_payload(cp)})

    task = asyncio.create_task(_push_loop())
    yield
    task.cancel()


app = FastAPI(title="KubeAI Dashboard", lifespan=lifespan)

app.include_router(overview.router, prefix="/api")
app.include_router(agents.router, prefix="/api")
app.include_router(tasks.router, prefix="/api")
app.include_router(memory.router, prefix="/api")
app.include_router(blueprints.router, prefix="/api")
app.include_router(monitoring.router, prefix="/api")


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    """WebSocket endpoint for real-time dashboard state streaming.

    Analogous to 'kubectl get pods --watch' — clients connect here and
    receive live state updates from the KubeAI control plane.
    """
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
    """Start the KubeAI dashboard server.

    Analogous to 'kubectl proxy' — starts a local server providing access
    to the KubeAI control-plane API and dashboard UI.
    """
    import uvicorn
    uvicorn.run(app, host=host, port=port)
