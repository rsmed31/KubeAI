"""agentctl is the kubectl analogue for operating KubeAI runtime workflows."""

from __future__ import annotations

import json
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
def run_task(
    task: str,
    rag_template: str | None,
    memory_template: str | None,
    blueprint: str | None,
    domain: str,
    json_output: bool,
) -> None:
    """Build a run request payload for runtime dispatch."""
    request = {
        "task": task,
        "rag_template": rag_template,
        "memory_template": memory_template,
        "blueprint": blueprint,
        "domain": domain,
    }

    if json_output:
        click.echo(json.dumps(request, indent=2, sort_keys=True))
        return

    click.echo("Run request prepared")
    click.echo(f"Task: {task}")
    click.echo(f"RAG template: {rag_template or 'none'}")
    click.echo(f"Memory template: {memory_template or 'none'}")
    click.echo(f"Blueprint preference: {blueprint or 'auto'}")
    click.echo(f"Domain: {domain}")
    click.echo("Runtime dispatch integration will be handled by integration lane.")


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
    """Show local CLI registry status."""
    state = _load_state()
    click.echo("KubeAI CLI status")
    click.echo(f"- Registered blueprints: {len(state['blueprints'])}")
    click.echo(f"- Registered MCP servers: {len(state['mcps'])}")
    click.echo(f"- Built-in RAG templates: {len(_RAG_TEMPLATES)}")
    click.echo(f"- Built-in memory templates: {len(_MEMORY_TEMPLATES)}")


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
