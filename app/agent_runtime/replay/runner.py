"""Fixture-backed replay runner for deterministic regression evaluation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.agent_runtime.replay.drift_report import compute_drift
from app.agent_runtime.replay.fixture_schema import ReplayFixture


@dataclass(frozen=True)
class EvalCheck:
    name: str
    passed: bool
    message: str


@dataclass
class ReplayOutcome:
    fixture_id: str
    scenario_id: str
    status: str
    score: float
    checks: list[EvalCheck] = field(default_factory=list)
    drift: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "fixture_id": self.fixture_id,
            "scenario_id": self.scenario_id,
            "status": self.status,
            "score": self.score,
            "checks": [
                {"name": c.name, "passed": c.passed, "message": c.message}
                for c in self.checks
            ],
            "drift": self.drift,
        }


class ReplayRunner:
    """Evaluate a persisted run against a fixture's expected behaviour."""

    def __init__(self, *, agent_run_repository: Any) -> None:
        self._repo = agent_run_repository

    def run(self, fixture: ReplayFixture, *, run_id: str) -> ReplayOutcome:
        run = self._repo.get_run(run_id)
        if run is None:
            return ReplayOutcome(
                fixture_id=fixture.fixture_id,
                scenario_id=fixture.scenario_id,
                status="error",
                score=0.0,
                checks=[EvalCheck("run_exists", False, f"run {run_id} not found")],
            )

        events = self._repo.list_events(run_id)
        checks = _all_checks(fixture, run, events)
        failed = [c for c in checks if not c.passed]
        score = round((len(checks) - len(failed)) / len(checks), 4) if checks else 1.0
        drift = compute_drift(fixture, run, events)

        return ReplayOutcome(
            fixture_id=fixture.fixture_id,
            scenario_id=fixture.scenario_id,
            status="passed" if not failed else "failed",
            score=score,
            checks=checks,
            drift=drift,
        )


def _all_checks(
    fixture: ReplayFixture,
    run: dict[str, Any],
    events: list[dict[str, Any]],
) -> list[EvalCheck]:
    checks: list[EvalCheck] = []
    event_types = [str(e.get("type") or "") for e in events]
    tool_calls = [e for e in events if e.get("type") == "tool_call"]
    tool_names = [
        str((e.get("payload") or {}).get("tool_name") or "") for e in tool_calls
    ]
    searchable = _searchable_text(run, events)

    checks.append(
        EvalCheck(
            "terminal_status",
            run.get("status") == fixture.terminal_status,
            f"expected {fixture.terminal_status}, got {run.get('status')}",
        )
    )

    checks.append(
        EvalCheck(
            "final_report_present",
            bool(str(run.get("final_report") or "").strip()),
            "final report present" if run.get("final_report") else "final report missing",
        )
    )

    tool_count = len(tool_calls)
    checks.append(
        EvalCheck(
            "tool_call_count_range",
            fixture.min_tool_calls <= tool_count <= fixture.max_tool_calls,
            f"expected {fixture.min_tool_calls}-{fixture.max_tool_calls} tool calls, got {tool_count}",
        )
    )

    for event_type in fixture.required_event_types:
        checks.append(
            EvalCheck(
                f"event:{event_type}",
                event_type in event_types,
                f"event {event_type} {'observed' if event_type in event_types else 'missing'}",
            )
        )

    for i, expected in enumerate(fixture.expected_tool_calls):
        if expected.index is not None and expected.index < len(tool_names):
            actual_name = tool_names[expected.index]
        elif i < len(tool_names):
            actual_name = tool_names[i]
        else:
            actual_name = ""
        checks.append(
            EvalCheck(
                f"tool_order:{expected.tool_name}",
                actual_name == expected.tool_name,
                f"expected {expected.tool_name} at position {i}, got {actual_name or '(not called)'}",
            )
        )

    for signal in fixture.expected_signals:
        checks.append(
            EvalCheck(
                f"signal:{signal}",
                signal.lower() in searchable,
                f"signal {signal} {'observed' if signal.lower() in searchable else 'missing'}",
            )
        )

    for term in fixture.blocked_terms:
        checks.append(
            EvalCheck(
                f"blocked:{term}",
                term.lower() not in searchable,
                f"blocked term {term} {'absent' if term.lower() not in searchable else 'present'}",
            )
        )

    if fixture.expected_handoff:
        handoff_events = [e for e in events if e.get("type") == "handoff"]
        checks.append(
            EvalCheck(
                "handoff_required",
                len(handoff_events) > 0 or bool(run.get("handoff_reason")),
                "handoff event observed" if handoff_events else "handoff missing",
            )
        )

    report_text = str(run.get("final_report") or "")
    if "root cause" in report_text.lower() and not any(
        "evidence" in searchable or "citation" in searchable
        for _ in [1]
    ):
        checks.append(
            EvalCheck(
                "evidence_backed_root_cause",
                False,
                "root-cause claim without evidence or citation",
            )
        )

    return checks


def _searchable_text(run: dict[str, Any], events: list[dict[str, Any]]) -> str:
    parts = [
        str(run.get("goal") or ""),
        str(run.get("final_report") or ""),
        str(run.get("error_message") or ""),
    ]
    for event in events:
        parts.append(str(event.get("type") or ""))
        parts.append(str(event.get("message") or ""))
        parts.append(str(event.get("payload") or ""))
    return "\n".join(parts).lower()
