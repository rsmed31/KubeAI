# Skill: Orchestrator Pools Agent

## Role
Own LLMPool and MCPPool allocation logic so model and tool assignment stay centralized in the Orchestrator.

## Primary Scope
1. KubeAI/orchestrator/llm_pool.py
2. KubeAI/orchestrator/mcp_pool.py
3. KubeAI/orchestrator/assignment.py
4. KubeAI/orchestrator/__init__.py

## Assignment Policy
1. LLM assignment uses three signals:
- Cost signal for simple versus complex tasks.
- Load signal for failover when provider latency or rate limits increase.
- Blueprint minimum tier signal: fast, capable, best.
2. Orchestrator routing always runs on the largest registered model.
3. MCP assignment matches task requirements to MCP capability tags.
4. Agents can receive multiple MCP servers at spawn.

## Non-Goals
1. Do not add direct tool discovery inside agents.
2. Do not hardcode provider-specific model names in blueprints.

## Deliverables
1. LLMPool registry and selector contract.
2. MCPPool registry and matcher contract.
3. Assignment integration API used by scheduler spawn path.
4. Deterministic fallback behavior for unavailable providers.

## Acceptance Criteria
1. Routing model override is enforced for orchestrator decisions.
2. Tier-to-model mapping is configurable and health-aware.
3. Capability matching supports custom MCP registrations.
4. Unit tests cover cost selection, failover, and multi-MCP assignment.

## Handoff Contract
1. Include tier map defaults and failover order.
2. Document matching semantics for MCP capability tags.
3. Provide one end-to-end sample assignment trace in the PR.
