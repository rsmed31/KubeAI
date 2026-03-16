"""Unit tests for SharedMemory and memory backends including in-memory, SQLite, and etcd."""

from __future__ import annotations

import time
from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from KubeAI.memory import etcd_backend as etcd_module
from KubeAI.memory.etcd_backend import EtcdBackend
from KubeAI.memory.in_memory import InMemoryBackend
from KubeAI.memory.shared_memory import SharedMemory
from KubeAI.memory.sqlite_backend import SQLiteBackend


# ── InMemoryBackend ───────────────────────────────────────────────────────


class TestInMemoryBackend:
    def test_set_and_get(self) -> None:
        b = InMemoryBackend()
        b.set("k", "hello")
        assert b.get("k") == "hello"

    def test_get_missing_returns_none(self) -> None:
        assert InMemoryBackend().get("nonexistent") is None

    def test_delete_existing(self) -> None:
        b = InMemoryBackend()
        b.set("k", 1)
        assert b.delete("k") is True
        assert b.get("k") is None

    def test_delete_missing_returns_false(self) -> None:
        assert InMemoryBackend().delete("ghost") is False

    def test_keys_prefix_filter(self) -> None:
        b = InMemoryBackend()
        b.set("a:1", 1)
        b.set("a:2", 2)
        b.set("b:1", 3)
        assert sorted(b.keys("a:")) == ["a:1", "a:2"]

    def test_clear_removes_all(self) -> None:
        b = InMemoryBackend()
        b.set("x", 1)
        b.set("y", 2)
        b.clear()
        assert b.keys() == []

    def test_ttl_expiry(self) -> None:
        b = InMemoryBackend()
        b.set("k", "soon-gone", ttl_s=0.05)
        assert b.get("k") == "soon-gone"
        time.sleep(0.1)
        assert b.get("k") is None

    def test_keys_prunes_expired(self) -> None:
        b = InMemoryBackend()
        b.set("live", "yes")
        b.set("dead", "no", ttl_s=0.05)
        time.sleep(0.1)
        assert "dead" not in b.keys()
        assert "live" in b.keys()

    def test_repr(self) -> None:
        b = InMemoryBackend()
        b.set("a", 1)
        assert "InMemoryBackend" in repr(b)
        assert "1" in repr(b)


# ── SQLiteBackend ─────────────────────────────────────────────────────────


class TestSQLiteBackend:
    def test_set_and_get(self) -> None:
        b = SQLiteBackend()
        b.set("k", {"nested": True})
        assert b.get("k") == {"nested": True}

    def test_get_missing_returns_none(self) -> None:
        assert SQLiteBackend().get("missing") is None

    def test_delete_existing(self) -> None:
        b = SQLiteBackend()
        b.set("k", 42)
        assert b.delete("k") is True
        assert b.get("k") is None

    def test_delete_missing_returns_false(self) -> None:
        assert SQLiteBackend().delete("ghost") is False

    def test_keys_prefix_filter(self) -> None:
        b = SQLiteBackend()
        b.set("ns:a", 1)
        b.set("ns:b", 2)
        b.set("other:c", 3)
        assert sorted(b.keys("ns:")) == ["ns:a", "ns:b"]

    def test_clear_removes_all(self) -> None:
        b = SQLiteBackend()
        b.set("x", 1)
        b.clear()
        assert b.keys() == []

    def test_ttl_expiry(self) -> None:
        b = SQLiteBackend()
        b.set("ephemeral", "bye", ttl_s=0.05)
        assert b.get("ephemeral") == "bye"
        time.sleep(0.1)
        assert b.get("ephemeral") is None

    def test_keys_prunes_expired(self) -> None:
        b = SQLiteBackend()
        b.set("live", "yes")
        b.set("dead", "no", ttl_s=0.05)
        time.sleep(0.1)
        assert "dead" not in b.keys()
        assert "live" in b.keys()

    def test_upsert_overwrites(self) -> None:
        b = SQLiteBackend()
        b.set("k", "first")
        b.set("k", "second")
        assert b.get("k") == "second"

    def test_repr(self) -> None:
        b = SQLiteBackend()
        b.set("a", 1)
        r = repr(b)
        assert "SQLiteBackend" in r
        assert ":memory:" in r


# ── EtcdBackend (with fake client) ───────────────────────────────────────


@dataclass
class _FakeLease:
    ttl: int


@dataclass
class _FakeMetadata:
    key: bytes


class _FakeEtcdClient:
    def __init__(self) -> None:
        self.store: dict[str, tuple[bytes, _FakeLease | None]] = {}

    def get(self, key: str) -> tuple[bytes | None, _FakeMetadata | None]:
        row = self.store.get(key)
        if row is None:
            return None, None
        value, _lease = row
        return value, _FakeMetadata(key=key.encode("utf-8"))

    def put(self, key: str, value: str, lease: _FakeLease | None = None) -> None:
        self.store[key] = (value.encode("utf-8"), lease)

    def delete(self, key: str) -> bool:
        return self.store.pop(key, None) is not None

    def get_prefix(self, prefix: str) -> list[tuple[bytes, _FakeMetadata]]:
        rows: list[tuple[bytes, _FakeMetadata]] = []
        for key, (value, _lease) in self.store.items():
            if key.startswith(prefix):
                rows.append((value, _FakeMetadata(key=key.encode("utf-8"))))
        return rows

    def delete_prefix(self, prefix: str) -> None:
        for key in list(self.store):
            if key.startswith(prefix):
                del self.store[key]

    def lease(self, ttl: int) -> _FakeLease:
        return _FakeLease(ttl=ttl)


