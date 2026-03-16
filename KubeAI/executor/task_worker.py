"""TaskWorker connects the ControlPlaneAPI task queue to Orchestrator routing, AgentExecutor execution, and result recording."""

from __future__ import annotations

import threading
import time
from typing import TYPE_CHECKING

from KubeAI.executor.agent_executor import AgentExecutor

if TYPE_CHECKING:
    from KubeAI.api.control_plane import ControlPlaneAPI
    from KubeAI.blueprint import Blueprint, BlueprintRegistry
    from KubeAI.memory.shared_memory import SharedMemory
    from KubeAI.orchestrator.orchestrator import Orchestrator
    from KubeAI.scheduler.lifecycle import AgentLifecycleManager


class TaskWorker:
    """
    Background worker that dequeues submitted tasks and runs them end-to-end.

    Control flow:
      ControlPlaneAPI._task_queue → route blueprint → assign model →
      get_or_spawn agent → AgentExecutor.run() → record_task_result()

    Analogous to a Kubernetes controller reconciliation loop — runs as a
    daemon thread and processes tasks until process shutdown.
    """

    def __init__(
        self,
        control_plane: "ControlPlaneAPI",
        orchestrator: "Orchestrator",
        lifecycle: "AgentLifecycleManager",
        registry: "BlueprintRegistry",
        memory: "SharedMemory | None" = None,
        num_workers: int = 4,
    ) -> None:
        self._cp = control_plane
        self._orchestrator = orchestrator
        self._lifecycle = lifecycle
        self._registry = registry
        self._memory = memory
        self._executor = AgentExecutor()
        self._num_workers = num_workers
        self._threads: list[threading.Thread] = []

    def start(self) -> None:
        """Start *num_workers* daemon threads draining the task queue (idempotent)."""
        if self._threads:
            return
        for i in range(self._num_workers):
            t = threading.Thread(
                target=self._worker_loop,
                daemon=True,
                name=f"kubeai-task-worker-{i}",
            )
            t.start()
            self._threads.append(t)

    def _worker_loop(self) -> None:
        """Drain the task queue indefinitely, processing one task at a time."""
        while True:
            try:
                task_info = self._cp._task_queue.get(timeout=1.0)  # noqa: SLF001
            except Exception:
                continue
            try:
                self._process_task(task_info)
            except Exception:
                # Record failure to prevent queue stall; best-effort
                task_id = task_info.get("task_id", "unknown")
                try:
                    self._cp.record_task_result(
                        task_id=task_id,
                        blueprint=task_info.get("blueprint", "unknown"),
                        status="failed",
                        latency_ms=0.0,
                        token_cost=0.0,
                    )
                except Exception:
                    pass
            finally:
                try:
                    self._cp._task_queue.task_done()  # noqa: SLF001
                except Exception:
                    pass

    def _process_task(self, task_info: dict) -> None:
        """Route, assign, spawn, execute, and record a single task."""
        task_id: str = task_info["task_id"]
        description: str = task_info.get("description", "")
        preferred_blueprint_name: str | None = task_info.get("blueprint")

        # ── 1. Route to blueprint ─────────────────────────────────────────
        blueprints = self._registry.list_blueprints()
        if not blueprints:
            raise RuntimeError("No blueprints registered — cannot route task")

        # Honour explicit blueprint preference if valid
        blueprint: "Blueprint | None" = None
        if preferred_blueprint_name and preferred_blueprint_name != "unknown":
            try:
                blueprint = self._registry.get(preferred_blueprint_name)
            except KeyError:
                pass

        confidence = 1.0
        if blueprint is None:
            t0 = time.monotonic()
            blueprint, confidence = self._orchestrator.route(description, blueprints)
            routing_latency_ms = (time.monotonic() - t0) * 1000
        else:
            routing_latency_ms = 0.0

        # ── 2. Assign model + MCPs ────────────────────────────────────────
        assignment = self._orchestrator.assign(blueprint, task=description)

        # ── 3. Record routing decision (Gap 5) ───────────────────────────
        self._cp.record_routing_decision(
            task_id=task_id,
            blueprint=blueprint.name,
            model_id=assignment.model_id,
            provider=assignment.provider,
            confidence=confidence,
            cost_hint=0.5,
            latency_ms=routing_latency_ms,
        )

        # ── 4. Get or spawn an agent ──────────────────────────────────────
        agent = self._lifecycle.get_or_spawn(blueprint)

        # ── 5. Execute via LiteLLM ────────────────────────────────────────
        t0 = time.monotonic()
        result = self._executor.run(
            task=description,
            blueprint=blueprint,
            assignment=assignment,
            memory=self._memory,
            agent_id=agent.agent_id,
        )

        # ── 6. Update agent state and record result ───────────────────────
        self._lifecycle.record_task_complete(agent.agent_id)
        self._lifecycle.mark_idle(agent.agent_id)

        self._cp.record_task_result(
            task_id=task_id,
            blueprint=blueprint.name,
            status="success",
            latency_ms=result.latency_ms,
            token_cost=result.token_cost,
            agent_id=agent.agent_id,
        )

        # Store result text in shared memory for CLI polling
        if self._memory is not None:
            self._memory.set_short_term("task_results", task_id, result.text)

    def __repr__(self) -> str:
        alive = sum(1 for t in self._threads if t.is_alive())
        return f"TaskWorker(workers={self._num_workers}, alive={alive})"
