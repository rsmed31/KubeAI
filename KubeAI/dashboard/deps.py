"""Dashboard dependency injection — runtime bootstrap wiring all KubeAI components once at startup."""

from __future__ import annotations

import os
import logging
import pathlib
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from KubeAI.adapters.registry import AdapterRegistry
from KubeAI.adapters.selector import AdapterSelector
from KubeAI.api.control_plane import ControlPlaneAPI
from KubeAI.blueprint import Blueprint, BlueprintRegistry
from KubeAI.config.store import ConfigStore
from KubeAI.config.skill import SkillRegistry
from KubeAI.workflow.intake import WorkflowIntake
from KubeAI.deployment import (
    AutoscaleController,
    AutoscaleControllerConfig,
    DeploymentReconciler,
    DeploymentSpec,
    HorizontalAgentScaler,
)
from KubeAI.memory.shared_memory import SharedMemory
from KubeAI.orchestrator.assignment import AssignmentPolicy
from KubeAI.orchestrator.llm_pool import LLMPool, ModelEntry, ModelTier
from KubeAI.orchestrator.mcp_pool import MCPPool, MCPServer
from KubeAI.orchestrator.orchestrator import Orchestrator
from KubeAI.benchmarks.engine import BenchmarkEngine
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
    deployment_reconciler: DeploymentReconciler
    autoscaler: HorizontalAgentScaler
    autoscale_controller: AutoscaleController
    config_store: ConfigStore
    skill_registry: SkillRegistry
    benchmark_engine: BenchmarkEngine
    adapter_registry: AdapterRegistry
    adapter_selector: AdapterSelector
    workflow_intake: WorkflowIntake


