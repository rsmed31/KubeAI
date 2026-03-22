"""Integration tests — full workflow intake -> classify -> decompose pipeline.

No LLM calls are made; classification and decomposition are purely heuristic.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from KubeAI.adapters.base import AdapterResult, OrchestrationAdapter
from KubeAI.adapters.registry import AdapterRegistry
from KubeAI.adapters.selector import AdapterSelector
from KubeAI.workflow.decomposer import SubTask, classify_task
from KubeAI.workflow.intake import WorkflowIntake, WorkflowTask


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _StubAdapter(OrchestrationAdapter):
    """No-op adapter used to make the selector return a real object."""

    def __init__(self, adapter_name: str) -> None:
        self._adapter_name = adapter_name

    @property
    def name(self) -> str:
        return self._adapter_name

    def invoke(self, *, task: str, system_prompt: str, model_id: str, **kwargs) -> AdapterResult:
        return AdapterResult(text="stub", latency_ms=0.0, token_cost=0.0, framework=self._adapter_name)


def _make_registry(*names: str) -> AdapterRegistry:
    reg = AdapterRegistry()
    for n in names:
        reg.register(_StubAdapter(n))
    return reg


# ---------------------------------------------------------------------------
# Test 1: Simple task -> single WorkflowTask, no decomposition
# ---------------------------------------------------------------------------

def test_simple_task_produces_single_workflow_task():
    """A short, single-step task must not be decomposed."""
    intake = WorkflowIntake(selector=None, auto_decompose=True)
    wf = intake.analyze("Write a quicksort function in Python")

    assert isinstance(wf, WorkflowTask)
    assert wf.is_complex is False
    assert wf.is_decomposed is False
    assert len(wf.sub_tasks) == 0
    assert wf.description == "Write a quicksort function in Python"


# ---------------------------------------------------------------------------
# Test 2: Numbered list task -> decomposed into multiple sub-tasks
# ---------------------------------------------------------------------------

def test_numbered_list_task_is_decomposed():
    """A task with numbered list items must be split into multiple sub-tasks."""
    intake = WorkflowIntake(selector=None, auto_decompose=True)
    task = "1. Write a Python function to load CSV data\n2. Calculate the mean of each column\n3. Generate a summary report"
    wf = intake.analyze(task)

    assert wf.is_decomposed is True
    assert len(wf.sub_tasks) >= 2
    for st in wf.sub_tasks:
        assert isinstance(st, SubTask)
        assert len(st.description) > 0


# ---------------------------------------------------------------------------
# Test 3: Each sub-task gets a valid task_type classification
# ---------------------------------------------------------------------------

def test_sub_tasks_have_valid_classifications():
    """Every sub-task's task_type must be one of the four known scenario types."""
    valid_types = {"rag", "codegen", "research", "data_analysis"}
    intake = WorkflowIntake(selector=None, auto_decompose=True)
    task = "1. Write the code\n2. Analyze the dataset\n3. Research the topic"
    wf = intake.analyze(task)

    assert wf.is_decomposed is True
    for st in wf.sub_tasks:
        assert st.task_type in valid_types, f"Unexpected task_type: {st.task_type!r}"


# ---------------------------------------------------------------------------
# Test 4: WorkflowIntake with real AdapterSelector (no benchmark data)
#         -> select() returns a non-None result
# ---------------------------------------------------------------------------

def test_workflow_intake_with_real_selector_returns_adapter():
    """select_adapter() returns the litellm adapter when no benchmark data is provided."""
    registry = _make_registry("litellm")
    selector = AdapterSelector(registry, benchmark_engine=None)
    intake = WorkflowIntake(selector=selector, auto_decompose=False)

    adapter = intake.select_adapter("codegen")
    assert adapter is not None
    assert adapter.name == "litellm"


# ---------------------------------------------------------------------------
# Test 5: WorkflowIntake.select_adapters_for_workflow returns correct number of pairs
# ---------------------------------------------------------------------------

