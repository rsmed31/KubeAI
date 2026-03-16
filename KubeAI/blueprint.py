"""Blueprint is the Pod spec analogue: immutable declaration of an agent's capability, tier, and identity."""

from __future__ import annotations

from dataclasses import dataclass, field

from KubeAI.orchestrator.llm_pool import ModelTier


@dataclass(frozen=True)
class Blueprint:
    """
    Immutable declaration of an agent's capability, minimum tier, and identity.

    Analogous to a Kubernetes Pod spec: once registered, a Blueprint cannot be
    mutated. Agents are spawned from Blueprints at runtime by the Orchestrator.
    """

    name: str
    description: str
    tier: ModelTier
    system_prompt: str = ""
    required_capabilities: frozenset[str] = field(default_factory=frozenset)
    version: str = "1.0"

    def __repr__(self) -> str:
        caps = sorted(self.required_capabilities)
        return (
            f"Blueprint(name={self.name!r}, tier={self.tier.value!r}, "
            f"version={self.version!r}, capabilities={caps!r})"
        )


class BlueprintRegistry:
    """
    Registry of versioned Blueprint objects.

    Analogous to a container image registry: stores canonical Blueprint
    definitions by name and provides lookup and enumeration. Blueprints are
    stored as-is (already immutable frozen dataclasses) and never mutated
    after registration.
    """

    def __init__(self) -> None:
        self._blueprints: dict[str, Blueprint] = {}

    def register(self, blueprint: Blueprint) -> None:
        """
        Register a Blueprint under its name.

        If a Blueprint with the same name already exists it is replaced,
        allowing version upgrades while retaining the name key.

        Args:
            blueprint: The immutable Blueprint to store.
        """
        self._blueprints[blueprint.name] = blueprint

    def get(self, name: str) -> Blueprint:
        """
        Retrieve a Blueprint by name.

        Args:
            name: The blueprint name to look up.

        Returns:
            The registered Blueprint.

        Raises:
            KeyError: If no Blueprint with that name is registered.
        """
        if name not in self._blueprints:
            raise KeyError(f"Blueprint {name!r} not registered")
        return self._blueprints[name]

    def list_blueprints(self) -> list[Blueprint]:
        """Return a snapshot list of all registered Blueprints."""
        return list(self._blueprints.values())

    def __repr__(self) -> str:
        names = sorted(self._blueprints.keys())
        return f"BlueprintRegistry(blueprints={names!r})"
