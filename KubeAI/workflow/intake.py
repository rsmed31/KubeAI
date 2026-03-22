"""WorkflowIntake — receives, classifies, and optionally decomposes tasks.

Analogous to the Kubernetes API server's admission controller: every task
passes through here before being dispatched to the executor pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from KubeAI.workflow.decomposer import TaskDecomposer, SubTask, classify_task

if TYPE_CHECKING:
    from KubeAI.adapters.selector import AdapterSelector
    from KubeAI.adapters.base import OrchestrationAdapter


@dataclass
class WorkflowTask:
    """A fully analyzed task ready for execution.

    Contains the original task plus classification metadata that drives
    adapter selection and execution strategy.
    """
    description: str
    task_type: str              # 'rag' | 'codegen' | 'research' | 'data_analysis'
    sub_tasks: list[SubTask] = field(default_factory=list)
    is_decomposed: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_complex(self) -> bool:
        return self.is_decomposed and len(self.sub_tasks) > 1


class WorkflowIntake:
    """Intake pipeline for task classification and decomposition.

    Flow:
      1. classify(description) → task_type
      2. If complex: decompose(description) → list[SubTask]
      3. For each sub-task: selector.select(task_type) → best adapter

    This enables heterogeneous multi-framework execution — different parts
    of a complex task run on the framework that benchmarks best for that type.
    """

    def __init__(
        self,
        selector: "AdapterSelector | None" = None,
        auto_decompose: bool = True,
    ) -> None:
        self._selector = selector
        self._decomposer = TaskDecomposer()
        self._auto_decompose = auto_decompose

    def analyze(self, description: str) -> WorkflowTask:
        """Classify and optionally decompose a task description.

        Args:
            description: Natural language task description.

        Returns:
            WorkflowTask with type classification and optional sub-task list.
        """
        task_type = classify_task(description)
        sub_tasks: list[SubTask] = []
        is_decomposed = False

        if self._auto_decompose and self._decomposer.should_decompose(description):
            parts = self._decomposer.decompose(description)
            if len(parts) > 1:
                sub_tasks = parts
                is_decomposed = True

        return WorkflowTask(
            description=description,
            task_type=task_type,
            sub_tasks=sub_tasks,
            is_decomposed=is_decomposed,
        )

    def classify(self, description: str) -> str:
        """Classify a task description into a scenario type.

        Returns one of: 'rag', 'codegen', 'research', 'data_analysis'.
        """
        return classify_task(description)

    def select_adapter(self, task_type: str) -> "OrchestrationAdapter | None":
        """Return the best adapter for a task type, or None if no selector."""
        if self._selector is None:
            return None
        return self._selector.select(task_type)

    def select_adapters_for_workflow(
        self, workflow: WorkflowTask
    ) -> list[tuple[SubTask, "OrchestrationAdapter | None"]]:
        """Return (sub_task, adapter) pairs for a decomposed workflow.

        Each sub-task may get a different adapter based on its task_type.
        """
        if not workflow.is_decomposed:
            adapter = self.select_adapter(workflow.task_type)
            dummy = SubTask(description=workflow.description, task_type=workflow.task_type)
            return [(dummy, adapter)]

        return [
            (st, self.select_adapter(st.task_type))
            for st in workflow.sub_tasks
        ]

    def __repr__(self) -> str:
        return (
            f"WorkflowIntake(auto_decompose={self._auto_decompose}, "
            f"has_selector={self._selector is not None})"
        )
