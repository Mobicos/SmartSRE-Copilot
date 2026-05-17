"""Unit tests for app.infrastructure.tasks.dispatcher — async lifecycle."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.infrastructure.tasks.dispatcher import (
    LocalTaskDispatcher,
    __getattr__ as dispatcher_getattr,
)


def _make_settings(**overrides):
    defaults = {
        "task_requeue_timeout_seconds": 300,
        "task_queue_backend": "sqlite",
        "task_poll_interval_ms": 200,
        "redis_task_queue_name": "indexing_tasks",
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


# ---------------------------------------------------------------------------
# LocalTaskDispatcher
# ---------------------------------------------------------------------------


class TestDefaultProcessor:
    def test_default_indexing_processor(self):
        mock_service = MagicMock()
        mock_service.process_task.return_value = "completed"
        with patch("app.api.providers.get_indexing_task_service", return_value=mock_service):
            from app.infrastructure.tasks import dispatcher

            result = dispatcher._default_indexing_task_processor("t1", "/path/file.py")
            assert result == "completed"
            mock_service.process_task.assert_called_once_with("t1", "/path/file.py")


class TestLocalTaskDispatcher:
    def test_is_started_false(self):
        d = LocalTaskDispatcher(settings=_make_settings())
        assert d.is_started is False

    def test_custom_processor(self):
        proc = MagicMock(return_value="done")
        d = LocalTaskDispatcher(settings=_make_settings(), indexing_task_processor=proc)
        assert d._indexing_task_processor is proc

    @pytest.mark.asyncio
    async def test_start_sets_started(self):
        with patch("app.infrastructure.tasks.dispatcher.indexing_task_repository") as mock_repo:
            mock_repo.requeue_stale_processing_tasks.return_value = 0
            d = LocalTaskDispatcher(settings=_make_settings())
            await d.start()
            assert d.is_started is True
            mock_repo.requeue_stale_processing_tasks.assert_called_once()
            # Cancel the worker task
            if d._worker_task:
                d._worker_task.cancel()
                try:
                    await d._worker_task
                except asyncio.CancelledError:
                    pass

    @pytest.mark.asyncio
    async def test_start_idempotent(self):
        with patch("app.infrastructure.tasks.dispatcher.indexing_task_repository") as mock_repo:
            mock_repo.requeue_stale_processing_tasks.return_value = 0
            d = LocalTaskDispatcher(settings=_make_settings())
            await d.start()
            await d.start()  # second call should be noop
            assert d.is_started is True
            if d._worker_task:
                d._worker_task.cancel()
                try:
                    await d._worker_task
                except asyncio.CancelledError:
                    pass

    @pytest.mark.asyncio
    async def test_start_requeues_stale(self):
        with patch("app.infrastructure.tasks.dispatcher.indexing_task_repository") as mock_repo:
            mock_repo.requeue_stale_processing_tasks.return_value = 3
            d = LocalTaskDispatcher(settings=_make_settings())
            await d.start()
            mock_repo.requeue_stale_processing_tasks.assert_called_once_with(300)
            if d._worker_task:
                d._worker_task.cancel()
                try:
                    await d._worker_task
                except asyncio.CancelledError:
                    pass

    @pytest.mark.asyncio
    async def test_shutdown(self):
        with patch("app.infrastructure.tasks.dispatcher.indexing_task_repository") as mock_repo:
            mock_repo.requeue_stale_processing_tasks.return_value = 0
            d = LocalTaskDispatcher(settings=_make_settings())
            await d.start()
            assert d.is_started is True
            await d.shutdown()
            assert d.is_started is False
            assert d._worker_task is None

    @pytest.mark.asyncio
    async def test_shutdown_when_not_started(self):
        d = LocalTaskDispatcher(settings=_make_settings())
        await d.shutdown()  # should be noop
        assert d.is_started is False

    @pytest.mark.asyncio
    async def test_enqueue_redis(self):
        settings = _make_settings(task_queue_backend="redis")
        d = LocalTaskDispatcher(settings=settings)
        with patch("app.infrastructure.tasks.dispatcher.redis_manager") as mock_rm:
            await d.enqueue_indexing_task("t1", "/path/file.py")
            mock_rm.enqueue_json.assert_called_once_with(
                "indexing_tasks", {"task_id": "t1", "file_path": "/path/file.py"}
            )

    @pytest.mark.asyncio
    async def test_enqueue_local_started(self):
        settings = _make_settings(task_queue_backend="sqlite")
        d = LocalTaskDispatcher(settings=settings)
        d._started = True
        d._wake_event = asyncio.Event()
        await d.enqueue_indexing_task("t1", "/path")
        assert d._wake_event.is_set()

    @pytest.mark.asyncio
    async def test_enqueue_local_not_started(self):
        settings = _make_settings(task_queue_backend="sqlite")
        d = LocalTaskDispatcher(settings=settings)
        d._wake_event = asyncio.Event()
        await d.enqueue_indexing_task("t1", "/path")
        # wake_event should not be set when not started
        assert not d._wake_event.is_set()


# ---------------------------------------------------------------------------
# Module __getattr__
# ---------------------------------------------------------------------------


class TestDispatcherModuleGetattr:
    def test_getattr_task_dispatcher(self):
        result = dispatcher_getattr("task_dispatcher")
        assert isinstance(result, LocalTaskDispatcher)

    def test_getattr_unknown_raises(self):
        with pytest.raises(AttributeError):
            dispatcher_getattr("unknown_attr")
