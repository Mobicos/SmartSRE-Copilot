"""Unit tests for app.infrastructure.tasks.agent_resume — AgentResumeDispatcher."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.infrastructure.tasks.agent_resume import (
    AgentResumeDispatcher,
    __getattr__ as resume_getattr,
)


def _make_settings(**overrides):
    defaults = {
        "task_queue_backend": "redis",
        "agent_resume_queue_name": "agent_resume_tasks",
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


class TestDefaultResumeProcessor:
    @pytest.mark.asyncio
    async def test_default_processor(self):
        mock_service = MagicMock()
        mock_service.process_resume_task = AsyncMock(return_value={"status": "ok"})
        with patch("app.api.providers.get_agent_resume_service", return_value=mock_service):
            from app.infrastructure.tasks import agent_resume

            result = await agent_resume._default_agent_resume_task_processor({"task_id": "t1"})
            assert result == {"status": "ok"}
            mock_service.process_resume_task.assert_called_once_with({"task_id": "t1"})


class TestAgentResumeDispatcher:
    def test_is_started_false(self):
        d = AgentResumeDispatcher(settings=_make_settings())
        assert d.is_started is False

    def test_custom_processor(self):
        proc = AsyncMock(return_value={"status": "ok"})
        d = AgentResumeDispatcher(settings=_make_settings(), resume_task_processor=proc)
        assert d._resume_task_processor is proc

    @pytest.mark.asyncio
    async def test_start_redis(self):
        with patch("app.infrastructure.tasks.agent_resume.redis_manager") as mock_rm:
            d = AgentResumeDispatcher(settings=_make_settings())
            await d.start()
            assert d.is_started is True
            mock_rm.initialize.assert_called_once()
            # Cleanup
            if d._worker_task:
                d._worker_task.cancel()
                try:
                    await d._worker_task
                except asyncio.CancelledError:
                    pass

    @pytest.mark.asyncio
    async def test_start_non_redis_idle(self):
        settings = _make_settings(task_queue_backend="sqlite")
        d = AgentResumeDispatcher(settings=settings)
        await d.start()
        assert d.is_started is True
        assert d._worker_task is None  # no worker in non-redis mode

    @pytest.mark.asyncio
    async def test_start_idempotent(self):
        with patch("app.infrastructure.tasks.agent_resume.redis_manager"):
            d = AgentResumeDispatcher(settings=_make_settings())
            await d.start()
            await d.start()  # second call noop
            assert d.is_started is True
            if d._worker_task:
                d._worker_task.cancel()
                try:
                    await d._worker_task
                except asyncio.CancelledError:
                    pass

    @pytest.mark.asyncio
    async def test_shutdown(self):
        with patch("app.infrastructure.tasks.agent_resume.redis_manager"):
            d = AgentResumeDispatcher(settings=_make_settings())
            await d.start()
            assert d.is_started is True
            await d.shutdown()
            assert d.is_started is False
            assert d._worker_task is None

    @pytest.mark.asyncio
    async def test_shutdown_when_not_started(self):
        d = AgentResumeDispatcher(settings=_make_settings())
        await d.shutdown()
        assert d.is_started is False


# ---------------------------------------------------------------------------
# Module __getattr__
# ---------------------------------------------------------------------------


class TestAgentResumeModuleGetattr:
    def test_getattr_agent_resume_dispatcher(self):
        result = resume_getattr("agent_resume_dispatcher")
        assert isinstance(result, AgentResumeDispatcher)

    def test_getattr_unknown_raises(self):
        with pytest.raises(AttributeError):
            resume_getattr("unknown_attr")
