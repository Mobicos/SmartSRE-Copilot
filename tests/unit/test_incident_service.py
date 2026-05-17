"""Unit tests for incident context, timeline, handoff summary, and analytics."""

from __future__ import annotations

from typing import Any

from app.agent_runtime.incident_types import (
    AnalyticsCategory,
)
from app.application.incident_service import (
    AnalyticsService,
    HandoffSummaryService,
    IncidentContextService,
    IncidentTimelineService,
    _extract_confidence,
    _extract_evidence,
    _extract_failure_reasons,
    _extract_tool_attempts,
    _suggest_next_actions,
)

# ---------------------------------------------------------------------------
# Fake repositories
# ---------------------------------------------------------------------------


class _FakeIncidentRepo:
    def __init__(self) -> None:
        self._incidents: dict[str, dict[str, Any]] = {}
        self._links: list[dict[str, Any]] = []
        self._next_id = 1

    def create_incident(self, **kwargs: Any) -> str:
        iid = f"inc-{self._next_id}"
        self._next_id += 1
        self._incidents[iid] = {"incident_id": iid, "status": "open", **kwargs}
        return iid

    def get_incident(self, incident_id: str) -> dict[str, Any] | None:
        return self._incidents.get(incident_id)

    def list_incidents(self, *, workspace_id=None, status=None, limit=50):
        results = list(self._incidents.values())
        if workspace_id:
            results = [r for r in results if r.get("workspace_id") == workspace_id]
        if status:
            results = [r for r in results if r.get("status") == status]
        return results[:limit]

    def update_incident_status(self, incident_id, status, *, summary=None):
        if incident_id in self._incidents:
            self._incidents[incident_id]["status"] = status

    def add_link(self, **kwargs: Any) -> str:
        lid = f"il-{len(self._links)+1}"
        self._links.append({"link_id": lid, **kwargs})
        return lid

    def list_links(self, incident_id: str) -> list[dict[str, Any]]:
        return [lk for lk in self._links if lk["incident_id"] == incident_id]

    def find_links_by_target(self, target_type, target_id):
        return [
            lk
            for lk in self._links
            if lk["target_type"] == target_type and lk["target_id"] == target_id
        ]


class _FakeAnalyticsRepo:
    def __init__(self) -> None:
        self._findings: list[dict[str, Any]] = []
        self._next_id = 1

    def create_finding(self, **kwargs: Any) -> str:
        fid = f"af-{self._next_id}"
        self._next_id += 1
        self._findings.append({"finding_id": fid, **kwargs})
        return fid

    def list_findings(self, *, workspace_id=None, category=None, status=None, limit=50):
        results = self._findings
        if category:
            results = [r for r in results if r.get("category") == category]
        return results[:limit]

    def update_finding_status(self, finding_id, status):
        for f in self._findings:
            if f["finding_id"] == finding_id:
                f["status"] = status


class _FakeRunRepo:
    def __init__(
        self,
        runs: list[dict[str, Any]] | None = None,
        events_map: dict[str, list[dict[str, Any]]] | None = None,
    ):
        self._runs = {r.get("run_id"): r for r in (runs or [])}
        self._events = events_map or {}

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        return self._runs.get(run_id)

    def list_events(self, run_id: str) -> list[dict[str, Any]]:
        return self._events.get(run_id, [])

    def list_runs(self, *, limit: int = 50) -> list[dict[str, Any]]:
        return list(self._runs.values())[:limit]


# ---------------------------------------------------------------------------
# Incident context service
# ---------------------------------------------------------------------------


def test_create_incident():
    svc = IncidentContextService(
        incident_repository=_FakeIncidentRepo(),
        agent_run_repository=_FakeRunRepo(),
    )
    result = svc.create_incident(
        workspace_id="ws-1",
        title="API 5xx spike",
        severity="P1",
        source="alert",
        service_name="checkout",
    )
    assert result["incident_id"].startswith("inc-")
    assert result["status"] == "open"
    assert result["severity"] == "P1"


def test_link_run_to_incident():
    repo = _FakeIncidentRepo()
    svc = IncidentContextService(
        incident_repository=repo,
        agent_run_repository=_FakeRunRepo(),
    )
    iid = repo.create_incident(workspace_id="ws-1", title="test", severity="P2", source="manual")
    link_id = svc.link_run(iid, "run-123")
    assert link_id.startswith("il-")
    links = repo.list_links(iid)
    assert len(links) == 1
    assert links[0]["target_type"] == "agent_run"
    assert links[0]["target_id"] == "run-123"


