# KubeAI Adapters

Adapters wrap external AI agent frameworks behind a single `OrchestrationAdapter`
interface. The runtime selects an adapter at spawn time so the framework can be
swapped via config without touching agent business logic.

---

## Interface

Every adapter must implement three members defined in
`KubeAI/adapters/base.py`:

```python
class OrchestrationAdapter(ABC):

    @property
    @abstractmethod
    def name(self) -> str:
        """Framework identifier, e.g. 'litellm', 'langchain'."""

    @abstractmethod
    def invoke(
        self,
        *,
        task: str,
        system_prompt: str,
        model_id: str,
        api_key: str = "",
        base_url: str = "",
        max_tokens: int = 2048,
        tools: list[dict] | None = None,
        context: str = "",
        **kwargs,
    ) -> AdapterResult:
        """Execute a task and return a standardised result."""

    def health_check(self) -> bool:
        """Return True if this adapter's dependencies are importable."""
        return True
```

### AdapterResult fields

| Field        | Type              | Description                                         |
|--------------|-------------------|-----------------------------------------------------|
| `text`       | `str`             | The framework's response text                       |
| `latency_ms` | `float`           | Wall-clock time for the invocation in milliseconds  |
| `token_cost` | `float`           | Estimated USD cost based on tokens consumed         |
| `raw_usage`  | `dict[str, Any]`  | Raw token counts (`prompt_tokens`, `total_tokens`)  |
| `framework`  | `str`             | Adapter name, populated automatically               |
| `metadata`   | `dict[str, Any]`  | Any extra data the adapter wants to surface         |

---

## Built-in adapters

| Name           | Module                                  | Requires                       |
|----------------|-----------------------------------------|--------------------------------|
| `litellm`      | `KubeAI.adapters.litellm_adapter`       | `litellm`                      |
| `langchain`    | `KubeAI.adapters.langchain_adapter`     | `langchain-community`          |
| `llamaindex`   | `KubeAI.adapters.llamaindex_adapter`    | `llama-index`                  |
| `autogen`      | `KubeAI.adapters.autogen_adapter`       | `pyautogen`                    |
| `crewai`       | `KubeAI.adapters.crewai_adapter`        | `crewai`                       |

---

## Writing a custom adapter

1. Subclass `OrchestrationAdapter`.
2. Implement `name`, `invoke`, and optionally `health_check`.
3. Return an `AdapterResult` — never a raw string or dict.

```python
# my_project/my_adapter.py
from KubeAI.adapters.base import AdapterResult, OrchestrationAdapter
import time


class MyFrameworkAdapter(OrchestrationAdapter):

    @property
    def name(self) -> str:
        return "my_framework"

    def invoke(self, *, task, system_prompt, model_id,
               api_key="", base_url="", max_tokens=2048,
               tools=None, context="", **kwargs) -> AdapterResult:
        import my_framework_sdk

        t0 = time.monotonic()
        response = my_framework_sdk.run(
            prompt=f"{system_prompt}\n\n{task}",
            model=model_id,
            max_tokens=max_tokens,
        )
        latency_ms = (time.monotonic() - t0) * 1000

        return AdapterResult(
            text=response.text,
            latency_ms=latency_ms,
            token_cost=response.usage.total_tokens / 1000.0 * 0.002,
            raw_usage={"total_tokens": response.usage.total_tokens},
            framework=self.name,
        )

    def health_check(self) -> bool:
        try:
            import my_framework_sdk  # noqa: F401
            return True
        except ImportError:
            return False
```

---

## Registering an adapter

### At runtime (programmatic)

```python
from KubeAI.adapters.registry import AdapterRegistry
from my_project.my_adapter import MyFrameworkAdapter

registry = AdapterRegistry()
registry.register(MyFrameworkAdapter())
```

Pass the registry to the `BenchmarkEngine` or attach it to the `Runtime` object
so it is available to the API:

```python
runtime.adapter_registry = registry
```

### Via the CLI (local check)

The `agentctl adapters list` and `agentctl adapters health` commands
auto-discover adapters by attempting to import each module under
`KubeAI.adapters.*`. To include your custom adapter, either:

- Place it under `KubeAI/adapters/` and add it to `_register_available_adapters`
  in `KubeAI/cli.py`, or
- Register it programmatically before calling CLI logic.

---

## AdapterRegistry API

```python
registry.register(adapter)          # add or replace by name
registry.get("litellm")             # fetch by name (raises KeyError if missing)
registry.list_adapters()            # list[OrchestrationAdapter]
registry.list_names()               # sorted list of registered names
registry.has("langchain")           # bool
registry.healthy_adapters()         # only those passing health_check()
```

---

## Adapter selection policy

The `AgentExecutor` reads `orchestrator.adapter` from `ConfigStore` to decide
which adapter to use for a given invocation. If the key is not set, `litellm`
is used as the default.

Change the active adapter at runtime (no restart required when PostgreSQL DSN
is configured):

```bash
agentctl config set orchestrator.adapter langchain
```