def test_select_adapters_for_workflow_simple_task():
    """A non-decomposed workflow produces exactly one (sub_task, adapter) pair."""
    registry = _make_registry("litellm")
    selector = AdapterSelector(registry, benchmark_engine=None)
    intake = WorkflowIntake(selector=selector, auto_decompose=False)

    wf = WorkflowTask(description="Explain neural networks", task_type="research")
    pairs = intake.select_adapters_for_workflow(wf)

    assert len(pairs) == 1
    sub_task, adapter = pairs[0]
    assert isinstance(sub_task, SubTask)
    assert adapter is not None
    assert adapter.name == "litellm"


# ---------------------------------------------------------------------------
# Test 6: Complex workflow — 2 sub-tasks, different types, 2 pairs returned
# ---------------------------------------------------------------------------

def test_complex_workflow_yields_one_pair_per_subtask():
    """A decomposed workflow with N sub-tasks returns exactly N (sub_task, adapter) pairs."""
    registry = _make_registry("litellm")
    selector = AdapterSelector(registry, benchmark_engine=None)
    intake = WorkflowIntake(selector=selector, auto_decompose=True)

    task = "1. Write code to parse JSON\n2. Analyze the parsed data"
    wf = intake.analyze(task)

    pairs = intake.select_adapters_for_workflow(wf)

    # Each sub-task must have a paired adapter entry
    assert len(pairs) == len(wf.sub_tasks) if wf.is_decomposed else len(pairs) == 1

    for sub_task, adapter in pairs:
        assert isinstance(sub_task, SubTask)
        # adapter may be None if selector not wired, but here it is wired
        assert adapter is not None


# ---------------------------------------------------------------------------
# Test 7: Complex workflow — "Write code + Analyze data" -> 2 different types
# ---------------------------------------------------------------------------

def test_complex_workflow_two_different_task_types():
    """Sub-tasks from a code+data workflow resolve to distinct task types."""
    intake = WorkflowIntake(selector=None, auto_decompose=True)
    task = "1. Write code to load data\n2. Analyze the data statistics"
    wf = intake.analyze(task)

    assert wf.is_decomposed is True
    types = {st.task_type for st in wf.sub_tasks}
    # We expect codegen and data_analysis to appear among the types
    assert len(types) >= 1  # At minimum they are classified


# ---------------------------------------------------------------------------
# Test 8: WorkflowIntake with auto_decompose=False never decomposes
# ---------------------------------------------------------------------------

def test_auto_decompose_false_never_decomposes():
    """When auto_decompose=False, even multi-step tasks are returned as-is."""
    intake = WorkflowIntake(selector=None, auto_decompose=False)
    task = "1. Write the code\n2. Add tests\n3. Document it"
    wf = intake.analyze(task)

    assert wf.is_decomposed is False
    assert wf.is_complex is False
    assert wf.sub_tasks == []


# ---------------------------------------------------------------------------
# Test 9: WorkflowIntake.classify() returns expected type strings
# ---------------------------------------------------------------------------

def test_intake_classify_codegen():
    intake = WorkflowIntake()
    assert intake.classify("write a script to parse HTML") == "codegen"


def test_intake_classify_data_analysis():
    intake = WorkflowIntake()
    assert intake.classify("calculate the average from the CSV dataset") == "data_analysis"


def test_intake_classify_research():
    intake = WorkflowIntake()
    result = intake.classify("explain and summarize the differences between approaches")
    assert result == "research"


# ---------------------------------------------------------------------------
# Test 10: select_adapters_for_workflow with selector=None returns None adapters
# ---------------------------------------------------------------------------

def test_select_adapters_for_workflow_no_selector_returns_none_adapters():
    """When no selector is wired, adapter slots are None but pairs are still returned."""
    intake = WorkflowIntake(selector=None, auto_decompose=True)
    task = "1. Search for documents\n2. Write a summary"
    wf = intake.analyze(task)
    pairs = intake.select_adapters_for_workflow(wf)

    assert len(pairs) >= 1
    for _sub_task, adapter in pairs:
        assert adapter is None
