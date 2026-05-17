"""Unit tests for replay fixture schema, loader, runner, and drift report."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.agent_runtime.replay.drift_report import compute_drift
from app.agent_runtime.replay.fixture_schema import ReplayFixture
from app.agent_runtime.replay.hard_eval import (
    check_budget_compliance,
    check_citations_present,
    check_evidence_quality,
    check_terminal_status,
    check_tool_order,
)
from app.agent_runtime.replay.loader import load_fixture_by_id, load_fixtures
from app.agent_runtime.replay.runner import ReplayOutcome, ReplayRunner

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "agent_scenarios" / "fixtures"


# ---------------------------------------------------------------------------
# Fixture schema
# ---------------------------------------------------------------------------


def test_fixture_validates_terminal_status():
    fixture = ReplayFixture(
        fixture_id="test-1",
        scenario_id="cpu_high",
        title="Test",
        goal="test goal",
        terminal_status="completed",
    )
    assert fixture.fixture_id == "test-1"


def test_fixture_rejects_invalid_terminal_status():
    import pytest

    with pytest.raises(ValueError):
        ReplayFixture(
            fixture_id="test-1",
            scenario_id="cpu_high",
            title="Test",
            goal="test goal",
            terminal_status="bogus",
        )


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------


def test_load_all_fixtures():
    fixtures = load_fixtures(fixtures_dir=FIXTURES_DIR)
    assert len(fixtures) == 6
    ids = {f.fixture_id for f in fixtures}
    assert "cpu-high-fixture" in ids
    assert "http-5xx-spike-fixture" in ids


def test_load_fixture_by_id():
    fixture = load_fixture_by_id("cpu-high-fixture", fixtures_dir=FIXTURES_DIR)
    assert fixture is not None
    assert fixture.scenario_id == "cpu_high"
    assert fixture.min_tool_calls == 2


def test_load_fixture_nonexistent():
    assert load_fixture_by_id("no-such-fixture", fixtures_dir=FIXTURES_DIR) is None


def test_load_fixtures_empty_dir(tmp_path: Path):
    assert load_fixtures(fixtures_dir=tmp_path) == []


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


class _FakeRepo:
    def __init__(self, run: dict[str, Any], events: list[dict[str, Any]]):
        self._run = run
        self._events = events

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        return self._run if self._run.get("run_id") == run_id else None

    def list_events(self, run_id: str) -> list[dict[str, Any]]:
        return self._events if run_id else []


def _make_cpu_high_run() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    run = {
        "run_id": "r1",
        "status": "completed",
        "goal": "诊断 CPU 高负载",
        "final_report": "CPU 使用率 95%，进程 java 占用最高",
    }
    events = [
        {"type": "run_started", "payload": {}},
        {
            "type": "tool_call",
            "payload": {"tool_name": "GetMetrics", "arguments": {"metric": "cpu_usage_percent"}},
        },
        {"type": "tool_result", "payload": {"tool_name": "GetMetrics", "output": {"cpu": 95}}},
        {
            "type": "tool_call",
            "payload": {"tool_name": "GetProcessInfo", "arguments": {}},
        },
        {
            "type": "tool_result",
            "payload": {"tool_name": "GetProcessInfo", "output": {"top": "java"}},
        },
        {"type": "final_report", "payload": {"report": "CPU 使用率 95%"}},
    ]
    return run, events


def test_runner_passes_cpu_high():
    run, events = _make_cpu_high_run()
    fixture = load_fixture_by_id("cpu-high-fixture", fixtures_dir=FIXTURES_DIR)
    runner = ReplayRunner(agent_run_repository=_FakeRepo(run, events))
    outcome = runner.run(fixture, run_id="r1")
    assert isinstance(outcome, ReplayOutcome)
    assert outcome.status == "passed"
    assert outcome.score >= 0.8


def test_runner_fails_wrong_terminal_status():
    run, events = _make_cpu_high_run()
    run["status"] = "failed"
    fixture = load_fixture_by_id("cpu-high-fixture", fixtures_dir=FIXTURES_DIR)
    runner = ReplayRunner(agent_run_repository=_FakeRepo(run, events))
    outcome = runner.run(fixture, run_id="r1")
    assert outcome.status == "failed"
    failed_names = [c.name for c in outcome.checks if not c.passed]
    assert "terminal_status" in failed_names


def test_runner_error_on_missing_run():
    fixture = load_fixture_by_id("cpu-high-fixture", fixtures_dir=FIXTURES_DIR)
    runner = ReplayRunner(agent_run_repository=_FakeRepo({}, []))
    outcome = runner.run(fixture, run_id="nonexistent")
    assert outcome.status == "error"
    assert outcome.score == 0.0


def test_runner_to_dict():
    run, events = _make_cpu_high_run()
    fixture = load_fixture_by_id("cpu-high-fixture", fixtures_dir=FIXTURES_DIR)
    runner = ReplayRunner(agent_run_repository=_FakeRepo(run, events))
    outcome = runner.run(fixture, run_id="r1")
    d = outcome.to_dict()
    assert "fixture_id" in d
    assert "drift" in d
    assert isinstance(d["checks"], list)


# ---------------------------------------------------------------------------
# Drift report
# ---------------------------------------------------------------------------


def test_drift_report_match():
    run, events = _make_cpu_high_run()
    fixture = load_fixture_by_id("cpu-high-fixture", fixtures_dir=FIXTURES_DIR)
    drift = compute_drift(fixture, run, events)
    assert drift["terminal_status_match"] is True
    assert drift["actual_terminal_status"] == "completed"
    assert drift["tool_order_match"] is True
    assert drift["missing_event_types"] == []


def test_drift_report_mismatch():
    run, events = _make_cpu_high_run()
    run["status"] = "failed"
    fixture = load_fixture_by_id("cpu-high-fixture", fixtures_dir=FIXTURES_DIR)
    drift = compute_drift(fixture, run, events)
    assert drift["terminal_status_match"] is False
    assert drift["actual_terminal_status"] == "failed"


def test_drift_report_unexpected_events():
    run, events = _make_cpu_high_run()
    events.append({"type": "handoff", "payload": {}})
    fixture = load_fixture_by_id("cpu-high-fixture", fixtures_dir=FIXTURES_DIR)
    drift = compute_drift(fixture, run, events)
    assert "handoff" in drift["unexpected_event_types"]


# ---------------------------------------------------------------------------
# Hard eval checks
# ---------------------------------------------------------------------------


def test_check_tool_order_match():
    passed, _ = check_tool_order(["A", "B"], ["A", "B"])
    assert passed is True


def test_check_tool_order_mismatch():
    passed, msg = check_tool_order(["A", "B"], ["B", "A"])
    assert passed is False
    assert "expected" in msg


def test_check_tool_order_empty_expected():
    passed, _ = check_tool_order([], ["A"])
    assert passed is True


def test_check_budget_within():
    events = [{"type": "decision"}] * 5 + [{"type": "tool_call"}] * 3
    passed, _ = check_budget_compliance(events)
    assert passed is True


def test_check_budget_exceeded():
    events = [{"type": "decision"}] * 35 + [{"type": "tool_call"}] * 3
    passed, msg = check_budget_compliance(events, max_steps=30)
    assert passed is False
    assert "exceed" in msg


def test_check_terminal_status_ok():
    passed, _ = check_terminal_status("completed", "completed")
    assert passed is True


def test_check_terminal_status_fail():
    passed, _ = check_terminal_status("failed", "completed")
    assert passed is False


def test_check_evidence_quality_with_strong():
    events = [{"type": "tool_result", "payload": {"quality": "strong"}}]
    passed, _ = check_evidence_quality(events)
    assert passed is True


def test_check_evidence_quality_empty():
    passed, _ = check_evidence_quality([])
    assert passed is False


def test_check_citations_present():
    events = [{"type": "knowledge_context", "payload": {"citations": [{"title": "FAQ1"}]}}]
    passed, _ = check_citations_present(events)
    assert passed is True


def test_check_citations_missing():
    passed, _ = check_citations_present([])
    assert passed is False
