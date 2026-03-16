# Skill: RAG Agent

## Role
Implement RAG template variants that can be mounted onto an agent at spawn time.

## Primary Scope
1. KubeAI/templates/rag/basic.py
2. KubeAI/templates/rag/hybrid.py
3. KubeAI/templates/rag/reranking.py
4. templates/rag/basic.yaml
5. templates/rag/hybrid.yaml
6. templates/rag/reranking.yaml

## Implementation Rules
1. Keep dependencies minimal: numpy and rank_bm25.
2. sentence-transformers reranking is optional with graceful fallback.
3. Retrieval output must be deterministic for identical inputs and config.

## Non-Goals
1. Do not modify orchestrator routing behavior.
2. Do not implement memory template logic.

## Deliverables
1. Basic vector retrieval with cosine similarity.
2. Hybrid retrieval using BM25 plus vector search with reciprocal rank fusion.
3. Reranking stage with optional cross-encoder and fallback path.
4. YAML defaults and validation assumptions documented in module docstrings.

## Acceptance Criteria
1. add_documents and retrieve interfaces are type hinted and tested.
2. top_k and threshold settings are respected across strategies.
3. Empty corpus and empty query paths are handled safely.

## Handoff Contract
1. Include benchmark notes for retrieval quality and runtime.
2. Document fallback behavior in reranking module.
3. Include tests and sample config snippets in the PR.
