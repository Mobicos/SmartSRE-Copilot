"""Drift report: compare expected fixture behaviour against actual run output."""

from __future__ import annotations

from typing import Any

from app.agent_runtime.replay.fixture_schema import ReplayFixture


def compute_drift(
    fixture: ReplayFixture,
    run: dict[str, Any],
    events: list[dict[str, Any]],
) -> dict[str, Any]:
    event_types = [str(e.get("type") or "") for e in events]
    tool_calls = [e for e in events if e.get("type") == "tool_call"]
    tool_names = [
        str((e.get("payload") or {}).get("tool_name") or "") for e in tool_calls
    ]
    expected_tool_names = [tc.tool_name for tc in fixture.expected_tool_calls]

    missing_event_types = [
        t for t in fixture.required_event_types if t not in event_types
    ]
    unexpected_event_types = [
        t for t in set(event_types) if t not in fixture.required_event_types and t
    ]

    tool_order_match = tool_names == expected_tool_names[: len(tool_names)]
    tool_count_drift = len(tool_calls) - len(expected_tool_names)

    return {
        "terminal_status_match": run.get("status") == fixture.terminal_status,
        "actual_terminal_status": run.get("status"),
        "missing_event_types": missing_event_types,
        "unexpected_event_types": unexpected_event_types,
        "tool_order_match": tool_order_match,
        "actual_tool_names": tool_names,
        "expected_tool_names": expected_tool_names,
        "tool_count_drift": tool_count_drift,
        "total_events": len(events),
        "total_tool_calls": len(tool_calls),
    }
