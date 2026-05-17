"""Unit tests for domain entities and runtime events."""

from __future__ import annotations

from app.agent_runtime.events import (
    EVENT_PROACTIVE_ALERT,
    AgentRuntimeEvent,
    proactive_alert_event,
)
from app.domains.native_agent.entities import (
    AgentEvent,
    AgentRun,
    KnowledgeBase,
    Scene,
    ToolPolicy,
    Workspace,
)

# ---------------------------------------------------------------------------
# AgentRuntimeEvent
# ---------------------------------------------------------------------------


class TestAgentRuntimeEvent:
    def test_basic(self):
        event = AgentRuntimeEvent(
            type="tool_call",
            stage="execution",
            run_id="r1",
        )
        assert event.type == "tool_call"
        assert event.message == ""
        assert event.payload == {}

    def test_to_dict_minimal(self):
        event = AgentRuntimeEvent(type="x", stage="y", run_id="r1")
        d = event.to_dict()
        assert d == {"type": "x", "stage": "y", "run_id": "r1"}

    def test_to_dict_with_message(self):
        event = AgentRuntimeEvent(type="x", stage="y", run_id="r1", message="hello")
        d = event.to_dict()
        assert d["message"] == "hello"

    def test_to_dict_with_payload(self):
        event = AgentRuntimeEvent(type="x", stage="y", run_id="r1", payload={"key": "val"})
        d = event.to_dict()
        assert d["payload"] == {"key": "val"}

    def test_to_dict_with_status(self):
        event = AgentRuntimeEvent(type="x", stage="y", run_id="r1", status="completed")
        d = event.to_dict()
        assert d["status"] == "completed"

    def test_to_dict_with_final_report(self):
        event = AgentRuntimeEvent(type="x", stage="y", run_id="r1", final_report="done")
        d = event.to_dict()
        assert d["final_report"] == "done"


class TestProactiveAlertEvent:
    def test_basic(self):
        event = proactive_alert_event(
            run_id="r1",
            service_name="api",
            metric_type="cpu",
            severity="critical",
            message="CPU high",
        )
        assert event.type == EVENT_PROACTIVE_ALERT
        assert event.stage == "monitoring"
        assert event.run_id == "r1"
        assert event.payload["service_name"] == "api"
        assert event.payload["severity"] == "critical"

    def test_with_diagnosis_run(self):
        event = proactive_alert_event(
            run_id="r1",
            service_name="api",
            metric_type="cpu",
            severity="warning",
            message="high",
            run_id_diagnosis="diag-1",
            alert_key="api:cpu",
        )
        assert event.payload["diagnosis_run_id"] == "diag-1"
        assert event.payload["alert_key"] == "api:cpu"


# ---------------------------------------------------------------------------
# Workspace
# ---------------------------------------------------------------------------


class TestWorkspace:
    def test_from_record(self):
        w = Workspace.from_record({"id": "w1", "name": "WS", "description": "desc"})
        assert w.id == "w1"
        assert w.name == "WS"
        assert w.description == "desc"

    def test_to_dict(self):
        w = Workspace(id="w1", name="WS")
        d = w.to_dict()
        assert d == {"id": "w1", "name": "WS", "description": None}

    def test_roundtrip(self):
        w = Workspace(id="w1", name="WS", description="d")
        w2 = Workspace.from_record(w.to_dict())
        assert w2 == w


# ---------------------------------------------------------------------------
# KnowledgeBase
# ---------------------------------------------------------------------------


class TestKnowledgeBase:
    def test_from_record(self):
        kb = KnowledgeBase.from_record(
            {
                "id": "kb1",
                "workspace_id": "w1",
                "name": "KB",
                "description": "d",
                "version": "2.0",
            }
        )
        assert kb.version == "2.0"

    def test_from_record_defaults(self):
        kb = KnowledgeBase.from_record({"id": "kb1", "workspace_id": "w1", "name": "KB"})
        assert kb.version == "0.0.1"
        assert kb.description is None

    def test_to_dict(self):
        kb = KnowledgeBase(id="kb1", workspace_id="w1", name="KB", version="1.0")
        d = kb.to_dict()
        assert d["version"] == "1.0"

    def test_roundtrip(self):
        kb = KnowledgeBase(id="kb1", workspace_id="w1", name="KB", description="d", version="2.0")
        kb2 = KnowledgeBase.from_record(kb.to_dict())
        assert kb2 == kb


