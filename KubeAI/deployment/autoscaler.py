"""HorizontalAgentScaler is the HPA analogue: adjusts desired replica count based on observed pool load."""

from __future__ import annotations

import math
from dataclasses import dataclass

from .spec import DeploymentSpec, DeploymentStatus
from .reconciler import DeploymentReconciler


@dataclass(frozen=True)
class AutoscaleSignals:
    """Observed runtime signals used by queue and cost-aware autoscaling."""

    observed_load: float
    queue_depth: int = 0
    avg_token_cost: float | None = None


class HorizontalAgentScaler:
    """
    HPA-style autoscaler. Computes new replica count from observed load
    and calls reconcile() to apply it.

    scale(spec, observed_load) -> DeploymentStatus
      - If observed_load > target_load: scale up (ceil)
      - If observed_load < target_load * 0.5: scale down (floor, respecting min)
      - Otherwise: no change
    """

    def __init__(
        self,
        reconciler: DeploymentReconciler,
        *,
        queue_per_replica_target: int = 2,
    ) -> None:
        self._reconciler = reconciler
        self._queue_per_replica_target = max(1, int(queue_per_replica_target))

    def scale(self, spec: DeploymentSpec, observed_load: float) -> DeploymentStatus:
        """Compute desired replicas from observed load and reconcile."""
        return self.scale_by_signals(
            spec,
            AutoscaleSignals(observed_load=observed_load),
        )

    def scale_by_signals(self, spec: DeploymentSpec, signals: AutoscaleSignals) -> DeploymentStatus:
        """Compute desired replicas from load + queue depth + token-cost pressure."""
        current = self._reconciler.status(spec).ready or spec.min_replicas

        observed_load = max(0.0, float(signals.observed_load))
        queue_depth = max(0, int(signals.queue_depth))

        if observed_load > spec.target_load:
            # Scale up: replicas = ceil(current * observed / target)
            new_replicas = math.ceil(current * observed_load / spec.target_load)
        elif observed_load < spec.target_load * 0.5:
            # Scale down: replicas = floor(current * observed / target)
            new_replicas = max(spec.min_replicas, math.floor(current * observed_load / spec.target_load))
        else:
            new_replicas = current

        # Queue pressure ensures backlog can drive additional scale-up even when
        # utilization telemetry is stale or under-reporting burst demand.
        queue_required = math.ceil(queue_depth / self._queue_per_replica_target)
        if queue_required > new_replicas:
            new_replicas = queue_required

        # Cost pressure can dampen scale if average task cost exceeds the budget.
        if (
            spec.max_token_cost_per_task is not None
            and signals.avg_token_cost is not None
            and signals.avg_token_cost > spec.max_token_cost_per_task
        ):
            penalty_ratio = signals.avg_token_cost / spec.max_token_cost_per_task
            new_replicas = max(
                spec.min_replicas,
                math.floor(new_replicas / penalty_ratio),
            )

        new_replicas = max(spec.min_replicas, min(spec.max_replicas, new_replicas))
        scaled_spec = DeploymentSpec(
            name=spec.name,
            blueprint_name=spec.blueprint_name,
            replicas=new_replicas,
            min_replicas=spec.min_replicas,
            max_replicas=spec.max_replicas,
            target_load=spec.target_load,
            cost_hint=spec.cost_hint,
            max_token_cost_per_task=spec.max_token_cost_per_task,
            labels=spec.labels,
        )
        return self._reconciler.reconcile(scaled_spec)

    def __repr__(self) -> str:
        return f"HorizontalAgentScaler(reconciler={self._reconciler!r})"
