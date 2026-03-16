"""Orchestrator is the Ingress+Istio analogue: semantically routes tasks to blueprints using LLM scoring via the largest registered model."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable

from .assignment import Assignment, AssignmentPolicy

if TYPE_CHECKING:
    from KubeAI.blueprint import Blueprint

# Type alias: (task, blueprint, model_id) → score 0.0-1.0
ScoreFn = Callable[["Blueprint", str, str], float]

# Type alias: (task, model_id) → list[str]
DecomposeFn = Callable[[str, str], list[str]]


def _llm_score(task: str, blueprint: "Blueprint", model_id: str) -> float:
    """
    Default LLM-based scorer using the Anthropic SDK.

    Builds a prompt that asks the model to rate how well a blueprint matches a
    task, then parses the single decimal response. Falls back to 0.0 on any
    parse or API error.

    Args:
        task: The task description to score.
        blueprint: The Blueprint being evaluated.
        model_id: The model identifier to use for scoring.

    Returns:
        A float in [0.0, 1.0].
    """
    try:
        import anthropic  # type: ignore[import]
    except ImportError:
        return 0.0

    prompt = (
        f"Score how well this agent blueprint matches the task. "
        f"Blueprint: {blueprint.name} - {blueprint.description}. "
        f"Task: {task}. "
        f"Reply with only a decimal between 0.0 and 1.0."
    )
    try:
        client = anthropic.Anthropic()
        response = client.messages.create(
            model=model_id,
            max_tokens=16,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()
        return max(0.0, min(1.0, float(raw)))
    except Exception:
        return 0.0


def _llm_decompose(task: str, model_id: str, max_subtasks: int = 5) -> list[str]:
    """
    Default LLM-based task decomposer using the Anthropic SDK.

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
        import anthropic  # type: ignore[import]
    except ImportError:
        return [task]

    prompt = (
        f"Decompose this task into {max_subtasks} or fewer independent parallel subtasks. "
        f"Task: {task}. "
        f"Reply with one subtask per line, no numbering."
    )
    try:
        client = anthropic.Anthropic()
        response = client.messages.create(
            model=model_id,
            max_tokens=256,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text
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
        """
        self._policy = policy
        self._score_fn: ScoreFn = score_fn if score_fn is not None else _llm_score
        self._decompose_fn: DecomposeFn = (
            decompose_fn if decompose_fn is not None else _llm_decompose
        )

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
        model = self._policy.routing_model()
        scores: dict[str, float] = {
            bp.name: max(0.0, min(1.0, self._score_fn(task, bp, model.model_id)))
            for bp in blueprints
        }
        best = max(blueprints, key=lambda b: scores[b.name])
        return best, scores[best.name]

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
            task: Optional task string (reserved for future cost estimation).
            cost_hint: Float 0.0 (cheapest) to 1.0 (most capable).

        Returns:
            An immutable Assignment with the selected model and MCP servers.
        """
        return self._policy.assign(
            blueprint_tier=blueprint.tier,
            required_capabilities=blueprint.required_capabilities,
            cost_hint=cost_hint,
        )

    def __repr__(self) -> str:
        return f"Orchestrator(policy={self._policy!r})"