# ---------------------------------------------------------------------------
# Scene
# ---------------------------------------------------------------------------


class TestScene:
    def test_from_record(self):
        s = Scene.from_record(
            {
                "id": "s1",
                "workspace_id": "w1",
                "name": "Scene",
                "knowledge_bases": [{"id": "kb1", "workspace_id": "w1", "name": "KB"}],
                "tools": ["A", "B"],
                "agent_config": {"key": "val"},
            }
        )
        assert len(s.knowledge_bases) == 1
        assert s.tool_names == ["A", "B"]
        assert s.agent_config == {"key": "val"}

    def test_from_record_defaults(self):
        s = Scene.from_record({"id": "s1", "workspace_id": "w1", "name": "S"})
        assert s.knowledge_bases == []
        assert s.tool_names == []
        assert s.agent_config == {}

    def test_to_dict(self):
        s = Scene(id="s1", workspace_id="w1", name="S", tool_names=["A"])
        d = s.to_dict()
        assert d["tools"] == ["A"]
        assert "knowledge_bases" in d


# ---------------------------------------------------------------------------
# ToolPolicy
# ---------------------------------------------------------------------------


class TestToolPolicy:
    def test_from_record(self):
        tp = ToolPolicy.from_record(
            {
                "tool_name": "SearchLog",
                "scope": "chat",
                "risk_level": "high",
                "capability": "run",
                "enabled": False,
                "approval_required": True,
            }
        )
        assert tp.scope == "chat"
        assert tp.enabled is False
        assert tp.requires_approval() is True

    def test_from_record_defaults(self):
        tp = ToolPolicy.from_record({"tool_name": "X"})
        assert tp.scope == "diagnosis"
        assert tp.risk_level == "low"
        assert tp.enabled is True
        assert tp.requires_approval() is False

    def test_to_dict(self):
        tp = ToolPolicy(tool_name="X", scope="chat")
        d = tp.to_dict()
        assert d["tool_name"] == "X"
        assert d["scope"] == "chat"

    def test_roundtrip(self):
        tp = ToolPolicy(
            tool_name="X",
            scope="chat",
            risk_level="high",
            capability="run",
            enabled=True,
            approval_required=False,
        )
        tp2 = ToolPolicy.from_record(tp.to_dict())
        assert tp2 == tp


# ---------------------------------------------------------------------------
# AgentRun
# ---------------------------------------------------------------------------


class TestAgentRun:
    def test_from_record(self):
        ar = AgentRun.from_record(
            {
                "id": "r1",
                "workspace_id": "w1",
                "scene_id": "s1",
                "session_id": "sess1",
                "goal": "OOM",
                "status": "running",
                "final_report": "done",
            }
        )
        assert ar.is_completed() is False

    def test_from_record_with_run_id(self):
        ar = AgentRun.from_record(
            {
                "run_id": "r1",
                "workspace_id": "w1",
                "scene_id": "s1",
                "session_id": "sess1",
                "goal": "x",
                "status": "completed",
            }
        )
        assert ar.id == "r1"
        assert ar.is_completed() is True

    def test_from_record_defaults(self):
        ar = AgentRun.from_record(
            {
                "id": "r1",
                "workspace_id": "w1",
                "scene_id": "s1",
                "session_id": "s",
                "goal": "x",
                "status": "running",
            }
        )
        assert ar.final_report is None


# ---------------------------------------------------------------------------
# AgentEvent
# ---------------------------------------------------------------------------


class TestAgentEvent:
    def test_from_record(self):
        ae = AgentEvent.from_record(
            {
                "id": "e1",
                "run_id": "r1",
                "type": "tool_call",
                "stage": "execution",
                "message": "ok",
                "payload": {"k": "v"},
            }
        )
        assert ae.type == "tool_call"
        assert ae.payload == {"k": "v"}

    def test_from_record_empty_payload(self):
        ae = AgentEvent.from_record(
            {
                "id": "e1",
                "run_id": "r1",
                "type": "x",
                "stage": "y",
                "message": "m",
            }
        )
        assert ae.payload == {}
