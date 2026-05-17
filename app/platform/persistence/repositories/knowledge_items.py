"""Repositories for knowledge items and skill manifests."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlmodel import Session, col, select

from app.platform.persistence.database import get_engine
from app.platform.persistence.tables.agent import (
    KnowledgeAuditLogTable,
    KnowledgeItemTable,
    SkillManifestTable,
)


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _model_to_dict(obj: Any) -> dict[str, Any]:
    return {k: v for k, v in obj.__dict__.items() if k != "_sa_instance_state"}


class KnowledgeItemRepository:
    """CRUD + dedup queries for knowledge_items table."""

    def create(
        self,
        *,
        knowledge_base_id: str,
        item_type: str,
        title: str,
        content: str,
        dedup_hash: str,
        confidence: float = 0.5,
        source_run_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        created_by: str | None = None,
    ) -> int:
        now = _utc_now()
        with Session(bind=get_engine()) as db:
            item = KnowledgeItemTable(
                knowledge_base_id=knowledge_base_id,
                item_type=item_type,
                title=title,
                content=content,
                dedup_hash=dedup_hash,
                confidence=confidence,
                source_run_id=source_run_id,
                item_metadata=metadata,
                created_by=created_by,
                status="draft",
                created_at=now,
                updated_at=now,
            )
            db.add(item)
            db.commit()
            db.refresh(item)
            return int(item.id)

    def get(self, item_id: int) -> dict[str, Any] | None:
        with Session(bind=get_engine()) as db:
            row = db.get(KnowledgeItemTable, item_id)
            return _model_to_dict(row) if row else None

    def list_by_type(
        self,
        knowledge_base_id: str,
        item_type: str,
        *,
        status: str = "published",
    ) -> list[dict[str, Any]]:
        with Session(bind=get_engine()) as db:
            stmt = (
                select(KnowledgeItemTable)
                .where(KnowledgeItemTable.knowledge_base_id == knowledge_base_id)
                .where(KnowledgeItemTable.item_type == item_type)
                .where(KnowledgeItemTable.status == status)
                .order_by(col(KnowledgeItemTable.created_at).desc())
            )
            rows = db.exec(stmt).all()
            return [_model_to_dict(r) for r in rows]

    def list_drafts(self, knowledge_base_id: str) -> list[dict[str, Any]]:
        with Session(bind=get_engine()) as db:
            stmt = (
                select(KnowledgeItemTable)
                .where(KnowledgeItemTable.knowledge_base_id == knowledge_base_id)
                .where(KnowledgeItemTable.status == "draft")
                .order_by(col(KnowledgeItemTable.created_at).desc())
            )
            rows = db.exec(stmt).all()
            return [_model_to_dict(r) for r in rows]

    def update_status(
        self,
        item_id: int,
        status: str,
        *,
        published_by: str | None = None,
    ) -> None:
        now = _utc_now()
        with Session(bind=get_engine()) as db:
            row = db.get(KnowledgeItemTable, item_id)
            if row is None:
                return
            row.status = status
            row.updated_at = now
            if status == "published" and published_by:
                row.published_by = published_by
                row.published_at = now
            db.add(row)
            db.commit()

    def find_by_dedup_hash(self, knowledge_base_id: str, dedup_hash: str) -> dict[str, Any] | None:
        with Session(bind=get_engine()) as db:
            stmt = (
                select(KnowledgeItemTable)
                .where(KnowledgeItemTable.knowledge_base_id == knowledge_base_id)
                .where(KnowledgeItemTable.dedup_hash == dedup_hash)
                .where(KnowledgeItemTable.status != "archived")
                .limit(1)
            )
            row = db.exec(stmt).first()
            return _model_to_dict(row) if row else None

    def count_by_type(self, knowledge_base_id: str) -> dict[str, int]:
        with Session(bind=get_engine()) as db:
            stmt = (
                select(KnowledgeItemTable.item_type, KnowledgeItemTable.id)
                .where(KnowledgeItemTable.knowledge_base_id == knowledge_base_id)
                .where(KnowledgeItemTable.status == "published")
            )
            rows = db.exec(stmt).all()
            counts: dict[str, int] = {}
            for item_type, _ in rows:
                counts[item_type] = counts.get(item_type, 0) + 1
            return counts

    def log_audit(
        self,
        *,
        item_id: int,
        action: str,
        actor: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        now = _utc_now()
        with Session(bind=get_engine()) as db:
            db.add(
                KnowledgeAuditLogTable(
                    item_id=item_id,
                    action=action,
                    actor=actor,
                    audit_details=details,
                    created_at=now,
                )
            )
            db.commit()


class SkillManifestRepository:
    """CRUD for skill_manifests table."""

    def list_active(self) -> list[dict[str, Any]]:
        with Session(bind=get_engine()) as db:
            stmt = (
                select(SkillManifestTable)
                .where(SkillManifestTable.status == "active")
                .order_by(col(SkillManifestTable.skill_id).asc())
            )
            rows = db.exec(stmt).all()
            return [_model_to_dict(r) for r in rows]

    def get(self, skill_id: str) -> dict[str, Any] | None:
        with Session(bind=get_engine()) as db:
            stmt = select(SkillManifestTable).where(SkillManifestTable.skill_id == skill_id)
            row = db.exec(stmt).first()
            return _model_to_dict(row) if row else None

    def upsert(self, manifest: dict[str, Any]) -> None:
        now = _utc_now()
        with Session(bind=get_engine()) as db:
            stmt = select(SkillManifestTable).where(
                SkillManifestTable.skill_id == manifest["skill_id"]
            )
            existing = db.exec(stmt).first()
            if existing:
                for key in [
                    "name",
                    "description",
                    "trigger_conditions",
                    "diagnostic_steps",
                    "recommended_tools",
                    "evidence_requirements",
                    "risk_warnings",
                    "report_template",
                    "input_schema",
                    "output_schema",
                    "degradation_strategy",
                    "version",
                ]:
                    if key in manifest:
                        setattr(existing, key, manifest[key])
                existing.updated_at = now
                db.add(existing)
            else:
                db.add(
                    SkillManifestTable(
                        skill_id=manifest["skill_id"],
                        name=manifest["name"],
                        description=manifest.get("description"),
                        trigger_conditions=manifest["trigger_conditions"],
                        diagnostic_steps=manifest["diagnostic_steps"],
                        recommended_tools=manifest["recommended_tools"],
                        evidence_requirements=manifest["evidence_requirements"],
                        risk_warnings=manifest["risk_warnings"],
                        report_template=manifest.get("report_template"),
                        input_schema=manifest.get("input_schema"),
                        output_schema=manifest.get("output_schema"),
                        degradation_strategy=manifest.get("degradation_strategy"),
                        version=manifest.get("version", "1.0.0"),
                        status=manifest.get("status", "active"),
                        created_at=now,
                        updated_at=now,
                    )
                )
            db.commit()
