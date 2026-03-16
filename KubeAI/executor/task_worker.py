"""TaskWorker connects the ControlPlaneAPI task queue to Orchestrator routing, AgentExecutor execution, and result recording.

Phase 4 additions:
- TaskIntent analysis: detect URLs, data size, keyword signals
- Dynamic template selection: RAG for large docs, scraper for URLs
- Stage event emission: granular QUEUED → ROUTING → PROBING → EXECUTING → COMPLETE
- result_text stored back on TaskRecord
"""

from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from KubeAI.executor.agent_executor import AgentExecutor
from KubeAI.orchestrator.document_probe import DocumentProbe

if TYPE_CHECKING:
    from KubeAI.api.control_plane import ControlPlaneAPI
    from KubeAI.blueprint import Blueprint, BlueprintRegistry
    from KubeAI.memory.shared_memory import SharedMemory
    from KubeAI.orchestrator.orchestrator import Orchestrator
    from KubeAI.scheduler.lifecycle import AgentLifecycleManager
    from KubeAI.templates.base import Template

_URL_PATTERN = re.compile(r'https?://\S+')


@dataclass
class TaskIntent:
    """Structured analysis of what a task needs."""

    has_data: bool = False
    data_size: int = 0
    needs_rag: bool = False
    needs_chunking: bool = False
    needs_scraping: bool = False
    urls_to_scrape: list[str] = field(default_factory=list)
    inferred_capabilities: list[str] = field(default_factory=list)


