from __future__ import annotations

from app.persistence import (
    aiops_run_repository,
    audit_log_repository,
    conversation_repository,
)
from app.persistence.database import database_manager


def test_conversation_repository_saves_lists_and_deletes_session():
    conversation_repository.save_chat_exchange(
        "session-1",
        "How do I debug high CPU?",
        "Check recent deploys and hot threads.",
    )

    sessions = conversation_repository.list_sessions()
    messages = conversation_repository.get_session_messages("session-1")

    assert len(sessions) == 1
    assert sessions[0]["id"] == "session-1"
    assert sessions[0]["messageCount"] == 2
    assert [message.role for message in messages] == ["user", "assistant"]
    assert messages[0].content == "How do I debug high CPU?"

    assert conversation_repository.delete_session("session-1")
    assert conversation_repository.get_session_messages("session-1") == []


def test_aiops_run_repository_updates_status_and_report():
    run_id = aiops_run_repository.create_run("session-1", "diagnose alerts")

    aiops_run_repository.update_run(run_id, status="completed", report="root cause report")

    with database_manager.get_connection() as connection:
        row = connection.fetchone("SELECT status, report, error_message FROM aiops_runs")

    assert row is not None
    assert row["status"] == "completed"
    assert row["report"] == "root cause report"
    assert row["error_message"] is None


def test_audit_log_repository_persists_request_context():
    audit_log_repository.log_request(
        request_id="req-1",
        method="POST",
        path="/api/upload",
        status_code=202,
        subject="admin",
        role="admin",
        client_ip="127.0.0.1",
        user_agent="pytest",
    )

    with database_manager.get_connection() as connection:
        row = connection.fetchone(
            """
            SELECT request_id, method, path, status_code, subject, role, client_ip, user_agent
            FROM audit_logs
            """
        )

    assert row is not None
    assert dict(row) == {
        "request_id": "req-1",
        "method": "POST",
        "path": "/api/upload",
        "status_code": 202,
        "subject": "admin",
        "role": "admin",
        "client_ip": "127.0.0.1",
        "user_agent": "pytest",
    }
