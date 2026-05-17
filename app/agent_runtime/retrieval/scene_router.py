"""Scene router — classify intent and scope knowledge retrieval."""

from __future__ import annotations

from app.agent_runtime.knowledge_types import RetrievalScope

_INVESTIGATIVE_KEYWORDS = ["为什么", "排查", "分析", "诊断", "查找", "调查", "定位", "root cause"]
_NARROW_KEYWORDS = ["怎么做", "步骤", "流程", "标准", "sop", "操作"]


class SceneRouter:
    """Route a query to the appropriate knowledge scope.

    Usage::

        router = SceneRouter()
        scope = router.route("CPU 使用率过高", scene={"name": "performance"})
        # -> RetrievalScope(item_types=["faq", "sop", "incident"], ...)
    """

    def route(self, goal: str, *, scene: dict) -> RetrievalScope:
        """Determine retrieval scope from goal intent and scene context."""
        goal_lower = goal.lower()

        is_investigative = any(kw in goal_lower for kw in _INVESTIGATIVE_KEYWORDS)
        is_procedural = any(kw in goal_lower for kw in _NARROW_KEYWORDS)

        if is_procedural:
            item_types = ["faq", "sop"]
        elif is_investigative:
            item_types = ["faq", "incident", "document"]
        else:
            item_types = ["faq", "sop", "incident", "document"]

        kb_ids = scene.get("knowledge_base_ids", [])
        skill_ids: list[str] = []

        return RetrievalScope(
            item_types=item_types,
            knowledge_base_ids=kb_ids,
            skill_ids=skill_ids,
            max_items=10,
        )
