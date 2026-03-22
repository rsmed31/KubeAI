"""Shared utilities for KubeAI Airflow DAGs."""

from __future__ import annotations

import os


def get_postgres_conn_string() -> str:
    """Build PostgreSQL connection string from environment."""
    host = os.environ.get("POSTGRES_HOST", "localhost")
    port = os.environ.get("POSTGRES_PORT", "5432")
    db = os.environ.get("POSTGRES_DB", "kubeai")
    user = os.environ.get("POSTGRES_USER", "kubeai")
    password = os.environ.get("POSTGRES_PASSWORD", "kubeai_dev")
    return f"postgresql://{user}:{password}@{host}:{port}/{db}"


def get_kubeai_api_url() -> str:
    """Return the KubeAI API base URL."""
    return os.environ.get("KUBEAI_API_URL", "http://localhost:8080")
