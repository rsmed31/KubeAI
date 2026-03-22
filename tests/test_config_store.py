"""Tests for ConfigStore and SkillRegistry."""

from KubeAI.config.store import ConfigStore, ConfigEntry
from KubeAI.config.skill import Skill, SkillRegistry


def test_config_store_defaults():
    store = ConfigStore()
    assert store.get("rag.default_template") == "basic"
    assert store.get("rag.embedding_provider") == "fastembed"
    assert store.get("orchestrator.min_confidence") == 0.3


def test_config_store_set_get():
    store = ConfigStore()
    store.set("test.key", "test_value", category="general")
    assert store.get("test.key") == "test_value"


def test_config_store_delete():
    store = ConfigStore()
    store.set("temp.key", 42, category="general")
    assert store.get("temp.key") == 42
    assert store.delete("temp.key") is True
    assert store.get("temp.key") is None


def test_config_store_missing_key():
    store = ConfigStore()
    assert store.get("nonexistent") is None
    assert store.get("nonexistent", "fallback") == "fallback"


def test_config_store_change_callback():
    store = ConfigStore()
    changes = []
    store.on_change(lambda k, old, new: changes.append((k, old, new)))
    store.set("test.cb", "v1", category="general")
    store.set("test.cb", "v2", category="general")
    assert len(changes) == 2
    assert changes[0] == ("test.cb", None, "v1")
    assert changes[1] == ("test.cb", "v1", "v2")


def test_config_store_no_callback_on_same_value():
    store = ConfigStore()
    changes = []
    store.on_change(lambda k, old, new: changes.append((k, old, new)))
    store.set("test.same", "val", category="general")
    store.set("test.same", "val", category="general")
    assert len(changes) == 1  # Only first set fires callback


def test_config_store_grouped():
    store = ConfigStore()
    grouped = store.grouped()
    assert "rag" in grouped
    assert "orchestrator" in grouped


def test_config_store_list_by_category():
    store = ConfigStore()
    rag_configs = store.list_by_category("rag")
    assert len(rag_configs) > 0
    assert all(e.category == "rag" for e in rag_configs)


def test_skill_registry_create():
    reg = SkillRegistry()
    skill = reg.create(name="test_skill", system_prompt="Be helpful")
    assert skill.name == "test_skill"
    assert skill.system_prompt == "Be helpful"
    assert skill.enabled is True


def test_skill_registry_get():
    reg = SkillRegistry()
    skill = reg.create(name="sk1", system_prompt="prompt")
    retrieved = reg.get(skill.skill_id)
    assert retrieved.name == "sk1"


def test_skill_registry_update():
    reg = SkillRegistry()
    skill = reg.create(name="sk2", system_prompt="old")
    updated = reg.update(skill.skill_id, system_prompt="new", tags=["code"])
    assert updated.system_prompt == "new"
    assert updated.tags == ["code"]


def test_skill_registry_delete():
    reg = SkillRegistry()
    skill = reg.create(name="sk3")
    assert reg.delete(skill.skill_id) is True
    assert reg.delete(skill.skill_id) is False  # Already deleted


def test_skill_registry_list():
    reg = SkillRegistry()
    reg.create(name="a")
    reg.create(name="b")
    assert len(reg.list_skills()) == 2


def test_skill_registry_enabled():
    reg = SkillRegistry()
    s1 = reg.create(name="enabled_skill")
    s2 = reg.create(name="disabled_skill")
    reg.update(s2.skill_id, enabled=False)
    enabled = reg.list_enabled()
    assert len(enabled) == 1
    assert enabled[0].skill_id == s1.skill_id


def test_skill_visibility():
    reg = SkillRegistry()
    s1 = reg.create(name="code_review", visibility={"coding_agent": ["review"]})
    s2 = reg.create(name="general_help")  # No visibility = visible to all

    coding_skills = reg.skills_for_blueprint("coding_agent")
    assert len(coding_skills) == 2  # Both visible to coding_agent

    research_skills = reg.skills_for_blueprint("research_agent")
    assert len(research_skills) == 1  # Only general_help (no restriction)


def test_skill_to_dict():
    reg = SkillRegistry()
    skill = reg.create(name="test", system_prompt="p", tags=["a"])
    d = skill.to_dict()
    assert d["name"] == "test"
    assert d["system_prompt"] == "p"
    assert d["tags"] == ["a"]
