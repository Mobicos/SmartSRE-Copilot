"""Unit tests for release gate typed schema, OTel GenAI spans, and cancellation guard."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.agent_runtime.release_gate_types import (
    GateThresholds,
    KnowledgeGateResult,
    KnowledgeGateThresholds,
    ReleaseGateResult,
)
from app.agent_runtime.trace_collector import TraceCollector

# ---------------------------------------------------------------------------
# Release gate typed schema
# ---------------------------------------------------------------------------


def test_release_gate_defaults():
    result = ReleaseGateResult()
    assert result.gate_pass is False
    assert result.handoff_rate == 0.0
    assert result.approval_wait_time_p50_ms is None


def test_release_gate_thresholds():
    t = GateThresholds()
    assert t.goal_completion_rate_min == 0.80
    assert t.p95_latency_ms_max == 60000


def test_knowledge_gate_defaults():
    result = KnowledgeGateResult()
    assert result.faq_knowledge_ratio == 0.0
    assert result.low_confidence_refusal_rate == 1.0
    assert result.gate_pass is False


def test_knowledge_gate_thresholds():
    t = KnowledgeGateThresholds()
    assert t.faq_knowledge_ratio_min == 0.50


# ---------------------------------------------------------------------------
# OTel GenAI trace span
# ---------------------------------------------------------------------------


def test_gen_ai_span_no_otel():
    collector = TraceCollector()
    with collector.gen_ai_span(
        "llm_call",
        model="qwen-max",
        operation="chat",
        input_tokens=100,
        output_tokens=50,
        run_id="r-123",
    ) as span:
        assert span is not None


def test_gen_ai_span_attributes():
    collector = TraceCollector()
    with collector.gen_ai_span(
        "llm_call",
        model="qwen-max",
        operation="chat",
        input_tokens=100,
        output_tokens=50,
        run_id="r-123",
    ) as span:
        assert span is not None


def test_regular_span_with_attributes():
    collector = TraceCollector()
    with collector.span("test", attributes={"key": "value"}) as span:
        assert span is not None


# ---------------------------------------------------------------------------
# Cancellation guard in AgentResumeService
# ---------------------------------------------------------------------------


def test_cancelled_run_blocks_resume():
    from app.application.agent_resume_service import AgentResumeService

    mock_repo = MagicMock()
    mock_repo.get_run.return_value = {"run_id": "r1", "status": "cancelled"}
    mock_repo.list_events.return_value = []

    svc = AgentResumeService(
        agent_run_repository=mock_repo,
        tool_catalog=MagicMock(),
        tool_executor=MagicMock(),
    )

    import asyncio

    result = asyncio.get_event_loop().run_until_complete(
        svc.process_resume_task(
            {"run_id": "r1", "tool_name": "GetMetrics", "decision": "approved"}
        )
    )
    assert result["status"] == "ignored"
    assert result["reason"] == "run_cancelled"
