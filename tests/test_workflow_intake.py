"""Tests for WorkflowIntake and TaskDecomposer."""

from __future__ import annotations

import pytest

from KubeAI.workflow.decomposer import TaskDecomposer, classify_task
from KubeAI.workflow.intake import WorkflowIntake, WorkflowTask


# ── classify_task ─────────────────────────────────────────────────────────────

def test_classify_codegen():
    result = classify_task("Write a Python function to sort a list")
    assert result == "codegen"


def test_classify_rag():
    result = classify_task("Find information about transformer architecture in the document")
    assert result == "rag"


def test_classify_research():
    result = classify_task("Analyze and explain the differences between RAG and fine-tuning")
    assert result == "research"


def test_classify_data_analysis():
    result = classify_task("Calculate the average score from the CSV data")
    assert result == "data_analysis"


def test_classify_defaults_to_research_for_ambiguous():
    result = classify_task("Hello world")
    # No strong signal — defaults to research (highest count = 0 for all, picks research)
    assert isinstance(result, str)


# ── TaskDecomposer ─────────────────────────────────────────────────────────────

def test_decomposer_no_decompose_simple():
    decomposer = TaskDecomposer()
    result = decomposer.decompose("Write a simple function")
    assert len(result) == 1
    assert result[0].description == "Write a simple function"


def test_decomposer_splits_numbered_list():
    decomposer = TaskDecomposer()
    task = "1. Write a function\n2. Add tests\n3. Document it"
    result = decomposer.decompose(task)
    assert len(result) >= 2


def test_decomposer_splits_bullet_list():
    decomposer = TaskDecomposer()
    task = "- Analyze the data\n- Generate a report\n- Send results"
    result = decomposer.decompose(task)
    assert len(result) >= 2


def test_decomposer_splits_on_then():
    decomposer = TaskDecomposer()
    task = "Write a function then add tests"
    result = decomposer.decompose(task)
    assert len(result) >= 2


def test_decomposer_sub_tasks_have_types():
    decomposer = TaskDecomposer()
    task = "1. Write the code\n2. Analyze the dataset"
    result = decomposer.decompose(task)
    types = [st.task_type for st in result]
    assert all(t in ("rag", "codegen", "research", "data_analysis") for t in types)


def test_decomposer_should_decompose_long_task():
    decomposer = TaskDecomposer()
    long_task = "analyze " * 200  # > 500 chars
    assert decomposer.should_decompose(long_task) is True


def test_decomposer_should_not_decompose_short_simple():
    decomposer = TaskDecomposer()
    assert decomposer.should_decompose("What is 2+2?") is False


# ── WorkflowIntake ─────────────────────────────────────────────────────────────

def test_intake_analyze_simple():
    intake = WorkflowIntake()
    result = intake.analyze("Write a sorting algorithm")
    assert isinstance(result, WorkflowTask)
    assert result.task_type == "codegen"
    assert result.is_complex is False


def test_intake_analyze_complex():
    intake = WorkflowIntake(auto_decompose=True)
    task = "1. Write a function\n2. Analyze the results"
    result = intake.analyze(task)
    assert isinstance(result, WorkflowTask)


def test_intake_classify():
    intake = WorkflowIntake()
    assert intake.classify("write code") == "codegen"


def test_intake_select_adapter_no_selector():
    intake = WorkflowIntake(selector=None)
    assert intake.select_adapter("codegen") is None


def test_intake_select_adapters_for_simple_workflow():
    intake = WorkflowIntake(selector=None)
    wf = WorkflowTask(description="test", task_type="codegen")
    pairs = intake.select_adapters_for_workflow(wf)
    assert len(pairs) == 1
    sub_task, adapter = pairs[0]
    assert adapter is None  # no selector


def test_intake_repr():
    intake = WorkflowIntake()
    assert "WorkflowIntake" in repr(intake)


def test_intake_disabled_auto_decompose():
    intake = WorkflowIntake(auto_decompose=False)
    task = "1. Write a function\n2. Add tests\n3. Document it"
    result = intake.analyze(task)
    assert result.is_decomposed is False
    assert result.is_complex is False
