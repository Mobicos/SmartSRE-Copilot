"""AIOps run and event repositories."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlmodel import Session, col, select

from app.platform.persistence.database import get_engine
from app.platform.persistence.schema import AIOpsRun, AIOpsRunEvent


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _model_to_dict(obj: Any) -> dict[str, Any]:
    return {k: v for k, v in obj.__dict__.items() if k != "_sa_instance_state"}


class AIOpsRunRepository:
    """AIOps run repository."""

    def create_run_with_session(self, db: Session, session_id: str, task_input: str) -> str:
        run_id = str(uuid.uuid4())
        now = _utc_now()
        run = AIOpsRun(
            run_id=run_id,
            session_id=session_id,
            status="running",
            task_input=task_input,
            created_at=now,
            updated_at=now,
        )
        db.add(run)
        return run_id

    def create_run(self, session_id: str, task_input: str) -> str:
        with Session(bind=get_engine()) as db:
            run_id = self.create_run_with_session(db, session_id, task_input)
            db.commit()
        return run_id

    def update_run_with_session(
        self,
        db: Session,
        run_id: str,
        *,
        status: str,
        report: str | None = None,
        error_message: str | None = None,
    ) -> None:
        run = db.get(AIOpsRun, run_id)
        if run is None:
            return
        run.status = status
        if report is not None:
            run.report = report
        if error_message is not None:
            run.error_message = error_message
        run.updated_at = _utc_now()
        db.add(run)

    def update_run(
        self,
        run_id: str,
        *,
        status: str,
        report: str | None = None,
        error_message: str | None = None,
    ) -> None:
        with Session(bind=get_engine()) as db:
            self.update_run_with_session(
                db, run_id, status=status, report=report, error_message=error_message
            )
            db.commit()

    def get_run_with_session(self, db: Session, run_id: str) -> dict[str, Any] | None:
        run = db.get(AIOpsRun, run_id)
        return _model_to_dict(run) if run else None

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with Session(bind=get_engine()) as db:
            return self.get_run_with_session(db, run_id)

    def append_event_with_session(
        self,
        db: Session,
        run_id: str,
        *,
        event_type: str,
        stage: str,
        message: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        event = AIOpsRunEvent(
            run_id=run_id,
            event_type=event_type,
            stage=stage,
            message=message,
            payload=json.dumps(payload, ensure_ascii=False) if payload is not None else None,
            created_at=_utc_now(),
        )
        db.add(event)

    def append_event(
        self,
        run_id: str,
        *,
        event_type: str,
        stage: str,
        message: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        with Session(bind=get_engine()) as db:
            self.append_event_with_session(
                db, run_id, event_type=event_type, stage=stage, message=message, payload=payload
            )
            db.commit()

    def list_events_with_session(self, db: Session, run_id: str) -> list[dict[str, Any]]:
        statement = (
            select(AIOpsRunEvent)
            .where(AIOpsRunEvent.run_id == run_id)
            .order_by(col(AIOpsRunEvent.created_at).asc(), col(AIOpsRunEvent.id).asc())
        )
        rows = db.exec(statement).all()
        events: list[dict[str, Any]] = []
        for row in rows:
            payload = row.payload
            events.append(
                {
                    "id": row.id,
                    "runId": row.run_id,
                    "type": row.event_type,
                    "stage": row.stage,
                    "message": row.message,
                    "payload": json.loads(payload) if payload else None,
                    "createdAt": row.created_at,
                }
            )
        return events

    def list_events(self, run_id: str) -> list[dict[str, Any]]:
        with Session(bind=get_engine()) as db:
            return self.list_events_with_session(db, run_id)


aiops_run_repository = AIOpsRunRepository()
