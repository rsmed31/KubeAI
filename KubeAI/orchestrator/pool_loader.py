"""Pool loader is the ConfigMap analogue that hydrates LLMPool, MCPPool, and A2APool from declarative JSON."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .a2a_pool import A2AAgentCard, A2APool
from .assignment import AssignmentPolicy
from .llm_pool import LLMPool, ModelEntry, ModelTier
from .mcp_pool import MCPPool, MCPServer


class PoolConfigError(ValueError):
    """Raised when a JSON pool configuration is missing required fields or has invalid types."""


@dataclass(frozen=True)
class PoolBundle:
    """Container for pools loaded from JSON and ready for orchestrator wiring."""

    llm_pool: LLMPool
    mcp_pool: MCPPool
    a2a_pool: A2APool

    def assignment_policy(self) -> AssignmentPolicy:
        """Build an AssignmentPolicy from the loaded LLM and MCP pools."""
        return AssignmentPolicy(self.llm_pool, self.mcp_pool)

    def __repr__(self) -> str:
        return (
            f"PoolBundle(models={len(self.llm_pool.list_models())}, "
            f"mcps={len(self.mcp_pool.list_servers())}, "
            f"a2a_agents={len(self.a2a_pool.list_agents())})"
        )


def load_pools_from_json(path: str | Path) -> PoolBundle:
    """Load LLM, MCP, and A2A pools from a JSON configuration file."""
    data = _load_json_object(Path(path))

    llm_pool = LLMPool()
    for index, entry in enumerate(_require_list(data, "llm_models")):
        context = f"llm_models[{index}]"
        llm_pool.register(
            ModelEntry(
                model_id=_require_str(entry, "model_id", context),
                provider=_require_str(entry, "provider", context),
                tier=_parse_tier(_require_str(entry, "tier", context), context),
                cost_per_1k_tokens=_require_float(entry, "cost_per_1k_tokens", context),
                load=_optional_float(entry, "load", context, default=0.0),
                healthy=_optional_bool(entry, "healthy", context, default=True),
                description=_optional_str(entry, "description", context, default=""),
                is_local=_optional_bool(entry, "is_local", context, default=False),
            )
        )

    mcp_pool = MCPPool()
    for index, entry in enumerate(_require_list(data, "mcp_servers")):
        context = f"mcp_servers[{index}]"
        mcp_pool.register(
            MCPServer(
                server_id=_require_str(entry, "server_id", context),
                endpoint=_require_str(entry, "endpoint", context),
                capabilities=frozenset(_require_str_list(entry, "capabilities", context)),
                healthy=_optional_bool(entry, "healthy", context, default=True),
                description=_optional_str(entry, "description", context, default=""),
            )
        )

    a2a_pool = A2APool()
    for index, entry in enumerate(_require_list(data, "a2a_agents")):
        context = f"a2a_agents[{index}]"
        a2a_pool.register(
            A2AAgentCard(
                agent_id=_require_str(entry, "agent_id", context),
                name=_require_str(entry, "name", context),
                endpoint=_require_str(entry, "endpoint", context),
                capabilities=frozenset(_require_str_list(entry, "capabilities", context)),
                description=_optional_str(entry, "description", context, default=""),
                load=_optional_float(entry, "load", context, default=0.0),
                healthy=_optional_bool(entry, "healthy", context, default=True),
                metadata=_optional_dict(entry, "metadata", context, default={}),
            )
        )

    return PoolBundle(llm_pool=llm_pool, mcp_pool=mcp_pool, a2a_pool=a2a_pool)


def load_assignment_policy_from_json(path: str | Path) -> AssignmentPolicy:
    """Load LLMPool and MCPPool from JSON and return a ready AssignmentPolicy."""
    bundle = load_pools_from_json(path)
    if not bundle.llm_pool.list_models():
        raise PoolConfigError("Config must define at least one llm_models entry")
    return bundle.assignment_policy()


def _load_json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PoolConfigError(f"Pool config file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise PoolConfigError(f"Invalid JSON in {path}: {exc}") from exc

    if not isinstance(payload, dict):
        raise PoolConfigError("Pool config root must be a JSON object")

    return payload


def _require_list(data: Mapping[str, Any], key: str) -> list[Any]:
    value = data.get(key, [])
    if value is None:
        return []
    if not isinstance(value, list):
        raise PoolConfigError(f"Field {key!r} must be a list")
    return value


def _require_str(entry: Any, key: str, context: str) -> str:
    if not isinstance(entry, Mapping):
        raise PoolConfigError(f"{context} must be an object")

    value = entry.get(key)
    if not isinstance(value, str) or not value.strip():
        raise PoolConfigError(f"{context}.{key} must be a non-empty string")
    return value.strip()


def _require_float(entry: Any, key: str, context: str) -> float:
    if not isinstance(entry, Mapping):
        raise PoolConfigError(f"{context} must be an object")

    value = entry.get(key)
    if not isinstance(value, (int, float)):
        raise PoolConfigError(f"{context}.{key} must be a number")
    return float(value)


def _optional_float(entry: Any, key: str, context: str, default: float) -> float:
    if not isinstance(entry, Mapping):
        raise PoolConfigError(f"{context} must be an object")

    value = entry.get(key, default)
    if not isinstance(value, (int, float)):
        raise PoolConfigError(f"{context}.{key} must be a number")
    return float(value)


def _optional_bool(entry: Any, key: str, context: str, default: bool) -> bool:
    if not isinstance(entry, Mapping):
        raise PoolConfigError(f"{context} must be an object")

    value = entry.get(key, default)
    if not isinstance(value, bool):
        raise PoolConfigError(f"{context}.{key} must be a boolean")
    return value


def _optional_str(entry: Any, key: str, context: str, default: str) -> str:
    if not isinstance(entry, Mapping):
        raise PoolConfigError(f"{context} must be an object")

    value = entry.get(key, default)
    if not isinstance(value, str):
        raise PoolConfigError(f"{context}.{key} must be a string")
    return value


def _optional_dict(
    entry: Any,
    key: str,
    context: str,
    default: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(entry, Mapping):
        raise PoolConfigError(f"{context} must be an object")

    value = entry.get(key, default)
    if not isinstance(value, Mapping):
        raise PoolConfigError(f"{context}.{key} must be an object")
    return dict(value)


def _require_str_list(entry: Any, key: str, context: str) -> list[str]:
    if not isinstance(entry, Mapping):
        raise PoolConfigError(f"{context} must be an object")

    raw = entry.get(key)
    if not isinstance(raw, list):
        raise PoolConfigError(f"{context}.{key} must be a list")

    values: list[str] = []
    for idx, item in enumerate(raw):
        if not isinstance(item, str) or not item.strip():
            raise PoolConfigError(
                f"{context}.{key}[{idx}] must be a non-empty string"
            )
        values.append(item.strip())
    return values


def _parse_tier(value: str, context: str) -> ModelTier:
    try:
        return ModelTier(value)
    except ValueError as exc:
        allowed = ", ".join(tier.value for tier in ModelTier)
        raise PoolConfigError(
            f"{context}.tier must be one of: {allowed}"
        ) from exc
