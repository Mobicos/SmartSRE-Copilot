"""Unit tests for app.agent_runtime.loop — dataclasses and helpers."""

from __future__ import annotations

from app.agent_runtime.decision import (
    AgentDecision,
    AgentDecisionState,
    AgentGoalContract,
)
from app.agent_runtime.loop import (
    LoopBudget,
    LoopResult,
    LoopStep,
)

# ---------------------------------------------------------------------------
# LoopBudget
# ---------------------------------------------------------------------------


class TestLoopBudget:
    def test_defaults(self):
        b = LoopBudget()
        assert b.max_steps == 5
        assert b.max_time_seconds == 120.0
        assert b.max_tokens is None

    def test_normalize_clamps_values(self):
        b = LoopBudget(max_steps=0, max_time_seconds=-1.0, max_tokens=-5)
        n = b.normalize()
        assert n.max_steps == 1
        assert n.max_time_seconds == 0.001
        assert n.max_tokens == 0

    def test_normalize_preserves_valid(self):
        b = LoopBudget(max_steps=10, max_time_seconds=60.0, max_tokens=1000)
        n = b.normalize()
        assert n == b

    def test_normalize_none_tokens(self):
        b = LoopBudget(max_tokens=None)
        n = b.normalize()
        assert n.max_tokens is None


# ---------------------------------------------------------------------------
# LoopStep
# ---------------------------------------------------------------------------


class TestLoopStep:
    def test_metrics(self):
        decision = AgentDecision(
            action_type="call_tool",
            reasoning_summary="test",
        )
        step = LoopStep(
            step_index=0,
            decision=decision,
            token_usage=100,
            token_usage_detail={"prompt": 50, "completion": 50},
            cost_estimate={"total": 0.01},
        )
        m = step.metrics
        assert m["step_index"] == 0
        assert m["token_usage"] == {"prompt": 50, "completion": 50}
        assert m["cost_estimate"] == {"total": 0.01}


# ---------------------------------------------------------------------------
# LoopResult
# ---------------------------------------------------------------------------


class TestLoopResult:
    def test_step_count_empty(self):
        r = LoopResult(
            state=AgentDecisionState(goal=AgentGoalContract(goal="test")),
        )
        assert r.step_count == 0
        assert r.step_metrics == []

    def test_step_count_with_steps(self):
        decision = AgentDecision(
            action_type="call_tool",
            reasoning_summary="test",
        )
        steps = [
            LoopStep(step_index=0, decision=decision, token_usage=10),
            LoopStep(step_index=1, decision=decision, token_usage=20),
        ]
        r = LoopResult(
            state=AgentDecisionState(goal=AgentGoalContract(goal="test")),
            steps=steps,
        )
        assert r.step_count == 2
        metrics = r.step_metrics
        assert len(metrics) == 2
        assert metrics[0]["step_index"] == 0
        assert metrics[1]["step_index"] == 1

    def test_defaults(self):
        r = LoopResult(
            state=AgentDecisionState(goal=AgentGoalContract(goal="test")),
        )
        assert r.status == "running"
        assert r.termination_reason == "not_terminated"
        assert r.token_usage == 0
        assert r.evidence_items == []
