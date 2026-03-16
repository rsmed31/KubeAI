"""WebSocketManager is the event-bus analogue: broadcasts runtime state to all connected dashboard clients."""
import asyncio
import json
from fastapi import WebSocket


class WebSocketManager:
    """Manages all active WebSocket connections and broadcasts state updates.

    Analogous to the Kubernetes watch mechanism — clients subscribe and receive
    real-time state change events from the control plane.
    """

    def __init__(self) -> None:
        self.active: list[WebSocket] = []

    def __repr__(self) -> str:
        return f"WebSocketManager(active_connections={len(self.active)})"

    async def connect(self, ws: WebSocket) -> None:
        """Accept and register a new WebSocket client."""
        await ws.accept()
        self.active.append(ws)

    def disconnect(self, ws: WebSocket) -> None:
        """Remove a disconnected client from the active pool."""
        self.active = [c for c in self.active if c is not ws]

    async def broadcast(self, data: dict) -> None:
        """Broadcast a message to all active clients, pruning dead connections."""
        payload = json.dumps(data)
        dead: list[WebSocket] = []
        for ws in self.active:
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


manager = WebSocketManager()
