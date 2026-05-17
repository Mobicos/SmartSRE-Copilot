"""Unit tests for task dispatcher and agent resume dispatcher — no live DB/Redis."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.infrastructure.tasks.dispatcher import LocalTaskDispatcher

# ---------------------------------------------------------------------------
# LocalTaskDispatcher
# ---------------------------------------------------------------------------


class TestLocalTaskDispatcher:
    def _make_settings(self, **overrides) -> SimpleNamespace:
        defaults = {
            "task_queue_backend": "database",
            "task_requeue_timeout_seconds": 300,
            "task_poll_interval_ms": 100,
            "redis_task_queue_name": "indexing",
        }
        defaults.update(overrides)
        return SimpleNamespace(**defaults)

    def test_init_default_processor(self):
        dispatcher = LocalTaskDispatcher(settings=self._make_settings())
        assert dispatcher._indexing_task_processor is not None

    def test_init_custom_processor(self):
        custom = MagicMock(return_value="ok")
        dispatcher = LocalTaskDispatcher(
            settings=self._make_settings(),
            indexing_task_processor=custom,
        )
        assert dispatcher._indexing_task_processor is custom

    def test_is_started_false_before_start(self):
        dispatcher = LocalTaskDispatcher(settings=self._make_settings())
        assert dispatcher.is_started is False

    @pytest.mark.asyncio
    async def test_start_sets_started(self):
        settings = self._make_settings()
        dispatcher = LocalTaskDispatcher(settings=settings)
        with patch("app.infrastructure.tasks.dispatcher.indexing_task_repository") as mock_repo:
            mock_repo.requeue_stale_processing_tasks.return_value = 0
            # Start creates an asyncio task, which runs _worker_loop
            # We mock the worker loop to avoid it running indefinitely
            with patch.object(dispatcher, "_worker_loop", new_callable=AsyncMock):
                await dispatcher.start()
                assert dispatcher.is_started is True
                mock_repo.requeue_stale_processing_tasks.assert_called_once_with(
                    settings.task_requeue_timeout_seconds
                )
        # Cleanup
        await dispatcher.shutdown()

    @pytest.mark.asyncio
    async def test_shutdown_sets_not_started(self):
        settings = self._make_settings()
        dispatcher = LocalTaskDispatcher(settings=settings)
        with patch("app.infrastructure.tasks.dispatcher.indexing_task_repository") as mock_repo:
            mock_repo.requeue_stale_processing_tasks.return_value = 0
            with patch.object(dispatcher, "_worker_loop", new_callable=AsyncMock):
                await dispatcher.start()
                await dispatcher.shutdown()
                assert dispatcher.is_started is False

    @pytest.mark.asyncio
    async def test_start_is_idempotent(self):
        settings = self._make_settings()
        dispatcher = LocalTaskDispatcher(settings=settings)
        with patch("app.infrastructure.tasks.dispatcher.indexing_task_repository") as mock_repo:
            mock_repo.requeue_stale_processing_tasks.return_value = 0
            with patch.object(dispatcher, "_worker_loop", new_callable=AsyncMock):
                await dispatcher.start()
                await dispatcher.start()  # second call should be noop
                assert mock_repo.requeue_stale_processing_tasks.call_count == 1
        await dispatcher.shutdown()

    @pytest.mark.asyncio
    async def test_shutdown_when_not_started_is_noop(self):
        dispatcher = LocalTaskDispatcher(settings=self._make_settings())
        await dispatcher.shutdown()  # should not raise
        assert dispatcher.is_started is False


# ---------------------------------------------------------------------------
# AgentResumeDispatcher
# ---------------------------------------------------------------------------


class TestAgentResumeDispatcher:
    def _make_settings(self, **overrides) -> SimpleNamespace:
        defaults = {
            "task_queue_backend": "database",
            "agent_resume_queue_name": "resume",
        }
        defaults.update(overrides)
        return SimpleNamespace(**defaults)

    def test_is_started_false_before_start(self):
        from app.infrastructure.tasks.agent_resume import AgentResumeDispatcher

        dispatcher = AgentResumeDispatcher(settings=self._make_settings())
        assert dispatcher.is_started is False

    @pytest.mark.asyncio
    async def test_start_non_redis_sets_started(self):
        from app.infrastructure.tasks.agent_resume import AgentResumeDispatcher

        settings = self._make_settings(task_queue_backend="database")
        dispatcher = AgentResumeDispatcher(settings=settings)
        await dispatcher.start()
        assert dispatcher.is_started is True
        await dispatcher.shutdown()

    @pytest.mark.asyncio
    async def test_shutdown_sets_not_started(self):
        from app.infrastructure.tasks.agent_resume import AgentResumeDispatcher

        settings = self._make_settings(task_queue_backend="database")
        dispatcher = AgentResumeDispatcher(settings=settings)
        await dispatcher.start()
        await dispatcher.shutdown()
        assert dispatcher.is_started is False

    @pytest.mark.asyncio
    async def test_shutdown_when_not_started_is_noop(self):
        from app.infrastructure.tasks.agent_resume import AgentResumeDispatcher

        dispatcher = AgentResumeDispatcher(settings=self._make_settings())
        await dispatcher.shutdown()
        assert dispatcher.is_started is False
