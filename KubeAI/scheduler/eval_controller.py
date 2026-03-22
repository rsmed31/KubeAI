"""EvalController is the health-probe controller analogue: scores active agents and replaces underperformers."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from KubeAI.api.control_plane import ControlPlaneAPI
    from KubeAI.scheduler.lifecycle import AgentLifecycleManager, SpawnedAgent


# score_fn(agent) -> [0.0, 1.0]
ScoreAgentFn = Callable[["SpawnedAgent"], float]


@dataclass(frozen=True)
class EvalDecision:
    """One evaluation decision for one agent probe cycle."""

    agent_id: str
    blueprint: str
    score: float
    replaced: bool


class EvalController:
    """Scores agents and replaces unhealthy/low-quality ones."""

    def __init__(
        self,
        lifecycle: "AgentLifecycleManager",
        control_plane: "ControlPlaneAPI",
        *,
        score_fn: ScoreAgentFn,
        min_score: float = 0.6,
    ) -> None:
        self._lifecycle = lifecycle
        self._cp = control_plane
        self._score_fn = score_fn
        self._min_score = max(0.0, min(1.0, float(min_score)))
        self._lock = threading.RLock()

    def run_once(self) -> list[EvalDecision]:
        """Probe all active agents once and replace those below the threshold."""
        decisions: list[EvalDecision] = []
        for agent in self._lifecycle.list_agents():
            if agent.state == "terminated":
                continue

            raw_score = self._score_fn(agent)
            score = max(0.0, min(1.0, float(raw_score)))
            replaced = False

            self._cp._metrics.observe_histogram(  # noqa: SLF001
                "KubeAI_eval_score",
                value=score,
                labels={"blueprint": agent.blueprint.name},
            )

            if score < self._min_score:
                replaced = self._replace_agent(agent)

            decisions.append(
                EvalDecision(
                    agent_id=agent.agent_id,
                    blueprint=agent.blueprint.name,
                    score=score,
                    replaced=replaced,
                )
            )

        return decisions

    def _replace_agent(self, agent: "SpawnedAgent") -> bool:
        with self._lock:
            terminated = self._lifecycle.terminate(agent.agent_id)
            if not terminated:
                return False

            replacement = self._lifecycle.spawn(agent.blueprint)

        self._cp._events.publish(  # noqa: SLF001
            "agent.eval_replaced",
            {
                "old_agent_id": agent.agent_id,
                "new_agent_id": replacement.agent_id,
                "blueprint": agent.blueprint.name,
            },
        )
        return True

    def __repr__(self) -> str:
        return f"EvalController(min_score={self._min_score:.2f})"
