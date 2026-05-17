"""SQLite-based unit tests for repository _with_session methods.

Uses an in-memory SQLite database to test all _with_session repository methods
without requiring a live PostgreSQL instance. pgvector-specific raw SQL methods
(search_memory_vector, increment_validation_count) are skipped.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, event
from sqlmodel import Session, SQLModel

from app.platform.persistence.repositories.native_agent import (
    AgentFeedbackRepository,
    AgentMemoryRepository,
    AgentRunRepository,
    KnowledgeBaseRepository,
    SceneRepository,
    ToolPolicyRepository,
    WorkspaceRepository,
)
from app.platform.persistence.schema import (
    AgentFeedback,
    AgentMemory,
    AgentRun,
    KnowledgeBase,
    Scene,
    ToolPolicy,
    Workspace,
)


@pytest.fixture
def sqlite_session():
    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, _connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    SQLModel.metadata.create_all(engine)
    with Session(bind=engine) as session:
        yield session


def _now() -> datetime:
    return datetime.now(UTC)


def _create_workspace(db: Session, workspace_id: str = "ws-test") -> None:
    db.add(
        Workspace(
            workspace_id=workspace_id,
            name="Test Workspace",
            created_at=_now(),
            updated_at=_now(),
        )
    )
    db.flush()


# ---------------------------------------------------------------------------
# WorkspaceRepository
# ---------------------------------------------------------------------------


class TestWorkspaceRepositorySQLite:
    def test_create_and_get(self, sqlite_session):
        repo = WorkspaceRepository()
        wid = repo.create_workspace_with_session(sqlite_session, name="WS1", description="desc")
        result = repo.get_workspace_with_session(sqlite_session, wid)
        assert result is not None
        assert result["name"] == "WS1"
        assert result["description"] == "desc"

    def test_get_nonexistent_returns_none(self, sqlite_session):
        repo = WorkspaceRepository()
        assert repo.get_workspace_with_session(sqlite_session, "no-such-id") is None

    def test_list_workspaces(self, sqlite_session):
        repo = WorkspaceRepository()
        repo.create_workspace_with_session(sqlite_session, name="A")
        repo.create_workspace_with_session(sqlite_session, name="B")
        sqlite_session.commit()
        result = repo.list_workspaces_with_session(sqlite_session)
        assert len(result) == 2


# ---------------------------------------------------------------------------
# KnowledgeBaseRepository
# ---------------------------------------------------------------------------


class TestKnowledgeBaseRepositorySQLite:
    def test_create_and_list(self, sqlite_session):
        _create_workspace(sqlite_session)
        repo = KnowledgeBaseRepository()
        repo.create_knowledge_base_with_session(sqlite_session, "ws-test", name="KB1")
        sqlite_session.commit()
        result = repo.list_by_workspace_with_session(sqlite_session, "ws-test")
        assert len(result) == 1
        assert result[0]["name"] == "KB1"

    def test_get_many_empty_list(self, sqlite_session):
        repo = KnowledgeBaseRepository()
        assert repo.get_many_with_session(sqlite_session, []) == []

    def test_get_many(self, sqlite_session):
        _create_workspace(sqlite_session)
        repo = KnowledgeBaseRepository()
        kb1 = repo.create_knowledge_base_with_session(sqlite_session, "ws-test", name="A")
        kb2 = repo.create_knowledge_base_with_session(sqlite_session, "ws-test", name="B")
        sqlite_session.commit()
        result = repo.get_many_with_session(sqlite_session, [kb1, kb2])
        assert len(result) == 2

    def test_row_to_dict(self, sqlite_session):
        _create_workspace(sqlite_session)
        repo = KnowledgeBaseRepository()
        kb_id = repo.create_knowledge_base_with_session(
            sqlite_session, "ws-test", name="KB", description="d", version="1.0"
        )
        row = sqlite_session.get(KnowledgeBase, kb_id)
        d = KnowledgeBaseRepository._row_to_dict(row)
        assert d["name"] == "KB"
        assert d["version"] == "1.0"


# ---------------------------------------------------------------------------
# SceneRepository
# ---------------------------------------------------------------------------


class TestSceneRepositorySQLite:
    def test_create_scene(self, sqlite_session):
        _create_workspace(sqlite_session)
        repo = SceneRepository()
        scene_id = repo.create_scene_with_session(sqlite_session, "ws-test", name="Scene1")
        sqlite_session.commit()
        result = repo.get_scene_with_session(sqlite_session, scene_id)
        assert result is not None
        assert result["name"] == "Scene1"

    def test_get_nonexistent_returns_none(self, sqlite_session):
        repo = SceneRepository()
        assert repo.get_scene_with_session(sqlite_session, "no-such") is None

    def test_list_scenes_without_workspace_filter(self, sqlite_session):
        _create_workspace(sqlite_session)
        repo = SceneRepository()
        repo.create_scene_with_session(sqlite_session, "ws-test", name="S1")
        repo.create_scene_with_session(sqlite_session, "ws-test", name="S2")
        sqlite_session.commit()
        result = repo.list_scenes_with_session(sqlite_session)
        assert len(result) == 2

    def test_list_scenes_with_workspace_filter(self, sqlite_session):
        _create_workspace(sqlite_session)
        _create_workspace(sqlite_session, "ws-other")
        repo = SceneRepository()
        repo.create_scene_with_session(sqlite_session, "ws-test", name="S1")
        repo.create_scene_with_session(sqlite_session, "ws-other", name="S2")
        sqlite_session.commit()
        result = repo.list_scenes_with_session(sqlite_session, workspace_id="ws-test")
        assert len(result) == 1

    def test_delete_scene(self, sqlite_session):
        _create_workspace(sqlite_session)
        repo = SceneRepository()
        scene_id = repo.create_scene_with_session(sqlite_session, "ws-test", name="ToDelete")
        sqlite_session.commit()
        deleted = repo.delete_scene_with_session(sqlite_session, scene_id)
        assert deleted is True
        sqlite_session.flush()
        assert repo.get_scene_with_session(sqlite_session, scene_id) is None

    def test_delete_nonexistent_returns_false(self, sqlite_session):
        repo = SceneRepository()
        assert repo.delete_scene_with_session(sqlite_session, "no-such") is False

    def test_delete_scenes_by_name_prefix(self, sqlite_session):
        """Tests delete_scene_with_session indirectly — verifies delete works within session."""
        _create_workspace(sqlite_session)
        repo = SceneRepository()
        s1 = repo.create_scene_with_session(sqlite_session, "ws-test", name="test_s1")
        s2 = repo.create_scene_with_session(sqlite_session, "ws-test", name="test_s2")
        sqlite_session.commit()
        # Use delete_scene_with_session directly (delete_scenes_by_name_prefix uses get_engine)
        deleted = repo.delete_scene_with_session(sqlite_session, s1)
        assert deleted is True
        deleted = repo.delete_scene_with_session(sqlite_session, s2)
        assert deleted is True
        sqlite_session.commit()
        remaining = repo.list_scenes_with_session(sqlite_session)
        assert len(remaining) == 0

    def test_row_to_dict_without_links(self, sqlite_session):
        _create_workspace(sqlite_session)
        repo = SceneRepository()
        sid = repo.create_scene_with_session(
            sqlite_session, "ws-test", name="S", agent_config={"key": "val"}
        )
        row = sqlite_session.get(Scene, sid)
        d = SceneRepository._row_to_dict(row, include_links=False)
        assert d["name"] == "S"
        assert "knowledge_bases" not in d

    def test_row_to_dict_with_links(self, sqlite_session):
        _create_workspace(sqlite_session)
        repo = SceneRepository()
        sid = repo.create_scene_with_session(sqlite_session, "ws-test", name="S")
        row = sqlite_session.get(Scene, sid)
        d = SceneRepository._row_to_dict(row, include_links=True)
        assert "knowledge_bases" in d
        assert "tools" in d


# ---------------------------------------------------------------------------
# ToolPolicyRepository
# ---------------------------------------------------------------------------


class TestToolPolicyRepositorySQLite:
    def test_upsert_new(self, sqlite_session):
        repo = ToolPolicyRepository()
        result = repo.upsert_policy_with_session(
            sqlite_session, "SearchLog", scope="diagnosis", risk_level="low"
        )
        assert result["tool_name"] == "SearchLog"
        assert result["enabled"] is True

    def test_upsert_update(self, sqlite_session):
        repo = ToolPolicyRepository()
        repo.upsert_policy_with_session(sqlite_session, "Log", risk_level="low")
        updated = repo.upsert_policy_with_session(sqlite_session, "Log", risk_level="high")
        assert updated["risk_level"] == "high"

    def test_get_policy(self, sqlite_session):
        repo = ToolPolicyRepository()
        repo.upsert_policy_with_session(sqlite_session, "CheckCPU")
        result = repo.get_policy_with_session(sqlite_session, "CheckCPU")
        assert result is not None
        assert result["tool_name"] == "CheckCPU"

    def test_get_policy_nonexistent(self, sqlite_session):
        repo = ToolPolicyRepository()
        assert repo.get_policy_with_session(sqlite_session, "no-such") is None

    def test_list_policies(self, sqlite_session):
        repo = ToolPolicyRepository()
        repo.upsert_policy_with_session(sqlite_session, "A")
        repo.upsert_policy_with_session(sqlite_session, "B")
        sqlite_session.commit()
        result = repo.list_policies_with_session(sqlite_session)
        assert len(result) == 2

    def test_row_to_dict(self, sqlite_session):
        now = _now()
        row = ToolPolicy(
            tool_name="T",
            scope="chat",
            risk_level="high",
            capability="run",
            enabled=True,
            approval_required=True,
            created_at=now,
            updated_at=now,
        )
        d = ToolPolicyRepository._row_to_dict(row)
        assert d["tool_name"] == "T"
        assert d["approval_required"] is True


# ---------------------------------------------------------------------------
# AgentRunRepository
# ---------------------------------------------------------------------------


class TestAgentRunRepositorySQLite:
    def _make_run(self, db: Session, run_id: str = "run-1") -> None:
        db.add(
            AgentRun(
                run_id=run_id,
                workspace_id="ws-test",
                session_id="sess-1",
                status="running",
                goal="diagnose OOM",
                created_at=_now(),
                updated_at=_now(),
            )
        )

    def test_create_and_get(self, sqlite_session):
        _create_workspace(sqlite_session)
        repo = AgentRunRepository()
        run_id = repo.create_run_with_session(
            sqlite_session,
            workspace_id="ws-test",
            scene_id=None,
            session_id="sess-1",
            goal="diagnose OOM",
        )
        result = repo.get_run_with_session(sqlite_session, run_id)
        assert result is not None
        assert result["status"] == "running"
        assert result["goal"] == "diagnose OOM"

    def test_update_run_status(self, sqlite_session):
        _create_workspace(sqlite_session)
        repo = AgentRunRepository()
        run_id = repo.create_run_with_session(
            sqlite_session,
            workspace_id="ws-test",
            scene_id=None,
            session_id="s",
            goal="test",
        )
        repo.update_run_with_session(
            sqlite_session, run_id, status="completed", final_report="done"
        )
        result = repo.get_run_with_session(sqlite_session, run_id)
        assert result["status"] == "completed"
        assert result["final_report"] == "done"

    def test_update_run_nonexistent(self, sqlite_session):
        repo = AgentRunRepository()
        # Should not raise
        repo.update_run_with_session(sqlite_session, "no-such", status="done")

    def test_list_runs(self, sqlite_session):
        _create_workspace(sqlite_session)
        repo = AgentRunRepository()
        repo.create_run_with_session(
            sqlite_session,
            workspace_id="ws-test",
            scene_id=None,
            session_id="s",
            goal="g1",
        )
        repo.create_run_with_session(
            sqlite_session,
            workspace_id="ws-test",
            scene_id=None,
            session_id="s",
            goal="g2",
        )
        sqlite_session.commit()
        result = repo.list_runs_with_session(sqlite_session, limit=10)
        assert len(result) == 2

    def test_update_run_metrics(self, sqlite_session):
        _create_workspace(sqlite_session)
        repo = AgentRunRepository()
        run_id = repo.create_run_with_session(
            sqlite_session,
            workspace_id="ws-test",
            scene_id=None,
            session_id="s",
            goal="g",
        )
        repo.update_run_metrics_with_session(
            sqlite_session,
            run_id,
            step_count=5,
            latency_ms=1200,
            token_usage={"prompt": 100},
            cost_estimate={"total": 0.05},
            recovery_count=2,
            regression_score=0.85,
        )
        result = repo.get_run_with_session(sqlite_session, run_id)
        assert result["step_count"] == 5
        assert result["latency_ms"] == 1200
        assert result["recovery_count"] == 2

    def test_update_run_metrics_nonexistent(self, sqlite_session):
        repo = AgentRunRepository()
        # Should not raise
        repo.update_run_metrics_with_session(sqlite_session, "no-such", step_count=1)

    def test_row_to_dict(self, sqlite_session):
        _create_workspace(sqlite_session)
        repo = AgentRunRepository()
        run_id = repo.create_run_with_session(
            sqlite_session,
            workspace_id="ws-test",
            scene_id=None,
            session_id="s",
            goal="g",
        )
        row = sqlite_session.get(AgentRun, run_id)
        d = AgentRunRepository._row_to_dict(row)
        assert d["run_id"] == run_id
        assert d["workspace_id"] == "ws-test"


# ---------------------------------------------------------------------------
# AgentFeedbackRepository
# ---------------------------------------------------------------------------


class TestAgentFeedbackRepositorySQLite:
    """Tests for AgentFeedbackRepository._with_session methods only.

    Note: list_badcases, get_badcase, review_badcase use get_engine() internally
    and cannot be tested with SQLite. Only _with_session variants are tested here.
    """

    def _create_run(self, db: Session) -> str:
        _create_workspace(db)
        run_id = f"run-{uuid.uuid4().hex[:8]}"
        db.add(
            AgentRun(
                run_id=run_id,
                workspace_id="ws-test",
                session_id="s",
                status="completed",
                goal="test",
                created_at=_now(),
                updated_at=_now(),
            )
        )
        db.flush()
        return run_id

    def test_create_feedback(self, sqlite_session):
        run_id = self._create_run(sqlite_session)
        repo = AgentFeedbackRepository()
        fid = repo.create_feedback_with_session(
            sqlite_session, run_id, rating="down", correction="fix this"
        )
        result = repo.list_feedback_with_session(sqlite_session, run_id)
        assert len(result) == 1
        assert result[0]["feedback_id"] == fid
        assert result[0]["correction"] == "fix this"

    def test_create_feedback_with_badcase_flag(self, sqlite_session):
        run_id = self._create_run(sqlite_session)
        repo = AgentFeedbackRepository()
        repo.create_feedback_with_session(
            sqlite_session, run_id, rating="down", badcase_flag=True, original_report="bad report"
        )
        result = repo.list_feedback_with_session(sqlite_session, run_id)
        assert result[0]["badcase_flag"] is True
        assert result[0]["original_report"] == "bad report"

    def test_list_feedback_empty(self, sqlite_session):
        repo = AgentFeedbackRepository()
        result = repo.list_feedback_with_session(sqlite_session, "nonexistent-run")
        assert result == []

    def test_feedback_row_to_dict(self, sqlite_session):
        run_id = self._create_run(sqlite_session)
        repo = AgentFeedbackRepository()
        fid = repo.create_feedback_with_session(sqlite_session, run_id, rating="up")
        sqlite_session.flush()
        row = sqlite_session.get(AgentFeedback, fid)
        d = AgentFeedbackRepository._feedback_row_to_dict(row)
        assert d["feedback_id"] == fid
        assert d["rating"] == "up"


# ---------------------------------------------------------------------------
# AgentMemoryRepository (non-embedding methods only)
# ---------------------------------------------------------------------------


class TestAgentMemoryRepositorySQLite:
    def test_create_memory(self, sqlite_session):
        _create_workspace(sqlite_session)
        repo = AgentMemoryRepository()
        mid = repo.create_memory_with_session(
            sqlite_session,
            workspace_id="ws-test",
            run_id=None,
            conclusion_text="OOM root cause",
            confidence=0.8,
        )
        row = sqlite_session.get(AgentMemory, mid)
        assert row is not None
        assert row.conclusion_text == "OOM root cause"
        assert row.confidence == 0.8

    def test_create_memory_with_metadata(self, sqlite_session):
        _create_workspace(sqlite_session)
        repo = AgentMemoryRepository()
        mid = repo.create_memory_with_session(
            sqlite_session,
            workspace_id="ws-test",
            run_id=None,
            conclusion_text="memory leak",
            conclusion_type="root_cause",
            confidence=0.9,
            metadata={"source": "test"},
        )
        row = sqlite_session.get(AgentMemory, mid)
        assert row.conclusion_type == "root_cause"
        assert row.memory_metadata == {"source": "test"}
