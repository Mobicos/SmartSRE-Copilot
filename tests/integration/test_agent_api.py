from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import native_agent
from app.platform.persistence import agent_memory_repository


class FakeStoredObject:
    key = "badcase.md"
    uri = "memory://badcase.md"
    local_path = "badcase.md"
    size = 128
    backend = "memory"


class FakeObjectStorage:
    def __init__(self):
        self.writes: list[tuple[str, bytes]] = []

    def put_bytes(self, key: str, content: bytes):
        self.writes.append((key, content))
        stored = FakeStoredObject()
        stored.key = key
        stored.uri = f"memory://{key}"
        stored.local_path = key
        stored.size = len(content)
        return stored


class FakeIndexingTaskService:
    def submit_task(self, filename: str, file_path: str) -> str:
        self.last_submit = {"filename": filename, "file_path": file_path}
        return "task-badcase"


class FakeTaskDispatcher:
    def __init__(self):
        self.enqueued: list[tuple[str, str]] = []

    async def enqueue_indexing_task(self, task_id: str, file_path: str) -> None:
        self.enqueued.append((task_id, file_path))


def test_native_agent_api_creates_scene_and_runs_agent(monkeypatch):
    app = FastAPI()
    app.include_router(native_agent.router, prefix="/api")
    client = TestClient(app)

    workspace_response = client.post(
        "/api/workspaces",
        json={"name": "SRE", "description": "on-call"},
    )
    workspace_id = workspace_response.json()["data"]["id"]

    scene_response = client.post(
        "/api/scenes",
        json={
            "workspace_id": workspace_id,
            "name": "Default Diagnosis",
            "description": "demo scene",
            "tool_names": [],
        },
    )
    scene_id = scene_response.json()["data"]["id"]

    run_response = client.post(
        "/api/agent/runs",
        json={
            "scene_id": scene_id,
            "session_id": "session-1",
            "goal": "diagnose alerts",
        },
    )
    run_data = run_response.json()["data"]
    events_response = client.get(f"/api/agent/runs/{run_data['run_id']}/events")

    assert workspace_response.status_code == 200
    assert scene_response.status_code == 200
    assert run_response.status_code == 200
    assert run_data["status"] == "completed"
    assert events_response.json()["data"][0]["type"] == "run_started"


def test_native_agent_api_lists_runs_after_agent_execution(monkeypatch):
    app = FastAPI()
    app.include_router(native_agent.router, prefix="/api")
    client = TestClient(app)

    workspace_id = client.post("/api/workspaces", json={"name": "SRE"}).json()["data"]["id"]
    scene_id = client.post(
        "/api/scenes",
        json={"workspace_id": workspace_id, "name": "Default Diagnosis"},
    ).json()["data"]["id"]

    run = client.post(
        "/api/agent/runs",
        json={"scene_id": scene_id, "session_id": "session-1", "goal": "diagnose alerts"},
    ).json()["data"]
    runs_response = client.get("/api/agent/runs")

    assert runs_response.status_code == 200
    assert runs_response.json()["data"][0]["run_id"] == run["run_id"]


def test_native_agent_api_merges_partial_tool_policy_updates(monkeypatch):
    app = FastAPI()
    app.include_router(native_agent.router, prefix="/api")
    client = TestClient(app)

    first_response = client.patch(
        "/api/tools/SearchLog/policy",
        json={"risk_level": "high", "approval_required": True},
    )
    second_response = client.patch(
        "/api/tools/SearchLog/policy",
        json={"enabled": False},
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert second_response.json()["data"] == {
        "tool_name": "SearchLog",
        "scope": "diagnosis",
        "risk_level": "high",
        "capability": None,
        "enabled": False,
        "approval_required": True,
        "created_at": second_response.json()["data"]["created_at"],
        "updated_at": second_response.json()["data"]["updated_at"],
    }


def test_native_agent_api_accepts_product_feedback_ratings(monkeypatch):
    object_storage = FakeObjectStorage()
    indexing_service = FakeIndexingTaskService()
    dispatcher = FakeTaskDispatcher()
    monkeypatch.setattr(native_agent, "get_object_storage", lambda: object_storage)
    monkeypatch.setattr(native_agent, "get_indexing_task_service", lambda: indexing_service)
    monkeypatch.setattr(native_agent, "task_dispatcher", dispatcher)

    app = FastAPI()
    app.include_router(native_agent.router, prefix="/api")
    client = TestClient(app)

    workspace_id = client.post("/api/workspaces", json={"name": "SRE"}).json()["data"]["id"]
    scene_id = client.post(
        "/api/scenes",
        json={"workspace_id": workspace_id, "name": "Default Diagnosis"},
    ).json()["data"]["id"]
    run_id = client.post(
        "/api/agent/runs",
        json={"scene_id": scene_id, "session_id": "session-1", "goal": "diagnose alerts"},
    ).json()["data"]["run_id"]

    response = client.post(
        f"/api/agent/runs/{run_id}/feedback",
        json={
            "rating": "wrong",
            "comment": "The report missed the release.",
            "correction": "Rollback fixed the incident.",
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["feedback_id"]
    assert data["badcase_flag"] is True
    assert data["correction"] == "Rollback fixed the incident."
    assert data["review_status"] == "pending"
    memories = agent_memory_repository.search_memory(
        workspace_id=workspace_id,
        query="Rollback fixed incident",
        limit=1,
    )
    assert memories[0]["conclusion_type"] == "correction"
    assert memories[0]["conclusion_text"] == "Rollback fixed the incident."

    badcases_response = client.get("/api/agent/badcases")
    assert badcases_response.status_code == 200
    badcase = badcases_response.json()["data"][0]
    assert badcase["feedback_id"] == data["feedback_id"]
    assert badcase["run"]["run_id"] == run_id

    review_response = client.post(
        f"/api/agent/badcases/{data['feedback_id']}/review",
        json={"review_status": "confirmed", "review_note": "On-call confirmed."},
    )
    assert review_response.status_code == 200
    reviewed = review_response.json()["data"]
    assert reviewed["review_status"] == "confirmed"
    assert reviewed["review_note"] == "On-call confirmed."
    assert reviewed["reviewed_by"] == "local-dev"

    promotion_response = client.post(f"/api/agent/badcases/{data['feedback_id']}/promote-knowledge")
    assert promotion_response.status_code == 202
    promotion = promotion_response.json()["data"]
    assert promotion["badcase"]["knowledge_status"] == "queued"
    assert promotion["badcase"]["knowledge_task_id"] == "task-badcase"
    assert promotion["filename"].startswith("badcase-")
    assert object_storage.writes[0][0] == promotion["filename"]
    assert b"Rollback fixed the incident." in object_storage.writes[0][1]
    assert dispatcher.enqueued == [("task-badcase", promotion["filename"])]