def test_list_incidents():
    repo = _FakeIncidentRepo()
    svc = IncidentContextService(
        incident_repository=repo,
        agent_run_repository=_FakeRunRepo(),
    )
    svc.create_incident(workspace_id="ws-1", title="inc-1", severity="P0", source="manual")
    svc.create_incident(workspace_id="ws-1", title="inc-2", severity="P1", source="alert")
    result = svc.list_incidents(workspace_id="ws-1")
    assert len(result) == 2


def test_update_incident_status():
    repo = _FakeIncidentRepo()
    svc = IncidentContextService(
        incident_repository=repo,
        agent_run_repository=_FakeRunRepo(),
    )
    iid = repo.create_incident(workspace_id="ws-1", title="test", severity="P2", source="manual")
    svc.update_status(iid, "investigating")
    assert repo.get_incident(iid)["status"] == "investigating"


# ---------------------------------------------------------------------------
# Timeline service
# ---------------------------------------------------------------------------


def test_build_timeline():
    run_events = [
        {"id": 1, "type": "run_started", "message": "started", "payload": {}, "created_at": "2026-05-17T10:00:00Z"},
        {"id": 2, "type": "tool_call", "message": "calling", "payload": {"tool_name": "GetMetrics"}, "created_at": "2026-05-17T10:00:01Z"},
        {"id": 3, "type": "tool_result", "message": "done", "payload": {"tool_name": "GetMetrics", "status": "success"}, "created_at": "2026-05-17T10:00:02Z"},
        {"id": 4, "type": "final_report", "message": "report", "payload": {}, "created_at": "2026-05-17T10:00:03Z"},
    ]
    run_repo = _FakeRunRepo(
        runs=[{"run_id": "r1", "status": "completed"}],
        events_map={"r1": run_events},
    )
    inc_repo = _FakeIncidentRepo()
    iid = inc_repo.create_incident(workspace_id="ws-1", title="test", severity="P2", source="manual")
    inc_repo.add_link(incident_id=iid, target_type="agent_run", target_id="r1", relationship="diagnosed_by")

    svc = IncidentTimelineService(
        incident_repository=inc_repo,
        agent_run_repository=run_repo,
    )
    timeline = svc.build_timeline(iid)
    assert len(timeline) == 4
    assert timeline[0]["event_type"] == "run_started"
    assert timeline[-1]["event_type"] == "final_report"
    assert all(e["incident_id"] == iid for e in timeline)


def test_find_incident_for_run():
    inc_repo = _FakeIncidentRepo()
    iid = inc_repo.create_incident(workspace_id="ws-1", title="test", severity="P2", source="manual")
    inc_repo.add_link(incident_id=iid, target_type="agent_run", target_id="r1", relationship="diagnosed_by")
    svc = IncidentTimelineService(
        incident_repository=inc_repo,
        agent_run_repository=_FakeRunRepo(),
    )
    assert svc.find_incident_for_run("r1") == iid
    assert svc.find_incident_for_run("r2") is None


# ---------------------------------------------------------------------------
# Handoff summary service
# ---------------------------------------------------------------------------


def test_build_handoff_summary():
    run_events = [
        {"type": "tool_call", "payload": {"tool_name": "GetMetrics", "arguments": {"metric": "cpu"}}},
        {"type": "tool_result", "payload": {"tool_name": "GetMetrics", "status": "success", "quality": "partial"}},
        {"type": "tool_result", "payload": {"tool_name": "SearchLog", "status": "error", "error": "timeout"}},
        {"type": "evidence_assessment", "payload": {"quality": "partial", "confidence": 0.4}},
    ]
    run_repo = _FakeRunRepo(
        runs=[{"run_id": "r1", "status": "handoff_required", "handoff_reason": "insufficient_evidence"}],
        events_map={"r1": run_events},
    )
    svc = HandoffSummaryService(agent_run_repository=run_repo)
    summary = svc.build_summary("r1", incident_id="inc-1")
    assert summary["run_id"] == "r1"
    assert summary["incident_id"] == "inc-1"
    assert len(summary["tools_attempted"]) == 1
    assert summary["tools_attempted"][0]["tool_name"] == "GetMetrics"
    assert len(summary["evidence_collected"]) >= 1
    assert len(summary["next_actions"]) > 0
    assert summary["handoff_reason"] == "insufficient_evidence"


