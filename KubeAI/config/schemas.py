"""Config key schemas and category definitions."""

from __future__ import annotations

# Config categories with their descriptions
CATEGORIES = {
    "rag": "RAG pipeline configuration",
    "llm": "LLM pool and model configuration",
    "mcp": "MCP server configuration",
    "blueprint": "Agent blueprint configuration",
    "skill": "Skill and workflow configuration",
    "orchestrator": "Orchestrator routing configuration",
    "general": "General system configuration",
}

# Default config keys with (default_value, category, description)
DEFAULT_CONFIGS: dict[str, tuple[object, str, str]] = {
    "rag.default_template":                ("basic",                                     "rag",          "Default RAG template (basic, hybrid, reranking)"),
    "rag.embedding_provider":              ("fastembed",                                  "rag",          "Embedding provider (fastembed, openai, cohere)"),
    "rag.chunking_strategy":               ({"chunk_size": 500, "overlap": 50},           "rag",          "Document chunking configuration"),
    "rag.vector_store_backend":            ("in_memory",                                  "rag",          "Vector store backend (in_memory, chroma, qdrant)"),
    "rag.reranker_model":                  ("cross-encoder/ms-marco-MiniLM-L-6-v2",       "rag",          "Cross-encoder model for reranking"),
    "rag.indexing_model":                  ("fastembed",                                  "rag",          "Model used for document indexing"),
    "orchestrator.min_confidence":          (0.3,                                          "orchestrator", "Minimum routing confidence threshold"),
    "orchestrator.routing_model_override":  (None,                                         "orchestrator", "Override routing model (null = use largest)"),
    "orchestrator.auto_decompose":          (True,                                         "orchestrator", "Auto-decompose complex tasks"),
}
