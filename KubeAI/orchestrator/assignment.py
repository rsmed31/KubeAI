"""AssignmentPolicy is the kube-scheduler analogue: combines LLMPool and MCPPool signals into an immutable spawn-time assignment."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

# sentinel — distinguishes "no key" from explicitly empty string
_UNSET = ""

from .llm_pool import LLMPool, ModelEntry, ModelTier
from .mcp_pool import MCPPool, MCPServer


@dataclass(frozen=True)
class Assignment:
    """
    Immutable spawn-time resource allocation produced by AssignmentPolicy.

    Analogous to a Kubernetes pod spec after scheduling: the agent receives
    this object at spawn and must not deviate from it.
    """

    model_id: str
    provider: str
    tier: ModelTier
    mcp_servers: tuple[MCPServer, ...] = field(default_factory=tuple)
    # Credentials forwarded from ModelEntry — never logged/serialised
    api_key: str = field(default="", repr=False, compare=False, hash=False)
    base_url: str = field(default="", compare=False, hash=False)

    def __repr__(self) -> str:
        mcp_ids = [s.server_id for s in self.mcp_servers]
        has_key = "yes" if self.api_key else "no"
        return (
            f"Assignment(model_id={self.model_id!r}, tier={self.tier.value!r}, "
            f"api_key={has_key}, mcp_servers={mcp_ids!r})"
        )


class AssignmentPolicy:
    """
    Combines LLMPool and MCPPool signals to produce a deterministic spawn-time
    resource assignment for each agent workload.

    Analogous to the Kubernetes scheduler's pod-to-node binding: given the
    blueprint's resource requirements (tier, capability tags) and real-time
    signals (cost hint, pool health), it emits an immutable Assignment consumed
    by the Scheduler at spawn time.

    Invariants enforced here:
    - Agents NEVER self-select their model or tools.
    - Orchestrator routing ALWAYS runs on the largest registered model
      (use routing_model() before every routing call).
    """

    def __init__(self, llm_pool: LLMPool, mcp_pool: MCPPool) -> None:
        self._llm = llm_pool
        self._mcp = mcp_pool

    def assign(
        self,
        *,
        blueprint_tier: ModelTier = ModelTier.FAST,
        required_capabilities: Iterable[str] = (),
        cost_hint: float = 0.5,
        task: str = "",
    ) -> Assignment:
        """
        Produce a complete spawn-time assignment.

        Args:
            blueprint_tier: Minimum model tier declared in the blueprint.
            required_capabilities: MCP capability tags the task needs.
            cost_hint: Float 0.0 (cheapest/simplest) to 1.0 (most capable)
                       signalling task complexity for LLM tier selection.
            task: Optional task text used to prefer pool entries whose
                descriptions semantically match the workload.

        Returns:
            An immutable Assignment with selected model metadata and MCP list.

        Raises:
            RuntimeError: If LLMPool cannot satisfy the minimum tier.
            ValueError: If MCPPool cannot cover a required capability.
        """
        model: ModelEntry = self._llm.select(
            minimum_tier=blueprint_tier,
            cost_hint=cost_hint,
            task=task,
        )
        mcps: list[MCPServer] = self._mcp.select(
            required_capabilities,
            task=task,
        )
        return Assignment(
            model_id=model.model_id,
            provider=model.provider,
            tier=model.tier,
            mcp_servers=tuple(mcps),
            api_key=model.api_key,
            base_url=model.base_url,
        )

    def routing_model(self) -> ModelEntry:
        """
        Return the model to use for orchestrator routing decisions.

        Always the largest (highest tier, then least loaded healthy) registered
        model — regardless of blueprint constraints or cost hints.
        This enforces the hard rule from agents.md §7.
        """
        return self._llm.routing_model()

    def __repr__(self) -> str:
        return f"AssignmentPolicy(llm_pool={self._llm!r}, mcp_pool={self._mcp!r})"
