"""Dashboard dependency injection — runtime bootstrap wiring all KubeAI components once at startup."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import TYPE_CHECKING

from KubeAI.api.control_plane import ControlPlaneAPI
from KubeAI.blueprint import Blueprint, BlueprintRegistry
from KubeAI.memory.shared_memory import SharedMemory
from KubeAI.orchestrator.assignment import AssignmentPolicy
from KubeAI.orchestrator.llm_pool import LLMPool, ModelEntry, ModelTier
from KubeAI.orchestrator.mcp_pool import MCPPool, MCPServer
from KubeAI.orchestrator.orchestrator import Orchestrator
from KubeAI.scheduler.lifecycle import AgentLifecycleManager

if TYPE_CHECKING:
    from KubeAI.executor.task_worker import TaskWorker


@dataclass
class Runtime:
    """Single object holding the complete wired KubeAI runtime."""

    control_plane: ControlPlaneAPI
    llm_pool: LLMPool
    mcp_pool: MCPPool
    orchestrator: Orchestrator
    lifecycle: AgentLifecycleManager
    registry: BlueprintRegistry
    memory: SharedMemory
    task_worker: "TaskWorker"


_runtime: Runtime | None = None


def bootstrap_runtime() -> Runtime:
    """Wire all components. Called once from lifespan(). Idempotent."""
    global _runtime
    if _runtime is not None:
        return _runtime

    # ── 1. Pools ──────────────────────────────────────────────────────────
    llm_pool = LLMPool()
    mcp_pool = MCPPool()

    _register_default_models(llm_pool)
    _register_default_mcps(mcp_pool)

    # ── 2. Policy + Orchestrator ───────────────────────────────────────────
    policy = AssignmentPolicy(llm_pool, mcp_pool)
    orchestrator = Orchestrator(policy)

    # ── 3. Control plane + shared memory ──────────────────────────────────
    cp = ControlPlaneAPI()
    memory = SharedMemory()

    # Expose llm_pool on cp so status queries can inspect model health
    cp._llm_pool = llm_pool  # noqa: SLF001

    # ── 4. Lifecycle manager ──────────────────────────────────────────────
    lifecycle = AgentLifecycleManager(policy, cp, memory)

    # ── 5. Blueprint registry ─────────────────────────────────────────────
    registry = BlueprintRegistry()
    _register_default_blueprints(registry)

    # ── 6. Task worker ────────────────────────────────────────────────────
    from KubeAI.executor.task_worker import TaskWorker

    worker = TaskWorker(cp, orchestrator, lifecycle, registry, memory)
    worker.start()

    # ── 7. Health probing ─────────────────────────────────────────────────
    llm_pool.start_health_probing(interval_s=60)

    _runtime = Runtime(
        control_plane=cp,
        llm_pool=llm_pool,
        mcp_pool=mcp_pool,
        orchestrator=orchestrator,
        lifecycle=lifecycle,
        registry=registry,
        memory=memory,
        task_worker=worker,
    )
    return _runtime


def get_runtime() -> Runtime:
    """Return the global Runtime, bootstrapping if needed."""
    global _runtime
    if _runtime is None:
        return bootstrap_runtime()
    return _runtime


def get_control_plane() -> ControlPlaneAPI:
    """FastAPI dependency: returns the shared ControlPlaneAPI instance."""
    return get_runtime().control_plane


import threading as _threading


@dataclass
class ClusterConfig:
    """Configuration for creating a new cluster."""
    name: str
    description: str = ""
    num_workers: int = 4
    inherit_models: bool = True   # copy default model registrations
    inherit_mcps: bool = True     # copy default MCP registrations
    inherit_blueprints: bool = True  # copy default blueprints


class ClusterRegistry:
    """Registry of named cluster runtimes — the multi-cluster control plane.

    Analogous to kubeconfig contexts: each entry is a fully wired, isolated
    KubeAI runtime with its own agent pool, task queue, and LLM/MCP resources.
    The 'default' cluster is always present after bootstrap.
    """

    def __init__(self) -> None:
        self._clusters: dict[str, Runtime] = {}
        self._lock = _threading.RLock()

    def register(self, name: str, runtime: Runtime) -> None:
        """Register a runtime under a cluster name."""
        with self._lock:
            self._clusters[name] = runtime

    def get(self, name: str) -> Runtime:
        """Return a cluster runtime by name. Raises KeyError if not found."""
        with self._lock:
            if name not in self._clusters:
                raise KeyError(f"Cluster {name!r} not found")
            return self._clusters[name]

    def list_clusters(self) -> list[str]:
        """Return sorted list of cluster names."""
        with self._lock:
            return sorted(self._clusters.keys())

    def exists(self, name: str) -> bool:
        with self._lock:
            return name in self._clusters

    def create(self, config: ClusterConfig) -> Runtime:
        """Create and register a new isolated cluster runtime."""
        from KubeAI.executor.task_worker import TaskWorker

        llm_pool = LLMPool()
        mcp_pool = MCPPool()

        if config.inherit_models:
            _register_default_models(llm_pool)
        if config.inherit_mcps:
            _register_default_mcps(mcp_pool)

        policy = AssignmentPolicy(llm_pool, mcp_pool)
        orchestrator = Orchestrator(policy)
        cp = ControlPlaneAPI()
        memory = SharedMemory()
        cp._llm_pool = llm_pool  # noqa: SLF001

        lifecycle = AgentLifecycleManager(policy, cp, memory)

        registry = BlueprintRegistry()
        if config.inherit_blueprints:
            _register_default_blueprints(registry)

        worker = TaskWorker(cp, orchestrator, lifecycle, registry, memory,
                            num_workers=config.num_workers)
        worker.start()
        llm_pool.start_health_probing(interval_s=60)

        runtime = Runtime(
            control_plane=cp,
            llm_pool=llm_pool,
            mcp_pool=mcp_pool,
            orchestrator=orchestrator,
            lifecycle=lifecycle,
            registry=registry,
            memory=memory,
            task_worker=worker,
        )
        self.register(config.name, runtime)
        return runtime

    def delete(self, name: str) -> bool:
        """Remove a cluster. Returns False if not found or if name=='default'."""
        if name == "default":
            return False
        with self._lock:
            return self._clusters.pop(name, None) is not None

    def snapshot(self) -> list[dict]:
        """Return a status snapshot of all clusters for the dashboard."""
        result = []
        with self._lock:
            names = sorted(self._clusters.keys())
        for name in names:
            try:
                rt = self.get(name)
                cp = rt.control_plane
                agents = cp.list_agents()
                tasks = cp.list_tasks(limit=1000)
                running = sum(1 for a in agents if a.state == "running")
                idle = sum(1 for a in agents if a.state == "idle")
                complete = sum(1 for t in tasks if t.status == "success")
                queued = sum(1 for t in tasks if t.status == "queued")
                models = [m.model_id for m in rt.llm_pool.list_models()]
                result.append({
                    "name": name,
                    "status": "healthy",
                    "agents": {"total": len(agents), "running": running, "idle": idle},
                    "tasks": {"total": len(tasks), "complete": complete, "queued": queued},
                    "models": models,
                    "blueprint_count": len(rt.registry.list_blueprints()),
                })
            except Exception:
                result.append({"name": name, "status": "error", "agents": {}, "tasks": {}})
        return result


_cluster_registry: ClusterRegistry | None = None


def get_cluster_registry() -> ClusterRegistry:
    """Return the global ClusterRegistry, creating the default cluster if needed."""
    global _cluster_registry
    if _cluster_registry is None:
        _cluster_registry = ClusterRegistry()
        # Register the default singleton runtime as the 'default' cluster
        _cluster_registry.register("default", get_runtime())
    return _cluster_registry


def get_cluster_runtime(name: str) -> Runtime:
    """Return the Runtime for a named cluster."""
    return get_cluster_registry().get(name)


# ── Default registrations ──────────────────────────────────────────────────

def _register_default_models(pool: LLMPool) -> None:
    """Register default Anthropic models unless overridden by KUBEAI_MODELS_CONFIG."""
    config_path = os.environ.get("KUBEAI_MODELS_CONFIG")
    if config_path:
        try:
            from KubeAI.orchestrator.pool_loader import load_pools_from_json
            load_pools_from_json(config_path, llm_pool=pool)
            return
        except Exception:
            pass  # Fall through to defaults

    pool.register(ModelEntry(
        model_id="claude-haiku-4-5-20251001",
        provider="anthropic",
        tier=ModelTier.FAST,
        cost_per_1k_tokens=0.001,
        description="Fast lightweight model for simple tasks",
    ))
    pool.register(ModelEntry(
        model_id="claude-sonnet-4-5",
        provider="anthropic",
        tier=ModelTier.CAPABLE,
        cost_per_1k_tokens=0.003,
        description="Balanced model for most tasks",
    ))
    pool.register(ModelEntry(
        model_id="claude-opus-4-5",
        provider="anthropic",
        tier=ModelTier.BEST,
        cost_per_1k_tokens=0.015,
        description="Most capable model for complex tasks",
    ))


def _register_default_mcps(pool: MCPPool) -> None:
    """Register default MCP server stubs."""
    pool.register(MCPServer(
        server_id="web_search",
        endpoint="http://localhost:9001/mcp/web_search",
        capabilities=frozenset({"web_search", "fetch_url"}),
        description="Web search and URL fetching",
    ))
    pool.register(MCPServer(
        server_id="code_exec",
        endpoint="http://localhost:9002/mcp/code_exec",
        capabilities=frozenset({"code_exec", "data_processing"}),
        description="Code execution and data processing",
    ))
    pool.register(MCPServer(
        server_id="db_query",
        endpoint="http://localhost:9003/mcp/db_query",
        capabilities=frozenset({"db_query", "sql"}),
        description="Database query execution",
    ))


def _register_default_blueprints(registry: BlueprintRegistry) -> None:
    """Register 4 default production blueprints."""
    registry.register(Blueprint(
        name="general_agent",
        description="General-purpose agent for broad tasks and questions",
        tier=ModelTier.FAST,
        system_prompt=(
            "You are a general-purpose AI assistant. You help with a wide variety of tasks "
            "including answering questions, analysis, writing, and reasoning. Be concise, "
            "accurate, and helpful."
        ),
        required_capabilities=frozenset(),
        version="1.0",
    ))
    registry.register(Blueprint(
        name="coding_agent",
        description="Software engineering agent for code writing, review, and debugging",
        tier=ModelTier.CAPABLE,
        system_prompt=(
            "You are an expert software engineer. You write clean, efficient, well-tested code. "
            "You debug issues methodically, explain your reasoning, and follow best practices. "
            "Prefer working solutions over theoretical ones."
        ),
        required_capabilities=frozenset({"code_exec"}),
        version="1.0",
    ))
    registry.register(Blueprint(
        name="research_agent",
        description="Research and information synthesis agent for deep analysis",
        tier=ModelTier.CAPABLE,
        system_prompt=(
            "You are a research specialist. You gather, synthesize, and analyze information "
            "from multiple sources. You produce structured, well-cited summaries and reports. "
            "Be thorough and identify key insights."
        ),
        required_capabilities=frozenset({"web_search"}),
        version="1.0",
    ))
    registry.register(Blueprint(
        name="data_agent",
        description="Data analysis agent for processing structured and unstructured data",
        tier=ModelTier.CAPABLE,
        system_prompt=(
            "You are a data analyst. You process, clean, and analyze datasets. You identify "
            "patterns, generate statistics, create summaries, and produce actionable insights. "
            "Handle CSV, JSON, SQL, and free-form data formats."
        ),
        required_capabilities=frozenset({"data_processing"}),
        version="1.0",
    ))
