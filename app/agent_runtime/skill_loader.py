"""Skill loader — load and cache active skill manifests at runtime startup."""

from __future__ import annotations

from typing import Any

from app.agent_runtime.knowledge_types import SkillManifest
from app.agent_runtime.skill_catalog import SkillCatalog


class SkillLoader:
    """Load and cache active skill manifests from catalog and database.

    Usage::

        loader = SkillLoader(catalog=SkillCatalog())
        loader.load_all()
        matched = loader.get_for_scene(scene={"name": "cpu_alert"}, goal="CPU high")
    """

    def __init__(
        self,
        *,
        catalog: SkillCatalog,
        skill_store: Any | None = None,
    ) -> None:
        self._catalog = catalog
        self._skill_store = skill_store
        self._cache: dict[str, SkillManifest] = {}

    def load_all(self) -> dict[str, SkillManifest]:
        """Load all available skills into the in-memory cache.

        Combines built-in catalog skills with any custom skills from the store.
        """
        self._cache.clear()

        # Load from built-in catalog
        for skill in self._catalog.all_skills:
            self._cache[skill.skill_id] = skill

        # Load from database store if available
        if self._skill_store is not None:
            try:
                db_skills = self._skill_store.list_active_skills()
                for raw in db_skills:
                    try:
                        manifest = SkillManifest(
                            skill_id=raw["skill_id"],
                            name=raw["name"],
                            description=raw.get("description", ""),
                            trigger_conditions=raw.get("trigger_conditions", {}),
                            diagnostic_steps=raw.get("diagnostic_steps", []),
                            recommended_tools=raw.get("recommended_tools", []),
                            evidence_requirements=raw.get("evidence_requirements", []),
                            risk_warnings=raw.get("risk_warnings", []),
                            report_template=raw.get("report_template", ""),
                            version=raw.get("version", "1.0.0"),
                        )
                        self._cache[manifest.skill_id] = manifest
                    except (KeyError, TypeError):
                        pass
            except Exception:
                pass

        return dict(self._cache)

    def get_for_scene(self, scene: dict[str, Any], goal: str) -> list[SkillManifest]:
        """Match skills for a given scene and goal from the loaded cache."""
        return self._catalog.match(scene=scene, goal=goal)

    def get(self, skill_id: str) -> SkillManifest | None:
        return self._cache.get(skill_id)

    @property
    def loaded_count(self) -> int:
        return len(self._cache)