def test_handoff_summary_missing_run():
    svc = HandoffSummaryService(agent_run_repository=_FakeRunRepo())
    summary = svc.build_summary("nonexistent")
    assert summary["error"] == "run_not_found"


# ---------------------------------------------------------------------------
# Analytics service
# ---------------------------------------------------------------------------


def test_analytics_detects_knowledge_gaps():
    runs = [
        {"run_id": f"r{i}", "status": "handoff_required", "handoff_reason": "missing_knowledge"}
        for i in range(5)
    ]
    svc = AnalyticsService(
        analytics_repository=_FakeAnalyticsRepo(),
        agent_run_repository=_FakeRunRepo(runs=runs),
        incident_repository=_FakeIncidentRepo(),
    )
    findings = svc.detect_findings(workspace_id="ws-1")
    categories = [f["category"] for f in findings]
    assert AnalyticsCategory.KNOWLEDGE_GAP in categories


def test_analytics_detects_tool_reliability():
    runs = [
        {"run_id": f"r{i}", "error_type": "timeout"}
        for i in range(4)
    ]
    svc = AnalyticsService(
        analytics_repository=_FakeAnalyticsRepo(),
        agent_run_repository=_FakeRunRepo(runs=runs),
        incident_repository=_FakeIncidentRepo(),
    )
    findings = svc.detect_findings(workspace_id="ws-1")
    categories = [f["category"] for f in findings]
    assert AnalyticsCategory.TOOL_RELIABILITY in categories


def test_analytics_detects_automation_candidates():
    runs = [
        {"run_id": f"r{i}", "duplicate_tool_call_count": 5}
        for i in range(3)
    ]
    svc = AnalyticsService(
        analytics_repository=_FakeAnalyticsRepo(),
        agent_run_repository=_FakeRunRepo(runs=runs),
        incident_repository=_FakeIncidentRepo(),
    )
    findings = svc.detect_findings(workspace_id="ws-1")
    categories = [f["category"] for f in findings]
    assert AnalyticsCategory.AUTOMATION_CANDIDATE in categories


def test_analytics_persist_findings():
    repo = _FakeAnalyticsRepo()
    svc = AnalyticsService(
        analytics_repository=repo,
        agent_run_repository=_FakeRunRepo(),
        incident_repository=_FakeIncidentRepo(),
    )
    findings = [
        {
            "category": "knowledge_gap",
            "title": "Test gap",
            "summary": "Test summary",
            "evidence_refs": [{"run_id": "r1"}],
        }
    ]
    ids = svc.persist_findings(workspace_id="ws-1", findings=findings)
    assert len(ids) == 1
    assert len(repo._findings) == 1


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def test_extract_evidence():
    events = [
        {"type": "tool_result", "payload": {"tool_name": "GetMetrics", "status": "success"}},
        {"type": "evidence_assessment", "payload": {"quality": "strong"}},
    ]
    evidence = _extract_evidence(events)
    assert len(evidence) == 2
    assert evidence[0]["tool_name"] == "GetMetrics"


def test_extract_tool_attempts():
    events = [
        {"type": "tool_call", "payload": {"tool_name": "GetMetrics", "arguments": {"metric": "cpu"}}},
    ]
    attempts = _extract_tool_attempts(events)
    assert len(attempts) == 1
    assert attempts[0]["tool_name"] == "GetMetrics"


def test_extract_failure_reasons():
    run = {"error_message": "timeout exceeded"}
    events = [{"type": "error", "payload": {"error": "connection refused"}}]
    reasons = _extract_failure_reasons(run, events)
    assert "timeout exceeded" in reasons
    assert "connection refused" in reasons


def test_suggest_next_actions_no_evidence():
    actions = _suggest_next_actions({"status": "handoff_required"}, [], ["error"])
    assert any("Collect missing evidence" in a for a in actions)
    assert any("Escalate" in a for a in actions)


def test_extract_confidence():
    events = [{"type": "evidence_assessment", "payload": {"confidence": 0.75}}]
    assert _extract_confidence(events) == 0.75


def test_extract_confidence_missing():
    assert _extract_confidence([]) == 0.0
