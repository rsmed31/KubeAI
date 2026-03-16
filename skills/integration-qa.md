# Skill: Integration and QA Agent

## Role
Validate composed behavior across lanes and prevent regressions before merge to main.

## Primary Scope
1. tests/**
2. examples/demo.py
3. README.md command and architecture consistency checks

## Verification Areas
1. Template composition:
- RAG template and memory template can attach to one agent simultaneously.
2. Runtime behavior:
- Scheduler reuse and lifecycle transitions remain valid.
3. CLI behavior:
- run, status, templates list, and blueprints commands align with runtime behavior.
4. Pool allocator behavior:
- LLMPool selection follows cost and blueprint tier constraints.
- LLMPool failover works when a provider is unavailable.
- MCPPool attaches one or more MCP servers from capability matches.

## Non-Goals
1. Do not redesign lane APIs during integration unless a blocker is proven.
2. Do not merge directly to main.

## Acceptance Criteria
1. Integration branch passes full test suite.
2. README examples execute without drift from implementation.
3. Known risks documented with owners.
4. Pool allocator test matrix is included in release recommendation.

## Handoff Contract
1. Publish regression summary with failures and fixes.
2. Publish release recommendation for integration merge.
3. Provide follow-up backlog for unresolved non-blocking issues.
