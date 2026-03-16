"""Deployment subsystem — the Deployment + HPA analogue for declarative agent fleet management."""
from .spec import DeploymentSpec, DeploymentStatus
from .reconciler import DeploymentReconciler
from .autoscaler import HorizontalAgentScaler

__all__ = ["DeploymentSpec", "DeploymentStatus", "DeploymentReconciler", "HorizontalAgentScaler"]
