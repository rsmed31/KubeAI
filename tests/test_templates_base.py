"""Unit tests for template infrastructure contracts and lifecycle hook behavior."""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from KubeAI.templates import (
    Template,
    TemplateConfig,
    TemplateHookError,
    TemplateMountError,
    attach_template,
    attach_templates,
    detach_templates,
    get_attached_templates,
    run_post_hooks,
    run_pre_hooks,
)


@dataclass
class _DummyAgent:
    """Simple test double for agent attach/detach lifecycle."""

    attach_calls: list[tuple[str, dict[str, object]]] = field(default_factory=list)
    detach_calls: list[str] = field(default_factory=list)


class _DummyTemplate(Template):
    """Template test double that records attach and transforms hook payloads."""

    def __init__(
        self,
        name: str,
        priority: int = 100,
        fail_attach: bool = False,
        fail_pre: bool = False,
        fail_post: bool = False,
        fail_detach: bool = False,
    ) -> None:
        super().__init__(name=name, priority=priority)
        self.fail_attach = fail_attach
        self.fail_pre = fail_pre
        self.fail_post = fail_post
        self.fail_detach = fail_detach

    def attach(self, agent: _DummyAgent, config: dict[str, object] | None = None) -> None:
        if self.fail_attach:
            raise ValueError("attach failure")
        agent.attach_calls.append((self.name, dict(config or {})))

    def detach(self, agent: _DummyAgent) -> None:
        if self.fail_detach:
            raise ValueError("detach failure")
        agent.detach_calls.append(self.name)

    def pre_run(self, task: str) -> str:
        if self.fail_pre:
            raise ValueError("pre failure")
        return f"{task}|pre:{self.name}"

    def post_run(self, result: str) -> str:
        if self.fail_post:
            raise ValueError("post failure")
        return f"{result}|post:{self.name}"


class TestTemplateConfig:
    def test_as_mapping_contains_defaults(self) -> None:
        config = TemplateConfig(name="rag")
        mapping = config.as_mapping()
        assert mapping["enabled"] is True
        assert mapping["priority"] == 100

    def test_options_override_defaults(self) -> None:
        config = TemplateConfig(
            name="memory",
            options={"priority": 5, "enabled": False, "window": 7},
            priority=100,
            enabled=True,
        )
        mapping = config.as_mapping()
        assert mapping["priority"] == 5
        assert mapping["enabled"] is False
        assert mapping["window"] == 7


class TestMountLifecycle:
    def test_registry_is_created_on_first_access(self) -> None:
        agent = _DummyAgent()
        assert get_attached_templates(agent) == []

    def test_attach_template_registers_and_sorts(self) -> None:
        agent = _DummyAgent()
        slow = _DummyTemplate(name="slow", priority=50)
        fast = _DummyTemplate(name="fast", priority=10)

        assert attach_template(agent, slow)
        assert attach_template(agent, fast)

        names = [template.name for template in get_attached_templates(agent)]
        assert names == ["fast", "slow"]

    def test_attach_template_replaces_existing_name(self) -> None:
        agent = _DummyAgent()
        first = _DummyTemplate(name="shared", priority=50)
        replacement = _DummyTemplate(name="shared", priority=1)

        attach_template(agent, first)
        attach_template(agent, replacement)

        templates = get_attached_templates(agent)
        assert len(templates) == 1
        assert templates[0] is replacement

    def test_attach_template_skips_when_disabled(self) -> None:
        agent = _DummyAgent()
        template = _DummyTemplate(name="disabled")
        attached = attach_template(agent, template, {"enabled": False})

        assert attached is False
        assert get_attached_templates(agent) == []
        assert agent.attach_calls == []

    def test_attach_template_wraps_errors(self) -> None:
        agent = _DummyAgent()
        template = _DummyTemplate(name="broken", fail_attach=True)

        with pytest.raises(TemplateMountError, match="broken"):
            attach_template(agent, template)

    def test_attach_templates_reads_per_template_configs(self) -> None:
        agent = _DummyAgent()
        rag = _DummyTemplate(name="rag", priority=100)
        memory = _DummyTemplate(name="memory", priority=100)

        attached = attach_templates(
            agent,
            [rag, memory],
            configs={
                "rag": TemplateConfig(name="rag", options={"priority": 5}),
                "memory": {"enabled": False},
            },
        )

        assert attached == ["rag"]
        templates = get_attached_templates(agent)
        assert len(templates) == 1
        assert templates[0].name == "rag"
        assert templates[0].priority == 5

    def test_invalid_registry_type_raises(self) -> None:
        agent = _DummyAgent()
        setattr(agent, "_kubeai_templates", "not-a-list")

        with pytest.raises(TemplateMountError, match="invalid"):
            get_attached_templates(agent)


class TestHooks:
    def test_run_pre_hooks_uses_priority_order(self) -> None:
        agent = _DummyAgent()
        one = _DummyTemplate(name="one", priority=20)
        two = _DummyTemplate(name="two", priority=10)

        attach_template(agent, one)
        attach_template(agent, two)

        transformed = run_pre_hooks(agent, "task")
        assert transformed == "task|pre:two|pre:one"

    def test_run_post_hooks_uses_reverse_priority_order(self) -> None:
        agent = _DummyAgent()
        one = _DummyTemplate(name="one", priority=20)
        two = _DummyTemplate(name="two", priority=10)

        attach_template(agent, one)
        attach_template(agent, two)

        transformed = run_post_hooks(agent, "result")
        assert transformed == "result|post:one|post:two"

    def test_run_pre_hooks_wraps_errors(self) -> None:
        agent = _DummyAgent()
        bad = _DummyTemplate(name="bad", fail_pre=True)
        attach_template(agent, bad)

        with pytest.raises(TemplateHookError, match="bad"):
            run_pre_hooks(agent, "task")

    def test_run_post_hooks_wraps_errors(self) -> None:
        agent = _DummyAgent()
        bad = _DummyTemplate(name="bad", fail_post=True)
        attach_template(agent, bad)

        with pytest.raises(TemplateHookError, match="bad"):
            run_post_hooks(agent, "result")


class TestDetach:
    def test_detach_runs_in_reverse_order_and_clears_registry(self) -> None:
        agent = _DummyAgent()
        first = _DummyTemplate(name="first", priority=50)
        second = _DummyTemplate(name="second", priority=10)

        attach_template(agent, first)
        attach_template(agent, second)

        detach_templates(agent)

        assert agent.detach_calls == ["first", "second"]
        assert get_attached_templates(agent) == []

    def test_detach_wraps_errors(self) -> None:
        agent = _DummyAgent()
        broken = _DummyTemplate(name="broken", fail_detach=True)
        attach_template(agent, broken)

        with pytest.raises(TemplateMountError, match="broken"):
            detach_templates(agent)
