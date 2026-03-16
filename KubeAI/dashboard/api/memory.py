"""Memory API — the kubectl describe pv / PersistentVolume status analogue for the 3-tier memory system."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from KubeAI.api.control_plane import ControlPlaneAPI
from KubeAI.dashboard.deps import get_control_plane

router = APIRouter()


@router.get("/memory")
def get_memory(cp: ControlPlaneAPI = Depends(get_control_plane)) -> dict:
    """Return a snapshot of the KubeAI 3-tier memory system.

    Analogous to 'kubectl get pv' — shows the utilization of the shared
    data plane across working, short-term, and long-term memory tiers.
    """
    return cp.memory_snapshot()
