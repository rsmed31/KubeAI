"""Unit tests for JSON-based pool loading and validation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from KubeAI.orchestrator import (
    ModelTier,
    PoolConfigError,
    load_assignment_policy_from_json,
    load_pools_from_json,
)


class TestPoolLoader:
    def test_load_pools_from_json_builds_all_pools(self, tmp_path: Path) -> None:
        config = {
            "llm_models": [
                {
                    "model_id": "model-fast",
                    "provider": "test",
                    "tier": "fast",
                    "cost_per_1k_tokens": 0.001,
                    "description": "fast general model",
                },
                {
                    "model_id": "model-best",
                    "provider": "test",
                    "tier": "best",
                    "cost_per_1k_tokens": 0.01,
                    "description": "best reasoning model",
                },
                {
                    "model_id": "llama3.1:8b",
                    "provider": "ollama",
                    "tier": "fast",
                    "cost_per_1k_tokens": 0.0,
                    "description": "local ollama model",
                    "is_local": True,
                },
                {
                    "model_id": "mistral-local-7b",
                    "provider": "local",
                    "tier": "capable",
                    "cost_per_1k_tokens": 0.0,
                    "description": "on-prem local runtime model",
                },
            ],
            "mcp_servers": [
                {
                    "server_id": "web",
                    "endpoint": "http://mcp/web",
                    "capabilities": ["web_search", "fetch_url"],
                    "description": "web retrieval",
                }
            ],
            "a2a_agents": [
                {
                    "agent_id": "agent-1",
                    "name": "agent-1",
                    "endpoint": "http://agents/1",
                    "capabilities": ["rag_retrieval", "fetch_url"],
                    "description": "research summarizer",
                    "metadata": {"domain": "default"},
                }
            ],
        }
        path = tmp_path / "pools.json"
        path.write_text(json.dumps(config), encoding="utf-8")

        bundle = load_pools_from_json(path)

        models = bundle.llm_pool.list_models()
        mcps = bundle.mcp_pool.list_servers()
        agents = bundle.a2a_pool.list_agents()

        assert len(models) == 4
        assert bundle.llm_pool.routing_model().tier == ModelTier.BEST
        assert any(model.model_id == "llama3.1:8b" and model.is_local_runtime() for model in models)
        assert any(model.provider == "local" and model.is_local_runtime() for model in models)
        assert len(mcps) == 1
        assert mcps[0].server_id == "web"
        assert mcps[0].description == "web retrieval"
        assert len(agents) == 1
        assert agents[0].agent_id == "agent-1"
        assert agents[0].description == "research summarizer"

    def test_load_assignment_policy_from_json(self, tmp_path: Path) -> None:
        config = {
            "llm_models": [
                {
                    "model_id": "model-capable",
                    "provider": "test",
                    "tier": "capable",
                    "cost_per_1k_tokens": 0.003,
                }
            ],
            "mcp_servers": [
                {
                    "server_id": "web",
                    "endpoint": "http://mcp/web",
                    "capabilities": ["web_search"],
                }
            ],
            "a2a_agents": [],
        }
        path = tmp_path / "policy.json"
        path.write_text(json.dumps(config), encoding="utf-8")

        policy = load_assignment_policy_from_json(path)
        assignment = policy.assign(required_capabilities=["web_search"])

        assert assignment.model_id == "model-capable"
        assert [server.server_id for server in assignment.mcp_servers] == ["web"]

    def test_invalid_root_type_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "bad.json"
        path.write_text(json.dumps(["not", "an", "object"]), encoding="utf-8")

        with pytest.raises(PoolConfigError, match="root"):
            load_pools_from_json(path)

    def test_invalid_model_tier_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "bad-tier.json"
        path.write_text(
            json.dumps(
                {
                    "llm_models": [
                        {
                            "model_id": "model-x",
                            "provider": "test",
                            "tier": "ultra",
                            "cost_per_1k_tokens": 0.1,
                        }
                    ],
                    "mcp_servers": [],
                    "a2a_agents": [],
                }
            ),
            encoding="utf-8",
        )

        with pytest.raises(PoolConfigError, match="tier"):
            load_pools_from_json(path)

    def test_invalid_mcp_capabilities_type_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "bad-mcp.json"
        path.write_text(
            json.dumps(
                {
                    "llm_models": [],
                    "mcp_servers": [
                        {
                            "server_id": "web",
                            "endpoint": "http://mcp/web",
                            "capabilities": "web_search",
                        }
                    ],
                    "a2a_agents": [],
                }
            ),
            encoding="utf-8",
        )

        with pytest.raises(PoolConfigError, match="capabilities"):
            load_pools_from_json(path)

    def test_missing_llm_models_for_policy_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "missing-llm.json"
        path.write_text(
            json.dumps(
                {
                    "mcp_servers": [],
                    "a2a_agents": [],
                }
            ),
            encoding="utf-8",
        )

        with pytest.raises(PoolConfigError, match="at least one llm_models"):
            load_assignment_policy_from_json(path)
