"""EtcdBackend is the Kubernetes etcd analogue: distributed strongly-consistent KV storage for KubeAI shared memory tiers."""

from __future__ import annotations

import json
import math
import threading
from typing import Any

from .base import SharedMemoryBackend


def _load_etcd3_module() -> Any:
    """Load the etcd3 client module with a clear install hint on failure."""
    try:
        import etcd3  # type: ignore[import-not-found]
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "etcd3 is required for EtcdBackend. Install it with 'pip install etcd3'."
        ) from exc
    return etcd3


class EtcdBackend(SharedMemoryBackend):
    """etcd-backed KV storage using optional TTL leases.

    This backend mirrors Kubernetes control-plane persistence semantics:
    strongly consistent writes, prefix-scoped key iteration, and optional
    lease-based expiry for short-lived keys.
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 2379,
        *,
        namespace: str = "kubeai",
        timeout_s: float = 5.0,
        user: str | None = None,
        password: str | None = None,
        client: Any | None = None,
    ) -> None:
        self._host = host
        self._port = int(port)
        self._namespace = namespace.strip().strip(":") or "kubeai"
        self._timeout_s = float(timeout_s)
        self._lock = threading.RLock()

        if client is not None:
            self._client = client
        else:
            try:
                etcd3 = _load_etcd3_module()
            except ModuleNotFoundError as exc:
                raise RuntimeError(
                    "etcd3 is required for EtcdBackend. Install it with 'pip install etcd3'."
                ) from exc
            self._client = etcd3.client(
                host=self._host,
                port=self._port,
                timeout=self._timeout_s,
                user=user,
                password=password,
            )

    def get(self, key: str) -> Any | None:
        """Return decoded value for key, or None if absent."""
        scoped = self._scoped_key(key)
        with self._lock:
            value, _metadata = self._client.get(scoped)
        if value is None:
            return None
        if isinstance(value, bytes):
            value = value.decode("utf-8")
        return json.loads(value)

    def set(self, key: str, value: Any, ttl_s: float | None = None) -> None:
        """Store JSON-encoded value with optional etcd lease-backed TTL."""
        scoped = self._scoped_key(key)
        serialised = json.dumps(value)
        with self._lock:
            if ttl_s is None:
                self._client.put(scoped, serialised)
                return

            lease_seconds = max(1, int(math.ceil(float(ttl_s))))
            lease = self._client.lease(lease_seconds)
            self._client.put(scoped, serialised, lease=lease)

    def delete(self, key: str) -> bool:
        """Delete key from etcd and return whether it existed."""
        scoped = self._scoped_key(key)
        with self._lock:
            deleted = self._client.delete(scoped)
        if isinstance(deleted, tuple):
            return bool(deleted[0])
        return bool(deleted)

    def keys(self, prefix: str = "") -> list[str]:
        """Return namespace-local keys filtered by prefix."""
        scoped_prefix = self._scoped_prefix(prefix)
        namespace_prefix = self._scoped_prefix("")

        with self._lock:
            rows = list(self._client.get_prefix(scoped_prefix))

        result: list[str] = []
        for _value, metadata in rows:
            key_bytes = getattr(metadata, "key", b"")
            full_key = key_bytes.decode("utf-8") if isinstance(key_bytes, bytes) else str(key_bytes)
            if not full_key.startswith(namespace_prefix):
                continue
            result.append(full_key[len(namespace_prefix):])
        return result

    def clear(self) -> None:
        """Delete every key under this backend namespace."""
        with self._lock:
            self._client.delete_prefix(self._scoped_prefix(""))

    def _scoped_key(self, key: str) -> str:
        stripped = key.strip()
        if not stripped:
            raise ValueError("key must not be empty")
        return f"{self._namespace}:{stripped}"

    def _scoped_prefix(self, prefix: str) -> str:
        base = f"{self._namespace}:"
        return f"{base}{prefix}" if prefix else base

    def __repr__(self) -> str:
        try:
            entry_count = len(self.keys())
        except Exception:
            entry_count = -1
        return (
            f"EtcdBackend(host={self._host!r}, port={self._port}, "
            f"namespace={self._namespace!r}, entries={entry_count})"
        )
