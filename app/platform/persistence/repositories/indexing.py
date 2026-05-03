"""Indexing task repository."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import sqlalchemy as sa
from sqlmodel import Session, col, select

from app.platform.persistence.database import get_engine
from app.platform.persistence.schema import IndexingTask


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _model_to_dict(obj: Any) -> dict[str, Any]:
    return {k: v for k, v in obj.__dict__.items() if k != "_sa_instance_state"}


class IndexingTaskRepository:
    """Indexing task repository."""

    ACTIVE_TASK_STATUSES = ("queued", "processing")
    ALLOWED_TASK_STATUSES = frozenset(
        {
            "queued",
            "processing",
            "completed",
            "failed_permanently",
        }
    )

    # ------------------------------------------------------------------
    # create_task
    # ------------------------------------------------------------------
    def create_task_with_session(
        self,
        db: Session,
        filename: str,
        file_path: str,
        *,
        max_retries: int,
    ) -> str:
        task_id = str(uuid.uuid4())
        now = _utc_now()
        task = IndexingTask(
            task_id=task_id,
            filename=filename,
            file_path=file_path,
            status="queued",
            attempt_count=0,
            max_retries=max_retries,
            created_at=now,
            updated_at=now,
        )
        db.add(task)
        return task_id

    def create_task(
        self,
        filename: str,
        file_path: str,
        *,
        max_retries: int,
    ) -> str:
        with Session(bind=get_engine()) as db:
            task_id = self.create_task_with_session(
                db, filename, file_path, max_retries=max_retries
            )
            db.commit()
        return task_id

    # ------------------------------------------------------------------
    # find_active_task_by_file_path
    # ------------------------------------------------------------------
    def find_active_task_by_file_path_with_session(
        self, db: Session, file_path: str
    ) -> dict[str, Any] | None:
        statement = (
            select(IndexingTask)
            .where(IndexingTask.file_path == file_path)
            .where(col(IndexingTask.status).in_(self.ACTIVE_TASK_STATUSES))
            .order_by(col(IndexingTask.created_at).desc())
            .limit(1)
        )
        row = db.exec(statement).first()
        return _model_to_dict(row) if row else None

    def find_active_task_by_file_path(self, file_path: str) -> dict[str, Any] | None:
        with Session(bind=get_engine()) as db:
            return self.find_active_task_by_file_path_with_session(db, file_path)

    # ------------------------------------------------------------------
    # update_task
    # ------------------------------------------------------------------
    def update_task_with_session(
        self,
        db: Session,
        task_id: str,
        *,
        status: str,
        error_message: str | None = None,
    ) -> None:
        task = db.get(IndexingTask, task_id)
        if task is None:
            return
        task.status = status
        task.error_message = error_message
        task.updated_at = _utc_now()
        db.add(task)

    def update_task(
        self,
        task_id: str,
        *,
        status: str,
        error_message: str | None = None,
    ) -> None:
        with Session(bind=get_engine()) as db:
            self.update_task_with_session(db, task_id, status=status, error_message=error_message)
            db.commit()

    # ------------------------------------------------------------------
    # get_task
    # ------------------------------------------------------------------
    def get_task_with_session(self, db: Session, task_id: str) -> dict[str, Any] | None:
        task = db.get(IndexingTask, task_id)
        return _model_to_dict(task) if task else None

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        with Session(bind=get_engine()) as db:
            return self.get_task_with_session(db, task_id)

    # ------------------------------------------------------------------
    # claim_task
    # ------------------------------------------------------------------
    def claim_task_with_session(self, db: Session, task_id: str) -> dict[str, Any] | None:
        """Claim a queued task within an existing session (no commit)."""
        now = _utc_now()
        stmt = (
            sa.update(IndexingTask)
            .where(
                col(IndexingTask.task_id) == task_id,
                col(IndexingTask.status) == "queued",
            )
            .values(
                status="processing",
                updated_at=now,
                error_message=None,
                attempt_count=IndexingTask.attempt_count + 1,
            )
        )
        result = db.exec(stmt)
        if result.rowcount == 0:
            return None
        task = db.get(IndexingTask, task_id)
        return _model_to_dict(task) if task else None

    def claim_task(self, task_id: str) -> dict[str, Any] | None:
        """Claim a queued task."""
        with Session(bind=get_engine()) as db:
            result = self.claim_task_with_session(db, task_id)
            db.commit()
        return result

    # ------------------------------------------------------------------
    # list_tasks_by_status
    # ------------------------------------------------------------------
    def list_tasks_by_status_with_session(
        self, db: Session, statuses: list[str]
    ) -> list[dict[str, Any]]:
        if not statuses:
            return []

        invalid_statuses = [s for s in statuses if s not in self.ALLOWED_TASK_STATUSES]
        if invalid_statuses:
            raise ValueError(f"Unsupported task statuses: {', '.join(invalid_statuses)}")

        normalized_statuses = list(dict.fromkeys(statuses))
        statement = (
            select(IndexingTask)
            .where(col(IndexingTask.status).in_(normalized_statuses))
            .order_by(col(IndexingTask.created_at).asc())
        )
        rows = db.exec(statement).all()
        return [_model_to_dict(row) for row in rows]

    def list_tasks_by_status(self, statuses: list[str]) -> list[dict[str, Any]]:
        with Session(bind=get_engine()) as db:
            return self.list_tasks_by_status_with_session(db, statuses)

    # ------------------------------------------------------------------
    # claim_next_queued_task
    # ------------------------------------------------------------------
    def claim_next_queued_task_with_session(self, db: Session) -> dict[str, Any] | None:
        statement = (
            select(IndexingTask)
            .where(IndexingTask.status == "queued")
            .order_by(col(IndexingTask.created_at).asc())
            .limit(1)
        )
        row = db.exec(statement).first()
        if row is None:
            return None
        return self.claim_task_with_session(db, row.task_id)

    def claim_next_queued_task(self) -> dict[str, Any] | None:
        with Session(bind=get_engine()) as db:
            result = self.claim_next_queued_task_with_session(db)
            db.commit()
        return result

    # ------------------------------------------------------------------
    # mark_retry_or_failed
    # ------------------------------------------------------------------
    def mark_retry_or_failed_with_session(
        self, db: Session, task_id: str, error_message: str
    ) -> dict[str, Any] | None:
        task = db.get(IndexingTask, task_id)
        if task is None:
            return None
        next_status = "failed_permanently" if task.attempt_count >= task.max_retries else "queued"
        task.status = next_status
        task.error_message = error_message
        task.updated_at = _utc_now()
        db.add(task)
        db.flush()
        db.refresh(task)
        return _model_to_dict(task)

    def mark_retry_or_failed(self, task_id: str, error_message: str) -> dict[str, Any] | None:
        with Session(bind=get_engine()) as db:
            result = self.mark_retry_or_failed_with_session(db, task_id, error_message)
            db.commit()
        return result

    # ------------------------------------------------------------------
    # requeue_stale_processing_tasks
    # ------------------------------------------------------------------
    def requeue_stale_processing_tasks_with_session(self, db: Session, timeout_seconds: int) -> int:
        threshold = datetime.now(UTC) - timedelta(seconds=timeout_seconds)
        requeued = 0
        statement = select(IndexingTask).where(IndexingTask.status == "processing")
        rows = db.exec(statement).all()

        for row in rows:
            if row.updated_at <= threshold:
                next_status = (
                    "failed_permanently" if row.attempt_count >= row.max_retries else "queued"
                )
                row.status = next_status
                row.updated_at = _utc_now()
                row.error_message = (
                    "Task requeued after worker timeout"
                    if next_status == "queued"
                    else "Task exceeded retry limit after worker timeout"
                )
                db.add(row)
                requeued += 1

        return requeued

    def requeue_stale_processing_tasks(self, timeout_seconds: int) -> int:
        with Session(bind=get_engine()) as db:
            requeued = self.requeue_stale_processing_tasks_with_session(db, timeout_seconds)
            db.commit()
        return requeued


indexing_task_repository = IndexingTaskRepository()
