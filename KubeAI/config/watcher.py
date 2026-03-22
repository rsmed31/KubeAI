"""ConfigWatcher — background thread that polls PostgreSQL for config changes."""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from KubeAI.config.store import ConfigStore

logger = logging.getLogger(__name__)


class ConfigWatcher:
    """Thin wrapper managing the ConfigStore's watch lifecycle."""

    def __init__(self, store: "ConfigStore", interval: float = 2.0) -> None:
        self._store = store
        self._interval = interval

    def start(self) -> None:
        self._store.start_watching()

    def stop(self) -> None:
        self._store.stop_watching()

    def __repr__(self) -> str:
        return f"ConfigWatcher(interval={self._interval})"
