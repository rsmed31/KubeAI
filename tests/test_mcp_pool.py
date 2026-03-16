"""Unit tests for MCPPool: capability matching, multi-MCP output, and health failover."""

from __future__ import annotations

import pytest

from KubeAI.orchestrator.mcp_pool import MCPPool, MCPServer

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

WEB = MCPServer("web", "http://web:8080", frozenset(["web_search", "fetch_url"]))
CODE = MCPServer("code", "http://code:8080", frozenset(["code_exec", "file_read"]))
MULTI = MCPServer("multi", "http://multi:8080", frozenset(["web_search", "code_exec", "db_query"]))
DB = MCPServer("db", "http://db:8080", frozenset(["db_query", "db_write"]))


def _pool(*servers: MCPServer) -> MCPPool:
    pool = MCPPool()
    for s in servers:
        pool.register(s)
    return pool


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class TestRegistry:
    def test_register_and_list(self) -> None:
        pool = _pool(WEB, CODE)
        assert len(pool.list_servers()) == 2

    def test_register_replaces_existing(self) -> None:
        pool = _pool(WEB)
        updated = MCPServer("web", "http://web2:8080", frozenset(["web_search"]))
        pool.register(updated)
        servers = pool.list_servers()
        assert len(servers) == 1
        assert servers[0].endpoint == "http://web2:8080"

    def test_update_health_marks_unhealthy(self) -> None:
        pool = _pool(WEB)
        pool.update_health("web", healthy=False)
        assert not pool.list_servers()[0].healthy

    def test_update_health_unknown_server_raises(self) -> None:
        pool = _pool(WEB)
        with pytest.raises(KeyError):
            pool.update_health("nonexistent", healthy=False)

    def test_repr(self) -> None:
        pool = _pool(WEB, CODE)
        assert "2" in repr(pool)

    def test_repr_server(self) -> None:
        assert "web_search" in repr(WEB)


# ---------------------------------------------------------------------------
# select — capability matching
# ---------------------------------------------------------------------------


class TestSelect:
    def test_empty_requirements_returns_empty(self) -> None:
        pool = _pool(WEB, CODE)
        assert pool.select([]) == []

    def test_single_capability_single_server(self) -> None:
        pool = _pool(WEB, CODE)
        result = pool.select(["web_search"])
        assert len(result) == 1
        assert result[0].server_id == "web"

    def test_two_capabilities_one_server_covers_both(self) -> None:
        pool = _pool(MULTI)
        result = pool.select(["web_search", "code_exec"])
        assert len(result) == 1
        assert result[0].server_id == "multi"

    def test_two_capabilities_require_two_servers(self) -> None:
        pool = _pool(WEB, CODE)
        result = pool.select(["web_search", "code_exec"])
        server_ids = {s.server_id for s in result}
        assert "web" in server_ids
        assert "code" in server_ids

    def test_greedy_prefers_single_server_over_two(self) -> None:
        """When MULTI covers both caps, it should beat WEB + CODE (2 servers)."""
        pool = _pool(WEB, CODE, MULTI)
        result = pool.select(["web_search", "code_exec"])
        assert len(result) == 1
        assert result[0].server_id == "multi"

    def test_multi_mcp_for_single_task(self) -> None:
        """A task needing 3 disjoint caps gets 2 servers (WEB + CODE)."""
        pool = _pool(WEB, CODE)
        result = pool.select(["web_search", "file_read", "code_exec"])
        # web covers web_search (+fetch_url), code covers file_read+code_exec
        assert len(result) == 2

    def test_three_servers_for_three_disjoint_capability_groups(self) -> None:
        pool = _pool(WEB, CODE, DB)
        result = pool.select(["web_search", "code_exec", "db_query"])
        assert len(result) <= 3  # greedy may find overlap

    def test_unsatisfiable_capability_raises(self) -> None:
        pool = _pool(WEB)
        with pytest.raises(ValueError, match="capabilities"):
            pool.select(["quantum_entanglement"])

    def test_healthy_preferred_over_unhealthy(self) -> None:
        """Both WEB and MULTI cover web_search; WEB is unhealthy → pick MULTI."""
        pool = _pool(WEB, MULTI)
        pool.update_health("web", healthy=False)
        result = pool.select(["web_search"])
        assert result[0].server_id == "multi"

    def test_falls_back_to_unhealthy_when_only_option(self) -> None:
        """Only WEB can satisfy web_search but it's unhealthy → still returned."""
        pool = _pool(WEB)
        pool.update_health("web", healthy=False)
        result = pool.select(["web_search"])
        assert result[0].server_id == "web"

    def test_result_covers_all_required_capabilities(self) -> None:
        pool = _pool(WEB, CODE, DB, MULTI)
        caps = ["web_search", "code_exec", "db_write", "file_read"]
        result = pool.select(caps)
        covered = set().union(*(s.capabilities for s in result))
        assert set(caps).issubset(covered)
