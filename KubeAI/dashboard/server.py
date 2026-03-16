"""KubeAI Dashboard server — the kubectl-proxy analogue for serving the control-plane UI."""
import asyncio
import json
import pathlib
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from .state import RuntimeState
from .ws_manager import manager
from .api import overview, agents, tasks, memory, blueprints, monitoring

BASE = pathlib.Path(__file__).parent


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage the background broadcast loop lifecycle.

    Analogous to the kube-controller-manager's reconciliation loop —
    periodically pushes updated state to all connected dashboard clients.
    """
    async def _push_loop() -> None:
        state = RuntimeState()
        while True:
            await asyncio.sleep(2)
            await manager.broadcast({"type": "state_update", "data": state.snapshot()})

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
    state = RuntimeState()
    await ws.send_text(json.dumps({"type": "state_update", "data": state.snapshot()}))
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(ws)


static_dir = BASE / "static"
if static_dir.exists():
    app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")


def serve(host: str = "0.0.0.0", port: int = 8080) -> None:
    """Start the KubeAI dashboard server.

    Analogous to 'kubectl proxy' — starts a local server providing access
    to the KubeAI control-plane API and dashboard UI.
    """
    import uvicorn
    uvicorn.run(app, host=host, port=port)
