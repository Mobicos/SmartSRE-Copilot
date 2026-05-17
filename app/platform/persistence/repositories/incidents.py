"""Repositories for incidents, incident links, and analytics findings."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlmodel import Session, col, select

from app.platform.persistence.database import get_engine
from app.platform.persistence.tables.agent import (
    AnalyticsFindingTable,
    IncidentLinkTable,
    IncidentTable,
)


class IncidentRepository:
    """CRUD for incidents and incident links."""

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
    ) -> str:
        incident_id = f"inc-{uuid.uuid4().hex[:12]}"
        now = datetime.now(UTC)
        with Session(get_engine()) as session:
            row = IncidentTable(
                incident_id=incident_id,
                workspace_id=workspace_id,
                title=title,
                severity=severity,
                status="open",
                source=source,
                service_name=service_name,
                owner=owner,
                summary=summary,
                created_at=now,
                updated_at=now,
            )
            session.add(row)
            session.commit()
        return incident_id

    def get_incident(self, incident_id: str) -> dict[str, Any] | None:
        with Session(get_engine()) as session:
            row = session.get(IncidentTable, incident_id)
            if row is None:
                return None
            return _incident_to_dict(row)

    def list_incidents(
        self,
        *,
        workspace_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        stmt = select(IncidentTable)
        if workspace_id:
            stmt = stmt.where(IncidentTable.workspace_id == workspace_id)
        if status:
            stmt = stmt.where(IncidentTable.status == status)
        stmt = stmt.order_by(col(IncidentTable.created_at).desc()).limit(limit)
        with Session(get_engine()) as session:
            rows = session.exec(stmt).all()
            return [_incident_to_dict(r) for r in rows]

    def update_incident_status(
        self, incident_id: str, status: str, *, summary: str | None = None
    ) -> None:
        with Session(get_engine()) as session:
            row = session.get(IncidentTable, incident_id)
            if row is None:
                return
            row.status = status
            row.updated_at = datetime.now(UTC)
            if status in ("resolved", "closed"):
                row.resolved_at = datetime.now(UTC)
            if summary is not None:
                row.summary = summary
            session.add(row)
            session.commit()

    def add_link(
        self,
        *,
        incident_id: str,
        target_type: str,
        target_id: str,
        relationship: str,
    ) -> str:
        link_id = f"il-{uuid.uuid4().hex[:12]}"
        now = datetime.now(UTC)
        with Session(get_engine()) as session:
            row = IncidentLinkTable(
                link_id=link_id,
                incident_id=incident_id,
                target_type=target_type,
                target_id=target_id,
                relationship=relationship,
                created_at=now,
            )
            session.add(row)
            session.commit()
        return link_id

    def list_links(self, incident_id: str) -> list[dict[str, Any]]:
        stmt = (
            select(IncidentLinkTable)
            .where(IncidentLinkTable.incident_id == incident_id)
            .order_by(col(IncidentLinkTable.created_at).asc())
        )
        with Session(get_engine()) as session:
            rows = session.exec(stmt).all()
            return [_link_to_dict(r) for r in rows]

    def find_links_by_target(self, target_type: str, target_id: str) -> list[dict[str, Any]]:
        stmt = select(IncidentLinkTable).where(
            IncidentLinkTable.target_type == target_type,
            IncidentLinkTable.target_id == target_id,
        )
        with Session(get_engine()) as session:
            rows = session.exec(stmt).all()
            return [_link_to_dict(r) for r in rows]


class AnalyticsRepository:
    """CRUD for analytics findings."""

    def create_finding(
        self,
        *,
        workspace_id: str,
        category: str,
        title: str,
        summary: str,
        evidence_refs: list[dict[str, Any]] | None = None,
    ) -> str:
        finding_id = f"af-{uuid.uuid4().hex[:12]}"
        now = datetime.now(UTC)
        with Session(get_engine()) as session:
            row = AnalyticsFindingTable(
                finding_id=finding_id,
                workspace_id=workspace_id,
                category=category,
                title=title,
                summary=summary,
                evidence_refs=evidence_refs or [],
                status="open",
                created_at=now,
                updated_at=now,
            )
            session.add(row)
            session.commit()
        return finding_id

    def list_findings(
        self,
        *,
        workspace_id: str | None = None,
        category: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        stmt = select(AnalyticsFindingTable)
        if workspace_id:
            stmt = stmt.where(AnalyticsFindingTable.workspace_id == workspace_id)
        if category:
            stmt = stmt.where(AnalyticsFindingTable.category == category)
        if status:
            stmt = stmt.where(AnalyticsFindingTable.status == status)
        stmt = stmt.order_by(col(AnalyticsFindingTable.created_at).desc()).limit(limit)
        with Session(get_engine()) as session:
            rows = session.exec(stmt).all()
            return [_finding_to_dict(r) for r in rows]

    def update_finding_status(self, finding_id: str, status: str) -> None:
        with Session(get_engine()) as session:
            row = session.get(AnalyticsFindingTable, finding_id)
            if row is None:
                return
            row.status = status
            row.updated_at = datetime.now(UTC)
            session.add(row)
            session.commit()


def _incident_to_dict(row: IncidentTable) -> dict[str, Any]:
    return {
        "incident_id": row.incident_id,
        "workspace_id": row.workspace_id,
        "title": row.title,
        "severity": row.severity,
        "service_name": row.service_name,
        "owner": row.owner,
        "status": row.status,
        "source": row.source,
        "summary": row.summary,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        "resolved_at": row.resolved_at.isoformat() if row.resolved_at else None,
    }


def _link_to_dict(row: IncidentLinkTable) -> dict[str, Any]:
    return {
        "link_id": row.link_id,
        "incident_id": row.incident_id,
        "target_type": row.target_type,
        "target_id": row.target_id,
        "relationship": row.relationship,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _finding_to_dict(row: AnalyticsFindingTable) -> dict[str, Any]:
    return {
        "finding_id": row.finding_id,
        "workspace_id": row.workspace_id,
        "category": row.category,
        "title": row.title,
        "summary": row.summary,
        "evidence_refs": row.evidence_refs if isinstance(row.evidence_refs, list) else [],
        "status": row.status,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }
