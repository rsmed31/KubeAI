"""Unit tests for AssignmentPolicy: integration of LLMPool + MCPPool assignment contracts."""

from __future__ import annotations

import pytest

from KubeAI.orchestrator.assignment import Assignment, AssignmentPolicy
from KubeAI.orchestrator.llm_pool import LLMPool, ModelEntry, ModelTier
from KubeAI.orchestrator.mcp_pool import MCPPool, MCPServer

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_policy() -> tuple[AssignmentPolicy, LLMPool, MCPPool]:
    llm = LLMPool()
    llm.register(ModelEntry("claude-haiku-4", "anthropic", ModelTier.FAST, 0.001))
    llm.register(ModelEntry("claude-sonnet-4", "anthropic", ModelTier.CAPABLE, 0.003))
    llm.register(ModelEntry("claude-opus-4", "anthropic", ModelTier.BEST, 0.015))

    mcp = MCPPool()
    mcp.register(MCPServer("web", "http://web:8080", frozenset(["web_search", "fetch_url"])))
    mcp.register(MCPServer("code", "http://code:8080", frozenset(["code_exec", "file_read"])))

    policy = AssignmentPolicy(llm, mcp)
    return policy, llm, mcp


# ---------------------------------------------------------------------------
# Basic assignment contracts
# ---------------------------------------------------------------------------


class TestAssignmentBasic:
    def test_returns_assignment_instance(self) -> None:
        policy, _, _ = _make_policy()
        result = policy.assign(blueprint_tier=ModelTier.FAST, cost_hint=0.5)
        assert isinstance(result, Assignment)

    def test_assignment_is_immutable(self) -> None:
        policy, _, _ = _make_policy()
        a = policy.assign()
        with pytest.raises((AttributeError, TypeError)):
            a.model_id = "hacked"  # type: ignore[misc]

    def test_provider_field_populated(self) -> None:
        policy, _, _ = _make_policy()
        a = policy.assign()
        assert a.provider == "anthropic"

    def test_no_required_capabilities_gives_empty_mcp_list(self) -> None:
        policy, _, _ = _make_policy()
        a = policy.assign(blueprint_tier=ModelTier.FAST)
        assert len(a.mcp_servers) == 0

    def test_repr_includes_model_and_tier(self) -> None:
        policy, _, _ = _make_policy()
        a = policy.assign()
        assert "model_id=" in repr(a)
        assert "tier=" in repr(a)


# ---------------------------------------------------------------------------
# LLM tier selection via policy
# ---------------------------------------------------------------------------


class TestAssignmentTierSelection:
    def test_minimum_tier_respected(self) -> None:
        policy, _, _ = _make_policy()
        a = policy.assign(blueprint_tier=ModelTier.BEST, cost_hint=0.0)
        assert a.tier == ModelTier.BEST

    def test_low_cost_hint_selects_fast(self) -> None:
        policy, _, _ = _make_policy()
        a = policy.assign(blueprint_tier=ModelTier.FAST, cost_hint=0.1)
        assert a.tier == ModelTier.FAST

    def test_high_cost_hint_selects_best(self) -> None:
        policy, _, _ = _make_policy()
        a = policy.assign(blueprint_tier=ModelTier.FAST, cost_hint=0.9)
        assert a.tier == ModelTier.BEST

    def test_mid_cost_hint_selects_capable(self) -> None:
        policy, _, _ = _make_policy()
        a = policy.assign(blueprint_tier=ModelTier.FAST, cost_hint=0.5)
        assert a.tier == ModelTier.CAPABLE


# ---------------------------------------------------------------------------
# MCP capability attachment
# ---------------------------------------------------------------------------


