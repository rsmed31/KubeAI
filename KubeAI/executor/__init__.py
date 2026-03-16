"""KubeAI executor — the kubelet analogue: runs tasks on spawned agents via LiteLLM."""

from KubeAI.executor.agent_executor import AgentExecutor, AgentResult

__all__ = ["AgentExecutor", "AgentResult"]
