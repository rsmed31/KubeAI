"""HorizontalAgentScaler is the HPA analogue: adjusts desired replica count based on observed pool load."""

from __future__ import annotations

import math

from .spec import DeploymentSpec, DeploymentStatus
from .reconciler import DeploymentReconciler


class HorizontalAgentScaler:
    """
    HPA-style autoscaler. Computes new replica count from observed load
    and calls reconcile() to apply it.

    scale(spec, observed_load) -> DeploymentStatus
      - If observed_load > target_load: scale up (ceil)
      - If observed_load < target_load * 0.5: scale down (floor, respecting min)
      - Otherwise: no change
    """

    def __init__(self, reconciler: DeploymentReconciler) -> None:
        self._reconciler = reconciler

    def scale(self, spec: DeploymentSpec, observed_load: float) -> DeploymentStatus:
        """Compute desired replicas from observed load and reconcile."""
        current = self._reconciler.status(spec).ready or spec.min_replicas
        if observed_load > spec.target_load:
            # Scale up: replicas = ceil(current * observed / target)
            new_replicas = math.ceil(current * observed_load / spec.target_load)
        elif observed_load < spec.target_load * 0.5:
            # Scale down: replicas = floor(current * observed / target)
            new_replicas = max(spec.min_replicas, math.floor(current * observed_load / spec.target_load))
        else:
            new_replicas = current

        new_replicas = max(spec.min_replicas, min(spec.max_replicas, new_replicas))
        scaled_spec = DeploymentSpec(
            name=spec.name,
            blueprint_name=spec.blueprint_name,
            replicas=new_replicas,
            min_replicas=spec.min_replicas,
            max_replicas=spec.max_replicas,
            target_load=spec.target_load,
            cost_hint=spec.cost_hint,
            labels=spec.labels,
        )
        return self._reconciler.reconcile(scaled_spec)

    def __repr__(self) -> str:
        return f"HorizontalAgentScaler(reconciler={self._reconciler!r})"
