"""Deployment subsystem — the Deployment + HPA analogue for declarative agent fleet management."""
from .spec import DeploymentSpec, DeploymentStatus
from .reconciler import DeploymentReconciler
from .autoscaler import AutoscaleSignals, HorizontalAgentScaler
from .controller import AutoscaleController, AutoscaleControllerConfig

__all__ = [
	"DeploymentSpec",
	"DeploymentStatus",
	"DeploymentReconciler",
	"HorizontalAgentScaler",
	"AutoscaleSignals",
	"AutoscaleController",
	"AutoscaleControllerConfig",
]
