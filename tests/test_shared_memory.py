"""Unit tests for SharedMemory, InMemoryBackend, and SQLiteBackend."""

from __future__ import annotations

import time

import pytest

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
