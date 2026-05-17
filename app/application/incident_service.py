"""Incident context service: timeline reconstruction, handoff summary, analytics."""

from __future__ import annotations

from typing import Any

from app.agent_runtime.incident_types import (
    AnalyticsCategory,
    HandoffSummary,
)
from app.platform.persistence.repositories.incidents import (
    AnalyticsRepository,
    IncidentRepository,
)


class IncidentContextService:
    """Create and manage incident context, link agent runs, and build timelines."""

    def __init__(
        self,
        *,
        incident_repository: IncidentRepository,
        agent_run_repository: Any,
    ) -> None:
        self._incident_repo = incident_repository
        self._agent_run_repo = agent_run_repository

    def create_incident(
        self,
        *,
        workspace_id: str,
        title: str,
        severity: str = "P2",
        source: str = "manual",
        service_name: str | None = None,
        owner: str | None = None,
        summary: str | None = None,
    ) -> dict[str, Any]:
        incident_id = self._incident_repo.create_incident(
            workspace_id=workspace_id,
            title=title,
            severity=severity,
            source=source,
            service_name=service_name,
            owner=owner,
            summary=summary,
        )
        return self._incident_repo.get_incident(incident_id) or {}

    def link_run(
        self, incident_id: str, run_id: str, *, relationship: str = "diagnosed_by"
    ) -> str:
        return self._incident_repo.add_link(
            incident_id=incident_id,
            target_type="agent_run",
            target_id=run_id,
            relationship=relationship,
        )

    def link_feedback(
        self, incident_id: str, feedback_id: str, *, relationship: str = "corrected_by"
    ) -> str:
        return self._incident_repo.add_link(
            incident_id=incident_id,
            target_type="feedback",
            target_id=feedback_id,
            relationship=relationship,
        )

    def link_knowledge(
        self, incident_id: str, knowledge_id: str, *, relationship: str = "promoted_to"
    ) -> str:
        return self._incident_repo.add_link(
            incident_id=incident_id,
            target_type="knowledge",
            target_id=knowledge_id,
            relationship=relationship,
        )

    def get_incident(self, incident_id: str) -> dict[str, Any] | None:
        return self._incident_repo.get_incident(incident_id)

    def list_incidents(
        self,
        *,
        workspace_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        return self._incident_repo.list_incidents(
            workspace_id=workspace_id, status=status, limit=limit
        )

    def update_status(
        self, incident_id: str, status: str, *, summary: str | None = None
    ) -> None:
        self._incident_repo.update_incident_status(incident_id, status, summary=summary)


class IncidentTimelineService:
    """Reconstruct incident timeline from persisted agent events and links."""

    def __init__(
        self,
        *,
        incident_repository: IncidentRepository,
        agent_run_repository: Any,
    ) -> None:
        self._incident_repo = incident_repository
        self._agent_run_repo = agent_run_repository

    def build_timeline(self, incident_id: str) -> list[dict[str, Any]]:
        links = self._incident_repo.list_links(incident_id)
        timeline_events: list[dict[str, Any]] = []

        for link in links:
            if link["target_type"] != "agent_run":
                continue
            run_id = link["target_id"]
            run = self._agent_run_repo.get_run(run_id)
            if run is None:
                continue
            events = self._agent_run_repo.list_events(run_id)
            for event in events:
                timeline_event = _event_to_timeline(incident_id, run_id, event)
                if timeline_event is not None:
                    timeline_events.append(timeline_event)

        timeline_events.sort(key=lambda e: e.get("created_at", ""))
        return timeline_events

    def find_incident_for_run(self, run_id: str) -> str | None:
        links = self._incident_repo.find_links_by_target("agent_run", run_id)
        return links[0]["incident_id"] if links else None


class HandoffSummaryService:
    """Build structured handoff summaries for low-confidence or failed runs."""

    def __init__(self, *, agent_run_repository: Any) -> None:
        self._agent_run_repo = agent_run_repository

    def build_summary(self, run_id: str, incident_id: str | None = None) -> dict[str, Any]:
        run = self._agent_run_repo.get_run(run_id)
        if run is None:
            return {"error": "run_not_found", "run_id": run_id}

        events = self._agent_run_repo.list_events(run_id)
        evidence_collected = _extract_evidence(events)
        tools_attempted = _extract_tool_attempts(events)
        failure_reasons = _extract_failure_reasons(run, events)
        next_actions = _suggest_next_actions(run, evidence_collected, failure_reasons)
        confidence = _extract_confidence(events)
        handoff_reason = run.get("handoff_reason") or _infer_handoff_reason(
            run, failure_reasons
        )

        summary = HandoffSummary(
            run_id=run_id,
            incident_id=incident_id,
            evidence_collected=evidence_collected,
            tools_attempted=tools_attempted,
            failure_reasons=failure_reasons,
            next_actions=next_actions,
            confidence=confidence,
            handoff_reason=handoff_reason,
        )
        return {
            "run_id": summary.run_id,
            "incident_id": summary.incident_id,
            "evidence_collected": summary.evidence_collected,
            "tools_attempted": summary.tools_attempted,
            "failure_reasons": summary.failure_reasons,
            "next_actions": summary.next_actions,
            "confidence": summary.confidence,
            "handoff_reason": summary.handoff_reason,
        }


class AnalyticsService:
    """Detect team improvement signals from run history and incident patterns."""

    def __init__(
        self,
        *,
        analytics_repository: AnalyticsRepository,
        agent_run_repository: Any,
        incident_repository: IncidentRepository,
    ) -> None:
        self._analytics_repo = analytics_repository
        self._agent_run_repo = agent_run_repository
        self._incident_repo = incident_repository

    def detect_findings(
        self, *, workspace_id: str, limit: int = 200
    ) -> list[dict[str, Any]]:
        runs = self._agent_run_repo.list_runs(limit=limit)
        findings: list[dict[str, Any]] = []

        knowledge_gap = self._detect_knowledge_gaps(workspace_id, runs)
        if knowledge_gap:
            findings.append(knowledge_gap)

        monitoring_gap = self._detect_monitoring_gaps(workspace_id, runs)
        if monitoring_gap:
            findings.append(monitoring_gap)

        tool_reliability = self._detect_tool_reliability(workspace_id, runs)
        if tool_reliability:
            findings.append(tool_reliability)

        automation = self._detect_automation_candidates(workspace_id, runs)
        if automation:
            findings.append(automation)

        return findings

    def persist_findings(
        self, *, workspace_id: str, findings: list[dict[str, Any]]
    ) -> list[str]:
        ids: list[str] = []
        for finding in findings:
            fid = self._analytics_repo.create_finding(
                workspace_id=workspace_id,
                category=finding["category"],
                title=finding["title"],
                summary=finding["summary"],
                evidence_refs=finding.get("evidence_refs", []),
            )
            ids.append(fid)
        return ids

    def list_findings(
        self,
        *,
        workspace_id: str | None = None,
        category: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        return self._analytics_repo.list_findings(
            workspace_id=workspace_id, category=category, limit=limit
        )

    def _detect_knowledge_gaps(
        self, workspace_id: str, runs: list[dict[str, Any]]
    ) -> dict[str, Any] | None:
        handoff_runs = [r for r in runs if r.get("handoff_reason")]
        if len(handoff_runs) < 3:
            return None
        return {
            "category": AnalyticsCategory.KNOWLEDGE_GAP,
            "title": f"{len(handoff_runs)} runs required handoff due to missing knowledge",
            "summary": "Multiple runs ended in handoff, suggesting knowledge base gaps.",
            "evidence_refs": [
                {"run_id": r.get("run_id"), "reason": r.get("handoff_reason")}
                for r in handoff_runs[:5]
            ],
        }

    def _detect_monitoring_gaps(
        self, workspace_id: str, runs: list[dict[str, Any]]
    ) -> dict[str, Any] | None:
        empty_runs = [
            r
            for r in runs
            if (r.get("empty_result_count") or 0) > 3
        ]
        if len(empty_runs) < 2:
            return None
        return {
            "category": AnalyticsCategory.MONITORING_GAP,
            "title": f"{len(empty_runs)} runs had excessive empty tool results",
            "summary": "Tools returning empty results suggest missing monitoring coverage.",
            "evidence_refs": [
                {"run_id": r.get("run_id"), "empty_count": r.get("empty_result_count")}
                for r in empty_runs[:5]
            ],
        }

    def _detect_tool_reliability(
        self, workspace_id: str, runs: list[dict[str, Any]]
    ) -> dict[str, Any] | None:
        error_runs = [r for r in runs if r.get("error_type")]
        if len(error_runs) < 3:
            return None
        return {
            "category": AnalyticsCategory.TOOL_RELIABILITY,
            "title": f"{len(error_runs)} runs encountered tool errors",
            "summary": "Recurring tool errors suggest reliability issues.",
            "evidence_refs": [
                {"run_id": r.get("run_id"), "error_type": r.get("error_type")}
                for r in error_runs[:5]
            ],
        }

    def _detect_automation_candidates(
        self, workspace_id: str, runs: list[dict[str, Any]]
    ) -> dict[str, Any] | None:
        duplicate_runs = [
            r for r in runs if (r.get("duplicate_tool_call_count") or 0) > 2
        ]
        if len(duplicate_runs) < 2:
            return None
        return {
            "category": AnalyticsCategory.AUTOMATION_CANDIDATE,
            "title": f"{len(duplicate_runs)} runs had repeated tool calls",
            "summary": "Repeated tool calls suggest automation or caching opportunities.",
            "evidence_refs": [
                {
                    "run_id": r.get("run_id"),
                    "duplicate_count": r.get("duplicate_tool_call_count"),
                }
                for r in duplicate_runs[:5]
            ],
        }


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _event_to_timeline(
    incident_id: str, run_id: str, event: dict[str, Any]
) -> dict[str, Any] | None:
    etype = event.get("type", "")
    payload = event.get("payload") or {}
    title_map: dict[str, str] = {
        "run_started": "Run started",
        "hypothesis": "Hypothesis formed",
        "decision": "Decision made",
        "tool_call": f"Tool called: {payload.get('tool_name', '?')}",
        "tool_result": f"Tool result: {payload.get('tool_name', '?')}",
        "evidence_assessment": "Evidence assessed",
        "approval_required": "Approval requested",
        "approval_decision": "Approval decision",
        "handoff": "Handoff initiated",
        "recovery": "Recovery action",
        "final_report": "Final report generated",
        "timeout": "Timeout",
        "error": "Error occurred",
    }
    title = title_map.get(etype, etype)
    summary = event.get("message") or str(payload)[:200]
    actor = "agent"
    if etype in ("approval_decision", "approval_required"):
        actor = "human"
    return {
        "incident_id": incident_id,
        "event_id": str(event.get("id", "")),
        "source": "agent_event",
        "event_type": etype,
        "title": title,
        "summary": summary,
        "actor": actor,
        "created_at": event.get("created_at", ""),
        "refs": {"run_id": run_id, "tool_name": payload.get("tool_name", "")},
    }


def _extract_evidence(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    for event in events:
        if event.get("type") in ("tool_result", "evidence_assessment"):
            payload = event.get("payload") or {}
            evidence.append(
                {
                    "tool_name": payload.get("tool_name", ""),
                    "status": payload.get("status", ""),
                    "quality": payload.get("quality", ""),
                }
            )
    return evidence


def _extract_tool_attempts(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    attempts: list[dict[str, Any]] = []
    for event in events:
        if event.get("type") == "tool_call":
            payload = event.get("payload") or {}
            attempts.append(
                {
                    "tool_name": payload.get("tool_name", ""),
                    "arguments": payload.get("arguments", {}),
                }
            )
    return attempts


def _extract_failure_reasons(
    run: dict[str, Any], events: list[dict[str, Any]]
) -> list[str]:
    reasons: list[str] = []
    if run.get("error_message"):
        reasons.append(str(run["error_message"]))
    for event in events:
        if event.get("type") in ("error", "timeout", "recovery"):
            payload = event.get("payload") or {}
            err = payload.get("error") or payload.get("reason") or ""
            if err and err not in reasons:
                reasons.append(str(err))
    return reasons


def _suggest_next_actions(
    run: dict[str, Any],
    evidence: list[dict[str, Any]],
    failure_reasons: list[str],
) -> list[str]:
    actions: list[str] = []
    if not evidence:
        actions.append("Collect missing evidence with diagnostic tools")
    if failure_reasons:
        actions.append("Investigate tool failures and retry with fallback")
    if run.get("status") == "handoff_required":
        actions.append("Escalate to human operator for manual diagnosis")
    if not actions:
        actions.append("Review final report and confirm resolution")
    return actions


def _extract_confidence(events: list[dict[str, Any]]) -> float:
    for event in reversed(events):
        payload = event.get("payload") or {}
        conf = payload.get("confidence")
        if conf is not None:
            try:
                return float(conf)
            except (ValueError, TypeError):
                pass
    return 0.0


def _infer_handoff_reason(
    run: dict[str, Any], failure_reasons: list[str]
) -> str:
    if failure_reasons:
        return failure_reasons[0]
    return "insufficient_evidence"
