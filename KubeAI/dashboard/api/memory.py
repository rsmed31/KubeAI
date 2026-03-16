"""Memory API — the kubectl describe pv / PersistentVolume status analogue for the 3-tier memory system."""
from fastapi import APIRouter
from ..state import RuntimeState

router = APIRouter()


@router.get("/memory")
def get_memory() -> dict:
    """Return a snapshot of the KubeAI 3-tier memory system.

    Analogous to 'kubectl get pv' — shows the utilization of the shared
    data plane across working, short-term, and long-term memory tiers.
    """
    state = RuntimeState()
    return state.get_memory_snapshot()
