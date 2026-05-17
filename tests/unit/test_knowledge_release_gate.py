"""Unit tests for knowledge release gate metrics."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from app.application.agent_metrics_service import AgentMetricsService


class _FakeRunRepository:
    def __init__(
        self,
        runs: list[dict[str, Any]],
        events_map: dict[str, list[dict[str, Any]]] | None = None,
    ):
        self._runs = runs
        self._events_map = events_map or {}

    def list_runs(self, *, limit: int = 50) -> list[dict[str, Any]]:
        return self._runs[:limit]

    def list_events(self, run_id: str) -> list[dict[str, Any]]:
        return self._events_map.get(run_id, [])


def _make_run(
    run_id: str,
    *,
    status: str = "completed",
    tool_call_count: int = 10,
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "status": status,
        "tool_call_count": tool_call_count,
        "latency_ms": 30000,
    }


def _make_service(
    runs: list[dict[str, Any]],
    events_map: dict[str, list[dict[str, Any]]] | None = None,
) -> AgentMetricsService:
    repo = _FakeRunRepository(runs, events_map)
    mock_scenario = MagicMock()
    mock_scenario.evaluate_run.return_value = {"score": 0.9, "status": "passed"}
    return AgentMetricsService(
        agent_run_repository=repo,  # type: ignore[arg-type]
        scenario_regression_service=mock_scenario,  # type: ignore[arg-type]
    )


# ---------------------------------------------------------------------------
# faq_knowledge_ratio
# ---------------------------------------------------------------------------


def test_gate_faq_ratio_default_zero():
    service = _make_service([])
    result = service.compute_knowledge_release_gate(kb_id="")
    assert result["faq_knowledge_ratio"] == 0.0


# ---------------------------------------------------------------------------
# low_confidence_refusal_rate
# ---------------------------------------------------------------------------


def test_gate_refusal_rate_all_refused():
    events_map = {
        "r1": [
            {
                "type": "knowledge_context",
                "payload": {"citations": [], "gate": {"refused": True}},
            }
        ],
        "r2": [
            {
                "type": "knowledge_context",
                "payload": {"citations": [], "gate": {"refused": True}},
            }
        ],
    }
    runs = [_make_run("r1"), _make_run("r2")]
    service = _make_service(runs, events_map)
    result = service.compute_knowledge_release_gate()
    assert result["low_confidence_refusal_rate"] == 1.0


def test_gate_refusal_rate_mixed():
    events_map = {
        "r1": [
            {
                "type": "knowledge_context",
                "payload": {"citations": [{"item_type": "faq"}], "gate": {"refused": False}},
            }
        ],
        "r2": [
            {
                "type": "knowledge_context",
                "payload": {"citations": [], "gate": {"refused": True}},
            }
        ],
    }
    runs = [_make_run("r1"), _make_run("r2")]
    service = _make_service(runs, events_map)
    result = service.compute_knowledge_release_gate()
    assert result["low_confidence_refusal_rate"] == 0.5


def test_gate_refusal_rate_no_retrievals():
    service = _make_service([_make_run("r1")])
    result = service.compute_knowledge_release_gate()
    assert result["low_confidence_refusal_rate"] == 1.0


# ---------------------------------------------------------------------------
# interception_rate + faq_hit_rate
# ---------------------------------------------------------------------------


def test_gate_interception_rate():
    events_map = {
        "r1": [
            {
                "type": "knowledge_context",
                "payload": {
                    "citations": [
                        {"item_type": "faq", "content": "a"},
                        {"item_type": "sop", "content": "b"},
                    ],
                    "gate": {"refused": False},
                },
            }
        ],
    }
    runs = [_make_run("r1", tool_call_count=10)]
    service = _make_service(runs, events_map)
    result = service.compute_knowledge_release_gate()
    assert result["interception_rate"] == 0.2  # 2 citations / 10 tool calls
    assert result["faq_hit_rate"] == 0.5  # 1 faq / 2 total citations


# ---------------------------------------------------------------------------
# gate_pass
# ---------------------------------------------------------------------------


def test_gate_pass_when_all_met():
    events_map = {
        "r1": [
            {
                "type": "knowledge_context",
                "payload": {"citations": [], "gate": {"refused": True}},
            }
        ],
    }
    runs = [_make_run("r1")]
    service = _make_service(runs, events_map)

    # Mock _compute_faq_ratio to return > 0.5
    service._compute_faq_ratio = lambda kb_id: 0.6  # type: ignore[method-assign]

    result = service.compute_knowledge_release_gate()
    assert result["gate_pass"] is True


def test_gate_fail_when_refusal_rate_low():
    events_map = {
        "r1": [
            {
                "type": "knowledge_context",
                "payload": {"citations": [{"item_type": "faq"}], "gate": {"refused": False}},
            }
        ],
    }
    runs = [_make_run("r1")]
    service = _make_service(runs, events_map)
    service._compute_faq_ratio = lambda kb_id: 0.6  # type: ignore[method-assign]

    result = service.compute_knowledge_release_gate()
    assert result["gate_pass"] is False
    assert result["low_confidence_refusal_rate"] == 0.0