class TestAssignmentMCPAttachment:
    def test_single_capability_attaches_one_server(self) -> None:
        policy, _, _ = _make_policy()
        a = policy.assign(required_capabilities=["web_search"])
        assert len(a.mcp_servers) == 1
        assert a.mcp_servers[0].server_id == "web"

    def test_two_disjoint_capabilities_attach_two_servers(self) -> None:
        policy, _, _ = _make_policy()
        a = policy.assign(required_capabilities=["web_search", "code_exec"])
        server_ids = {s.server_id for s in a.mcp_servers}
        assert "web" in server_ids
        assert "code" in server_ids

    def test_mcp_servers_cover_all_required_capabilities(self) -> None:
        policy, _, _ = _make_policy()
        caps = ["web_search", "code_exec", "file_read"]
        a = policy.assign(required_capabilities=caps)
        covered = set().union(*(s.capabilities for s in a.mcp_servers))
        assert set(caps).issubset(covered)


# ---------------------------------------------------------------------------
# Routing model override (hard rule from agents.md §7)
# ---------------------------------------------------------------------------


class TestRoutingModelOverride:
    def test_routing_model_is_always_largest(self) -> None:
        policy, _, _ = _make_policy()
        model = policy.routing_model()
        assert model.tier == ModelTier.BEST
        assert model.model_id == "claude-opus-4"

    def test_routing_model_skips_unhealthy_best(self) -> None:
        policy, llm, _ = _make_policy()
        llm.update_health("claude-opus-4", healthy=False)
        model = policy.routing_model()
        assert model.model_id == "claude-sonnet-4"

    def test_routing_model_independent_of_cost_hint(self) -> None:
        """routing_model() must ignore cost_hint — it always returns the largest."""
        policy, _, _ = _make_policy()
        # Even if we had just called assign() with cost_hint=0.0 (wants FAST),
        # routing_model() must still return BEST.
        policy.assign(blueprint_tier=ModelTier.FAST, cost_hint=0.0)
        model = policy.routing_model()
        assert model.tier == ModelTier.BEST


# ---------------------------------------------------------------------------
# Failover integration
# ---------------------------------------------------------------------------


class TestFailoverIntegration:
    def test_assign_falls_back_when_preferred_model_unhealthy(self) -> None:
        policy, llm, _ = _make_policy()
        llm.update_health("claude-haiku-4", healthy=False)
        # cost_hint=0.1 wants FAST but haiku is unhealthy → should pick next
        a = policy.assign(blueprint_tier=ModelTier.FAST, cost_hint=0.1)
        assert a.model_id != "claude-haiku-4"

    def test_assign_falls_back_when_preferred_model_overloaded(self) -> None:
        policy, llm, _ = _make_policy()
        llm.update_health("claude-sonnet-4", healthy=True, load=0.95)
        # cost_hint=0.5 wants CAPABLE (sonnet) but load is above threshold
        a = policy.assign(blueprint_tier=ModelTier.FAST, cost_hint=0.5)
        assert a.model_id != "claude-sonnet-4"

    def test_repr(self) -> None:
        policy, _, _ = _make_policy()
        assert "LLMPool" in repr(policy)
        assert "MCPPool" in repr(policy)


class TestDescriptionAwareSelection:
    def test_task_text_guides_model_and_mcp_selection(self) -> None:
        llm = LLMPool()
        llm.register(ModelEntry("cloud-fast", "anthropic", ModelTier.FAST, 0.001))
        llm.register(
            ModelEntry(
                "llama3.1:8b",
                "ollama",
                ModelTier.FAST,
                0.0,
                description="local offline ollama runtime",
            )
        )

        mcp = MCPPool()
        mcp.register(
            MCPServer(
                "internet-search",
                "http://search:8080",
                frozenset(["search"]),
                description="internet web research",
            )
        )
        mcp.register(
            MCPServer(
                "repo-search",
                "http://repo:8080",
                frozenset(["search"]),
                description="repository code symbol lookup",
            )
        )

        policy = AssignmentPolicy(llm, mcp)
        assignment = policy.assign(
            blueprint_tier=ModelTier.FAST,
            required_capabilities=["search"],
            cost_hint=0.1,
            task="run locally with ollama and search web documentation",
        )

        assert assignment.model_id == "llama3.1:8b"
        assert assignment.mcp_servers[0].server_id == "internet-search"
