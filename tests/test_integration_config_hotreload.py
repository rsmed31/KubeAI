"""Integration tests — ConfigStore change callbacks and SkillRegistry CRUD.

All tests use in-memory mode (dsn="") so no PostgreSQL instance is needed.
"""

from __future__ import annotations

import threading

import pytest

from KubeAI.config.skill import Skill, SkillRegistry
from KubeAI.config.store import ConfigStore


# ---------------------------------------------------------------------------
# Test 1: ConfigStore in-memory set triggers callback
# ---------------------------------------------------------------------------

def test_config_store_set_fires_callback():
    """Setting a new key fires the registered change callback with correct args."""
    store = ConfigStore(dsn="")
    received: list[tuple] = []

    store.on_change(lambda k, old, new: received.append((k, old, new)))
    store.set("myapp.feature_flag", True, category="myapp")

    assert len(received) == 1
    key, old_val, new_val = received[0]
    assert key == "myapp.feature_flag"
    assert old_val is None
    assert new_val is True


# ---------------------------------------------------------------------------
# Test 2: Multiple callbacks all fire on change
# ---------------------------------------------------------------------------

def test_config_store_multiple_callbacks_all_fire():
    """Every registered callback is invoked when a value changes."""
    store = ConfigStore(dsn="")
    log_a: list[str] = []
    log_b: list[str] = []
    log_c: list[str] = []

    store.on_change(lambda k, _o, _n: log_a.append(k))
    store.on_change(lambda k, _o, _n: log_b.append(k))
    store.on_change(lambda k, _o, _n: log_c.append(k))

    store.set("shared.key", "value", category="test")

    assert log_a == ["shared.key"]
    assert log_b == ["shared.key"]
    assert log_c == ["shared.key"]


# ---------------------------------------------------------------------------
# Test 3: Callback NOT fired when value is unchanged
# ---------------------------------------------------------------------------

def test_config_store_no_callback_when_value_unchanged():
    """Setting the same value twice only fires the callback on the first set."""
    store = ConfigStore(dsn="")
    fired: list[int] = []

    store.on_change(lambda _k, _o, _n: fired.append(1))
    store.set("stable.key", "same_value", category="general")
    store.set("stable.key", "same_value", category="general")  # identical — no callback

    assert len(fired) == 1


# ---------------------------------------------------------------------------
# Test 4: ConfigStore.list_all() returns all set values including defaults
# ---------------------------------------------------------------------------

def test_config_store_list_all_includes_defaults_and_custom():
    """list_all() returns every entry: loaded defaults plus any added keys."""
    store = ConfigStore(dsn="")
    initial_count = len(store.list_all())

    store.set("extra.key1", 42, category="extra")
    store.set("extra.key2", "hello", category="extra")

    all_entries = store.list_all()
    assert len(all_entries) == initial_count + 2

    keys = {e.key for e in all_entries}
    assert "extra.key1" in keys
    assert "extra.key2" in keys
    # Default keys are still present
    assert "rag.default_template" in keys


# ---------------------------------------------------------------------------
# Test 5: SkillRegistry in-memory CRUD — create, list, update, delete
# ---------------------------------------------------------------------------

def test_skill_registry_full_crud_cycle():
    """create / get / update / list / delete works entirely in memory."""
    reg = SkillRegistry(dsn="")

    # Create
    skill = reg.create(
        name="summariser",
        description="Summarises long documents",
        system_prompt="Be concise.",
        mcp_tools=["search"],
        tags=["nlp"],
    )
    assert isinstance(skill, Skill)
    assert skill.name == "summariser"
    assert skill.enabled is True

    # Get
    fetched = reg.get(skill.skill_id)
    assert fetched.skill_id == skill.skill_id

    # List
    all_skills = reg.list_skills()
    assert len(all_skills) == 1
    assert all_skills[0].skill_id == skill.skill_id

    # Update
    updated = reg.update(skill.skill_id, name="summariser_v2", tags=["nlp", "rag"])
    assert updated.name == "summariser_v2"
    assert "rag" in updated.tags

    # Delete
    assert reg.delete(skill.skill_id) is True
    assert reg.delete(skill.skill_id) is False  # already gone
    assert reg.list_skills() == []


# ---------------------------------------------------------------------------
# Test 6: Callback fires on value update (old -> new)
# ---------------------------------------------------------------------------

def test_config_store_callback_receives_old_and_new_value():
    """Callback receives the correct (key, old_value, new_value) triple on update."""
    store = ConfigStore(dsn="")
    transitions: list[tuple] = []

    store.on_change(lambda k, old, new: transitions.append((k, old, new)))

    store.set("counter", 1, category="test")
    store.set("counter", 2, category="test")
    store.set("counter", 3, category="test")

    assert len(transitions) == 3
    assert transitions[0] == ("counter", None, 1)
    assert transitions[1] == ("counter", 1, 2)
    assert transitions[2] == ("counter", 2, 3)


# ---------------------------------------------------------------------------
# Test 7: ConfigStore.grouped() returns dict keyed by category
# ---------------------------------------------------------------------------

def test_config_store_grouped_returns_category_dict():
    """grouped() returns a dict where keys are category names."""
    store = ConfigStore(dsn="")
    store.set("app.debug", True, category="app")
    store.set("app.version", "1.0", category="app")

    grouped = store.grouped()
    assert isinstance(grouped, dict)
    # Default categories are present
    assert "rag" in grouped
    assert "orchestrator" in grouped
    # Custom category was added
    assert "app" in grouped
    app_keys = {entry["key"] for entry in grouped["app"]}
    assert "app.debug" in app_keys
    assert "app.version" in app_keys


# ---------------------------------------------------------------------------
# Test 8: SkillRegistry filters by enabled flag
# ---------------------------------------------------------------------------

def test_skill_registry_list_enabled_filters_disabled():
    """list_enabled() omits skills whose enabled flag is False."""
    reg = SkillRegistry(dsn="")
    s1 = reg.create(name="active_skill")
    s2 = reg.create(name="inactive_skill")
    reg.update(s2.skill_id, enabled=False)

    enabled = reg.list_enabled()
    ids = {s.skill_id for s in enabled}
    assert s1.skill_id in ids
    assert s2.skill_id not in ids


# ---------------------------------------------------------------------------
# Test 9: SkillRegistry — missing skill raises KeyError
# ---------------------------------------------------------------------------

def test_skill_registry_get_missing_raises_key_error():
    """get() raises KeyError for an unknown skill_id."""
    reg = SkillRegistry(dsn="")
    with pytest.raises(KeyError):
        reg.get("nonexistent-id")


# ---------------------------------------------------------------------------
# Test 10: ConfigStore thread safety — concurrent sets all resolve
# ---------------------------------------------------------------------------

def test_config_store_concurrent_sets_are_thread_safe():
    """Concurrent writes from multiple threads should not corrupt the store."""
    store = ConfigStore(dsn="")
    errors: list[Exception] = []

    def writer(prefix: str) -> None:
        try:
            for i in range(20):
                store.set(f"{prefix}.key{i}", i, category=prefix)
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=writer, args=(f"t{n}",)) for n in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == [], f"Thread errors: {errors}"
    # Each thread wrote 20 keys, 5 threads → 100 unique keys (plus defaults)
    all_keys = {e.key for e in store.list_all()}
    for n in range(5):
        for i in range(20):
            assert f"t{n}.key{i}" in all_keys
