"""Skill model and registry — MCP tools + system prompts + workflow templates."""

from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class Skill:
    """A named, reusable skill combining tools, prompts, and workflow steps."""
    skill_id: str
    name: str
    description: str = ""
    system_prompt: str = ""
    mcp_tools: list[str] = field(default_factory=list)
    workflow_steps: list[dict[str, Any]] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    visibility: dict[str, list[str]] = field(default_factory=dict)
    enabled: bool = True
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "skill_id": self.skill_id,
            "name": self.name,
            "description": self.description,
            "system_prompt": self.system_prompt,
            "mcp_tools": self.mcp_tools,
            "workflow_steps": self.workflow_steps,
            "tags": self.tags,
            "visibility": self.visibility,
            "enabled": self.enabled,
        }


class SkillRegistry:
    """CRUD registry for skills, backed by PostgreSQL when available."""

    def __init__(self, dsn: str = "") -> None:
        self._dsn = dsn
        self._skills: dict[str, Skill] = {}
        self._lock = threading.RLock()

        if self._dsn:
            try:
                self._sync_from_db()
            except Exception as exc:
                logger.warning("Could not load skills from DB: %s", exc)

    def create(self, name: str, system_prompt: str = "",
               description: str = "", mcp_tools: list[str] | None = None,
               workflow_steps: list[dict] | None = None,
               tags: list[str] | None = None,
               visibility: dict[str, list[str]] | None = None) -> Skill:
        """Create and register a new skill."""
        skill = Skill(
            skill_id=str(uuid.uuid4())[:8],
            name=name,
            description=description,
            system_prompt=system_prompt,
            mcp_tools=mcp_tools or [],
            workflow_steps=workflow_steps or [],
            tags=tags or [],
            visibility=visibility or {},
        )
        with self._lock:
            self._skills[skill.skill_id] = skill

        if self._dsn:
            try:
                self._persist_skill(skill)
            except Exception as exc:
                logger.warning("Failed to persist skill %s: %s", skill.skill_id, exc)

        return skill

    def get(self, skill_id: str) -> Skill:
        """Get a skill by ID."""
        with self._lock:
            if skill_id not in self._skills:
                raise KeyError(f"Skill {skill_id!r} not found")
            return self._skills[skill_id]

    def update(self, skill_id: str, **kwargs: Any) -> Skill:
        """Update a skill's fields."""
        with self._lock:
            skill = self._skills.get(skill_id)
            if skill is None:
                raise KeyError(f"Skill {skill_id!r} not found")

            for key, value in kwargs.items():
                if hasattr(skill, key) and key != "skill_id":
                    setattr(skill, key, value)
            skill.updated_at = time.time()

        if self._dsn:
            try:
                self._persist_skill(skill)
            except Exception as exc:
                logger.warning("Failed to update skill %s in DB: %s", skill_id, exc)

        return skill

    def delete(self, skill_id: str) -> bool:
        """Delete a skill. Returns True if existed."""
        with self._lock:
            skill = self._skills.pop(skill_id, None)

        if skill is not None and self._dsn:
            try:
                self._delete_from_db(skill_id)
            except Exception as exc:
                logger.warning("Failed to delete skill %s from DB: %s", skill_id, exc)

        return skill is not None

    def list_skills(self) -> list[Skill]:
        """Return all skills."""
        with self._lock:
            return list(self._skills.values())

    def list_enabled(self) -> list[Skill]:
        """Return only enabled skills."""
        with self._lock:
            return [s for s in self._skills.values() if s.enabled]

    def skills_for_blueprint(self, blueprint_name: str) -> list[Skill]:
        """Return skills visible to a specific blueprint."""
        with self._lock:
            result = []
            for skill in self._skills.values():
                if not skill.enabled:
                    continue
                if not skill.visibility:
                    result.append(skill)  # No visibility restriction = visible to all
                elif blueprint_name in skill.visibility:
                    result.append(skill)
            return result

    def _get_connection(self):
        import psycopg2
        return psycopg2.connect(self._dsn)

    def _sync_from_db(self) -> None:
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT skill_id, name, description, system_prompt, "
                           "mcp_tools, workflow_steps, tags, visibility, enabled FROM skills")
                rows = cur.fetchall()
        finally:
            conn.close()

        with self._lock:
            for row in rows:
                sid, name, desc, prompt, tools, steps, tags, vis, enabled = row
                self._skills[sid] = Skill(
                    skill_id=sid, name=name, description=desc or "",
                    system_prompt=prompt or "",
                    mcp_tools=json.loads(tools) if isinstance(tools, str) else (tools or []),
                    workflow_steps=json.loads(steps) if isinstance(steps, str) else (steps or []),
                    tags=tags or [],
                    visibility=json.loads(vis) if isinstance(vis, str) else (vis or {}),
                    enabled=enabled,
                )

    def _persist_skill(self, skill: Skill) -> None:
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO skills (skill_id, name, description, system_prompt,
                       mcp_tools, workflow_steps, tags, visibility, enabled, updated_at)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                       ON CONFLICT (skill_id) DO UPDATE SET
                       name=EXCLUDED.name, description=EXCLUDED.description,
                       system_prompt=EXCLUDED.system_prompt, mcp_tools=EXCLUDED.mcp_tools,
                       workflow_steps=EXCLUDED.workflow_steps, tags=EXCLUDED.tags,
                       visibility=EXCLUDED.visibility, enabled=EXCLUDED.enabled,
                       updated_at=NOW()""",
                    (skill.skill_id, skill.name, skill.description, skill.system_prompt,
                     json.dumps(skill.mcp_tools), json.dumps(skill.workflow_steps),
                     skill.tags, json.dumps(skill.visibility), skill.enabled),
                )
            conn.commit()
        finally:
            conn.close()

    def _delete_from_db(self, skill_id: str) -> None:
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM skills WHERE skill_id = %s", (skill_id,))
            conn.commit()
        finally:
            conn.close()

    def __repr__(self) -> str:
        with self._lock:
            return f"SkillRegistry(skills={len(self._skills)})"
