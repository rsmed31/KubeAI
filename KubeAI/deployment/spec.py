"""DeploymentSpec is the Kubernetes Deployment manifest analogue: declares desired state for an agent fleet."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class DeploymentSpec:
    """Immutable desired-state declaration for an agent fleet."""

    name: str
    blueprint_name: str
    replicas: int = 1                    # desired replica count
    min_replicas: int = 1
    max_replicas: int = 10
    target_load: float = 0.7             # HPA target utilisation (0.0-1.0)
    cost_hint: float = 0.5
    labels: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.min_replicas < 1:
            raise ValueError("min_replicas must be >= 1")
        if self.max_replicas < self.min_replicas:
            raise ValueError("max_replicas must be >= min_replicas")
        if not (0.0 < self.target_load <= 1.0):
            raise ValueError("target_load must be in (0.0, 1.0]")

    def __repr__(self) -> str:
        return (
            f"DeploymentSpec(name={self.name!r}, blueprint={self.blueprint_name!r}, "
            f"replicas={self.replicas}, min={self.min_replicas}, max={self.max_replicas})"
        )


@dataclass
class DeploymentStatus:
    """Mutable observed state of a deployment — analogous to Deployment.status."""

    name: str
    desired: int
    ready: int
    available: int
    unavailable: int
    conditions: list[str] = field(default_factory=list)

    def __repr__(self) -> str:
        return (
            f"DeploymentStatus(name={self.name!r}, desired={self.desired}, "
            f"ready={self.ready}, available={self.available})"
        )