_runtime: Runtime | None = None
_LOGGER = logging.getLogger(__name__)


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

    # ── 5b. Config store + skills ──────────────────────────────────────
    postgres_dsn = os.environ.get("KUBEAI_POSTGRES_DSN", "")
    config_store = ConfigStore(dsn=postgres_dsn)
    skill_registry = SkillRegistry(dsn=postgres_dsn)
    _auto_register_file_skills(skill_registry)
    if postgres_dsn:
        config_store.start_watching()

    # ── 5c. Adapter registry + selector + workflow intake ─────────────────
    from KubeAI.adapters.litellm_adapter import LiteLLMAdapter
    adapter_registry = AdapterRegistry()
    adapter_registry.register(LiteLLMAdapter())
    # Register optional framework adapters if their deps are available
    for adapter_cls_path in [
        ("KubeAI.adapters.langchain_adapter", "LangChainAdapter"),
        ("KubeAI.adapters.llamaindex_adapter", "LlamaIndexAdapter"),
        ("KubeAI.adapters.autogen_adapter", "AutoGenAdapter"),
        ("KubeAI.adapters.crewai_adapter", "CrewAIAdapter"),
    ]:
        try:
            import importlib
            mod = importlib.import_module(adapter_cls_path[0])
            cls = getattr(mod, adapter_cls_path[1])
            adapter = cls()
            if adapter.health_check():
                adapter_registry.register(adapter)
        except Exception:
            pass

    # ── 6. Task worker ────────────────────────────────────────────────────
    from KubeAI.executor.task_worker import TaskWorker

    worker = TaskWorker(cp, orchestrator, lifecycle, registry, memory)
    worker.start()

    # ── 7. Deployment autoscaling control loop ───────────────────────────
    deployment_reconciler = DeploymentReconciler(lifecycle, registry, cp)
    autoscaler = HorizontalAgentScaler(deployment_reconciler)
    autoscale_controller = AutoscaleController(
        cp,
        deployment_reconciler,
        autoscaler,
        specs=_default_deployment_specs(registry),
        config=AutoscaleControllerConfig(interval_s=3.0, recent_tasks=50),
    )
    autoscale_controller.start()

    # ── 8. Health probing ─────────────────────────────────────────────────
    llm_pool.start_health_probing(interval_s=60)

    benchmark_engine = BenchmarkEngine()
    adapter_selector = AdapterSelector(adapter_registry, benchmark_engine)
    workflow_intake = WorkflowIntake(selector=adapter_selector)
    # Attach workflow intake to task worker for framework-aware execution
    worker._workflow_intake = workflow_intake  # noqa: SLF001

    _runtime = Runtime(
        control_plane=cp,
        llm_pool=llm_pool,
        mcp_pool=mcp_pool,
        orchestrator=orchestrator,
        lifecycle=lifecycle,
        registry=registry,
        memory=memory,
        task_worker=worker,
        deployment_reconciler=deployment_reconciler,
        autoscaler=autoscaler,
        autoscale_controller=autoscale_controller,
        config_store=config_store,
        skill_registry=skill_registry,
        benchmark_engine=benchmark_engine,
        adapter_registry=adapter_registry,
        adapter_selector=adapter_selector,
        workflow_intake=workflow_intake,
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

        deployment_reconciler = DeploymentReconciler(lifecycle, registry, cp)
        autoscaler = HorizontalAgentScaler(deployment_reconciler)
        autoscale_controller = AutoscaleController(
            cp,
            deployment_reconciler,
            autoscaler,
            specs=_default_deployment_specs(registry),
            config=AutoscaleControllerConfig(interval_s=3.0, recent_tasks=50),
        )
        autoscale_controller.start()

        llm_pool.start_health_probing(interval_s=60)

        # Per-cluster config store + skill registry
        cluster_postgres_dsn = os.environ.get("KUBEAI_POSTGRES_DSN", "")
        cluster_config_store = ConfigStore(dsn=cluster_postgres_dsn)
        cluster_skill_registry = SkillRegistry(dsn=cluster_postgres_dsn)
        _auto_register_file_skills(cluster_skill_registry)
        if cluster_postgres_dsn:
            cluster_config_store.start_watching()

        from KubeAI.adapters.litellm_adapter import LiteLLMAdapter
        cluster_adapter_registry = AdapterRegistry()
        cluster_adapter_registry.register(LiteLLMAdapter())
        cluster_benchmark_engine = BenchmarkEngine()
        cluster_selector = AdapterSelector(cluster_adapter_registry, cluster_benchmark_engine)
        cluster_intake = WorkflowIntake(selector=cluster_selector)
        worker._workflow_intake = cluster_intake  # noqa: SLF001

        runtime = Runtime(
            control_plane=cp,
            llm_pool=llm_pool,
            mcp_pool=mcp_pool,
            orchestrator=orchestrator,
            lifecycle=lifecycle,
            registry=registry,
            memory=memory,
            task_worker=worker,
            deployment_reconciler=deployment_reconciler,
            autoscaler=autoscaler,
            autoscale_controller=autoscale_controller,
            config_store=cluster_config_store,
            skill_registry=cluster_skill_registry,
            benchmark_engine=cluster_benchmark_engine,
            adapter_registry=cluster_adapter_registry,
            adapter_selector=cluster_selector,
            workflow_intake=cluster_intake,
        )
        self.register(config.name, runtime)
        return runtime

    def delete(self, name: str) -> bool:
        """Remove a cluster. Returns False if not found or if name=='default'."""
        if name == "default":
            return False
        with self._lock:
            runtime = self._clusters.pop(name, None)
        if runtime is None:
            return False
        try:
            runtime.autoscale_controller.stop()
        except Exception:
            pass
        return True

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
    """Register models for every provider whose required env vars are all set.

    If KUBEAI_MODELS_CONFIG env var points to a JSON file, that takes priority.
    """
    from KubeAI.orchestrator.llm_pool import SUPPORTED_PROVIDERS

    config_path = os.environ.get("KUBEAI_MODELS_CONFIG")
    if config_path:
        try:
            from KubeAI.orchestrator.pool_loader import load_pools_from_json
            loaded = load_pools_from_json(config_path)
            for model in loaded.models:
                pool.register(model)
            return
        except Exception:
            pass  # Fall through to auto-detection

    # Auto-detect: register default models for each provider with all required env vars
    registered = 0
    for provider_id, info in SUPPORTED_PROVIDERS.items():
        # Skip providers explicitly marked as not auto-registerable
        if info.get("auto_register") is False:
            continue

        # For endpoint-detected providers (e.g. Ollama), check endpoint reachability
        if info.get("auto_detect") == "endpoint":
            base_url = os.environ.get(
                f"KUBEAI_{provider_id.upper()}_BASE_URL",
                info.get("default_base_url", ""),
            )
            if not _check_endpoint_reachable(base_url):
                continue
            api_key = "ollama"  # LiteLLM convention for local providers
        else:
            # Check ALL required env vars are set
            required_env = info.get("required_env", [])
            if not required_env:
                continue
            missing = [var for var in required_env if not os.environ.get(var, "")]
            if missing:
                if len(missing) < len(required_env):
                    _LOGGER.warning(
                        "Provider %s skipped: missing env vars %s (have %s)",
                        provider_id,
                        missing,
                        [v for v in required_env if v not in missing],
                    )
                continue
            env_var = info.get("api_key_env")
            api_key = os.environ.get(env_var, "") if env_var else ""
            base_url = os.environ.get(
                f"KUBEAI_{provider_id.upper()}_BASE_URL",
                info.get("default_base_url", ""),
            )

        is_local = info.get("is_local", False)
        defaults = info.get("default_models", {})
        tier_map = {
            "fast":    (ModelTier.FAST,    0.001),
            "capable": (ModelTier.CAPABLE, 0.003),
            "best":    (ModelTier.BEST,    0.015),
        }
        for tier_name, model_id in defaults.items():
            tier, default_cost = tier_map[tier_name]
            pool.register(ModelEntry(
                model_id=model_id,
                provider=provider_id,
                tier=tier,
                cost_per_1k_tokens=default_cost,
                description=f"{info['name']} {tier_name} model",
                is_local=is_local,
                api_key=api_key,
                base_url=base_url,
            ))
            registered += 1

    if registered == 0:
        _LOGGER.warning(
            "No LLM models auto-registered from environment; pool starts empty"
        )


def _check_endpoint_reachable(url: str, timeout: float = 1.0) -> bool:
    """Quick HTTP check to see if a local endpoint is up."""
    if not url:
        return False
    import urllib.request
    import urllib.error
    try:
        req = urllib.request.Request(url, method="HEAD")
        urllib.request.urlopen(req, timeout=timeout)  # noqa: S310
        return True
    except Exception:
        return False


def _register_default_mcps(pool: MCPPool) -> None:
    """Do not auto-register MCP servers; they are configured via API/UI."""
    _ = pool


def _register_default_blueprints(registry: BlueprintRegistry) -> None:
    """Register 4 default production blueprints."""
    if os.environ.get("KUBEAI_NO_DEFAULT_BLUEPRINTS", "").strip() == "1":
        return

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


def _default_deployment_specs(registry: BlueprintRegistry) -> list[DeploymentSpec]:
    """Create one autoscaling deployment spec per registered blueprint."""
    specs: list[DeploymentSpec] = []
    for blueprint in registry.list_blueprints():
        specs.append(
            DeploymentSpec(
                name=f"deploy-{blueprint.name}",
                blueprint_name=blueprint.name,
                replicas=0,
                min_replicas=0,
                max_replicas=6,
                target_load=0.7,
                max_token_cost_per_task=0.03,
                labels={"blueprint": blueprint.name},
            )
        )
    return specs


def _auto_register_file_skills(skill_registry: SkillRegistry) -> None:
    """Load markdown files from /skills into SkillRegistry when missing."""
    skills_dir = pathlib.Path(__file__).resolve().parents[2] / "skills"
    if not skills_dir.exists() or not skills_dir.is_dir():
        return

    try:
        existing_names = {s.name.strip().lower() for s in skill_registry.list_skills()}
    except Exception:
        existing_names = set()

    heading_pattern = re.compile(r"^#\s+Skill:\s*(.+)$", re.IGNORECASE | re.MULTILINE)
    role_pattern = re.compile(r"^##\s+Role\s*$", re.IGNORECASE | re.MULTILINE)

    for path in sorted(skills_dir.glob("*.md")):
        try:
            raw = path.read_text(encoding="utf-8")
        except Exception:
            continue
        text = raw.strip()
        if not text:
            continue

        heading_match = heading_pattern.search(text)
        skill_name = (heading_match.group(1).strip() if heading_match else path.stem.replace("-", " ").title())
        if skill_name.lower() in existing_names:
            continue

        description = ""
        role_match = role_pattern.search(text)
        if role_match:
            after_role = text[role_match.end():].strip().splitlines()
            for line in after_role:
                candidate = line.strip().lstrip("- ").strip()
                if candidate and not candidate.startswith("#"):
                    description = candidate
                    break
        if not description:
            description = f"Auto-registered from skills/{path.name}"

        try:
            skill_registry.create(
                name=skill_name,
                description=description[:300],
                system_prompt=text[:12000],
                tags=["file-skill", path.stem],
            )
            existing_names.add(skill_name.lower())
        except Exception:
            continue
