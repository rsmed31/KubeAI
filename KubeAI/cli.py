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


if __name__ == "__main__":
    main()
