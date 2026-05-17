"""Unit tests for application service static helpers and pure functions."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

# ---------------------------------------------------------------------------
# app.application.aiops_application_service — static helpers
# ---------------------------------------------------------------------------


class TestAIOpsStaticHelpers:
    def test_runtime_event_to_dict_with_to_dict(self):
        from app.application.aiops_application_service import AIOpsApplicationService

        event = SimpleNamespace(to_dict=lambda: {"type": "run_started", "stage": "init"})
        result = AIOpsApplicationService._runtime_event_to_dict(event)
        assert result["type"] == "run_started"

    def test_runtime_event_to_dict_non_dict_to_dict(self):
        from app.application.aiops_application_service import AIOpsApplicationService

        event = SimpleNamespace(to_dict=lambda: "not a dict")
        result = AIOpsApplicationService._runtime_event_to_dict(event)
        assert result == {}

    def test_runtime_event_to_dict_plain_dict(self):
        from app.application.aiops_application_service import AIOpsApplicationService

        event = {"type": "tool_call", "stage": "exec"}
        result = AIOpsApplicationService._runtime_event_to_dict(event)
        assert result == event

    def test_runtime_event_to_dict_unknown_type(self):
        from app.application.aiops_application_service import AIOpsApplicationService

        result = AIOpsApplicationService._runtime_event_to_dict("string")
        assert result == {}

    def test_event_payload_valid(self):
        from app.application.aiops_application_service import AIOpsApplicationService

        event = {"payload": {"tool_name": "SearchLog"}}
        assert AIOpsApplicationService._event_payload(event) == {"tool_name": "SearchLog"}

    def test_event_payload_missing(self):
        from app.application.aiops_application_service import AIOpsApplicationService

        assert AIOpsApplicationService._event_payload({}) == {}

    def test_event_payload_non_dict(self):
        from app.application.aiops_application_service import AIOpsApplicationService

        event = {"payload": "invalid"}
        assert AIOpsApplicationService._event_payload(event) == {}

    def test_translate_run_started(self):
        from app.application.aiops_application_service import AIOpsApplicationService

        result = AIOpsApplicationService._translate_native_event({"type": "run_started"})
        assert result["type"] == "status"
        assert result["stage"] == "agent_started"

    def test_translate_hypothesis(self):
        from app.application.aiops_application_service import AIOpsApplicationService

        result = AIOpsApplicationService._translate_native_event(
            {"type": "hypothesis", "message": "OOM suspected"}
        )
        assert result["type"] == "plan"
        assert "OOM suspected" in result["plan"][0]

    def test_translate_tool_call(self):
        from app.application.aiops_application_service import AIOpsApplicationService

        event = {"type": "tool_call", "payload": {"tool_name": "SearchLog"}}
        result = AIOpsApplicationService._translate_native_event(event)
        assert result["type"] == "status"
        assert "SearchLog" in result["message"]

    def test_translate_tool_result(self):
        from app.application.aiops_application_service import AIOpsApplicationService

        event = {
            "type": "tool_result",
            "payload": {"tool_name": "SearchLog", "output": "log data"},
        }
        result = AIOpsApplicationService._translate_native_event(event)
        assert result["type"] == "step_complete"
        assert result["current_step"] == "SearchLog"

    def test_translate_tool_result_error(self):
        from app.application.aiops_application_service import AIOpsApplicationService

        event = {
            "type": "tool_result",
            "payload": {"tool_name": "X", "error": "timeout"},
        }
        result = AIOpsApplicationService._translate_native_event(event)
        assert "timeout" in result["result_preview"]

    def test_translate_final_report(self):
        from app.application.aiops_application_service import AIOpsApplicationService

        event = {
            "type": "final_report",
            "payload": {"report": "# Report\nDone"},
        }
        result = AIOpsApplicationService._translate_native_event(event)
        assert result["type"] == "report"
        assert "# Report" in result["report"]

    def test_translate_complete(self):
        from app.application.aiops_application_service import AIOpsApplicationService

        event = {"type": "complete", "final_report": "Done"}
        result = AIOpsApplicationService._translate_native_event(event)
        assert result["type"] == "complete"
        assert result["diagnosis"]["report"] == "Done"

    def test_translate_unknown_type(self):
        from app.application.aiops_application_service import AIOpsApplicationService

        event = {"type": "unknown_event", "stage": "custom", "message": "hello"}
        result = AIOpsApplicationService._translate_native_event(event)
        assert result["type"] == "status"
        assert result["message"] == "hello"

    def test_ensure_default_scene_existing_workspace(self):
        from app.application.aiops_application_service import AIOpsApplicationService

        mock_runtime = MagicMock()
        mock_aiops_repo = MagicMock()
        mock_conv_repo = MagicMock()
        mock_ws_repo = MagicMock()
        mock_ws_repo.list_workspaces.return_value = [{"id": "ws-1"}]
        mock_scene_repo = MagicMock()
        mock_scene_repo.list_scenes.return_value = [{"id": "scene-1"}]

        svc = AIOpsApplicationService(
            agent_runtime=mock_runtime,
            aiops_run_repository=mock_aiops_repo,
            conversation_repository=mock_conv_repo,
            workspace_repository=mock_ws_repo,
            scene_repository=mock_scene_repo,
        )
        scene_id = svc._ensure_default_scene()
        assert scene_id == "scene-1"
        mock_ws_repo.create_workspace.assert_not_called()

    def test_ensure_default_scene_creates_workspace_and_scene(self):
        from app.application.aiops_application_service import AIOpsApplicationService

        mock_ws_repo = MagicMock()
        mock_ws_repo.list_workspaces.return_value = []
        mock_ws_repo.create_workspace.return_value = "ws-new"
        mock_scene_repo = MagicMock()
        mock_scene_repo.list_scenes.return_value = []
        mock_scene_repo.create_scene.return_value = "scene-new"

        svc = AIOpsApplicationService(
            agent_runtime=MagicMock(),
            aiops_run_repository=MagicMock(),
            conversation_repository=MagicMock(),
            workspace_repository=mock_ws_repo,
            scene_repository=mock_scene_repo,
        )
        scene_id = svc._ensure_default_scene()
        assert scene_id == "scene-new"
        mock_ws_repo.create_workspace.assert_called_once()


# ---------------------------------------------------------------------------
# app.application.scenario_regression_service
# ---------------------------------------------------------------------------


class TestRegressionScenario:
    def test_to_dict(self):
        from app.application.scenario_regression_service import RegressionScenario

        s = RegressionScenario(
            id="test",
            title="Test",
            priority="P0",
            goal="test goal",
            expected_signals=("signal",),
            required_event_types=("event",),
            blocked_terms=("blocked",),
            min_tool_calls=1,
        )
        d = s.to_dict()
        assert d["id"] == "test"
        assert d["expected_signals"] == ["signal"]
        assert d["blocked_terms"] == ["blocked"]
        assert d["min_tool_calls"] == 1

    def test_to_dict_defaults(self):
        from app.application.scenario_regression_service import RegressionScenario

        s = RegressionScenario(
            id="x",
            title="X",
            priority="P2",
            goal="g",
            expected_signals=(),
            required_event_types=(),
        )
        d = s.to_dict()
        assert d["blocked_terms"] == []
        assert d["min_tool_calls"] == 0


class TestScenarioHelpers:
    def test_scenario_by_id_found(self):
        from app.application.scenario_regression_service import (
            SCENARIOS,
            _scenario_by_id,
        )

        scenario = _scenario_by_id(SCENARIOS[0].id)
        assert scenario.id == SCENARIOS[0].id

    def test_scenario_by_id_not_found(self):
        from app.application.scenario_regression_service import _scenario_by_id

        with pytest.raises(ValueError, match="scenario_not_found"):
            _scenario_by_id("nonexistent-id")

    def test_check_passed(self):
        from app.application.scenario_regression_service import _check

        result = _check("test_check", True, "passed")
        assert result["passed"] is True
        assert result["message"] == "passed"

    def test_check_failed(self):
        from app.application.scenario_regression_service import _check

        result = _check("test_check", False, "failed")
        assert result["passed"] is False

    def test_searchable_text(self):
        from app.application.scenario_regression_service import _searchable_text

        run = {"goal": "diagnose OOM", "final_report": "Memory leak found"}
        events = [{"type": "tool_call", "message": "searched logs", "payload": "data"}]
        text = _searchable_text(run, events)
        assert "oom" in text
        assert "memory leak" in text
        assert "tool_call" in text
        assert "searched logs" in text


class TestScenarioRegressionServiceEvaluate:
    def test_list_scenarios(self):
        from app.application.scenario_regression_service import (
            SCENARIOS,
            ScenarioRegressionService,
        )

        svc = ScenarioRegressionService(agent_run_repository=MagicMock())
        result = svc.list_scenarios()
        assert len(result) == len(SCENARIOS)
        assert result[0]["id"] == SCENARIOS[0].id

    def test_evaluate_run_not_found(self):
        from app.application.scenario_regression_service import ScenarioRegressionService

        mock_repo = MagicMock()
        mock_repo.get_run.return_value = None
        svc = ScenarioRegressionService(agent_run_repository=mock_repo)
        result = svc.evaluate_run(scenario_id="cpu_high", run_id="nonexistent")
        assert result is None

    def test_evaluate_run_passed(self):
        from app.application.scenario_regression_service import SCENARIOS, ScenarioRegressionService

        scenario = next(s for s in SCENARIOS if s.id == "cpu_high")
        mock_repo = MagicMock()
        mock_repo.get_run.return_value = {
            "status": "completed",
            "final_report": "CPU high due to process X",
            "goal": scenario.goal,
        }
        mock_repo.list_events.return_value = [
            {"type": "run_started", "message": "started", "payload": ""},
            {"type": "tool_result", "message": "CPU 95%", "payload": "data"},
            {"type": "final_report", "message": "done", "payload": ""},
        ]
        svc = ScenarioRegressionService(agent_run_repository=mock_repo)
        result = svc.evaluate_run(scenario_id="cpu_high", run_id="r1")
        assert result is not None
        assert result["run_id"] == "r1"
        assert "score" in result
        assert "checks" in result

    def test_evaluate_run_failed_checks(self):
        from app.application.scenario_regression_service import SCENARIOS, ScenarioRegressionService

        scenario = next(s for s in SCENARIOS if s.id == "cpu_high")
        mock_repo = MagicMock()
        mock_repo.get_run.return_value = {
            "status": "failed",
            "final_report": "",
            "goal": scenario.goal,
        }
        mock_repo.list_events.return_value = []  # no events
        svc = ScenarioRegressionService(agent_run_repository=mock_repo)
        result = svc.evaluate_run(scenario_id="cpu_high", run_id="r1")
        assert result["status"] == "failed"
        failed = [c for c in result["checks"] if not c["passed"]]
        assert len(failed) > 0


# ---------------------------------------------------------------------------
# app.application.indexing.service
# ---------------------------------------------------------------------------


class TestFormatIndexingError:
    def test_basic(self):
        from app.application.indexing.service import _format_indexing_error

        result = _format_indexing_error(RuntimeError("timeout"), file_path="/a/b.py")
        assert "RuntimeError" in result
        assert "timeout" in result
        assert "/a/b.py" in result

    def test_empty_message(self):
        from app.application.indexing.service import _format_indexing_error

        result = _format_indexing_error(ValueError(""), file_path="/x.py")
        assert "ValueError" in result


class TestIndexingTaskService:
    def test_submit_task_new(self):
        from app.application.indexing.service import IndexingTaskService

        mock_repo = MagicMock()
        mock_repo.find_active_task_by_file_path.return_value = None
        mock_repo.create_task.return_value = "task-1"

        svc = IndexingTaskService(
            repository=mock_repo,
            vector_indexer_provider=lambda: MagicMock(),
            max_retries_provider=lambda: 3,
        )
        task_id = svc.submit_task("file.py", "/path/file.py")
        assert task_id == "task-1"
        mock_repo.create_task.assert_called_once()

    def test_submit_task_reuse_existing(self):
        from app.application.indexing.service import IndexingTaskService

        mock_repo = MagicMock()
        mock_repo.find_active_task_by_file_path.return_value = {
            "task_id": "existing-task",
            "status": "processing",
        }

        svc = IndexingTaskService(
            repository=mock_repo,
            vector_indexer_provider=lambda: MagicMock(),
            max_retries_provider=lambda: 3,
        )
        task_id = svc.submit_task("file.py", "/path/file.py")
        assert task_id == "existing-task"
        mock_repo.create_task.assert_not_called()

    def test_process_task_success(self):
        from app.application.indexing.service import IndexingTaskService

        mock_indexer = MagicMock()
        mock_repo = MagicMock()
        svc = IndexingTaskService(
            repository=mock_repo,
            vector_indexer_provider=lambda: mock_indexer,
            max_retries_provider=lambda: 3,
        )
        result = svc.process_task("task-1", "/path/file.py")
        assert result == "completed"
        mock_repo.update_task.assert_called_once_with("task-1", status="completed")

    def test_process_task_with_object_storage(self):
        from app.application.indexing.service import IndexingTaskService

        mock_indexer = MagicMock()
        mock_storage = MagicMock()
        mock_repo = MagicMock()
        svc = IndexingTaskService(
            repository=mock_repo,
            vector_indexer_provider=lambda: mock_indexer,
            max_retries_provider=lambda: 3,
            object_storage=mock_storage,
        )
        result = svc.process_task("task-1", "/path/file.py")
        assert result == "completed"
        mock_storage.cleanup_local_cache.assert_called_once_with("/path/file.py")

    def test_process_task_object_storage_cleanup_failure_ignored(self):
        from app.application.indexing.service import IndexingTaskService

        mock_indexer = MagicMock()
        mock_storage = MagicMock()
        mock_storage.cleanup_local_cache.side_effect = OSError("disk full")
        mock_repo = MagicMock()
        svc = IndexingTaskService(
            repository=mock_repo,
            vector_indexer_provider=lambda: mock_indexer,
            max_retries_provider=lambda: 3,
            object_storage=mock_storage,
        )
        # Should not raise despite cleanup failure
        result = svc.process_task("task-1", "/path/file.py")
        assert result == "completed"

    def test_process_task_indexer_failure_retries(self):
        from app.application.indexing.service import IndexingTaskService

        mock_indexer = MagicMock()
        mock_indexer.index_single_file.side_effect = RuntimeError("connection lost")
        mock_repo = MagicMock()
        mock_repo.mark_retry_or_failed.return_value = {
            "status": "queued",
            "attempt_count": 1,
            "max_retries": 3,
        }
        svc = IndexingTaskService(
            repository=mock_repo,
            vector_indexer_provider=lambda: mock_indexer,
            max_retries_provider=lambda: 3,
        )
        result = svc.process_task("task-1", "/path/file.py")
        assert result == "queued"
        mock_repo.mark_retry_or_failed.assert_called_once()

    def test_process_task_indexer_failure_permanent(self):
        from app.application.indexing.service import IndexingTaskService

        mock_indexer = MagicMock()
        mock_indexer.index_single_file.side_effect = RuntimeError("fatal")
        mock_repo = MagicMock()
        mock_repo.mark_retry_or_failed.return_value = None  # task not found
        svc = IndexingTaskService(
            repository=mock_repo,
            vector_indexer_provider=lambda: mock_indexer,
            max_retries_provider=lambda: 3,
        )
        result = svc.process_task("task-1", "/path/file.py")
        assert result == "missing"


# ---------------------------------------------------------------------------
# app.application.chat_application_service
# ---------------------------------------------------------------------------


class TestChatApplicationService:
    def test_clear_session(self):
        from app.application.chat_application_service import ChatApplicationService

        mock_rag = MagicMock()
        mock_rag.clear_session.return_value = True
        mock_conv = MagicMock()
        mock_conv.delete_session.return_value = True
        mock_events = MagicMock()
        svc = ChatApplicationService(
            rag_agent_service=mock_rag,
            conversation_repository=mock_conv,
            chat_tool_event_repository=mock_events,
        )
        result = svc.clear_session("sess-1")
        assert result is True
        mock_conv.delete_session.assert_called_once_with("sess-1")

    @pytest.mark.asyncio
    async def test_run_chat(self):
        from app.application.chat_application_service import ChatApplicationService

        mock_rag = MagicMock()
        mock_rag.query = AsyncMock(
            return_value=SimpleNamespace(
                answer="AI response",
                tool_events=[{"tool": "SearchLog"}],
            )
        )
        mock_conv = MagicMock()
        mock_events = MagicMock()
        svc = ChatApplicationService(
            rag_agent_service=mock_rag,
            conversation_repository=mock_conv,
            chat_tool_event_repository=mock_events,
        )
        result = await svc.run_chat("sess-1", "What is OOM?")
        assert "answer" in result
        assert result["answer"] == "AI response"
        mock_conv.save_chat_exchange.assert_called_once()


# ---------------------------------------------------------------------------
# app.application.agent_resume_service — helper methods
# ---------------------------------------------------------------------------


class TestAgentResumeServiceHelpers:
    def test_find_original_action_not_found(self):
        from app.application.agent_resume_service import AgentResumeService

        mock_repo = MagicMock()
        mock_repo.list_events.return_value = []
        svc = AgentResumeService(
            agent_run_repository=mock_repo,
            tool_catalog=MagicMock(),
            tool_executor=MagicMock(),
        )
        result = svc._find_original_action("run-1", "SearchLog")
        assert result is None

    def test_find_original_action_found(self):
        from app.application.agent_resume_service import AgentResumeService

        mock_repo = MagicMock()
        mock_repo.list_events.return_value = [
            {"type": "other", "payload": {}},
            {
                "type": "tool_call",
                "payload": {"tool_name": "SearchLog", "arguments": {"q": "x"}},
            },
        ]
        svc = AgentResumeService(
            agent_run_repository=mock_repo,
            tool_catalog=MagicMock(),
            tool_executor=MagicMock(),
        )
        result = svc._find_original_action("run-1", "SearchLog")
        assert result is not None
        assert result["tool_name"] == "SearchLog"

    def test_find_original_action_non_dict_payload(self):
        from app.application.agent_resume_service import AgentResumeService

        mock_repo = MagicMock()
        mock_repo.list_events.return_value = [
            {"type": "tool_call", "payload": "not a dict"},
        ]
        svc = AgentResumeService(
            agent_run_repository=mock_repo,
            tool_catalog=MagicMock(),
            tool_executor=MagicMock(),
        )
        assert svc._find_original_action("run-1", "X") is None

    def test_latest_approval_decision(self):
        from app.application.agent_resume_service import AgentResumeService

        mock_repo = MagicMock()
        mock_repo.list_events.return_value = [
            {
                "type": "approval_decision",
                "payload": {"tool_name": "SearchLog", "decision": "approved"},
            },
        ]
        svc = AgentResumeService(
            agent_run_repository=mock_repo,
            tool_catalog=MagicMock(),
            tool_executor=MagicMock(),
        )
        result = svc._latest_approval_decision("run-1", "SearchLog")
        assert result["decision"] == "approved"

    def test_latest_approval_decision_not_found(self):
        from app.application.agent_resume_service import AgentResumeService

        mock_repo = MagicMock()
        mock_repo.list_events.return_value = []
        svc = AgentResumeService(
            agent_run_repository=mock_repo,
            tool_catalog=MagicMock(),
            tool_executor=MagicMock(),
        )
        result = svc._latest_approval_decision("run-1", "SearchLog")
        assert result == {}

    def test_latest_approval_decision_wrong_tool(self):
        from app.application.agent_resume_service import AgentResumeService

        mock_repo = MagicMock()
        mock_repo.list_events.return_value = [
            {
                "type": "approval_decision",
                "payload": {"tool_name": "OtherTool", "decision": "approved"},
            },
        ]
        svc = AgentResumeService(
            agent_run_repository=mock_repo,
            tool_catalog=MagicMock(),
            tool_executor=MagicMock(),
        )
        result = svc._latest_approval_decision("run-1", "SearchLog")
        assert result == {}

    def test_checkpoint_status_with_saver(self):
        from unittest.mock import patch

        from app.application.agent_resume_service import AgentResumeService

        svc = AgentResumeService(
            agent_run_repository=MagicMock(),
            tool_catalog=MagicMock(),
            tool_executor=MagicMock(),
            decision_runtime=None,
        )
        with patch("app.application.agent_resume_service.checkpoint_saver") as mock_saver:
            mock_saver.get_tuple.return_value = None
            result = svc._checkpoint_status("run-1", "agent-v2")
            assert result == "missing"

    def test_checkpoint_status_error(self):
        from unittest.mock import patch

        from app.application.agent_resume_service import AgentResumeService

        svc = AgentResumeService(
            agent_run_repository=MagicMock(),
            tool_catalog=MagicMock(),
            tool_executor=MagicMock(),
            decision_runtime=None,
        )
        with patch("app.application.agent_resume_service.checkpoint_saver") as mock_saver:
            mock_saver.get_tuple.side_effect = RuntimeError("no connection")
            result = svc._checkpoint_status("run-1", "agent-v2")
            assert result == "error"