class TaskWorker:
    """
    Background worker that dequeues submitted tasks and runs them end-to-end.

    Control flow:
      ControlPlaneAPI._task_queue → intent analysis → route blueprint →
      assign model → scrape/probe data → select templates →
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
        self._probe = DocumentProbe()
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
            except Exception as exc:
                task_id = task_info.get("task_id", "unknown")
                self._cp.update_task_stage(task_id, "failed", f"Task failed: {exc}")
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

    def _analyze_task_intent(
        self,
        description: str,
        data: str | None,
        data_url: str | None,
    ) -> TaskIntent:
        """Analyze task text and data to determine what processing is needed."""
        intent = TaskIntent()

        # URL detection in description
        urls = _URL_PATTERN.findall(description)
        if data_url:
            urls.append(data_url)
        if urls:
            intent.urls_to_scrape = urls
            intent.needs_scraping = True

        # Data size analysis
        if data:
            intent.has_data = True
            intent.data_size = len(data)
            intent.needs_rag = len(data) > 2000    # >2KB → use RAG
            intent.needs_chunking = len(data) > 10_000  # >10KB → chunk + vector

        # Keyword-based capability inference from DocumentProbe
        intent.inferred_capabilities = DocumentProbe.infer_capabilities(description)

        return intent

    def _select_templates(
        self,
        description: str,
        data: str | None,
        data_url: str | None,
        intent: TaskIntent,
    ) -> tuple[list["Template"], str]:
        """
        Select and prepare templates based on task intent.

        Returns (templates, augmented_task) where augmented_task may have
        small documents injected directly into the prompt.
        """
        templates: list["Template"] = []
        augmented_task = description

        # Handle URL scraping
        if intent.needs_scraping and intent.urls_to_scrape:
            try:
                from KubeAI.scraper.pipeline import RAGScraper
                from KubeAI.templates.rag.basic import BasicRAG
                scraper = RAGScraper(chunk_size=400, overlap=40)
                rag = BasicRAG()
                total_chunks = scraper.scrape_and_load(intent.urls_to_scrape, rag)
                if total_chunks > 0:
                    templates.append(rag)
            except Exception:
                # Scraping failed — continue without RAG
                pass

        # Handle uploaded data
        if data:
            if intent.needs_chunking:
                # Large doc → chunk into BasicRAG
                try:
                    from KubeAI.scraper.chunker import chunk_texts
                    from KubeAI.templates.rag.basic import BasicRAG
                    rag = BasicRAG()
                    chunks = chunk_texts([data], chunk_size=500, overlap=50)
                    rag.add_documents(chunks)
                    templates.append(rag)
                except Exception:
                    # Fall through to direct injection
                    augmented_task = f"{description}\n\nDocument:\n{data[:8000]}"
            elif intent.needs_rag:
                # Medium doc → inject as context
                augmented_task = f"{description}\n\nDocument:\n{data}"
            else:
                # Small doc → inject inline
                augmented_task = f"{description}\n\nContext:\n{data}"

        return templates, augmented_task

    def _process_task(self, task_info: dict) -> None:
        """Route, analyze, assign, spawn, execute, and record a single task."""
        task_id: str = task_info["task_id"]
        description: str = task_info.get("description", "")
        preferred_blueprint_name: str | None = task_info.get("blueprint")
        data: str | None = task_info.get("data")
        data_url: str | None = task_info.get("data_url")

        # ── Stage: ROUTING ────────────────────────────────────────────────
        self._cp.update_task_stage(task_id, "routing", "Analyzing task and routing to blueprint")

        # ── 1. Analyze intent ─────────────────────────────────────────────
        intent = self._analyze_task_intent(description, data, data_url)

        # ── 2. Route to blueprint ─────────────────────────────────────────
        blueprints = self._registry.list_blueprints()
        if not blueprints:
            raise RuntimeError("No blueprints registered — cannot route task")

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

        # ── 3. Assign model + MCPs ────────────────────────────────────────
        assignment = self._orchestrator.assign(blueprint, task=description)

        self._cp.update_task_stage(
            task_id, "assigned",
            f"Assigned to blueprint={blueprint.name}, model={assignment.model_id}",
            blueprint=blueprint.name,
            model_id=assignment.model_id,
            confidence=confidence,
        )

        self._cp.record_routing_decision(
            task_id=task_id,
            blueprint=blueprint.name,
            model_id=assignment.model_id,
            provider=assignment.provider,
            confidence=confidence,
            cost_hint=0.5,
            latency_ms=routing_latency_ms,
        )

        # ── Stage: DATA PROBING ───────────────────────────────────────────
        if intent.has_data or intent.needs_scraping:
            self._cp.update_task_stage(
                task_id, "data_probing",
                f"Probing task data: size={intent.data_size}B, "
                f"needs_rag={intent.needs_rag}, scraping={intent.needs_scraping}, "
                f"urls={len(intent.urls_to_scrape)}",
                data_size=intent.data_size,
                needs_scraping=intent.needs_scraping,
                url_count=len(intent.urls_to_scrape),
            )

        # ── Stage: SCRAPING / RAG LOADING ─────────────────────────────────
        if intent.needs_scraping:
            self._cp.update_task_stage(
                task_id, "scraping",
                f"Scraping {len(intent.urls_to_scrape)} URL(s)",
                urls=intent.urls_to_scrape[:3],
            )

        templates, augmented_task = self._select_templates(description, data, data_url, intent)

        if templates:
            self._cp.update_task_stage(
                task_id, "rag_loaded",
                f"Loaded {len(templates)} template(s) for context enrichment",
                template_count=len(templates),
            )

        # ── 4. Get or spawn an agent ──────────────────────────────────────
        agent = self._lifecycle.get_or_spawn(blueprint)

        # ── Stage: EXECUTING ──────────────────────────────────────────────
        self._cp.update_task_stage(
            task_id, "executing",
            f"Executing task on agent {agent.agent_id}",
            agent_id=agent.agent_id,
        )

        # ── 5. Execute via LiteLLM ────────────────────────────────────────
        result = self._executor.run(
            task=augmented_task,
            blueprint=blueprint,
            assignment=assignment,
            memory=self._memory,
            agent_id=agent.agent_id,
            templates=templates if templates else None,
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

        # Store result_text on the task record
        try:
            self._cp.update_task_result_text(task_id, result.text)
        except Exception:
            pass

        # ── Stage: COMPLETE ───────────────────────────────────────────────
        self._cp.update_task_stage(
            task_id, "complete",
            f"Task completed in {result.latency_ms:.0f}ms",
            latency_ms=result.latency_ms,
            token_cost=result.token_cost,
        )

        # Store result text in shared memory for CLI polling
        if self._memory is not None:
            self._memory.set_short_term("task_results", task_id, result.text)

    def __repr__(self) -> str:
        alive = sum(1 for t in self._threads if t.is_alive())
        return f"TaskWorker(workers={self._num_workers}, alive={alive})"
