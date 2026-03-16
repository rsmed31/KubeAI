"""Document dispatch is the ingress-controller analogue that probes documents and routes them directly to RAG-ready agents."""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import count
from typing import Any, Iterable

from KubeAI.scheduler.module_policy import SchedulerModulePolicy

from .a2a_router import A2ARouter, RoutedA2ATask
from .document_probe import DocumentProbe, ProbedDocument


@dataclass(frozen=True)
class DocumentDispatchResult:
    """Immutable result for one direct document dispatch operation."""

    dispatch_id: str
    routed_task: RoutedA2ATask
    probe: ProbedDocument
    required_modules: tuple[str, ...] = field(default_factory=tuple)

    def __repr__(self) -> str:
        return (
            f"DocumentDispatchResult(dispatch_id={self.dispatch_id!r}, "
            f"target={self.routed_task.target.agent_id!r}, "
            f"modules={self.required_modules!r})"
        )


class DocumentDispatcher:
    """Probe-first dispatch path for sending document payloads to A2A agents."""

    def __init__(
        self,
        router: A2ARouter,
        *,
        probe: DocumentProbe | None = None,
        module_policy: SchedulerModulePolicy | None = None,
        required_modules: Iterable[str] = ("document_dispatch", "rag_retrieval"),
    ) -> None:
        self._router = router
        self._probe = probe or DocumentProbe()
        self._module_policy = module_policy or SchedulerModulePolicy(default_enabled=True)
        self._required_modules = tuple(sorted(set(required_modules)))
        self._counter = count(1)

    def dispatch(
        self,
        task: str,
        document: str,
        *,
        preferred_agent_id: str | None = None,
        required_capabilities: Iterable[str] = (),
        metadata: dict[str, Any] | None = None,
        probe_result: ProbedDocument | None = None,
    ) -> DocumentDispatchResult:
        """Route a document task through probe inference to a RAG-ready target."""
        if not task.strip():
            raise ValueError("task must not be empty")

        resolved_probe = probe_result or self._probe.probe(document)
        capabilities = set(required_capabilities)
        capabilities.update(resolved_probe.required_capabilities)
        capabilities.add("rag_retrieval")

        payload = dict(metadata or {})
        payload.update(
            {
                "document": document,
                "document_preview": resolved_probe.preview,
                "probe": {
                    "estimated_tokens": resolved_probe.estimated_tokens,
                    "cost_hint": resolved_probe.cost_hint,
                    "required_capabilities": list(resolved_probe.required_capabilities),
                },
            }
        )

        routed_task = self._router.route(
            task=task,
            required_capabilities=sorted(capabilities),
            preferred_agent_id=preferred_agent_id,
            payload=payload,
        )

        try:
            self._module_policy.assert_enabled(
                self._required_modules,
                agent_id=routed_task.target.agent_id,
            )
        except Exception:
            self._router.complete(routed_task)
            raise

        dispatch_id = f"dispatch-{next(self._counter)}"
        return DocumentDispatchResult(
            dispatch_id=dispatch_id,
            routed_task=routed_task,
            probe=resolved_probe,
            required_modules=self._required_modules,
        )

    def complete(self, result: DocumentDispatchResult) -> None:
        """Release resources associated with a completed dispatch."""
        self._router.complete(result.routed_task)

    def __repr__(self) -> str:
        return (
            f"DocumentDispatcher(router={self._router!r}, "
            f"required_modules={self._required_modules!r})"
        )
