"""Unit tests for app.agent_runtime.state — dataclasses and helpers."""

from __future__ import annotations

from types import SimpleNamespace

from app.agent_runtime.constants import MAX_TOOL_OUTPUT_CHARS
from app.agent_runtime.state import (
    AgentRunState,
    EvidenceItem,
    Hypothesis,
    KnowledgeContext,
    ToolAction,
    ToolPolicySnapshot,
    _truncate_output,
)

# ---------------------------------------------------------------------------
# Hypothesis
# ---------------------------------------------------------------------------


class TestHypothesis:
    def test_from_goal(self):
        h = Hypothesis.from_goal("OOM diagnosis")
        assert "OOM diagnosis" in h.summary


# ---------------------------------------------------------------------------
# KnowledgeContext
# ---------------------------------------------------------------------------


class TestKnowledgeContext:
    def test_empty(self):
        ctx = KnowledgeContext.empty()
        assert ctx.knowledge_bases == []
        assert ctx.has_knowledge() is False
        assert ctx.summary == "未配置场景知识库。"
        assert ctx.to_report_lines() == []

    def test_with_knowledge(self):
        ctx = KnowledgeContext(
            knowledge_bases=[{"name": "KB1", "version": "1.0", "description": "desc"}]
        )
        assert ctx.has_knowledge() is True
        assert "KB1" in ctx.summary
        assert "1" in ctx.summary
        lines = ctx.to_report_lines()
        assert len(lines) == 1
        assert "KB1" in lines[0]
        assert "desc" in lines[0]

    def test_to_event_payload(self):
        ctx = KnowledgeContext(knowledge_bases=[{"name": "KB1", "version": "1.0"}])
        payload = ctx.to_event_payload()
        assert "knowledge_bases" in payload
        assert "summary" in payload

    def test_report_line_no_description(self):
        ctx = KnowledgeContext(knowledge_bases=[{"name": "KB", "version": "1"}])
        lines = ctx.to_report_lines()
        assert "暂无描述" in lines[0]


# ---------------------------------------------------------------------------
# ToolPolicySnapshot
# ---------------------------------------------------------------------------


class TestToolPolicySnapshot:
    def test_from_policy_none(self):
        snap = ToolPolicySnapshot.from_policy(None, tool_name="SearchLog")
        assert snap.tool_name == "SearchLog"
        assert snap.scope == "diagnosis"
        assert snap.approval_state == "not_required"

    def test_from_policy_dict(self):
        snap = ToolPolicySnapshot.from_policy(
            {"tool_name": "X", "scope": "chat", "approval_required": True},
            tool_name="fallback",
        )
        assert snap.tool_name == "X"
        assert snap.scope == "chat"
        assert snap.approval_state == "required"

    def test_to_dict(self):
        snap = ToolPolicySnapshot(tool_name="T", enabled=True)
        d = snap.to_dict()
        assert d["tool_name"] == "T"
        assert d["enabled"] is True


# ---------------------------------------------------------------------------
# ToolAction
# ---------------------------------------------------------------------------


class TestToolAction:
    def test_from_tool_name(self):
        action = ToolAction.from_tool_name("SearchLog", goal="OOM diagnosis")
        assert action.tool_name == "SearchLog"
        assert "query" in action.arguments

    def test_mark_executed(self):
        action = ToolAction.from_tool_name("X", goal="test")
        executed = action.mark_executed("success")
        assert executed.execution_status == "success"
        assert action.execution_status == "pending"  # immutable

    def test_approval_state(self):
        action = ToolAction.from_tool_name("X", goal="test")
        assert action.approval_state == "not_required"

    def test_to_event_payload(self):
        action = ToolAction.from_tool_name("X", goal="test")
        payload = action.to_event_payload()
        assert payload["tool_name"] == "X"
        assert "policy" in payload

    def test_result_event_payload(self):
        action = ToolAction.from_tool_name("X", goal="test")
        result = SimpleNamespace(
            tool_name="X",
            status="success",
            arguments={"query": "test"},
            output="result",
            error=None,
            policy=None,
            latency_ms=100,
        )
        payload = action.result_event_payload(result)
        assert payload["status"] == "success"
        assert payload["latency_ms"] == 100
        assert "governance" in payload


