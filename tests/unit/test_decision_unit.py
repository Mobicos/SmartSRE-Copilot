"""Unit tests for app.agent_runtime.decision — Pydantic models, helpers, and providers."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.agent_runtime.decision import (
    AgentDecision,
    AgentDecisionRuntime,
    AgentDecisionState,
    AgentGoalContract,
    AgentHypothesis,
    AgentObservation,
    DecisionProviderFactory,
    DeterministicDecisionProvider,
    EvidenceAssessment,
    FinalReportContract,
    QwenDecisionProvider,
    RecoveryDecision,
    RuntimeBudget,
    StopCondition,
    SuccessCriteria,
    _best_evidence,
    _extract_response_token_usage,
    _parse_strict_json,
    _qwen_decision_prompt,
    _route_decision,
    _usage_int,
    build_initial_decision_state,
)

# ---------------------------------------------------------------------------
# Pydantic models — construction & validation
# ---------------------------------------------------------------------------


class TestSuccessCriteria:
    def test_basic(self):
        c = SuccessCriteria(description="must produce report")
        assert c.description == "must produce report"
        assert c.required is True

    def test_empty_description_rejected(self):
        with pytest.raises(ValueError):
            SuccessCriteria(description="")


class TestStopCondition:
    def test_defaults(self):
        sc = StopCondition()
        assert sc.max_steps == 5
        assert sc.max_minutes == 2.0
        assert sc.confidence_threshold == 0.75

    def test_custom(self):
        sc = StopCondition(max_steps=10, max_minutes=5.0, confidence_threshold=0.9)
        assert sc.max_steps == 10


class TestAgentObservation:
    def test_basic(self):
        obs = AgentObservation(source="tool", summary="CPU 95%")
        assert obs.source == "tool"
        assert obs.confidence == 0.0
        assert obs.citations == []


class TestAgentHypothesis:
    def test_basic(self):
        h = AgentHypothesis(hypothesis_id="h1", summary="OOM suspected")
        assert h.priority == 1
        assert h.confidence == 0.0


class TestRuntimeBudget:
    def test_exhausted_when_steps_zero(self):
        b = RuntimeBudget(remaining_steps=0)
        assert b.exhausted is True

    def test_exhausted_when_tool_calls_zero(self):
        b = RuntimeBudget(remaining_tool_calls=0)
        assert b.exhausted is True

    def test_not_exhausted(self):
        b = RuntimeBudget(remaining_steps=5, remaining_tool_calls=5)
        assert b.exhausted is False


class TestAgentDecision:
    def test_basic_construction(self):
        d = AgentDecision(
            action_type="call_tool",
            reasoning_summary="check logs",
            selected_tool="SearchLog",
        )
        assert d.action_type == "call_tool"
        assert d.selected_tool == "SearchLog"

    def test_reject_private_reasoning(self):
        with pytest.raises(ValueError, match="private reasoning"):
            AgentDecision(
                action_type="call_tool",
                reasoning_summary="My chain-of-thought says...",
            )

    def test_normalize_actual_evidence(self):
        d = AgentDecision(
            action_type="observe",
            reasoning_summary="looking",
            evidence=EvidenceAssessment(quality="strong", confidence=0.9),
        )
        assert d.actual_evidence is d.evidence

    def test_normalize_selected_action(self):
        d = AgentDecision(
            action_type="call_tool",
            reasoning_summary="test",
        )
        assert d.selected_action == "call_tool"

    def test_normalize_decision_status(self):
        d = AgentDecision(
            action_type="recover",
            reasoning_summary="retry",
        )
        assert d.decision_status == "recover"

    def test_handoff_reason_from_recovery(self):
        d = AgentDecision(
            action_type="handoff",
            reasoning_summary="handoff needed",
            recovery=RecoveryDecision(required=True, reason="budget_exhausted"),
        )
        assert d.handoff_reason == "budget_exhausted"

    def test_to_event_payload(self):
        d = AgentDecision(
            action_type="observe",
            reasoning_summary="checking",
        )
        payload = d.to_event_payload()
        assert isinstance(payload, dict)
        assert payload["action_type"] == "observe"


class TestAgentDecisionState:
    def test_with_decision_call_tool(self):
        state = AgentDecisionState(
            goal=AgentGoalContract(goal="diagnose OOM"),
        )
        decision = AgentDecision(
            action_type="call_tool",
            reasoning_summary="call SearchLog",
        )
        new_state = state.with_decision(decision)
        assert new_state.status == "running"
        assert len(new_state.decisions) == 1

    def test_with_decision_ask_approval(self):
        state = AgentDecisionState(
            goal=AgentGoalContract(goal="fix"),
        )
        decision = AgentDecision(
            action_type="ask_approval",
            reasoning_summary="needs approval",
        )
        new_state = state.with_decision(decision)
        assert new_state.status == "waiting_approval"

    def test_with_decision_final_report(self):
        state = AgentDecisionState(
            goal=AgentGoalContract(goal="done"),
        )
        decision = AgentDecision(
            action_type="final_report",
            reasoning_summary="reporting",
        )
        new_state = state.with_decision(decision)
        assert new_state.status == "completed"

    def test_with_decision_handoff(self):
        state = AgentDecisionState(
            goal=AgentGoalContract(goal="handoff"),
        )
        decision = AgentDecision(
            action_type="handoff",
            reasoning_summary="need human",
        )
        new_state = state.with_decision(decision)
        assert new_state.status == "handoff_required"


# ---------------------------------------------------------------------------
# DeterministicDecisionProvider
# ---------------------------------------------------------------------------


class TestDeterministicDecisionProvider:
    def _make_state(self, **overrides):
        defaults = {
            "goal": AgentGoalContract(goal="diagnose"),
            "budget": RuntimeBudget(remaining_steps=5, remaining_tool_calls=5),
            "available_tools": ["SearchLog", "CheckCPU"],
            "executed_tools": [],
            "evidence": [],
            "consecutive_empty_evidence": 0,
        }
        defaults.update(overrides)
        return AgentDecisionState(**defaults)

    def test_budget_exhausted_handoff(self):
        state = self._make_state(
            budget=RuntimeBudget(remaining_steps=0, remaining_tool_calls=0),
        )
        provider = DeterministicDecisionProvider()
        d = provider.decide(state)
        assert d.action_type == "handoff"
        assert d.recovery.required is True

    def test_strong_evidence_final_report(self):
        state = self._make_state(
            evidence=[
                EvidenceAssessment(quality="strong", confidence=0.9, summary="OOM confirmed"),
            ],
        )
        provider = DeterministicDecisionProvider()
        d = provider.decide(state)
        assert d.action_type == "final_report"
        assert d.confidence >= 0.8

    def test_consecutive_empty_evidence_recover(self):
        state = self._make_state(consecutive_empty_evidence=2)
        provider = DeterministicDecisionProvider()
        d = provider.decide(state)
        assert d.action_type == "recover"
        assert d.recovery.reason == "empty_evidence"

    def test_remaining_tools_call_tool(self):
        state = self._make_state(
            available_tools=["SearchLog", "CheckCPU"],
            executed_tools=[],
        )
        provider = DeterministicDecisionProvider()
        d = provider.decide(state)
        assert d.action_type == "call_tool"
        assert d.selected_tool == "SearchLog"

    def test_no_remaining_tools_handoff(self):
        state = self._make_state(
            available_tools=["SearchLog"],
            executed_tools=["SearchLog"],
        )
        provider = DeterministicDecisionProvider()
        d = provider.decide(state)
        assert d.action_type == "handoff"
        assert d.recovery.reason == "no_available_tools"

    def test_token_usage_zero(self):
        provider = DeterministicDecisionProvider()
        usage = provider.get_token_usage()
        assert usage["total"] == 0

    def test_cost_estimate_zero(self):
        provider = DeterministicDecisionProvider()
        cost = provider.get_cost_estimate()
        assert cost["total_cost"] == 0.0


# ---------------------------------------------------------------------------
# QwenDecisionProvider
# ---------------------------------------------------------------------------


class TestQwenDecisionProvider:
    def _make_state(self, **overrides):
        defaults = {
            "goal": AgentGoalContract(goal="test"),
            "budget": RuntimeBudget(),
            "available_tools": ["SearchLog"],
            "executed_tools": [],
            "evidence": [],
        }
        defaults.update(overrides)
        return AgentDecisionState(**defaults)

    def test_valid_json_decision(self):
        decision_payload = {
            "action_type": "call_tool",
            "reasoning_summary": "search logs",
            "selected_tool": "SearchLog",
            "tool_arguments": {"query": "test"},
            "confidence": 0.8,
        }
        mock_invoke = MagicMock(return_value=json.dumps(decision_payload))
        provider = QwenDecisionProvider(mock_invoke)
        state = self._make_state()
        d = provider.decide(state)
        assert d.action_type == "call_tool"
        assert d.selected_tool == "SearchLog"

    def test_invalid_json_returns_recover(self):
        mock_invoke = MagicMock(return_value="not valid json {{{")
        provider = QwenDecisionProvider(mock_invoke)
        state = self._make_state()
        d = provider.decide(state)
        assert d.action_type == "recover"
        assert d.recovery.reason == "invalid_model_output"

    def test_unknown_tool_returns_recover(self):
        decision_payload = {
            "action_type": "call_tool",
            "reasoning_summary": "use unknown",
            "selected_tool": "UnknownTool",
            "confidence": 0.8,
        }
        mock_invoke = MagicMock(return_value=json.dumps(decision_payload))
        provider = QwenDecisionProvider(mock_invoke)
        state = self._make_state()
        d = provider.decide(state)
        assert d.action_type == "recover"
        assert d.recovery.reason == "unknown_tool"

    def test_low_confidence_returns_recover(self):
        decision_payload = {
            "action_type": "call_tool",
            "reasoning_summary": "uncertain",
            "selected_tool": "SearchLog",
            "confidence": 0.1,
        }
        mock_invoke = MagicMock(return_value=json.dumps(decision_payload))
        provider = QwenDecisionProvider(mock_invoke)
        state = self._make_state()
        d = provider.decide(state)
        assert d.action_type == "recover"
        assert d.recovery.reason == "low_confidence"

    def test_get_token_usage_unavailable(self):
        mock_invoke = MagicMock(return_value="{}")
        provider = QwenDecisionProvider(mock_invoke)
        usage = provider.get_token_usage()
        assert usage["source"] == "provider_usage_unavailable"

    def test_get_token_usage_from_callable(self):
        mock_invoke = MagicMock(return_value="{}")
        mock_invoke.get_token_usage = MagicMock(return_value={"total": 100})
        provider = QwenDecisionProvider(mock_invoke)
        usage = provider.get_token_usage()
        assert usage["total"] == 100

    def test_get_cost_estimate_unavailable(self):
        mock_invoke = MagicMock(return_value="{}")
        provider = QwenDecisionProvider(mock_invoke)
        cost = provider.get_cost_estimate()
        assert cost["source"] == "provider_usage_unavailable"

    def test_get_cost_estimate_from_callable(self):
        mock_invoke = MagicMock(return_value="{}")
        mock_invoke.get_cost_estimate = MagicMock(return_value={"total_cost": 0.05})
        provider = QwenDecisionProvider(mock_invoke)
        cost = provider.get_cost_estimate()
        assert cost["total_cost"] == 0.05


# ---------------------------------------------------------------------------
# _parse_strict_json
# ---------------------------------------------------------------------------


class TestParseStrictJson:
    def test_valid(self):
        assert _parse_strict_json('{"a": 1}') == {"a": 1}

    def test_markdown_fence_rejected(self):
        with pytest.raises(ValueError, match="Markdown fences"):
            _parse_strict_json('```json\n{"a": 1}\n```')

    def test_non_dict_rejected(self):
        with pytest.raises(ValueError, match="non-object"):
            _parse_strict_json("[1, 2]")

    def test_invalid_json(self):
        with pytest.raises(json.JSONDecodeError):
            _parse_strict_json("not json")


# ---------------------------------------------------------------------------
# _best_evidence
# ---------------------------------------------------------------------------


class TestBestEvidence:
    def test_empty_returns_default(self):
        result = _best_evidence([])
        assert result.quality == "empty"

    def test_single_strong(self):
        e = EvidenceAssessment(quality="strong", confidence=0.9)
        assert _best_evidence([e]) is e

    def test_picks_best_quality(self):
        weak = EvidenceAssessment(quality="weak")
        strong = EvidenceAssessment(quality="strong")
        partial = EvidenceAssessment(quality="partial")
        result = _best_evidence([weak, strong, partial])
        assert result.quality == "strong"


# ---------------------------------------------------------------------------
# _usage_int
# ---------------------------------------------------------------------------


class TestUsageInt:
    def test_first_key(self):
        assert _usage_int({"prompt": 10}, "prompt", "input") == 10

    def test_fallback_key(self):
        assert _usage_int({"input": 20}, "prompt", "input") == 20

    def test_missing_key(self):
        assert _usage_int({}, "prompt") == 0

    def test_none_value(self):
        assert _usage_int({"prompt": None}, "prompt") == 0

    def test_string_value(self):
        assert _usage_int({"prompt": "42"}, "prompt") == 42

    def test_negative_clamped(self):
        assert _usage_int({"prompt": -5}, "prompt") == 0

    def test_bool_is_int(self):
        # bool is subclass of int in Python, so int(True) == 1
        assert _usage_int({"prompt": True}, "prompt") == 1


# ---------------------------------------------------------------------------
# _extract_response_token_usage
# ---------------------------------------------------------------------------


class TestExtractResponseTokenUsage:
    def test_no_usage_returns_unavailable(self):
        result = _extract_response_token_usage(SimpleNamespace())
        assert result["source"] == "provider_usage_unavailable"

    def test_usage_metadata_dict(self):
        resp = SimpleNamespace(
            usage_metadata={"prompt_tokens": 10, "completion_tokens": 20, "total": 30}
        )
        result = _extract_response_token_usage(resp)
        assert result["total"] == 30
        assert result["prompt_tokens"] == 10

    def test_response_metadata_fallback(self):
        resp = SimpleNamespace(
            usage_metadata=None,
            response_metadata={
                "token_usage": {"input_tokens": 5, "output_tokens": 15, "total_tokens": 20}
            },
        )
        result = _extract_response_token_usage(resp)
        assert result["total"] == 20

    def test_total_computed_from_parts(self):
        resp = SimpleNamespace(usage_metadata={"prompt_tokens": 10, "completion_tokens": 20})
        result = _extract_response_token_usage(resp)
        assert result["total"] == 30


# ---------------------------------------------------------------------------
# _route_decision
# ---------------------------------------------------------------------------


class TestRouteDecision:
    def test_no_decisions(self):
        assert _route_decision({}) == "end"

    def test_call_tool(self):
        assert _route_decision({"decisions": [{"action_type": "call_tool"}]}) == "act"

    def test_recover(self):
        assert _route_decision({"decisions": [{"action_type": "recover"}]}) == "recover"

    def test_final_report(self):
        assert _route_decision({"decisions": [{"action_type": "final_report"}]}) == "final_report"

    def test_observe(self):
        assert _route_decision({"decisions": [{"action_type": "observe"}]}) == "end"

    def test_non_list_decisions(self):
        assert _route_decision({"decisions": "invalid"}) == "end"

    def test_empty_decisions(self):
        assert _route_decision({"decisions": []}) == "end"


# ---------------------------------------------------------------------------
# _qwen_decision_prompt
# ---------------------------------------------------------------------------


class TestQwenDecisionPrompt:
    def test_returns_json_string(self):
        state = AgentDecisionState(
            goal=AgentGoalContract(goal="diagnose OOM"),
            available_tools=["SearchLog"],
        )
        prompt = _qwen_decision_prompt(state)
        parsed = json.loads(prompt)
        assert "goal" in parsed
        assert "required_json_shape" in parsed
        assert parsed["available_tools"] == ["SearchLog"]


# ---------------------------------------------------------------------------
# build_initial_decision_state
# ---------------------------------------------------------------------------


class TestBuildInitialDecisionState:
    def test_basic(self):
        state = build_initial_decision_state(
            run_id="r1",
            goal="diagnose OOM",
            workspace_id="ws-1",
            scene_id="s1",
            available_tools=["SearchLog", "CheckCPU"],
        )
        assert state.run_id == "r1"
        assert state.goal.goal == "diagnose OOM"
        assert state.available_tools == ["SearchLog", "CheckCPU"]
        assert len(state.observations) == 1
        assert len(state.hypothesis_queue) == 1

    def test_with_string_success_criteria(self):
        state = build_initial_decision_state(
            run_id=None,
            goal="fix",
            workspace_id=None,
            scene_id=None,
            available_tools=[],
            success_criteria=["must complete"],
        )
        assert len(state.goal.success_criteria) == 1
        assert state.goal.success_criteria[0].description == "must complete"

    def test_with_success_criteria_object(self):
        sc = SuccessCriteria(description="done")
        state = build_initial_decision_state(
            run_id=None,
            goal="fix",
            workspace_id=None,
            scene_id=None,
            available_tools=[],
            success_criteria=[sc],
        )
        assert state.goal.success_criteria[0] is sc

    def test_custom_budget(self):
        budget = RuntimeBudget(max_steps=3)
        state = build_initial_decision_state(
            run_id=None,
            goal="x",
            workspace_id=None,
            scene_id=None,
            available_tools=[],
            budget=budget,
        )
        assert state.budget.max_steps == 3

    def test_executed_tools(self):
        state = build_initial_decision_state(
            run_id=None,
            goal="x",
            workspace_id=None,
            scene_id=None,
            available_tools=["A", "B"],
            executed_tools=["A"],
        )
        assert state.executed_tools == ["A"]


# ---------------------------------------------------------------------------
# AgentDecisionRuntime
# ---------------------------------------------------------------------------


class TestAgentDecisionRuntime:
    def test_decide_once_with_deterministic(self):
        runtime = AgentDecisionRuntime()
        state = AgentDecisionState(
            goal=AgentGoalContract(goal="test"),
            budget=RuntimeBudget(remaining_steps=5, remaining_tool_calls=5),
            available_tools=["SearchLog"],
        )
        result = runtime.decide_once(state)
        assert len(result.decisions) == 1

    def test_decide_once_with_fallback(self):
        failing_provider = MagicMock()
        failing_provider.decide.side_effect = RuntimeError("LLM down")
        failing_provider.get_token_usage.return_value = {"total": 0}
        failing_provider.get_cost_estimate.return_value = {"total_cost": 0}
        fallback = DeterministicDecisionProvider()

        runtime = AgentDecisionRuntime(
            provider=failing_provider,
            fallback_provider=fallback,
        )
        state = AgentDecisionState(
            goal=AgentGoalContract(goal="test"),
        )
        result = runtime.decide_once(state)
        assert len(result.decisions) == 1
        events = runtime.consume_provider_fallback_events()
        assert len(events) == 1
        assert events[0]["reason"] == "RuntimeError"

    def test_consume_provider_fallback_events_clears(self):
        runtime = AgentDecisionRuntime()
        runtime._provider_fallback_events.append({"from_provider": "qwen", "to_provider": "det"})
        events = runtime.consume_provider_fallback_events()
        assert len(events) == 1
        assert runtime.consume_provider_fallback_events() == []

    def test_get_token_usage(self):
        runtime = AgentDecisionRuntime()
        usage = runtime.get_token_usage()
        assert usage["source"] == "provider_usage_unavailable"

    def test_get_cost_estimate(self):
        runtime = AgentDecisionRuntime()
        cost = runtime.get_cost_estimate()
        assert cost["source"] == "provider_usage_unavailable"


# ---------------------------------------------------------------------------
# DecisionProviderFactory
# ---------------------------------------------------------------------------


class TestDecisionProviderFactory:
    def test_create_deterministic(self):
        settings = SimpleNamespace(agent_decision_provider="deterministic")
        factory = DecisionProviderFactory(settings)
        provider = factory.create_provider()
        assert isinstance(provider, DeterministicDecisionProvider)

    def test_create_qwen_requires_factory(self):
        settings = SimpleNamespace(agent_decision_provider="qwen")
        factory = DecisionProviderFactory(settings)
        with pytest.raises(ValueError, match="chat_model_factory"):
            factory.create_provider()

    def test_create_runtime_deterministic(self):
        settings = SimpleNamespace(agent_decision_provider="deterministic")
        factory = DecisionProviderFactory(settings)
        runtime = factory.create_runtime()
        assert isinstance(runtime, AgentDecisionRuntime)


# ---------------------------------------------------------------------------
# FinalReportContract
# ---------------------------------------------------------------------------


class TestFinalReportContract:
    def test_basic(self):
        report = FinalReportContract(summary="done")
        assert report.summary == "done"
        assert report.handoff_required is False

    def test_to_event_payload(self):
        report = FinalReportContract(summary="report", confidence=0.8)
        payload = report.to_event_payload()
        assert payload["summary"] == "report"
        assert payload["confidence"] == 0.8
