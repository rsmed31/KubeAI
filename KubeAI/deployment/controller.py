"""AutoscaleController is the HPA control-loop analogue: continuously applies queue/load/cost scaling decisions against live control-plane signals."""

from __future__ import annotations

import threading
from dataclasses import dataclass

from KubeAI.api.control_plane import ControlPlaneAPI

from .autoscaler import AutoscaleSignals, HorizontalAgentScaler
from .reconciler import DeploymentReconciler
from .spec import DeploymentSpec, DeploymentStatus


@dataclass(frozen=True)
class AutoscaleControllerConfig:
    """Configuration for periodic autoscaling reconciliation."""

    interval_s: float = 5.0
    recent_tasks: int = 50
    keep_warm_min_replicas: bool = False


class AutoscaleController:
    """Background controller that continuously scales deployments from live signals."""

    def __init__(
        self,
        control_plane: ControlPlaneAPI,
        reconciler: DeploymentReconciler,
        scaler: HorizontalAgentScaler,
        *,
        specs: list[DeploymentSpec] | None = None,
        config: AutoscaleControllerConfig | None = None,
    ) -> None:
        self._cp = control_plane
        self._reconciler = reconciler
        self._scaler = scaler
        self._config = config or AutoscaleControllerConfig()
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._specs: dict[str, DeploymentSpec] = {}
        for spec in specs or []:
            self._specs[spec.name] = spec

    def register_spec(self, spec: DeploymentSpec) -> None:
        """Add or replace one deployment spec managed by this controller."""
        with self._lock:
            self._specs[spec.name] = spec

    def unregister_spec(self, deployment_name: str) -> bool:
        """Remove one managed deployment spec by deployment name."""
        with self._lock:
            return self._specs.pop(deployment_name, None) is not None

    def list_specs(self) -> list[DeploymentSpec]:
        """Return a snapshot list of managed deployment specs."""
        with self._lock:
            return list(self._specs.values())

    def run_once(self) -> dict[str, DeploymentStatus]:
        """Run one full autoscaling reconciliation cycle over all managed specs."""
        statuses: dict[str, DeploymentStatus] = {}
        for spec in self.list_specs():
            observed_load = self._observed_load_for_blueprint(spec.blueprint_name)
            raw_signals = self._cp.autoscale_signals(
                blueprint=spec.blueprint_name,
                recent_tasks=self._config.recent_tasks,
            )
            signals = AutoscaleSignals(
                observed_load=observed_load,
                queue_depth=int(raw_signals.get("queue_depth", 0.0)),
                avg_token_cost=float(raw_signals.get("avg_token_cost", 0.0)),
            )

            if self._should_skip_cold_start(spec, signals, observed_load):
                statuses[spec.name] = self._reconciler.status(spec)
                continue

            statuses[spec.name] = self._scaler.scale_by_signals(spec, signals)
        return statuses

    def start(self) -> None:
        """Start background autoscaling loop (idempotent)."""
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._loop,
                daemon=True,
                name="kubeai-autoscale-controller",
            )
            self._thread.start()

    def stop(self) -> None:
        """Stop background autoscaling loop if running."""
        self._stop_event.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=max(1.0, self._config.interval_s * 2.0))

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self.run_once()
            except Exception:
                pass
            self._stop_event.wait(self._config.interval_s)

    def _observed_load_for_blueprint(self, blueprint_name: str) -> float:
        agents = [
            agent
            for agent in self._cp.list_agents()
            if agent.metadata.get("blueprint") == blueprint_name
            and agent.state in {"running", "idle"}
        ]
        if not agents:
            return 0.0
        return float(sum(max(0.0, agent.load) for agent in agents) / len(agents))

    def _should_skip_cold_start(
        self,
        spec: DeploymentSpec,
        signals: AutoscaleSignals,
        observed_load: float,
    ) -> bool:
        if self._config.keep_warm_min_replicas:
            return False

        status = self._reconciler.status(spec)
        return (
            status.ready == 0
            and observed_load <= 0.0
            and signals.queue_depth <= 0
        )

    def __repr__(self) -> str:
        return (
            f"AutoscaleController(specs={len(self.list_specs())}, "
            f"interval_s={self._config.interval_s:.1f})"
        )
