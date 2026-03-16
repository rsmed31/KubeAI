# Skill: Memory Agent

## Role
Implement memory template variants that manage conversational history and fact recall.

## Primary Scope
1. KubeAI/templates/memory/sliding_window.py
2. KubeAI/templates/memory/summarizing.py
3. KubeAI/templates/memory/episodic.py
4. templates/memory/sliding_window.yaml
5. templates/memory/summarizing.yaml
6. templates/memory/episodic.yaml

## Implementation Rules
1. Templates must remain composable with RAG templates.
2. Summarization must use the same configured LLM path as runtime.
3. Episodic memory stores extracted facts and injects only relevant facts.

## Non-Goals
1. Do not alter shared memory tier semantics.
2. Do not implement CLI commands.

## Deliverables
1. Sliding window strategy by configurable turn count.
2. Summarizing strategy with token threshold and recent turn retention.
3. Episodic strategy with fact extraction and similarity retrieval.
4. YAML defaults with safe conservative values.

## Acceptance Criteria
1. History truncation or summarization never drops recent configured turns.
2. Fact retrieval path handles low-similarity edge cases gracefully.
3. Unit tests cover short history, long history, and empty history.

## Handoff Contract
1. Provide examples of injected memory context payloads.
2. Document token threshold assumptions.
3. Include performance notes on large histories.
