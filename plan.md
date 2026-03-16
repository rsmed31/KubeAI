# KubeAI Implementation Plan

## Objective
Reach safe parallel execution for implementation lanes, including smart LLM and MCP allocation policy, plus modular data-ingestion and dispatch capabilities (RAG scraper, knowledge graph builder, custom A2A pool, direct document dispatch), then pause for delegated execution.

## Scope For This Wave
1. Delegation docs and workflow controls.
2. Template and CLI scaffolding required for parallel work.
3. Ownership, dependencies, and merge gates.
4. Orchestrator assignment policy for LLMPool and MCPPool.
5. Modular RAG ingestion and dispatch extensions attachable or removable per agent via scheduler policy.

Excluded from this wave:
1. REST API and dashboard implementation.
2. Kubernetes operator work.
3. Production deployment automation.

## Milestones
1. M0: Alignment
- Validate architecture constraints from CLAUDE.md.
- Confirm repository baseline and naming choices.
- Status: complete.

2. M1: Delegation Assets
- Create agents.md.
- Create skills folder with role-specific execution briefs.
- Create plan.md.
- Status: complete.

3. M2: Parallel Workflow Enablement
- Publish branch strategy and merge policy.
- Publish lane dependencies and handoff contract.
- Create implementation scaffolding paths to avoid file ownership collisions.
- Status: complete.

4. M3: Orchestrator Pool Policy
- Add LLMPool assignment policy using cost, load, and blueprint tier signals.
- Add MCPPool assignment policy using capability tags and multi-MCP attachment.
- Enforce the rule that routing uses the largest registered model.
- Status: complete.

5. M4: Delegated Execution
- Template infrastructure lane delivers contract.
- Orchestrator pools lane delivers allocator contracts.
- RAG and memory lanes implement in parallel.
- CLI lane implements command surface in parallel.
- Integration and QA lane validates composition.
- Status: in progress.

6. M5: Modular RAG Ingestion and Graph (next)
- Add RAG scraper module to ingest raw documents or URLs for retrieval pipelines.
- Add knowledge graph builder module to extract entity and relation structure from ingested content.
- Ensure scraper and knowledge graph modules are scheduler-manageable attachments per agent.
- Status: planned.

7. M6: Custom A2A Pool and Direct Document Dispatch (next)
- Add custom A2A pool for capability-aware inter-agent routing and connection reuse.
- Add direct-document dispatch flow: sample a small document slice, infer handling path, and send document payload directly to a spawned RAG-ready agent.
- Ensure dispatch and A2A modules are scheduler-manageable attachments per agent.
- Status: planned.

## Dependency Graph
1. Lane A Template Infrastructure blocks Lane B RAG and Lane C Memory.
2. Lane F Orchestrator Pools must publish assignment interfaces before final CLI wiring.
3. Lane D CLI can begin after runtime interfaces are fixed.
4. Lane E Integration and QA runs after Lanes B, C, D, and F complete.
5. Lane G RAG Scraper depends on Lane A contract and can run in parallel with Lane B.
6. Lane H Knowledge Graph Builder depends on Lane G document ingestion interfaces.
7. Lane I Custom A2A Pool depends on Lane F allocator contracts.
8. Lane J Direct Document Dispatch depends on Lanes G and I and requires scheduler module-policy hooks.

## Lane Assignment Map
1. Lane A: KubeAI/templates/base.py and attach hooks.
2. Lane B: KubeAI/templates/rag/* plus templates/rag/*.yaml.
3. Lane C: KubeAI/templates/memory/* plus templates/memory/*.yaml.
4. Lane D: KubeAI/cli.py and CLI behavior docs.
5. Lane E: tests, demo updates, and release verification.
6. Lane F: KubeAI/orchestrator/llm_pool.py, KubeAI/orchestrator/mcp_pool.py, and assignment policy contracts.
7. Lane G: KubeAI/templates/rag/scraper.py and templates/rag/scraper.yaml.
8. Lane H: KubeAI/templates/rag/knowledge_graph.py and templates/rag/knowledge_graph.yaml.
9. Lane I: KubeAI/orchestrator/a2a_pool.py and KubeAI/orchestrator/a2a_router.py.
10. Lane J: KubeAI/orchestrator/document_dispatch.py, KubeAI/orchestrator/document_probe.py, and KubeAI/scheduler/module_policy.py.

## Merge Order
1. feat/agent-template-infra
2. feat/agent-pools
3. feat/agent-rag
4. feat/agent-memory
5. feat/agent-cli
6. feat/agent-rag-scraper
7. feat/agent-knowledge-graph
8. feat/agent-a2a-pool
9. feat/agent-document-dispatch
10. feat/agent-integration
11. feat/integration-kubeai-runtime to main

## Verification Gates
1. Documentation gate
- Ownership has no overlaps.
- Every lane includes acceptance criteria and handoff requirements.

2. Code gate
- Tests pass for templates and CLI.
- One RAG template and one memory template can be attached together.
- LLMPool tests validate cost-tier selection, load failover, and routing-model override.
- MCPPool tests validate capability matching and multi-MCP attachment for one agent.
- Scraper tests validate sampling, extraction, and chunking behavior.
- Knowledge graph tests validate entity and relation extraction plus graph serialization.
- Custom A2A pool tests validate registration, health, and capability-aware routing.
- Direct dispatch tests validate probe-read to scheduler spawn to RAG-ready agent handoff.
- Scheduler module-policy tests validate per-agent enable and disable behavior for each extension module.

3. Integration gate
- Full suite passes on integration branch.
- README examples match executable CLI behavior.

## Pause Condition
Stop once M2 is complete and all delegation artifacts are committed, then wait for delegated lane execution.

Current state:
1. Parallel workflow reached.
2. Lanes A through D and Lane F are implemented with passing tests.
3. Full suite is green with 90 passing tests.
4. Requested modular extensions are integrated into the plan as Lanes G through J.
5. Remaining execution lanes are E and G through J.
