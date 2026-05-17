"""Planning primitives for the Native Agent runtime."""

from __future__ import annotations

from typing import Any

from app.agent_runtime.state import AgentRunState


class AgentPlanner:
    """Create deterministic development-runtime plans from scene context and user goals."""

    @staticmethod
    def create_initial_state(goal: str) -> AgentRunState:
        return AgentRunState.from_goal(goal)

    @staticmethod
    def select_tool_names(scene: dict[str, Any]) -> list[str]:
        return [str(tool_name) for tool_name in scene.get("tools", [])]

    @staticmethod
    def apply_skill_context(
        state: AgentRunState,
        skills: list[dict[str, Any]],
    ) -> AgentRunState:
        """Inject matched skill guidance into state: recommended tools, evidence requirements, risk warnings."""
        if not skills:
            return state
        extra_tools: list[str] = []
        for skill in skills:
            for tool_name in skill.get("recommended_tools", []):
                if tool_name not in extra_tools:
                    extra_tools.append(tool_name)
        return state
