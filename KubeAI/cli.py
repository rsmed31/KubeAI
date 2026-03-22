"""agentctl is the kubectl analogue for operating KubeAI runtime workflows."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import click
import yaml


_STATE_DIR = ".kubeai"
_STATE_FILE = "cli_state.json"

_RAG_TEMPLATES = ("basic", "hybrid", "reranking", "knowledge_graph", "scraper")
_MEMORY_TEMPLATES = ("sliding_window", "summarizing", "episodic")


def _state_path() -> Path:
    return Path.cwd() / _STATE_DIR / _STATE_FILE


def _default_state() -> dict[str, list[dict[str, Any]]]:
    return {
        "blueprints": [],
        "mcps": [],
    }


def _load_state() -> dict[str, list[dict[str, Any]]]:
    path = _state_path()
    if not path.exists():
        return _default_state()

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - defensive read wrapper
        raise click.ClickException(f"Failed to parse CLI state: {exc}") from exc

    if not isinstance(raw, dict):
        raise click.ClickException("CLI state file is invalid")

    state = _default_state()
    for key in state:
        value = raw.get(key, [])
        if isinstance(value, list):
            state[key] = value
    return state


def _save_state(state: dict[str, list[dict[str, Any]]]) -> None:
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")


def _upsert(items: list[dict[str, Any]], key: str, record: dict[str, Any]) -> str:
    value = record.get(key)
    for index, current in enumerate(items):
        if current.get(key) == value:
            items[index] = record
            return "updated"
    items.append(record)
    return "registered"


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        raise click.ClickException(f"Failed to parse YAML file {path}: {exc}") from exc

    if not isinstance(data, dict):
        raise click.ClickException(f"YAML root must be a mapping in {path}")
    return data


@click.group(help="KubeAI control CLI")
def main() -> None:
    """Entrypoint for KubeAI operator commands."""


@main.command("run")
@click.argument("task", type=str)
@click.option("--rag", "rag_template", type=click.Choice(_RAG_TEMPLATES), default=None)
@click.option("--memory", "memory_template", type=click.Choice(_MEMORY_TEMPLATES), default=None)
@click.option("--blueprint", type=str, default=None, help="Preferred blueprint name")
@click.option("--domain", type=str, default="default", show_default=True, help="Runtime domain")
@click.option("--json-output", is_flag=True, help="Print request payload as JSON")
@click.option("--timeout", type=float, default=5.0, show_default=True, help="Seconds to wait for task result (set higher for slow models)")
def run_task(
    task: str,
    rag_template: str | None,
    memory_template: str | None,
    blueprint: str | None,
    domain: str,
    json_output: bool,
    timeout: float,
) -> None:
    """Submit a task to the KubeAI runtime and print the result."""
    if json_output:
        request = {
            "task": task,
            "rag_template": rag_template,
            "memory_template": memory_template,
            "blueprint": blueprint,
            "domain": domain,
        }
        click.echo(json.dumps(request, indent=2, sort_keys=True))
        return

    # Always echo task options so callers / tests can confirm what was submitted.
    click.echo(f"Task: {task}")
    click.echo(f"RAG template: {rag_template or 'none'}")
    click.echo(f"Memory template: {memory_template or 'none'}")
    click.echo(f"Blueprint preference: {blueprint or 'auto'}")
    click.echo(f"Domain: {domain}")

    try:
        from KubeAI.dashboard.deps import get_control_plane
    except ImportError:
        click.echo("(runtime not available — task logged only)")
        return

    cp = get_control_plane()
    task_info = cp.submit_task(task, blueprint=blueprint)
    task_id = task_info["task_id"]
    click.echo(f"Submitted task {task_id} — waiting for result...")

    result_text = _poll_task_result(cp, task_id, timeout=timeout)
    if result_text is not None:
        click.echo(result_text)
    else:
        click.echo(f"Task {task_id} did not complete within the timeout. Check 'agentctl status'.")


def _poll_task_result(cp: Any, task_id: str, timeout: float = 120) -> str | None:
    """Poll until the task completes and return result text, or None on timeout."""
    from KubeAI.dashboard.deps import get_control_plane

    # Try to read result from shared memory (TaskWorker stores it there)
    try:
        from KubeAI.memory.shared_memory import SharedMemory
        memory = SharedMemory()
    except Exception:
        memory = None

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        # Check shared memory first (fastest path)
        if memory is not None:
            text = memory.get_short_term("task_results", task_id)
            if text is not None:
                return str(text)

        # Fall back to checking task record status
        with cp._lock:
            record = cp._tasks.get(task_id)
        if record is not None and record.status in {"success", "complete", "failed", "error"}:
            if memory is not None:
                text = memory.get_short_term("task_results", task_id)
                if text is not None:
                    return str(text)
            return f"Task completed with status: {record.status}"

        time.sleep(0.5)

    return None


@main.group("blueprints")
def blueprints_group() -> None:
    """Blueprint registry operations."""


@blueprints_group.command("list")
def blueprints_list() -> None:
    """List locally registered blueprints."""
    state = _load_state()
    entries = state["blueprints"]
    if not entries:
        click.echo("No blueprints registered.")
        return

    click.echo("Registered blueprints:")
    for item in sorted(entries, key=lambda entry: (str(entry.get("name", "")), str(entry.get("version", "")))):
        click.echo(
            f"- {item.get('name', 'unknown')}"
            f" v{item.get('version', 'latest')}"
            f" ({item.get('path', 'unknown source')})"
        )


@blueprints_group.command("register")
@click.argument("path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
def blueprints_register(path: Path) -> None:
    """Register blueprint metadata from a YAML file."""
    data = _load_yaml(path)

    name = str(data.get("name") or path.stem)
    version = str(data.get("version") or "latest")
    record = {
        "id": f"{name}:{version}",
        "name": name,
        "version": version,
        "path": str(path),
    }

    state = _load_state()
    action = _upsert(state["blueprints"], "id", record)
    _save_state(state)
    click.echo(f"{action.capitalize()} blueprint {name} v{version}")


@main.group("templates")
def templates_group() -> None:
    """Template catalog commands."""


@templates_group.command("list")
def templates_list() -> None:
    """List built-in RAG and memory templates."""
    click.echo("RAG templates:")
    for name in _RAG_TEMPLATES:
        click.echo(f"- {name}")

    click.echo("Memory templates:")
    for name in _MEMORY_TEMPLATES:
        click.echo(f"- {name}")


@main.group("mcps")
def mcps_group() -> None:
    """MCP registry operations."""


@mcps_group.command("list")
def mcps_list() -> None:
    """List locally registered MCP endpoints."""
    state = _load_state()
    entries = state["mcps"]
    if not entries:
        click.echo("No MCP servers registered.")
        return

    click.echo("Registered MCP servers:")
    for item in sorted(entries, key=lambda entry: str(entry.get("name", ""))):
        capabilities = item.get("capabilities", [])
        cap_text = ", ".join(str(cap) for cap in capabilities) if capabilities else "none"
        click.echo(
            f"- {item.get('name', 'unknown')}"
            f" -> {item.get('endpoint', 'unknown endpoint')}"
            f" | capabilities: {cap_text}"
        )


@mcps_group.command("register")
@click.argument("path_or_url", type=str)
def mcps_register(path_or_url: str) -> None:
    """Register an MCP endpoint from local YAML or direct URL."""
    parsed = urlparse(path_or_url)
    state = _load_state()

    if parsed.scheme in {"http", "https"}:
        name = parsed.path.strip("/").split("/")[-1] or parsed.netloc
        if not name:
            name = "mcp"
        record = {
            "name": name,
            "endpoint": path_or_url,
            "capabilities": [],
            "source": "url",
        }
    else:
        path = Path(path_or_url)
        if not path.exists() or not path.is_file():
            raise click.ClickException(f"MCP source does not exist: {path_or_url}")

        data = _load_yaml(path)
        name = str(data.get("name") or path.stem)
        endpoint = str(data.get("endpoint") or "").strip()
        if not endpoint:
            raise click.ClickException("MCP YAML must include a non-empty 'endpoint'")

        raw_capabilities = data.get("capabilities", [])
        if raw_capabilities is None:
            raw_capabilities = []
        if not isinstance(raw_capabilities, list):
            raise click.ClickException("MCP YAML field 'capabilities' must be a list")

        capabilities = [str(capability) for capability in raw_capabilities]
        record = {
            "name": name,
            "endpoint": endpoint,
            "capabilities": capabilities,
            "source": str(path),
        }

    action = _upsert(state["mcps"], "name", record)
    _save_state(state)
    click.echo(f"{action.capitalize()} MCP {record['name']} at {record['endpoint']}")


@main.command("status")
def status() -> None:
    """Show runtime status including model pool health, agents, and tasks."""
    state = _load_state()
    click.echo("KubeAI CLI status")
    click.echo(f"- Registered blueprints: {len(state['blueprints'])}")
    click.echo(f"- Registered MCP servers: {len(state['mcps'])}")
    click.echo(f"- Built-in RAG templates: {len(_RAG_TEMPLATES)}")
    click.echo(f"- Built-in memory templates: {len(_MEMORY_TEMPLATES)}")

    # Try to pull live runtime data
    try:
        from KubeAI.dashboard.deps import get_control_plane
        cp = get_control_plane()
    except Exception:
        click.echo("\n(runtime not available — start with `agentctl api-server`)")
        return

    # ── Control plane overview ────────────────────────────────────────────
    try:
        overview = cp.get_overview()
        click.echo("\nControl Plane")
        click.echo(f"  Active agents : {overview['active_agents']} / {overview['agents_total']}")
        click.echo(f"  Tasks total   : {overview['tasks_total']}")
        click.echo(f"  Avg latency   : {overview['avg_latency_ms']:.0f} ms")
    except Exception:
        pass

    # ── LLM pool table (kubectl get nodes equivalent) ─────────────────────
    try:
        from KubeAI.orchestrator.llm_pool import LLMPool
        # Only available if a pool was attached to the dashboard control plane
        pool = getattr(cp, "_llm_pool", None)
        if pool is not None:
            models = pool.list_models()
            if models:
                click.echo("\nModel Pool")
                header = f"  {'MODEL':<40} {'TIER':<10} {'HEALTH':<8} {'LOAD':<6} {'COST/1K':>8}"
                click.echo(header)
                click.echo("  " + "-" * 74)
                for m in sorted(models, key=lambda x: x.model_id):
                    health = "healthy" if m.healthy else "UNHEALTHY"
                    click.echo(
                        f"  {m.model_id:<40} {m.tier.value:<10} {health:<8} "
                        f"{m.load:<6.2f} ${m.cost_per_1k_tokens:>7.4f}"
                    )
    except Exception:
        pass


@main.command("demo")
def demo() -> None:
    """Print a short command walkthrough for local operator usage."""
    click.echo("KubeAI demo command flow")
    click.echo("1. agentctl templates list")
    click.echo("2. agentctl blueprints register ./my_blueprint.yaml")
    click.echo("3. agentctl mcps register ./mcp/postgres.yaml")
    click.echo("4. agentctl run \"Summarize this document\" --rag basic --memory summarizing")
    click.echo("5. agentctl status")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _api_base() -> str:
    import os
    return os.environ.get("KUBEAI_API_URL", "http://localhost:8080").rstrip("/")


def _api_get(path: str) -> Any:
    """Perform a GET request against the KubeAI API. Returns parsed JSON."""
    import urllib.request
    url = f"{_api_base()}{path}"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            return json.loads(resp.read().decode())
    except Exception as exc:
        raise click.ClickException(f"API request failed ({url}): {exc}") from exc


def _api_post(path: str, payload: dict[str, Any]) -> Any:
    """Perform a POST request against the KubeAI API. Returns parsed JSON."""
    import urllib.request
    url = f"{_api_base()}{path}"
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode())
    except Exception as exc:
        raise click.ClickException(f"API request failed ({url}): {exc}") from exc


def _api_put(path: str, payload: dict[str, Any]) -> Any:
    """Perform a PUT request against the KubeAI API. Returns parsed JSON."""
    import urllib.request
    url = f"{_api_base()}{path}"
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json"},
        method="PUT",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())
    except Exception as exc:
        raise click.ClickException(f"API request failed ({url}): {exc}") from exc


# ── Benchmarks commands ───────────────────────────────────────────────────────

@main.group("benchmarks")
def benchmarks_group() -> None:
    """Benchmark framework adapters against standardised scenarios."""


@benchmarks_group.command("list")
def benchmarks_list() -> None:
    """List all stored benchmark run results."""
    rows = _api_get("/api/benchmarks/runs")
    if not rows:
        click.echo("No benchmark runs recorded yet.")
        return

    click.echo(f"{'RUN ID':<38} {'SCENARIO':<14} {'FRAMEWORK':<12} {'QUALITY':>7} {'LATENCY ms':>11} {'COST':>9}  RECORDED AT")
    click.echo("-" * 110)
    for r in rows:
        click.echo(
            f"{r.get('run_id', ''):<38}"
            f" {r.get('scenario', ''):<14}"
            f" {r.get('framework', ''):<12}"
            f" {r.get('quality_score', 0.0):>7.4f}"
            f" {r.get('latency_ms', 0.0):>11.1f}"
            f" {r.get('token_cost', 0.0):>9.6f}"
            f"  {r.get('recorded_at', '')}"
        )


@benchmarks_group.command("run")
@click.option(
    "--scenario",
    type=click.Choice(["rag", "codegen", "research", "data_analysis"]),
    required=True,
    help="Benchmark scenario to execute.",
)
@click.option(
    "--framework",
    type=str,
    default=None,
    help="Adapter name (e.g. litellm). Omit to run all registered adapters.",
)
@click.option(
    "--num-runs",
    type=int,
    default=3,
    show_default=True,
    help="Number of times to run each adapter.",
)
def benchmarks_run(scenario: str, framework: str | None, num_runs: int) -> None:
    """Trigger a benchmark run and display the new result records."""
    payload: dict[str, Any] = {"scenario": scenario, "num_runs": num_runs}
    if framework:
        payload["framework"] = framework

    click.echo(f"Running benchmark scenario '{scenario}' ({num_runs} run(s))...")
    rows = _api_post("/api/benchmarks/run", payload)

    if not rows:
        click.echo("No results returned.")
        return

    click.echo(f"\n{'FRAMEWORK':<12} {'QUALITY':>7} {'LATENCY ms':>11} {'COST':>9}")
    click.echo("-" * 46)
    for r in rows:
        click.echo(
            f"{r.get('framework', ''):<12}"
            f" {r.get('quality_score', 0.0):>7.4f}"
            f" {r.get('latency_ms', 0.0):>11.1f}"
            f" {r.get('token_cost', 0.0):>9.6f}"
        )
    click.echo(f"\n{len(rows)} result(s) stored. Run 'agentctl benchmarks leaderboard' to compare.")


@benchmarks_group.command("leaderboard")
def benchmarks_leaderboard() -> None:
    """Show aggregated benchmark leaderboard sorted by quality score."""
    rows = _api_get("/api/benchmarks/leaderboard")
    if not rows:
        click.echo("No benchmark data available. Run 'agentctl benchmarks run' first.")
        return

    click.echo(f"{'#':<4} {'FRAMEWORK':<14} {'SCENARIO':<14} {'AVG QUALITY':>11} {'AVG LATENCY ms':>15} {'AVG COST':>10} {'RUNS':>5}")
    click.echo("-" * 80)
    for i, r in enumerate(rows, start=1):
        click.echo(
            f"{i:<4}"
            f" {r.get('framework', ''):<14}"
            f" {r.get('scenario', ''):<14}"
            f" {r.get('avg_quality_score', 0.0):>11.4f}"
            f" {r.get('avg_latency_ms', 0.0):>15.1f}"
            f" {r.get('avg_token_cost', 0.0):>10.6f}"
            f" {r.get('num_runs', 0):>5}"
        )


# ── Config commands ───────────────────────────────────────────────────────────

@main.group("config")
def config_group() -> None:
    """Runtime configuration management."""


@config_group.command("get")
@click.argument("key")
def config_get(key: str) -> None:
    """Get the current value of a config key (e.g. rag.default_template)."""
    result = _api_get(f"/api/config/{key}")
    click.echo(f"{result['key']} = {json.dumps(result['value'])}")


@config_group.command("set")
@click.argument("key")
@click.argument("value")
@click.option("--category", default="", help="Config category override.")
@click.option("--description", default="", help="Human-readable description.")
def config_set(key: str, value: str, category: str, description: str) -> None:
    """Set a config key to VALUE (parsed as JSON if possible, else kept as string)."""
    # Attempt JSON decode so booleans, numbers, and objects work
    try:
        parsed_value: Any = json.loads(value)
    except json.JSONDecodeError:
        parsed_value = value

    payload: dict[str, Any] = {"value": parsed_value}
    if category:
        payload["category"] = category
    if description:
        payload["description"] = description

    result = _api_put(f"/api/config/{key}", payload)
    click.echo(f"Updated: {result['key']} = {json.dumps(result['value'])}")


@config_group.command("list")
def config_list() -> None:
    """List all config entries grouped by category."""
    grouped = _api_get("/api/config")
    if not grouped:
        click.echo("No config entries found.")
        return

    for category in sorted(grouped.keys()):
        entries = grouped[category]
        click.echo(f"\n[{category}]")
        click.echo(f"  {'KEY':<45} {'VALUE':<30} DESCRIPTION")
        click.echo("  " + "-" * 90)
        for entry in sorted(entries, key=lambda e: e.get("key", "")):
            raw_val = json.dumps(entry.get("value"))
            val_display = raw_val if len(raw_val) <= 30 else raw_val[:27] + "..."
            click.echo(
                f"  {entry.get('key', ''):<45}"
                f" {val_display:<30}"
                f" {entry.get('description', '')}"
            )


# ── Skills commands ───────────────────────────────────────────────────────────

@main.group("skills")
def skills_group() -> None:
    """Skill registry management."""


@skills_group.command("list")
def skills_list() -> None:
    """List all registered skills."""
    rows = _api_get("/api/skills")
    if not rows:
        click.echo("No skills registered.")
        return

    click.echo(f"{'ID':<10} {'NAME':<24} {'ENABLED':<8} {'TAGS':<30} DESCRIPTION")
    click.echo("-" * 100)
    for s in rows:
        tags = ", ".join(s.get("tags") or []) or "-"
        enabled = "yes" if s.get("enabled", True) else "no"
        click.echo(
            f"{s.get('skill_id', ''):<10}"
            f" {s.get('name', ''):<24}"
            f" {enabled:<8}"
            f" {tags:<30}"
            f" {s.get('description', '')}"
        )


@skills_group.command("create")
@click.argument("name")
@click.argument("system_prompt")
@click.option("--description", default="", help="Short description of the skill.")
@click.option("--tags", default="", help="Comma-separated tags (e.g. rag,coding).")
def skills_create(name: str, system_prompt: str, description: str, tags: str) -> None:
    """Create a new skill with NAME and SYSTEM_PROMPT."""
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
    payload: dict[str, Any] = {
        "name": name,
        "system_prompt": system_prompt,
        "description": description,
        "tags": tag_list,
        "mcp_tools": [],
        "workflow_steps": [],
        "visibility": {},
    }
    result = _api_post("/api/skills", payload)
    click.echo(f"Created skill '{result['name']}' with ID {result['skill_id']}")


# ── Adapters commands (local — no server required) ────────────────────────────

@main.group("adapters")
def adapters_group() -> None:
    """Framework adapter registry operations (local)."""


@adapters_group.command("list")
def adapters_list() -> None:
    """List all adapters that can be imported in this environment."""
    from KubeAI.adapters.registry import AdapterRegistry

    registry = AdapterRegistry()

    # Register all known adapters that are importable
    _register_available_adapters(registry)

    adapters = registry.list_adapters()
    if not adapters:
        click.echo("No adapters available. Install adapter dependencies (litellm, langchain, etc.).")
        return

    click.echo(f"{'NAME':<20} {'HEALTHY':<8} MODULE")
    click.echo("-" * 60)
    for adapter in sorted(adapters, key=lambda a: a.name):
        healthy = "yes" if adapter.health_check() else "no"
        module = type(adapter).__module__
        click.echo(f"{adapter.name:<20} {healthy:<8} {module}")


@adapters_group.command("health")
def adapters_health() -> None:
    """Run health_check() on each available adapter and report status."""
    from KubeAI.adapters.registry import AdapterRegistry

    registry = AdapterRegistry()
    _register_available_adapters(registry)

    adapters = registry.list_adapters()
    if not adapters:
        click.echo("No adapters found to health-check.")
        return

    all_healthy = True
    for adapter in sorted(adapters, key=lambda a: a.name):
        healthy = adapter.health_check()
        status = "HEALTHY" if healthy else "UNHEALTHY"
        if not healthy:
            all_healthy = False
        click.echo(f"  {adapter.name:<20} {status}")

    if all_healthy:
        click.echo("\nAll adapters healthy.")
    else:
        click.echo("\nOne or more adapters are unhealthy. Check that their dependencies are installed.")


def _register_available_adapters(registry: Any) -> None:
    """Attempt to import and register each known adapter."""
    candidates = [
        ("KubeAI.adapters.litellm_adapter", "LiteLLMAdapter"),
        ("KubeAI.adapters.langchain_adapter", "LangChainAdapter"),
        ("KubeAI.adapters.llamaindex_adapter", "LlamaIndexAdapter"),
        ("KubeAI.adapters.autogen_adapter", "AutoGenAdapter"),
        ("KubeAI.adapters.crewai_adapter", "CrewAIAdapter"),
    ]
    for module_path, class_name in candidates:
        try:
            import importlib
            mod = importlib.import_module(module_path)
            cls = getattr(mod, class_name)
            registry.register(cls())
        except Exception:
            # Adapter dependencies not installed — skip silently
            pass


if __name__ == "__main__":
    main()
