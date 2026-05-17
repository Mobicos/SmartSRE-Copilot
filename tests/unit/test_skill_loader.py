"""Unit tests for SkillLoader (skill runtime integration)."""

from __future__ import annotations

from typing import Any

from app.agent_runtime.skill_catalog import SkillCatalog
from app.agent_runtime.skill_loader import SkillLoader


class _FakeSkillStore:
    def __init__(self, skills: list[dict[str, Any]] | None = None) -> None:
        self._skills = skills or []

    def list_active_skills(self) -> list[dict[str, Any]]:
        return self._skills


def test_load_all_builtin_skills():
    loader = SkillLoader(catalog=SkillCatalog())
    loaded = loader.load_all()
    assert len(loaded) == 7
    assert "sre-cpu-high" in loaded


def test_load_all_with_custom_store():
    custom = [
        {
            "skill_id": "custom-x",
            "name": "Custom X",
            "trigger_conditions": {"keywords": ["x"], "scene_patterns": []},
            "diagnostic_steps": [{"step": 1, "action": "x"}],
            "recommended_tools": ["XTool"],
            "evidence_requirements": ["x_data"],
            "risk_warnings": ["none"],
            "report_template": "Report: {goal}",
        }
    ]
    store = _FakeSkillStore(custom)
    loader = SkillLoader(catalog=SkillCatalog(), skill_store=store)
    loaded = loader.load_all()
    assert len(loaded) == 8
    assert "custom-x" in loaded


def test_get_for_scene():
    loader = SkillLoader(catalog=SkillCatalog())
    loader.load_all()
    matched = loader.get_for_scene(scene={}, goal="CPU 高负载")
    assert any(s.skill_id == "sre-cpu-high" for s in matched)


def test_get_by_id():
    loader = SkillLoader(catalog=SkillCatalog())
    loader.load_all()
    skill = loader.get("sre-cpu-high")
    assert skill is not None
    assert skill.name == "CPU High Diagnosis"


def test_get_nonexistent():
    loader = SkillLoader(catalog=SkillCatalog())
    loader.load_all()
    assert loader.get("nonexistent") is None


def test_loaded_count():
    loader = SkillLoader(catalog=SkillCatalog())
    assert loader.loaded_count == 0
    loader.load_all()
    assert loader.loaded_count == 7


def test_store_error_graceful():
    class _BrokenStore:
        def list_active_skills(self) -> list[dict[str, Any]]:
            raise RuntimeError("db down")

    loader = SkillLoader(catalog=SkillCatalog(), skill_store=_BrokenStore())
    loaded = loader.load_all()
    assert len(loaded) == 7  # built-in still loaded
