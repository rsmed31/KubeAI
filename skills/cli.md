# Skill: CLI Agent

## Role
Build the agentctl command interface that operators use to run and observe KubeAI.

## Primary Scope
1. KubeAI/cli.py
2. CLI usage examples in README.md when command behavior is finalized.

## Command Surface
1. agentctl run "<task>" [--rag basic|hybrid|reranking] [--memory sliding_window|summarizing|episodic]
2. agentctl blueprints list
3. agentctl blueprints register <path.yaml>
4. agentctl templates list
5. agentctl mcps list
6. agentctl mcps register <path-or-url>
7. agentctl status
8. agentctl demo

## Implementation Rules
1. Use click unless integration constraints force argparse.
2. Print human-readable output by default.
3. Exit non-zero on recoverable command errors with actionable messages.
4. The CLI forwards pool registration metadata; it does not perform model or tool assignment.

## Non-Goals
1. Do not implement template internals.
2. Do not add orchestration routing shortcuts.

## Acceptance Criteria
1. Help text is complete and accurate.
2. Flags map directly to runtime/template selection.
3. Command error handling is consistent.
4. MCP registration and listing commands are discoverable and validated.

## Handoff Contract
1. Include transcript examples for success and failure.
2. List unresolved UX questions.
3. Add tests for flag parsing and command dispatch.
