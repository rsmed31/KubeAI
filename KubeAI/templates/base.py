"""Template primitives are the Helm-chart analogue that inject capabilities into agent instances."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from threading import RLock
from typing import Any, Iterable, MutableMapping

_TEMPLATE_REGISTRY_ATTR = "_kubeai_templates"
_TEMPLATE_LOCK_ATTR = "_kubeai_templates_lock"


class TemplateError(RuntimeError):
    """Base exception for template mounting and lifecycle failures."""


class TemplateMountError(TemplateError):
    """Raised when template attach or detach operations fail."""


class TemplateHookError(TemplateError):
    """Raised when a template lifecycle hook fails."""


@dataclass(slots=True)
class TemplateConfig:
    """Typed container for template mount configuration."""

    name: str
    options: dict[str, Any] = field(default_factory=dict)
    enabled: bool = True
    priority: int = 100

    def as_mapping(self) -> dict[str, Any]:
        """Return normalized mapping used by template attach operations."""
        mapping = dict(self.options)
        mapping.setdefault("enabled", self.enabled)
        mapping.setdefault("priority", self.priority)
        return mapping


def _normalize_config(config: TemplateConfig | MutableMapping[str, Any] | None) -> dict[str, Any]:
    """Normalize supported config inputs into a mutable dictionary."""
    if config is None:
        return {}
    if isinstance(config, TemplateConfig):
        return config.as_mapping()
    return dict(config)


class Template(ABC):
    """Base contract for any capability template mounted on an agent."""

    def __init__(self, name: str, priority: int = 100) -> None:
        self.name = name
        self.priority = priority

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}(name={self.name!r}, "
            f"priority={self.priority})"
        )

    def configure(self, config: MutableMapping[str, Any] | None = None) -> None:
        """Apply base configuration fields shared by all templates."""
        normalized = _normalize_config(config)
        if "priority" in normalized:
            self.priority = int(normalized["priority"])

    @abstractmethod
    def attach(
        self,
        agent: Any,
        config: MutableMapping[str, Any] | None = None,
    ) -> None:
        """Attach template behavior to an agent instance at spawn time."""

    def detach(self, agent: Any) -> None:
        """Detach template behavior from an agent instance."""
        _ = agent

    def pre_run(self, task: str) -> str:
        """Run before the agent execution path and return the transformed task."""
        return task

    def post_run(self, result: str) -> str:
        """Run after agent execution and return the transformed result."""
        return result


def get_attached_templates(agent: Any) -> list[Template]:
    """Return template registry attached to an agent, creating it if missing."""
    registry = getattr(agent, _TEMPLATE_REGISTRY_ATTR, None)
    if registry is None:
        registry = []
        setattr(agent, _TEMPLATE_REGISTRY_ATTR, registry)
    if not isinstance(registry, list):
        raise TemplateMountError(
            f"Agent template registry is invalid: {type(registry).__name__}"
        )
    return registry


def _get_registry_lock(agent: Any) -> RLock:
    """Return per-agent lock guarding template registry operations."""
    lock = getattr(agent, _TEMPLATE_LOCK_ATTR, None)
    if lock is None:
        lock = RLock()
        setattr(agent, _TEMPLATE_LOCK_ATTR, lock)
    return lock


def _snapshot_templates(agent: Any) -> list[Template]:
    """Return a safe copy of template registry under lock."""
    with _get_registry_lock(agent):
        return list(get_attached_templates(agent))


def attach_template(
    agent: Any,
    template: Template,
    config: TemplateConfig | MutableMapping[str, Any] | None = None,
) -> bool:
    """Attach one template and register it on the agent.

    Returns True when attached, False when skipped because enabled=False.
    """
    normalized = _normalize_config(config)
    if normalized.get("enabled") is False:
        return False

    template.configure(normalized)
    try:
        template.attach(agent=agent, config=normalized)
    except Exception as exc:  # pragma: no cover - passthrough wrapper
        raise TemplateMountError(f"Failed to attach template {template.name!r}") from exc

    with _get_registry_lock(agent):
        registry = [item for item in get_attached_templates(agent) if item.name != template.name]
        registry.append(template)
        registry.sort(key=lambda item: item.priority)
        setattr(agent, _TEMPLATE_REGISTRY_ATTR, registry)
    return True


def attach_templates(
    agent: Any,
    templates: Iterable[Template],
    configs: MutableMapping[str, TemplateConfig | MutableMapping[str, Any]] | None = None,
) -> list[str]:
    """Attach a set of templates and return the names that were attached."""
    attached: list[str] = []
    for template in templates:
        template_config = None
        if configs and template.name in configs:
            template_config = configs[template.name]
        if attach_template(agent=agent, template=template, config=template_config):
            attached.append(template.name)
    return attached


def detach_templates(agent: Any) -> None:
    """Detach all templates from an agent in reverse order."""
    registry = _snapshot_templates(agent)
    for template in reversed(registry):
        try:
            template.detach(agent)
        except Exception as exc:  # pragma: no cover - passthrough wrapper
            raise TemplateMountError(f"Failed to detach template {template.name!r}") from exc
    with _get_registry_lock(agent):
        setattr(agent, _TEMPLATE_REGISTRY_ATTR, [])


def run_pre_hooks(agent: Any, task: str) -> str:
    """Run pre_run hooks in ascending priority order."""
    current = task
    for template in _snapshot_templates(agent):
        try:
            current = template.pre_run(current)
        except Exception as exc:  # pragma: no cover - passthrough wrapper
            raise TemplateHookError(
                f"pre_run failed for template {template.name!r}"
            ) from exc
    return current


def run_post_hooks(agent: Any, result: str) -> str:
    """Run post_run hooks in reverse priority order."""
    current = result
    for template in reversed(_snapshot_templates(agent)):
        try:
            current = template.post_run(current)
        except Exception as exc:  # pragma: no cover - passthrough wrapper
            raise TemplateHookError(
                f"post_run failed for template {template.name!r}"
            ) from exc
    return current
