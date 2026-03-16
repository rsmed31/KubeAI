"""DeploymentReconciler is the Deployment controller analogue: continuously reconciles desired replica count against observed agent state."""

from __future__ import annotations

import threading
import time
from typing import TYPE_CHECKING

from KubeAI.api.control_plane import ControlPlaneAPI
from .spec import DeploymentSpec, DeploymentStatus

if TYPE_CHECKING:
    from KubeAI.blueprint import BlueprintRegistry
    from KubeAI.scheduler.lifecycle import AgentLifecycleManager


class DeploymentReconciler:
    """
    Reconciliation loop that keeps actual agent count == spec.replicas.

    reconcile(spec) — runs one sync cycle (spawn missing, terminate excess)
    start_watch(spec, interval_s) — starts background reconciliation thread
    stop_watch(name) — stops reconciliation for a deployment
    status(spec) -> DeploymentStatus
    """

    def __init__(
        self,
        lifecycle: "AgentLifecycleManager",
        registry: "BlueprintRegistry",
        control_plane: ControlPlaneAPI,
    ) -> None:
        self._lifecycle = lifecycle
        self._registry = registry
        self._cp = control_plane
        self._watches: dict[str, threading.Event] = {}
        self._lock = threading.RLock()

    def reconcile(self, spec: DeploymentSpec) -> DeploymentStatus:
        """Run one reconciliation cycle: bring actual count to spec.replicas."""
        blueprint = self._registry.get(spec.blueprint_name)
        agents = [
            a for a in self._lifecycle.list_agents()
            if a.blueprint.name == spec.blueprint_name
            and a.state != "terminated"
        ]
        actual = len(agents)
        desired = max(spec.min_replicas, min(spec.max_replicas, spec.replicas))

        if actual < desired:
            for _ in range(desired - actual):
                self._lifecycle.spawn(blueprint, cost_hint=spec.cost_hint)
        elif actual > desired:
            # Terminate excess idle agents first, then running ones
            excess = agents[desired:]
            for a in sorted(excess, key=lambda x: x.state != "idle"):
                self._lifecycle.terminate(a.agent_id)

        running = [a for a in self._lifecycle.list_agents()
                   if a.blueprint.name == spec.blueprint_name and a.state == "running"]
        idle = [a for a in self._lifecycle.list_agents()
                if a.blueprint.name == spec.blueprint_name and a.state == "idle"]
        ready = len(running) + len(idle)
        return DeploymentStatus(
            name=spec.name,
            desired=desired,
            ready=ready,
            available=ready,
            unavailable=max(0, desired - ready),
        )

    def start_watch(self, spec: DeploymentSpec, interval_s: float = 10.0) -> None:
        """Start a background reconciliation loop for *spec*."""
        stop_event = threading.Event()
        with self._lock:
            if spec.name in self._watches:
                return  # already watching
            self._watches[spec.name] = stop_event

        def _loop() -> None:
            while not stop_event.is_set():
                try:
                    self.reconcile(spec)
                except Exception:
                    pass
                stop_event.wait(interval_s)

        t = threading.Thread(target=_loop, daemon=True, name=f"reconciler-{spec.name}")
        t.start()

    def stop_watch(self, name: str) -> None:
        """Stop the reconciliation loop for a deployment by name."""
        with self._lock:
            event = self._watches.pop(name, None)
        if event:
            event.set()

    def status(self, spec: DeploymentSpec) -> DeploymentStatus:
        """Return current observed status without reconciling."""
        agents = [
            a for a in self._lifecycle.list_agents()
            if a.blueprint.name == spec.blueprint_name and a.state != "terminated"
        ]
        ready = len(agents)
        desired = max(spec.min_replicas, min(spec.max_replicas, spec.replicas))
        return DeploymentStatus(
            name=spec.name,
            desired=desired,
            ready=ready,
            available=ready,
            unavailable=max(0, desired - ready),
        )

    def __repr__(self) -> str:
        with self._lock:
            return f"DeploymentReconciler(watches={list(self._watches.keys())})"
