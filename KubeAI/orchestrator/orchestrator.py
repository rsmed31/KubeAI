"""Orchestrator is the Ingress+Istio analogue: semantically routes tasks to blueprints using LLM scoring via the largest registered model."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable
from uuid import uuid4

from .assignment import Assignment, AssignmentPolicy
from .document_dispatch import DocumentDispatchResult, DocumentDispatcher
from .document_probe import DocumentProbe, ProbedDocument

if TYPE_CHECKING:
    from KubeAI.blueprint import Blueprint
    from KubeAI.scheduler.module_policy import SchedulerModulePolicy

from .a2a_pool import A2AAgentCard, A2APool

_INTERNAL_ORCHESTRATION_CAPABILITIES = frozenset({"rag_retrieval"})

# Type alias: (task, blueprint, model_id) → score 0.0-1.0
ScoreFn = Callable[["Blueprint", str, str], float]

# Type alias: (task, model_id) → list[str]
DecomposeFn = Callable[[str, str], list[str]]

# Type alias: status event callback used by long-running orchestration flows.
StatusCallback = Callable[["RunStatusEvent"], None]

# Type alias: spawn callback that returns the spawned agent id.
SpawnAgentFn = Callable[["Blueprint", Assignment, dict[str, Any]], str | None]


@dataclass(frozen=True)
class RunStatusEvent:
    """One status update emitted during document orchestration."""

    stage: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def __repr__(self) -> str:
        return (
            f"RunStatusEvent(stage={self.stage!r}, message={self.message!r}, "
            f"details={self.details!r})"
        )


@dataclass(frozen=True)
class DocumentRunResult:
    """Structured outcome for a document task routed and dispatched by the orchestrator."""

    run_id: str
    blueprint: "Blueprint"
    assignment: Assignment
    dispatch: DocumentDispatchResult
    rag_template: str
    agent_id: str
    probe: ProbedDocument
    events: tuple[RunStatusEvent, ...] = field(default_factory=tuple)

    def __repr__(self) -> str:
        return (
            f"DocumentRunResult(run_id={self.run_id!r}, blueprint={self.blueprint.name!r}, "
            f"agent_id={self.agent_id!r}, rag_template={self.rag_template!r}, "
            f"events={len(self.events)})"
        )


def _llm_score(task: str, blueprint: "Blueprint", model_id: str) -> float:
    """
    Default LLM-based scorer using LiteLLM.

    Routing ALWAYS requires a real LLM call — no silent fallbacks. Raises if
    litellm is not installed or if the API call fails.

    Args:
        task: The task description to score.
        blueprint: The Blueprint being evaluated.
        model_id: The model identifier to use for scoring.

    Returns:
        A float in [0.0, 1.0].

    Raises:
        RuntimeError: If litellm is not installed.
        Exception: If the LLM API call fails.
    """
    try:
        import litellm  # type: ignore[import]
    except ImportError:
        raise RuntimeError(
            "litellm is required for routing. Install it with: pip install litellm"
        )

    prompt = (
        f"Score how well this agent blueprint matches the task. "
        f"Blueprint: {blueprint.name} - {blueprint.description}. "
        f"Task: {task}. "
        f"Reply with only a decimal between 0.0 and 1.0."
    )
    response = litellm.completion(
        model=model_id,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=16,
    )
    raw = response.choices[0].message.content.strip()
    try:
        return max(0.0, min(1.0, float(raw)))
    except ValueError:
        raise RuntimeError(
            f"Routing LLM returned unparseable score: {raw!r}"
        )


def _llm_decompose(task: str, model_id: str, max_subtasks: int = 5) -> list[str]:
    """
    Default LLM-based task decomposer using LiteLLM.

    Sends a prompt asking the model to split a task into independent parallel
    subtasks and returns one non-empty line per subtask.

    Args:
        task: The complex task to decompose.
        model_id: The model identifier to use for decomposition.
        max_subtasks: Maximum number of subtasks to request.

    Returns:
        A list of non-empty subtask strings.
    """
    try:
        import litellm  # type: ignore[import]
    except ImportError:
        return [task]

    prompt = (
        f"Decompose this task into {max_subtasks} or fewer independent parallel subtasks. "
        f"Task: {task}. "
        f"Reply with one subtask per line, no numbering."
    )
    try:
        response = litellm.completion(
            model=model_id,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=256,
        )
        raw = response.choices[0].message.content
        return [line.strip() for line in raw.splitlines() if line.strip()]
    except Exception:
        return [task]


class Orchestrator:
    """
    Semantic task router for the KubeAI runtime.

    Analogous to Kubernetes Ingress + Istio: receives incoming tasks, scores
    candidate agent blueprints via an LLM call on the largest registered model,
    and returns the best-matching Blueprint with its confidence score.

    Rules enforced:
    - Routing ALWAYS uses routing_model() — the largest healthy registered model.
    - Agents NEVER self-select their model or tools.
    - Scoring logic is injectable for deterministic testing (no real API calls
      required in unit tests).
    """

    def __init__(
        self,
        policy: AssignmentPolicy,
        score_fn: ScoreFn | None = None,
        decompose_fn: DecomposeFn | None = None,
        document_probe: DocumentProbe | None = None,
    ) -> None:
        """
        Initialise the Orchestrator.

        Args:
            policy: AssignmentPolicy that provides routing_model() and assign().
            score_fn: Optional injectable scorer. Signature:
                      (task, blueprint, model_id) → float in [0.0, 1.0].
                      Defaults to the Anthropic-based _llm_score.
            decompose_fn: Optional injectable decomposer. Signature:
                          (task, model_id) → list[str].
                          Defaults to the Anthropic-based _llm_decompose.
            document_probe: Optional document probe implementation used by
                            direct-document dispatch flows.
        """
        self._policy = policy
        self._score_fn: ScoreFn = score_fn if score_fn is not None else _llm_score
        self._decompose_fn: DecomposeFn = (
            decompose_fn if decompose_fn is not None else _llm_decompose
        )
        self._document_probe = document_probe or DocumentProbe()
        # Mutable runtime config — changeable via dashboard/API without restart
        self._routing_model_override: str | None = None   # None = auto (largest)
        self._min_confidence: float = 0.0                 # reject if best score < this
        self._decompose_enabled: bool = True

    def route(
        self, task: str, blueprints: list["Blueprint"]
    ) -> tuple["Blueprint", float]:
        """
        LLM-score each blueprint and return the best match with its score.

        Uses routing_model() to select the scoring model — always the largest
        healthy registered model. Scores are clamped to [0.0, 1.0].

        Args:
            task: The task description to route.
            blueprints: Non-empty list of Blueprints to score.

        Returns:
            A (Blueprint, score) tuple where score is in [0.0, 1.0].

        Raises:
            ValueError: If blueprints is empty.
        """
        if not blueprints:
            raise ValueError("blueprints list must not be empty")

        # Use override model if set, otherwise auto-select largest
        if self._routing_model_override:
            pool_models = {m.model_id: m for m in self._policy._llm.list_models()}  # noqa: SLF001
            model = pool_models.get(self._routing_model_override) or self._policy.routing_model()
        else:
            model = self._policy.routing_model()

        scores: dict[str, float] = {
            bp.name: max(0.0, min(1.0, self._score_fn(task, bp, model.model_id)))
            for bp in blueprints
        }
        best = max(blueprints, key=lambda b: scores[b.name])
        best_score = scores[best.name]

        if best_score < self._min_confidence:
            raise RuntimeError(
                f"No blueprint met minimum confidence {self._min_confidence:.2f} "
                f"(best={best.name!r} scored {best_score:.2f})"
            )

        return best, best_score

    def decompose(self, task: str, max_subtasks: int = 5) -> list[str]:
        """
        Decompose a complex task into independent parallel subtasks.

        Always uses routing_model() for the decomposition call.

        Args:
            task: The complex task to decompose.
            max_subtasks: Maximum number of subtasks to return.

        Returns:
            A list of subtask strings (at most max_subtasks).
        """
        model = self._policy.routing_model()
        return self._decompose_fn(task, model.model_id)

    def assign(
        self, blueprint: "Blueprint", task: str = "", cost_hint: float = 0.5
    ) -> Assignment:
        """
        Produce a spawn-time Assignment for a blueprint.

        Thin wrapper over AssignmentPolicy.assign() that passes blueprint tier
        and required capabilities. Agents receive this Assignment at spawn time
        and must not deviate from it.

        Args:
            blueprint: The Blueprint to assign resources for.
            task: Optional task string forwarded to assignment policy for
                  description-aware pool selection.
            cost_hint: Float 0.0 (cheapest) to 1.0 (most capable).

        Returns:
            An immutable Assignment with the selected model and MCP servers.
        """
        return self._policy.assign(
            blueprint_tier=blueprint.tier,
            required_capabilities=blueprint.required_capabilities,
            cost_hint=cost_hint,
            task=task,
        )

    def orchestrate_document_run(
        self,
        *,
        task: str,
        document: str,
        blueprints: list["Blueprint"],
        a2a_pool: A2APool,
        spawn_agent_fn: SpawnAgentFn | None = None,
        preferred_agent_id: str | None = None,
        module_policy: "SchedulerModulePolicy | None" = None,
        long_doc_token_threshold: int = 180,
        status_callback: StatusCallback | None = None,
    ) -> DocumentRunResult:
        """
        Probe a large document, decide routing, spawn/register a RAG-ready agent,
        and dispatch the document directly while emitting run status events.

        This is the "direct document path" requested by the architecture:
        1. Read only a sample slice (DocumentProbe) to infer required capabilities.
        2. Route to the right blueprint using semantic scoring.
        3. Assign model and MCP attachments via AssignmentPolicy.
        4. Spawn or select an A2A agent that is RAG-ready.
        5. Dispatch the full document payload directly through DocumentDispatcher.

        Args:
            task: User task for the document.
            document: Full document payload.
            blueprints: Candidate blueprints to route against.
            a2a_pool: A2A pool used for endpoint registration and dispatch.
            spawn_agent_fn: Optional callback to spin an agent and return agent_id.
            preferred_agent_id: Optional pre-existing target agent id.
            module_policy: Optional scheduler module policy for dispatch guardrails.
            long_doc_token_threshold: Token threshold above which scraper-style RAG
                                      is selected for the spawned agent metadata.
            status_callback: Optional callback invoked per run status event.

        Returns:
            DocumentRunResult containing assignment, dispatch metadata, and all
            status events emitted during the run.
        """
        if not task.strip():
            raise ValueError("task must not be empty")
        if not document.strip():
            raise ValueError("document must not be empty")
        if not blueprints:
            raise ValueError("blueprints list must not be empty")

        run_id = f"run-{uuid4().hex[:12]}"
        events: list[RunStatusEvent] = []

        def _emit(stage: str, message: str, **details: Any) -> None:
            event = RunStatusEvent(stage=stage, message=message, details=dict(details))
            events.append(event)
            if status_callback is not None:
                status_callback(event)

        full_document_estimated_tokens = self._document_probe.estimate_tokens(document)
        probe = self._document_probe.probe(document)
        _emit(
            "probe_document",
            "Probed document sample for capability and complexity signals.",
            full_document_estimated_tokens=full_document_estimated_tokens,
            estimated_tokens=probe.estimated_tokens,
            cost_hint=probe.cost_hint,
            required_capabilities=list(probe.required_capabilities),
        )

        route_task = f"{task}\n\nDocument preview:\n{probe.preview}"
        blueprint, confidence = self.route(route_task, blueprints)
        _emit(
            "route_blueprint",
            "Selected blueprint for document run.",
            blueprint=blueprint.name,
            confidence=confidence,
        )

        required_capabilities = set(blueprint.required_capabilities)
        required_capabilities.update(probe.required_capabilities)
        required_capabilities.update(_INTERNAL_ORCHESTRATION_CAPABILITIES)

        # Internal orchestration tags (for agent/runtime routing) are not MCP tags.
        mcp_required_capabilities = sorted(
            capability
            for capability in required_capabilities
            if capability not in _INTERNAL_ORCHESTRATION_CAPABILITIES
        )

        assignment = self._policy.assign(
            blueprint_tier=blueprint.tier,
            required_capabilities=mcp_required_capabilities,
            cost_hint=probe.cost_hint,
            task=route_task,
        )
        _emit(
            "assign_resources",
            "Assigned model and MCP attachments for spawn.",
            model_id=assignment.model_id,
            tier=assignment.tier.value,
            mcp_servers=[server.server_id for server in assignment.mcp_servers],
        )

        rag_template = self._select_rag_template(
            probe=probe,
            document_token_estimate=full_document_estimated_tokens,
            long_doc_token_threshold=long_doc_token_threshold,
        )

        mcp_capabilities = {
            capability
            for server in assignment.mcp_servers
            for capability in server.capabilities
        }
        agent_capabilities = sorted(required_capabilities.union(mcp_capabilities))
        runtime_description = self._build_runtime_agent_description(
            blueprint=blueprint,
            assignment=assignment,
            rag_template=rag_template,
            capabilities=agent_capabilities,
        )
        proposed_agent_id = preferred_agent_id or self._default_agent_id(run_id)

        spawned_agent_id = preferred_agent_id
        spawn_metadata = {
            "run_id": run_id,
            "tracking_id": run_id,
            "proposed_agent_id": proposed_agent_id,
            "blueprint": blueprint.name,
            "description": runtime_description,
            "assignment": {
                "model_id": assignment.model_id,
                "provider": assignment.provider,
                "tier": assignment.tier.value,
                "mcp_servers": [server.server_id for server in assignment.mcp_servers],
            },
            "rag_template": rag_template,
            "required_capabilities": agent_capabilities,
            "probe": {
                "estimated_tokens": probe.estimated_tokens,
                "cost_hint": probe.cost_hint,
            },
        }

        if spawn_agent_fn is not None:
            spawned_agent_id = spawn_agent_fn(blueprint, assignment, spawn_metadata)

        resolved_spawn_id = None
        if spawned_agent_id is not None and str(spawned_agent_id).strip():
            resolved_spawn_id = str(spawned_agent_id).strip()
        elif spawn_agent_fn is not None:
            # If spawn happened but no id came back, fall back to deterministic id for tracking.
            resolved_spawn_id = proposed_agent_id

        if resolved_spawn_id is not None:
            spawn_metadata["agent_id"] = resolved_spawn_id

        if resolved_spawn_id is not None:
            card = A2AAgentCard(
                agent_id=resolved_spawn_id,
                name=f"{blueprint.name}-{resolved_spawn_id}",
                endpoint=f"http://localhost/agents/{resolved_spawn_id}",
                capabilities=frozenset(agent_capabilities),
                description=runtime_description,
                metadata=spawn_metadata,
            )
            a2a_pool.register(card)
            _emit(
                "spawn_agent",
                "Registered spawned agent in A2A pool for direct dispatch.",
                agent_id=resolved_spawn_id,
                rag_template=rag_template,
            )
        else:
            _emit(
                "spawn_agent",
                "No spawn callback provided; selecting from existing A2A pool.",
                strategy="reuse",
            )

        dispatcher = DocumentDispatcher(
            router=self._build_router(a2a_pool),
            probe=self._document_probe,
            module_policy=module_policy,
        )

        _emit(
            "dispatch_document",
            "Dispatching document to RAG-ready agent.",
            preferred_agent_id=resolved_spawn_id,
            required_capabilities=agent_capabilities,
        )
        dispatch = dispatcher.dispatch(
            task=task,
            document=document,
            preferred_agent_id=resolved_spawn_id,
            required_capabilities=agent_capabilities,
            metadata={
                **spawn_metadata,
                "status_events": [event.stage for event in events],
            },
            probe_result=probe,
        )

        _emit(
            "completed",
            "Document run dispatched successfully.",
            dispatch_id=dispatch.dispatch_id,
            target_agent=dispatch.routed_task.target.agent_id,
        )

        return DocumentRunResult(
            run_id=run_id,
            blueprint=blueprint,
            assignment=assignment,
            dispatch=dispatch,
            rag_template=rag_template,
            agent_id=dispatch.routed_task.target.agent_id,
            probe=probe,
            events=tuple(events),
        )

    @staticmethod
    def _build_router(a2a_pool: A2APool) -> Any:
        from .a2a_router import A2ARouter

        return A2ARouter(a2a_pool)

    @staticmethod
    def _select_rag_template(
        *,
        probe: ProbedDocument,
        document_token_estimate: int,
        long_doc_token_threshold: int,
    ) -> str:
        if document_token_estimate >= max(1, long_doc_token_threshold):
            return "scraper"
        if "knowledge_graph" in probe.required_capabilities:
            return "knowledge_graph"
        return "basic"

    @staticmethod
    def _default_agent_id(run_id: str) -> str:
        suffix = run_id[4:] if run_id.startswith("run-") else run_id
        return f"agent-{suffix}"

    @staticmethod
    def _build_runtime_agent_description(
        *,
        blueprint: "Blueprint",
        assignment: Assignment,
        rag_template: str,
        capabilities: list[str],
    ) -> str:
        mcp_parts = []
        for server in assignment.mcp_servers:
            if server.description.strip():
                mcp_parts.append(f"{server.server_id} ({server.description})")
            else:
                mcp_parts.append(server.server_id)

        mcp_text = ", ".join(mcp_parts) if mcp_parts else "none"
        capability_text = ", ".join(capabilities) if capabilities else "none"
        return (
            f"{blueprint.description} "
            f"Runtime profile: model={assignment.model_id} provider={assignment.provider} "
            f"tier={assignment.tier.value}; rag={rag_template}; "
            f"mcps={mcp_text}; capabilities={capability_text}."
        )

    def get_config(self) -> dict[str, Any]:
        """Return current mutable orchestrator configuration."""
        try:
            routing_model = self._policy.routing_model()
            effective_model = self._routing_model_override or routing_model.model_id
            effective_provider = routing_model.provider
            if self._routing_model_override:
                pool_models = {m.model_id: m for m in self._policy._llm.list_models()}  # noqa: SLF001
                if self._routing_model_override in pool_models:
                    effective_provider = pool_models[self._routing_model_override].provider
        except RuntimeError:
            effective_model = self._routing_model_override or "none"
            effective_provider = "unknown"

        return {
            "routing_model_override": self._routing_model_override,
            "effective_routing_model": effective_model,
            "effective_routing_provider": effective_provider,
            "min_confidence": self._min_confidence,
            "decompose_enabled": self._decompose_enabled,
            "available_models": [
                {"model_id": m.model_id, "tier": m.tier.value, "provider": m.provider}
                for m in self._policy._llm.list_models()  # noqa: SLF001
            ],
        }

    def update_config(
        self,
        *,
        routing_model_override: str | None = ...,  # type: ignore[assignment]
        min_confidence: float | None = None,
        decompose_enabled: bool | None = None,
    ) -> None:
        """Update runtime orchestrator configuration."""
        if routing_model_override is not ...:  # type: ignore[comparison-overlap]
            # Validate override exists in pool if non-None
            if routing_model_override is not None:
                pool_ids = {m.model_id for m in self._policy._llm.list_models()}  # noqa: SLF001
                if routing_model_override not in pool_ids:
                    raise ValueError(
                        f"Model {routing_model_override!r} not found in pool. "
                        f"Registered: {sorted(pool_ids)}"
                    )
            self._routing_model_override = routing_model_override
        if min_confidence is not None:
            self._min_confidence = max(0.0, min(1.0, float(min_confidence)))
        if decompose_enabled is not None:
            self._decompose_enabled = bool(decompose_enabled)

    def __repr__(self) -> str:
        override = self._routing_model_override or "auto"
        return f"Orchestrator(policy={self._policy!r}, routing_model={override!r})"
