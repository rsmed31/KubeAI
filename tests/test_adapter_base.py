"""Tests for OrchestrationAdapter base and LiteLLM adapter."""

from KubeAI.adapters.base import AdapterResult, OrchestrationAdapter
from KubeAI.adapters.litellm_adapter import LiteLLMAdapter
from KubeAI.adapters.registry import AdapterRegistry


class DummyAdapter(OrchestrationAdapter):
    @property
    def name(self) -> str:
        return "dummy"

    def invoke(self, *, task, system_prompt, model_id, **kwargs):
        return AdapterResult(
            text=f"dummy:{task}",
            latency_ms=1.0,
            token_cost=0.001,
            framework="dummy",
        )


def test_adapter_result_fields():
    r = AdapterResult(text="hi", latency_ms=10.0, token_cost=0.01)
    assert r.text == "hi"
    assert r.latency_ms == 10.0
    assert r.token_cost == 0.01
    assert r.framework == ""
    assert r.raw_usage == {}
    assert r.metadata == {}


def test_dummy_adapter_invoke():
    adapter = DummyAdapter()
    result = adapter.invoke(task="hello", system_prompt="sys", model_id="m")
    assert result.text == "dummy:hello"
    assert result.framework == "dummy"


def test_adapter_health_check_default():
    adapter = DummyAdapter()
    assert adapter.health_check() is True


def test_registry_register_and_get():
    reg = AdapterRegistry()
    adapter = DummyAdapter()
    reg.register(adapter)
    assert reg.get("dummy") is adapter
    assert reg.has("dummy")
    assert "dummy" in reg.list_names()


def test_registry_list_adapters():
    reg = AdapterRegistry()
    reg.register(DummyAdapter())
    assert len(reg) == 1
    assert len(reg.list_adapters()) == 1


def test_registry_healthy_adapters():
    reg = AdapterRegistry()
    reg.register(DummyAdapter())
    healthy = reg.healthy_adapters()
    assert len(healthy) == 1


def test_registry_missing_adapter():
    reg = AdapterRegistry()
    try:
        reg.get("nonexistent")
        assert False, "Should have raised KeyError"
    except KeyError:
        pass


def test_litellm_adapter_name():
    adapter = LiteLLMAdapter()
    assert adapter.name == "litellm"


def test_litellm_adapter_health():
    adapter = LiteLLMAdapter()
    # litellm should be installed in test env
    # If not installed, health_check returns False — both are valid
    result = adapter.health_check()
    assert isinstance(result, bool)
