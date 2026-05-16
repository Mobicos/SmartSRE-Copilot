"""Integration test: collaborative intervention full flow (T060)."""

from __future__ import annotations

from typing import Any

from app.agent_runtime.decision import (
    AgentDecision,
    AgentDecisionState,
    AgentGoalContract,
    EvidenceAssessment,
)
from app.agent_runtime.intervention import (
    Intervention,
    InterventionBridge,
    InterventionType,
)
from app.agent_runtime.loop import BoundedReActLoop, LoopBudget

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _state(
    goal: str = "diagnose OOM",
    run_id: str = "run-iv-1",
    ws: str = "ws-1",
) -> AgentDecisionState:
    return AgentDecisionState(
        run_id=run_id,
        goal=AgentGoalContract(goal=goal, workspace_id=ws),
    )


class _CallToolProvider:
    """Provider that always returns call_tool with configurable confidence."""

    provider_name = "test"

    def __init__(self, confidence: float = 0.8, tool: str = "check_memory"):
        self._confidence = confidence
        self._tool = tool
        self.seen_states: list[AgentDecisionState] = []

    def decide(self, state: AgentDecisionState) -> AgentDecision:
        self.seen_states.append(state)
        return AgentDecision(
            action_type="call_tool",
            selected_tool=self._tool,
            reasoning_summary="checking",
            evidence=EvidenceAssessment(quality="weak"),
            confidence=self._confidence,
        )


class _LowConfidenceProvider:
    """Provider whose confidence drops over time then recovers."""

    provider_name = "test"

    def __init__(self) -> None:
        self._call = 0

    def decide(self, state: AgentDecisionState) -> AgentDecision:
        self._call += 1
        # Steps 1-3: low confidence; step 4+: terminal
        if self._call <= 3:
            conf = 0.1
        else:
            return AgentDecision(
                action_type="final_report",
                selected_tool=None,
                reasoning_summary="recovered",
                evidence=EvidenceAssessment(quality="strong"),
                confidence=0.9,
            )
        return AgentDecision(
            action_type="call_tool",
            selected_tool="check",
            reasoning_summary="low confidence check",
            evidence=EvidenceAssessment(quality="weak"),
            confidence=conf,
        )


def _noop_executor(decision: AgentDecision) -> dict[str, Any]:
    return {"status": "ok", "data": f"tool result from {decision.selected_tool}"}


# ---------------------------------------------------------------------------
# Full intervention flow integration tests
# ---------------------------------------------------------------------------


class TestInterventionFullFlow:
    def test_inject_evidence_mid_execution(self):
        """
        Start run → inject evidence mid-execution → verify next decision sees it.
        """
        bridge = InterventionBridge()
        provider = _CallToolProvider()

        loop = BoundedReActLoop(
            provider=provider,
            intervention_bridge=bridge,
            tool_executor=_noop_executor,
        )

        # Inject evidence before the loop starts (simulating mid-flight injection)
        bridge.add(
            Intervention(
                intervention_id="iv-1",
                run_id="run-iv-1",
                intervention_type=InterventionType.INJECT_EVIDENCE,
                payload={"content": "数据库连接池耗尽，最大连接数=200", "source": "operator"},
            )
        )

        loop.run(
            _state(),
            LoopBudget(max_steps=2, max_time_seconds=30),
        )

        # Provider should have seen the injected observation
        assert len(provider.seen_states) >= 1
        obs_summaries = [o.summary for o in provider.seen_states[0].observations]
        assert any("数据库连接池耗尽" in s for s in obs_summaries)

    def test_replace_tool_call_mid_execution(self):
        """
        Provider chooses tool A → intervention replaces with tool B → tool B is executed.
        """
        bridge = InterventionBridge()
        bridge.add(
            Intervention(
                intervention_id="iv-replace",
                run_id="run-iv-2",
                intervention_type=InterventionType.REPLACE_TOOL_CALL,
                payload={"selected_tool": "query_database", "reasoning_summary": "human override"},
            )
        )

        provider = _CallToolProvider(tool="wrong_tool")
        loop = BoundedReActLoop(
            provider=provider,
            intervention_bridge=bridge,
            tool_executor=_noop_executor,
        )
        result = loop.run(
            _state(run_id="run-iv-2"),
            LoopBudget(max_steps=2, max_time_seconds=30),
        )
        # First step's decision should be replaced
        assert result.steps[0].decision.selected_tool == "query_database"
        assert result.steps[0].decision.reasoning_summary == "human override"

    def test_modify_goal_mid_execution(self):
        """
        Inject goal modification → provider sees updated goal in next decision.
        """
        bridge = InterventionBridge()
        bridge.add(
            Intervention(
                intervention_id="iv-goal",
                run_id="run-iv-3",
                intervention_type=InterventionType.MODIFY_GOAL,
                payload={"goal": "investigate memory leak in worker pool"},
            )
        )

        provider = _CallToolProvider()
        loop = BoundedReActLoop(
            provider=provider,
            intervention_bridge=bridge,
            tool_executor=_noop_executor,
        )
        loop.run(
            _state(goal="original goal", run_id="run-iv-3"),
            LoopBudget(max_steps=1, max_time_seconds=30),
        )
        assert provider.seen_states[0].goal.goal == "investigate memory leak in worker pool"

    def test_low_confidence_auto_handoff(self):
        """
        3 consecutive steps with confidence < 0.3 → auto-handoff triggered.
        """
        loop = BoundedReActLoop(
            provider=_LowConfidenceProvider(),
            max_low_confidence_steps=3,
            low_confidence_threshold=0.3,
        )
        result = loop.run(
            _state(run_id="run-handoff"),
            LoopBudget(max_steps=5, max_time_seconds=60),
        )
        assert result.termination_reason == "low_confidence_handoff"
        assert len(result.steps) == 3

    def test_combined_inject_then_replace(self):
        """
        Both inject_evidence and replace_tool_call in same run → both applied.
        """
        bridge = InterventionBridge()
        bridge.add(
            Intervention(
                intervention_id="iv-obs",
                run_id="run-iv-combo",
                intervention_type=InterventionType.INJECT_EVIDENCE,
                payload={"content": "日志显示 connection timeout", "source": "operator"},
            )
        )
        bridge.add(
            Intervention(
                intervention_id="iv-tool",
                run_id="run-iv-combo",
                intervention_type=InterventionType.REPLACE_TOOL_CALL,
                payload={"selected_tool": "query_logs", "reasoning_summary": "check logs first"},
            )
        )

        provider = _CallToolProvider(tool="original_tool")
        loop = BoundedReActLoop(
            provider=provider,
            intervention_bridge=bridge,
            tool_executor=_noop_executor,
        )
        result = loop.run(
            _state(run_id="run-iv-combo"),
            LoopBudget(max_steps=2, max_time_seconds=30),
        )
        # Observation injected
        obs_summaries = [o.summary for o in provider.seen_states[0].observations]
        assert any("connection timeout" in s for s in obs_summaries)
        # Tool replaced
        assert result.steps[0].decision.selected_tool == "query_logs"
