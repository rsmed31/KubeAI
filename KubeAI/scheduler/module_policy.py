"""Scheduler module policy is the admission-controller analogue that enables or disables extension modules per agent."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Iterable


class ModulePolicyError(PermissionError):
    """Raised when one or more required modules are disabled for an agent."""


@dataclass(frozen=True)
class ModuleDecision:
    """One module enablement decision at global or per-agent scope."""

    module: str
    enabled: bool
    agent_id: str | None = None

    def __repr__(self) -> str:
        scope = self.agent_id if self.agent_id is not None else "global"
        return (
            f"ModuleDecision(module={self.module!r}, enabled={self.enabled}, "
            f"scope={scope!r})"
        )


class SchedulerModulePolicy:
    """Maintain per-module policy flags globally and per target agent."""

    def __init__(self, default_enabled: bool = True) -> None:
        self._default_enabled = bool(default_enabled)
        self._global_flags: dict[str, bool] = {}
        self._agent_flags: dict[str, dict[str, bool]] = {}
        self._lock = threading.RLock()

    def enable(self, module: str, agent_id: str | None = None) -> ModuleDecision:
        """Enable a module globally or for a specific agent."""
        return self._set(module=module, enabled=True, agent_id=agent_id)

    def disable(self, module: str, agent_id: str | None = None) -> ModuleDecision:
        """Disable a module globally or for a specific agent."""
        return self._set(module=module, enabled=False, agent_id=agent_id)

    def clear_agent(self, agent_id: str) -> None:
        """Remove all agent-specific module overrides."""
        with self._lock:
            self._agent_flags.pop(agent_id, None)

    def is_enabled(self, module: str, agent_id: str | None = None) -> bool:
        """Return whether a module is enabled for the given agent context."""
        normalized = self._normalize(module)
        with self._lock:
            if agent_id is not None:
                agent_overrides = self._agent_flags.get(agent_id)
                if agent_overrides and normalized in agent_overrides:
                    return agent_overrides[normalized]

            if normalized in self._global_flags:
                return self._global_flags[normalized]

            return self._default_enabled

    def enabled_modules(self, modules: Iterable[str], agent_id: str | None = None) -> list[str]:
        """Return enabled subset of module names preserving deterministic order."""
        normalized = []
        seen: set[str] = set()
        for module in modules:
            name = self._normalize(module)
            if name in seen:
                continue
            seen.add(name)
            if self.is_enabled(name, agent_id=agent_id):
                normalized.append(name)
        return normalized

    def assert_enabled(self, modules: Iterable[str], agent_id: str | None = None) -> None:
        """Raise ModulePolicyError when any required module is disabled."""
        normalized = []
        seen: set[str] = set()
        for module in modules:
            name = self._normalize(module)
            if name in seen:
                continue
            seen.add(name)
            normalized.append(name)

        disabled = [
            module
            for module in normalized
            if not self.is_enabled(module, agent_id=agent_id)
        ]
        if disabled:
            scope = agent_id if agent_id is not None else "global"
            raise ModulePolicyError(
                f"Disabled modules for scope {scope!r}: {disabled!r}"
            )

    def snapshot(self) -> dict[str, dict[str, bool] | bool]:
        """Return a policy snapshot suitable for status/debug output."""
        with self._lock:
            return {
                "default_enabled": self._default_enabled,
                "global": dict(self._global_flags),
                "agents": {agent: dict(flags) for agent, flags in self._agent_flags.items()},
            }

    def _set(self, *, module: str, enabled: bool, agent_id: str | None) -> ModuleDecision:
        normalized = self._normalize(module)
        with self._lock:
            if agent_id is None:
                self._global_flags[normalized] = enabled
                return ModuleDecision(module=normalized, enabled=enabled)

            flags = self._agent_flags.setdefault(agent_id, {})
            flags[normalized] = enabled
            return ModuleDecision(module=normalized, enabled=enabled, agent_id=agent_id)

    @staticmethod
    def _normalize(module: str) -> str:
        cleaned = module.strip()
        if not cleaned:
            raise ValueError("module name must not be empty")
        return cleaned

    def __repr__(self) -> str:
        with self._lock:
            return (
                f"SchedulerModulePolicy(default_enabled={self._default_enabled}, "
                f"global_modules={len(self._global_flags)}, "
                f"agent_overrides={len(self._agent_flags)})"
            )
