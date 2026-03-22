"""Global pytest configuration for KubeAI test runs."""

from __future__ import annotations

import os

# Unit and integration tests use synthetic providers/models without real keys.
os.environ.setdefault("KUBEAI_ENFORCE_PROVIDER_CREDENTIALS", "0")
