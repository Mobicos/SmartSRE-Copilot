"""Domain models for incident context, timeline, handoff summary, and analytics."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class IncidentSeverity(StrEnum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"


class IncidentStatus(StrEnum):
    OPEN = "open"
    INVESTIGATING = "investigating"
    MITIGATED = "mitigated"
    RESOLVED = "resolved"
    CLOSED = "closed"


class IncidentSource(StrEnum):
    MANUAL = "manual"
    ALERT = "alert"
    PROACTIVE_PROBE = "proactive_probe"


class IncidentLinkTarget(StrEnum):
    AGENT_RUN = "agent_run"
    FEEDBACK = "feedback"
    KNOWLEDGE = "knowledge"
    ALERT = "alert"
    TICKET = "ticket"


class AnalyticsCategory(StrEnum):
    KNOWLEDGE_GAP = "knowledge_gap"
    MONITORING_GAP = "monitoring_gap"
    AUTOMATION_CANDIDATE = "automation_candidate"
    TOOL_RELIABILITY = "tool_reliability"
    PRODUCT_DEFECT = "product_defect"


@dataclass(frozen=True)
class Incident:
    incident_id: str
    workspace_id: str
    title: str
    severity: str
    status: str
    source: str
    service_name: str | None = None
    owner: str | None = None
    summary: str | None = None
    resolved_at: str | None = None


@dataclass(frozen=True)
class IncidentLink:
    link_id: str
    incident_id: str
    target_type: str
    target_id: str
    relationship: str


@dataclass(frozen=True)
class IncidentTimelineEvent:
    incident_id: str
    event_id: str
    source: str
    event_type: str
    title: str
    summary: str
    actor: str
    created_at: str
    refs: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class HandoffSummary:
    run_id: str
    incident_id: str | None
    evidence_collected: list[dict[str, Any]]
    tools_attempted: list[dict[str, Any]]
    failure_reasons: list[str]
    next_actions: list[str]
    confidence: float
    handoff_reason: str


@dataclass(frozen=True)
class AnalyticsFinding:
    finding_id: str
    workspace_id: str
    category: str
    title: str
    summary: str
    evidence_refs: list[dict[str, Any]]
    status: str = "open"
