# KubeAI Delegation Control Plane

This document defines how multiple coding agents collaborate safely on KubeAI.

## Mission
Build KubeAI through parallel component lanes while preserving architecture invariants.

## Non-Negotiable Engineering Rules
1. Agents are stateless. Persistent task context must live in SharedMemory only.
2. Blueprints are immutable. New behavior requires a new version, never mutation in place.
3. Orchestrator routing is semantic and LLM-scored only, with no hardcoded keyword routing.
4. Templates are composable and attach at spawn time; they do not subclass Agent.
5. Every Python module must include a module docstring with the K8s analogy.
6. Blueprint model requirements are tier-based (fast, capable, best), not provider-specific model names.
7. The Orchestrator routing step always runs on the largest registered model.
8. Agents never self-select models or tools; they receive LLM and MCP assignments at spawn.

## Branch Model
1. feat/agent-template-infra
2. feat/agent-pools
3. feat/agent-rag
4. feat/agent-memory
5. feat/agent-cli
6. feat/agent-integration
7. feat/integration-kubeai-runtime

Mainline policy:
- Role branches merge into feat/integration-kubeai-runtime first.
- Main receives merge commits only after integration gate passes.

## Ownership Matrix
1. Template Infrastructure Agent
- Primary files:
  - KubeAI/templates/base.py
  - KubeAI/templates/__init__.py
- Responsibility: define stable template contract and attach lifecycle hooks.

2. Orchestrator Pools Agent
- Primary files:
  - KubeAI/orchestrator/llm_pool.py
  - KubeAI/orchestrator/mcp_pool.py
  - KubeAI/orchestrator/assignment.py
  - KubeAI/orchestrator/__init__.py
- Responsibility: assign LLM tier/model and MCP attachments based on policy signals.

3. RAG Agent
- Primary files:
  - KubeAI/templates/rag/basic.py
  - KubeAI/templates/rag/hybrid.py
  - KubeAI/templates/rag/reranking.py
  - templates/rag/basic.yaml
  - templates/rag/hybrid.yaml
  - templates/rag/reranking.yaml
- Responsibility: retrieval pipelines and deterministic fallback behavior.

4. Memory Agent
- Primary files:
  - KubeAI/templates/memory/sliding_window.py
  - KubeAI/templates/memory/summarizing.py
  - KubeAI/templates/memory/episodic.py
  - templates/memory/sliding_window.yaml
  - templates/memory/summarizing.yaml
  - templates/memory/episodic.yaml
- Responsibility: history management and fact memory injection patterns.

5. CLI Agent
- Primary files:
  - KubeAI/cli.py
- Responsibility: agentctl command surface and clear output formatting.

6. Integration and QA Agent
- Primary files:
  - tests/**
  - examples/demo.py
  - README.md
- Responsibility: end-to-end composition, regression tests, and docs parity.

7. Release Manager Agent
- Primary files:
  - plan.md
  - agents.md
  - skills/**
- Responsibility: sequencing, merge risk management, and release readiness.

## Handoff Contract
1. Each role branch must include a short handoff note in the PR description:
- completed scope
- API contract changes
- known risks
- tests executed
- blocked follow-ups
2. No cross-lane edits to another agent's primary file set without explicit coordination.
3. Integration conflicts are resolved in feat/integration-kubeai-runtime only.

## Definition Of Done (Per Lane)
1. All owned files implemented with type hints and public method docstrings.
2. New classes have a readable __repr__ or __str__ output.
3. Unit tests cover happy path plus one failure path per public method.
4. No architecture rule violation from the non-negotiable rules.
5. Handoff contract completed.

## Delegation Start Commands
1. git checkout -b feat/agent-template-infra
2. git checkout -b feat/agent-pools
3. git checkout -b feat/agent-rag
4. git checkout -b feat/agent-memory
5. git checkout -b feat/agent-cli
6. git checkout -b feat/agent-integration
7. git checkout -b feat/integration-kubeai-runtime

## Current Status
Parallel workflow is enabled when Template Infrastructure and Orchestrator Pools publish stable contracts in their branches.
