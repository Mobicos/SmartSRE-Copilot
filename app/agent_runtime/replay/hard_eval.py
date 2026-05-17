"""Hard eval checks: tool order, budget compliance, evidence quality, terminal status."""

from __future__ import annotations

from typing import Any


def check_tool_order(
    expected: list[str], actual: list[str]
) -> tuple[bool, str]:
    if not expected:
        return True, "no expected tool order"
    if actual == expected:
        return True, "tool order matches"
    return False, f"expected {expected}, got {actual}"


def check_budget_compliance(
    events: list[dict[str, Any]],
    *,
    max_steps: int = 30,
    max_tool_calls: int = 50,
) -> tuple[bool, str]:
    decisions = [e for e in events if e.get("type") == "decision"]
    tool_calls = [e for e in events if e.get("type") == "tool_call"]
    issues: list[str] = []
    if len(decisions) > max_steps:
        issues.append(f"decisions {len(decisions)} exceed max_steps {max_steps}")
    if len(tool_calls) > max_tool_calls:
        issues.append(f"tool_calls {len(tool_calls)} exceed max {max_tool_calls}")
    if issues:
        return False, "; ".join(issues)
    return True, "within budget"


def check_terminal_status(
    actual_status: str, expected_status: str = "completed"
) -> tuple[bool, str]:
    if actual_status == expected_status:
        return True, f"terminal status {actual_status}"
    return False, f"expected {expected_status}, got {actual_status}"


def check_evidence_quality(
    events: list[dict[str, Any]],
) -> tuple[bool, str]:
    evidence_events = [
        e for e in events if e.get("type") in {"tool_result", "evidence_assessment"}
    ]
    if not evidence_events:
        return False, "no evidence events found"
    quality_values = []
    for e in evidence_events:
        payload = e.get("payload") or {}
        q = payload.get("quality") or payload.get("confidence")
        if q is not None:
            quality_values.append(q)
    if not quality_values:
        return True, "evidence events present (quality not explicitly rated)"
    has_strong = any(v in ("strong", "high") or (isinstance(v, (int, float)) and v >= 0.6) for v in quality_values)
    if has_strong:
        return True, "at least one strong evidence assessment"
    return False, "no strong evidence assessments found"


def check_citations_present(events: list[dict[str, Any]]) -> tuple[bool, str]:
    for event in events:
        if event.get("type") == "knowledge_context":
            payload = event.get("payload") or {}
            citations = payload.get("citations") or []
            if citations:
                return True, f"{len(citations)} citations present"
    return False, "no knowledge citations found"