class TestEtcdBackend:
    def test_set_get_and_prefix_keys(self) -> None:
        backend = EtcdBackend(client=_FakeEtcdClient(), namespace="ns")
        backend.set("long_term:agent:fact", {"ok": True})
        backend.set("long_term:agent:other", 2)
        backend.set("working:agent-1:ctx", "value")

        assert backend.get("long_term:agent:fact") == {"ok": True}
        assert sorted(backend.keys("long_term:agent:")) == [
            "long_term:agent:fact",
            "long_term:agent:other",
        ]

    def test_delete_and_clear(self) -> None:
        backend = EtcdBackend(client=_FakeEtcdClient(), namespace="ns")
        backend.set("k1", 1)
        backend.set("k2", 2)

        assert backend.delete("k1") is True
        assert backend.delete("missing") is False
        backend.clear()
        assert backend.keys() == []

    def test_set_with_ttl_uses_lease(self) -> None:
        client = _FakeEtcdClient()
        backend = EtcdBackend(client=client, namespace="ns")

        backend.set("ttl-key", "v", ttl_s=0.2)

        value, lease = client.store["ns:ttl-key"]
        assert value.decode("utf-8") == '"v"'
        assert lease is not None
        assert lease.ttl == 1

    def test_missing_etcd_dependency_raises_clear_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def _raise() -> SimpleNamespace:
            raise ModuleNotFoundError("No module named 'etcd3'")

        monkeypatch.setattr(etcd_module, "_load_etcd3_module", _raise)

        with pytest.raises(RuntimeError, match="Install it with 'pip install etcd3'"):
            EtcdBackend()

    def test_repr_contains_backend_details(self) -> None:
        backend = EtcdBackend(client=_FakeEtcdClient(), namespace="ns")
        backend.set("a", 1)
        text = repr(backend)
        assert "EtcdBackend" in text
        assert "namespace='ns'" in text


# ── SharedMemory facade ───────────────────────────────────────────────────


class TestSharedMemory:
    def _mem(self) -> SharedMemory:
        return SharedMemory()

    def test_working_set_get(self) -> None:
        m = self._mem()
        m.set_working("agent-1", "ctx", {"step": 1})
        assert m.get_working("agent-1", "ctx") == {"step": 1}

    def test_working_get_missing_returns_none(self) -> None:
        assert self._mem().get_working("agent-x", "nothing") is None

    def test_working_isolation_between_agents(self) -> None:
        m = self._mem()
        m.set_working("a1", "key", "A")
        m.set_working("a2", "key", "B")
        assert m.get_working("a1", "key") == "A"
        assert m.get_working("a2", "key") == "B"

    def test_clear_working_removes_only_that_agent(self) -> None:
        m = self._mem()
        m.set_working("a1", "k", 1)
        m.set_working("a2", "k", 2)
        m.clear_working("a1")
        assert m.get_working("a1", "k") is None
        assert m.get_working("a2", "k") == 2

    def test_handoff_copies_all_keys(self) -> None:
        m = self._mem()
        m.set_working("src", "x", 10)
        m.set_working("src", "y", 20)
        m.handoff("src", "dst")
        assert m.get_working("dst", "x") == 10
        assert m.get_working("dst", "y") == 20

    def test_handoff_does_not_remove_source(self) -> None:
        m = self._mem()
        m.set_working("src", "k", "val")
        m.handoff("src", "dst")
        assert m.get_working("src", "k") == "val"

    def test_short_term_set_get(self) -> None:
        m = self._mem()
        m.set_short_term("domain-A", "fact", "the sky is blue")
        assert m.get_short_term("domain-A", "fact") == "the sky is blue"

    def test_short_term_isolation_between_domains(self) -> None:
        m = self._mem()
        m.set_short_term("d1", "k", 1)
        m.set_short_term("d2", "k", 2)
        assert m.get_short_term("d1", "k") == 1
        assert m.get_short_term("d2", "k") == 2

    def test_long_term_set_get(self) -> None:
        m = self._mem()
        m.set_long_term("coding_agent", "style_guide", "pep8")
        assert m.get_long_term("coding_agent", "style_guide") == "pep8"

    def test_long_term_keys_returns_suffix_only(self) -> None:
        m = self._mem()
        m.set_long_term("bp", "a", 1)
        m.set_long_term("bp", "b", 2)
        assert sorted(m.keys_long_term("bp")) == ["a", "b"]

    def test_long_term_delete(self) -> None:
        m = self._mem()
        m.set_long_term("bp", "fact", "x")
        assert m.delete_long_term("bp", "fact") is True
        assert m.get_long_term("bp", "fact") is None

    def test_repr(self) -> None:
        m = self._mem()
        r = repr(m)
        assert "SharedMemory" in r
        assert "working" in r
        assert "long_term" in r

    def test_selects_etcd_long_term_backend_when_configured(self) -> None:
        m = SharedMemory(
            long_term_backend="etcd",
            etcd_client=_FakeEtcdClient(),
        )
        m.set_long_term("bp", "fact", "value")
        assert m.get_long_term("bp", "fact") == "value"

    def test_invalid_long_term_backend_raises(self) -> None:
        with pytest.raises(ValueError, match="sqlite|etcd"):
            SharedMemory(long_term_backend="postgres")
