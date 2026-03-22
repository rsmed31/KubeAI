"""ConfigStore — PostgreSQL-backed configuration with in-memory cache and hot-reload."""

from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)

# Type for change callbacks: (key, old_value, new_value)
ChangeCallback = Callable[[str, Any, Any], None]


@dataclass
class ConfigEntry:
    """Single config entry."""
    key: str
    value: Any
    category: str
    description: str = ""
    updated_at: float = 0.0
    updated_by: str = "system"


class ConfigStore:
    """PostgreSQL-backed config store with in-memory cache and change notification.

    Falls back to in-memory defaults when PostgreSQL is unreachable.
    """

    def __init__(self, dsn: str = "", poll_interval: float = 2.0) -> None:
        self._dsn = dsn
        self._poll_interval = poll_interval
        self._cache: dict[str, ConfigEntry] = {}
        self._callbacks: list[ChangeCallback] = []
        self._lock = threading.RLock()
        self._watcher_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._last_poll: float = 0.0

        # Load defaults into cache
        self._load_defaults()

        # Try initial PostgreSQL load
        if self._dsn:
            try:
                self._sync_from_db()
            except Exception as exc:
                logger.warning("Could not connect to PostgreSQL, using defaults: %s", exc)

    def _load_defaults(self) -> None:
        """Load default config values into cache."""
        defaults = {
            "rag.default_template":             ("basic",                                          "rag",          "Default RAG template"),
            "rag.embedding_provider":           ("fastembed",                                      "rag",          "Embedding provider"),
            "rag.chunking_strategy":            ({"chunk_size": 500, "overlap": 50},               "rag",          "Document chunking config"),
            "rag.vector_store_backend":         ("in_memory",                                      "rag",          "Vector store backend"),
            "rag.reranker_model":               ("cross-encoder/ms-marco-MiniLM-L-6-v2",           "rag",          "Reranker model"),
            "rag.indexing_model":               ("fastembed",                                      "rag",          "Indexing model"),
            "orchestrator.min_confidence":       (0.3,                                              "orchestrator", "Min routing confidence"),
            "orchestrator.routing_model_override": (None,                                          "orchestrator", "Routing model override"),
            "orchestrator.auto_decompose":       (True,                                             "orchestrator", "Auto-decompose complex tasks"),
        }
        with self._lock:
            for key, (value, category, desc) in defaults.items():
                if key not in self._cache:
                    self._cache[key] = ConfigEntry(
                        key=key, value=value, category=category,
                        description=desc, updated_at=time.time(),
                    )

    def get(self, key: str, default: Any = None) -> Any:
        """Get a config value. Returns default if key not found."""
        with self._lock:
            entry = self._cache.get(key)
            return entry.value if entry is not None else default

    def set(self, key: str, value: Any, category: str = "general",
            description: str = "", updated_by: str = "api") -> None:
        """Set a config value. Persists to PostgreSQL and fires change callbacks."""
        with self._lock:
            old_entry = self._cache.get(key)
            old_value = old_entry.value if old_entry else None

            entry = ConfigEntry(
                key=key, value=value, category=category or (old_entry.category if old_entry else "general"),
                description=description or (old_entry.description if old_entry else ""),
                updated_at=time.time(), updated_by=updated_by,
            )
            self._cache[key] = entry

        # Persist to PostgreSQL
        if self._dsn:
            try:
                self._persist_to_db(entry)
            except Exception as exc:
                logger.warning("Failed to persist config %s to DB: %s", key, exc)

        # Fire callbacks
        if old_value != value:
            self._fire_callbacks(key, old_value, value)

    def delete(self, key: str) -> bool:
        """Delete a config key. Returns True if existed."""
        with self._lock:
            entry = self._cache.pop(key, None)

        if entry is not None and self._dsn:
            try:
                self._delete_from_db(key)
            except Exception as exc:
                logger.warning("Failed to delete config %s from DB: %s", key, exc)

        return entry is not None

    def list_all(self) -> list[ConfigEntry]:
        """Return all config entries."""
        with self._lock:
            return list(self._cache.values())

    def list_by_category(self, category: str) -> list[ConfigEntry]:
        """Return config entries for a category."""
        with self._lock:
            return [e for e in self._cache.values() if e.category == category]

    def grouped(self) -> dict[str, list[dict[str, Any]]]:
        """Return config grouped by category for API response."""
        result: dict[str, list[dict[str, Any]]] = {}
        with self._lock:
            for entry in self._cache.values():
                if entry.category not in result:
                    result[entry.category] = []
                result[entry.category].append({
                    "key": entry.key,
                    "value": entry.value,
                    "description": entry.description,
                    "updated_by": entry.updated_by,
                })
        return result

    def on_change(self, callback: ChangeCallback) -> None:
        """Register a callback for config changes."""
        self._callbacks.append(callback)

    def _fire_callbacks(self, key: str, old_value: Any, new_value: Any) -> None:
        """Fire all registered change callbacks."""
        for cb in self._callbacks:
            try:
                cb(key, old_value, new_value)
            except Exception as exc:
                logger.warning("Config change callback failed for %s: %s", key, exc)

    def start_watching(self) -> None:
        """Start background thread polling PostgreSQL for changes."""
        if not self._dsn or self._watcher_thread is not None:
            return
        self._stop_event.clear()
        self._watcher_thread = threading.Thread(
            target=self._watch_loop, daemon=True, name="config-watcher",
        )
        self._watcher_thread.start()

    def stop_watching(self) -> None:
        """Stop the background watcher thread."""
        self._stop_event.set()
        if self._watcher_thread is not None:
            self._watcher_thread.join(timeout=5.0)
            self._watcher_thread = None

    def _watch_loop(self) -> None:
        """Poll PostgreSQL for config changes."""
        while not self._stop_event.is_set():
            try:
                self._sync_from_db()
            except Exception as exc:
                logger.debug("Config watch poll failed: %s", exc)
            self._stop_event.wait(self._poll_interval)

    def _get_connection(self):
        """Get a PostgreSQL connection."""
        import psycopg2
        return psycopg2.connect(self._dsn)

    def _sync_from_db(self) -> None:
        """Sync cache from PostgreSQL, firing callbacks for changes."""
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT config_key, config_value, category, description, "
                    "EXTRACT(EPOCH FROM updated_at), updated_by FROM config_store"
                )
                rows = cur.fetchall()
        finally:
            conn.close()

        with self._lock:
            for key, value_json, category, desc, updated_at, updated_by in rows:
                value = json.loads(value_json) if isinstance(value_json, str) else value_json
                old_entry = self._cache.get(key)
                old_value = old_entry.value if old_entry else None

                self._cache[key] = ConfigEntry(
                    key=key, value=value, category=category,
                    description=desc or "", updated_at=float(updated_at or 0),
                    updated_by=updated_by or "system",
                )

                if old_value != value:
                    self._fire_callbacks(key, old_value, value)

        self._last_poll = time.time()

    def _persist_to_db(self, entry: ConfigEntry) -> None:
        """Upsert a config entry to PostgreSQL."""
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO config_store (config_key, config_value, category, description, updated_at, updated_by)
                       VALUES (%s, %s, %s, %s, NOW(), %s)
                       ON CONFLICT (config_key) DO UPDATE
                       SET config_value = EXCLUDED.config_value,
                           category = EXCLUDED.category,
                           description = EXCLUDED.description,
                           updated_at = NOW(),
                           updated_by = EXCLUDED.updated_by""",
                    (entry.key, json.dumps(entry.value), entry.category,
                     entry.description, entry.updated_by),
                )
            conn.commit()
        finally:
            conn.close()

    def _delete_from_db(self, key: str) -> None:
        """Delete a config entry from PostgreSQL."""
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM config_store WHERE config_key = %s", (key,))
            conn.commit()
        finally:
            conn.close()

    def __repr__(self) -> str:
        with self._lock:
            return f"ConfigStore(entries={len(self._cache)}, dsn={'set' if self._dsn else 'none'})"
