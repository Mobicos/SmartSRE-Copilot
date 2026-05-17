"""Incident context, timeline, handoff summary, and analytics API routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.providers import (
    get_analytics_service,
    get_handoff_summary_service,
    get_incident_context_service,
    get_incident_timeline_service,
)

router = APIRouter(prefix="/incidents", tags=["incidents"])


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------


class IncidentCreateRequest(BaseModel):
    workspace_id: str
    title: str
    severity: str = "P2"
    source: str = "manual"
    service_name: str | None = None
    owner: str | None = None
    summary: str | None = None


class IncidentLinkRequest(BaseModel):
    target_type: str
    target_id: str
    relationship: str


class IncidentStatusUpdate(BaseModel):
    status: str
    summary: str | None = None


class IncidentResponse(BaseModel):
    incident_id: str
    workspace_id: str
    title: str
    severity: str
    status: str
    source: str
    service_name: str | None = None
    owner: str | None = None
    summary: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    resolved_at: str | None = None


class TimelineEventResponse(BaseModel):
    incident_id: str
    event_id: str
    source: str
    event_type: str
    title: str
    summary: str
    actor: str
    created_at: str
    refs: dict[str, Any] = Field(default_factory=dict)


class HandoffSummaryResponse(BaseModel):
    run_id: str
    incident_id: str | None = None
    evidence_collected: list[dict[str, Any]] = Field(default_factory=list)
    tools_attempted: list[dict[str, Any]] = Field(default_factory=list)
    failure_reasons: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    handoff_reason: str = ""


class AnalyticsFindingResponse(BaseModel):
    finding_id: str
    workspace_id: str
    category: str
    title: str
    summary: str
    evidence_refs: list[dict[str, Any]] = Field(default_factory=list)
    status: str = "open"
    created_at: str | None = None


# ---------------------------------------------------------------------------
# Incident CRUD
# ---------------------------------------------------------------------------


@router.post("/", response_model=IncidentResponse)
def create_incident(
    body: IncidentCreateRequest,
    svc: Any = Depends(get_incident_context_service),
) -> dict[str, Any]:
    result = svc.create_incident(
        workspace_id=body.workspace_id,
        title=body.title,
        severity=body.severity,
        source=body.source,
        service_name=body.service_name,
        owner=body.owner,
        summary=body.summary,
    )
    return result


@router.get("/", response_model=list[IncidentResponse])
def list_incidents(
    workspace_id: str | None = None,
    status: str | None = None,
    limit: int = 50,
    svc: Any = Depends(get_incident_context_service),
) -> list[dict[str, Any]]:
    return svc.list_incidents(workspace_id=workspace_id, status=status, limit=limit)


@router.get("/{incident_id}", response_model=IncidentResponse)
def get_incident(
    incident_id: str,
    svc: Any = Depends(get_incident_context_service),
) -> dict[str, Any]:
    result = svc.get_incident(incident_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    return result


@router.patch("/{incident_id}/status")
def update_incident_status(
    incident_id: str,
    body: IncidentStatusUpdate,
    svc: Any = Depends(get_incident_context_service),
) -> dict[str, str]:
    svc.update_status(incident_id, body.status, summary=body.summary)
    return {"status": "updated", "incident_id": incident_id}


# ---------------------------------------------------------------------------
# Incident links
# ---------------------------------------------------------------------------


@router.post("/{incident_id}/links")
def add_incident_link(
    incident_id: str,
    body: IncidentLinkRequest,
    svc: Any = Depends(get_incident_context_service),
) -> dict[str, str]:
    link_id = svc._incident_repo.add_link(
        incident_id=incident_id,
        target_type=body.target_type,
        target_id=body.target_id,
        relationship=body.relationship,
    )
    return {"link_id": link_id, "incident_id": incident_id}


@router.get("/{incident_id}/links")
def list_incident_links(
    incident_id: str,
    svc: Any = Depends(get_incident_context_service),
) -> list[dict[str, Any]]:
    return svc._incident_repo.list_links(incident_id)


# ---------------------------------------------------------------------------
# Timeline
# ---------------------------------------------------------------------------


@router.get("/{incident_id}/timeline", response_model=list[TimelineEventResponse])
def get_incident_timeline(
    incident_id: str,
    svc: Any = Depends(get_incident_timeline_service),
) -> list[dict[str, Any]]:
    return svc.build_timeline(incident_id)


# ---------------------------------------------------------------------------
# Handoff summary
# ---------------------------------------------------------------------------


@router.get("/handoff/{run_id}", response_model=HandoffSummaryResponse)
def get_handoff_summary(
    run_id: str,
    incident_id: str | None = None,
    svc: Any = Depends(get_handoff_summary_service),
) -> dict[str, Any]:
    return svc.build_summary(run_id, incident_id=incident_id)


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------


@router.get("/analytics/findings", response_model=list[AnalyticsFindingResponse])
def list_analytics_findings(
    workspace_id: str | None = None,
    category: str | None = None,
    limit: int = 50,
    svc: Any = Depends(get_analytics_service),
) -> list[dict[str, Any]]:
    return svc.list_findings(workspace_id=workspace_id, category=category, limit=limit)