# ---------------------------------------------------------------------------
# EvidenceItem
# ---------------------------------------------------------------------------


class TestEvidenceItem:
    def test_from_tool_result(self):
        result = SimpleNamespace(
            tool_name="SearchLog",
            status="success",
            output="log data",
            error=None,
        )
        item = EvidenceItem.from_tool_result(result)
        assert item.tool_name == "SearchLog"
        assert item.status == "success"
        assert item.output == "log data"

    def test_to_report_line_success(self):
        item = EvidenceItem(tool_name="SearchLog", status="success", output="found")
        assert item.to_report_line() == "SearchLog: found"

    def test_to_report_line_approval_required(self):
        item = EvidenceItem(tool_name="X", status="approval_required")
        assert "等待人工审批" in item.to_report_line()

    def test_to_report_line_disabled(self):
        item = EvidenceItem(tool_name="X", status="disabled")
        assert "策略禁用" in item.to_report_line()

    def test_to_report_line_error(self):
        item = EvidenceItem(tool_name="X", status="error", error="timeout")
        assert "timeout" in item.to_report_line()


# ---------------------------------------------------------------------------
# AgentRunState
# ---------------------------------------------------------------------------


class TestAgentRunState:
    def test_from_goal(self):
        state = AgentRunState.from_goal("OOM diagnosis")
        assert state.goal == "OOM diagnosis"
        assert "OOM diagnosis" in state.hypothesis.summary

    def test_add_evidence(self):
        state = AgentRunState.from_goal("test")
        item = EvidenceItem(tool_name="X", status="success")
        state.add_evidence(item)
        assert len(state.evidence) == 1

    def test_add_action(self):
        state = AgentRunState.from_goal("test")
        action = ToolAction.from_tool_name("X", goal="test")
        state.add_action(action)
        assert len(state.actions) == 1

    def test_evidence_report_lines(self):
        state = AgentRunState.from_goal("test")
        state.add_evidence(EvidenceItem(tool_name="X", status="success", output="data"))
        lines = state.evidence_report_lines()
        assert len(lines) == 1
        assert "X" in lines[0]

    def test_set_knowledge_context(self):
        state = AgentRunState.from_goal("test")
        ctx = KnowledgeContext(knowledge_bases=[{"name": "KB", "version": "1"}])
        state.set_knowledge_context(ctx)
        assert state.knowledge_context.has_knowledge()


# ---------------------------------------------------------------------------
# _truncate_output
# ---------------------------------------------------------------------------


class TestTruncateOutput:
    def test_none(self):
        assert _truncate_output(None) is None

    def test_short_string(self):
        assert _truncate_output("hello") == "hello"

    def test_long_string(self):
        long_text = "x" * (MAX_TOOL_OUTPUT_CHARS + 100)
        result = _truncate_output(long_text)
        assert len(result) < len(long_text)
        assert "truncated" in result

    def test_dict_within_limit(self):
        d = {"key": "value"}
        assert _truncate_output(d) == d

    def test_dict_over_limit(self):
        d = {"key": "x" * (MAX_TOOL_OUTPUT_CHARS + 100)}
        result = _truncate_output(d)
        assert isinstance(result, str)
        assert "truncated" in result

    def test_non_serializable_long(self):
        class LongRepr:
            def __str__(self):
                return "x" * (MAX_TOOL_OUTPUT_CHARS + 100)

        result = _truncate_output(LongRepr())
        assert isinstance(result, str)
        assert "truncated" in result

    def test_non_serializable_short(self):
        # object() has a short repr, so it won't be truncated — returns the object itself
        obj = object()
        result = _truncate_output(obj)
        assert result is obj
