"""Config and Skills API routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Any

router = APIRouter(prefix="/api/config", tags=["config"])
skills_router = APIRouter(prefix="/api/skills", tags=["skills"])


class ConfigUpdateRequest(BaseModel):
    value: Any
    category: str = ""
    description: str = ""


class SkillCreateRequest(BaseModel):
    name: str
    description: str = ""
    system_prompt: str = ""
    mcp_tools: list[str] = []
    workflow_steps: list[dict[str, Any]] = []
    tags: list[str] = []
    visibility: dict[str, list[str]] = {}


class SkillUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    system_prompt: str | None = None
    mcp_tools: list[str] | None = None
    workflow_steps: list[dict[str, Any]] | None = None
    tags: list[str] | None = None
    visibility: dict[str, list[str]] | None = None
    enabled: bool | None = None


def _get_config_store():
    from KubeAI.dashboard.deps import get_runtime
    return get_runtime().config_store


def _get_skill_registry():
    from KubeAI.dashboard.deps import get_runtime
    return get_runtime().skill_registry


# ── Config routes ───────────────────────────────────────────────────────

@router.get("")
def list_config():
    store = _get_config_store()
    return store.grouped()


@router.get("/{key:path}")
def get_config(key: str):
    store = _get_config_store()
    value = store.get(key)
    if value is None:
        raise HTTPException(status_code=404, detail=f"Config key {key!r} not found")
    return {"key": key, "value": value}


@router.put("/{key:path}")
def set_config(key: str, body: ConfigUpdateRequest):
    store = _get_config_store()
    store.set(key, body.value, category=body.category,
              description=body.description, updated_by="dashboard")
    return {"key": key, "value": body.value, "status": "updated"}


@router.delete("/{key:path}")
def delete_config(key: str):
    store = _get_config_store()
    deleted = store.delete(key)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Config key {key!r} not found")
    return {"key": key, "status": "deleted"}


# ── Skills routes ───────────────────────────────────────────────────────

@skills_router.get("")
def list_skills():
    reg = _get_skill_registry()
    return [s.to_dict() for s in reg.list_skills()]


@skills_router.post("")
def create_skill(body: SkillCreateRequest):
    reg = _get_skill_registry()
    skill = reg.create(
        name=body.name,
        description=body.description,
        system_prompt=body.system_prompt,
        mcp_tools=body.mcp_tools,
        workflow_steps=body.workflow_steps,
        tags=body.tags,
        visibility=body.visibility,
    )
    return skill.to_dict()


@skills_router.get("/{skill_id}")
def get_skill(skill_id: str):
    reg = _get_skill_registry()
    try:
        return reg.get(skill_id).to_dict()
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Skill {skill_id!r} not found")


@skills_router.put("/{skill_id}")
def update_skill(skill_id: str, body: SkillUpdateRequest):
    reg = _get_skill_registry()
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    try:
        skill = reg.update(skill_id, **updates)
        return skill.to_dict()
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Skill {skill_id!r} not found")


@skills_router.delete("/{skill_id}")
def delete_skill(skill_id: str):
    reg = _get_skill_registry()
    if not reg.delete(skill_id):
        raise HTTPException(status_code=404, detail=f"Skill {skill_id!r} not found")
    return {"skill_id": skill_id, "status": "deleted"}
