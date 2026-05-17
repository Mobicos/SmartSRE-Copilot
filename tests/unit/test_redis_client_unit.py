"""Unit tests for app.infrastructure.redis_client — URL helper and RedisManager."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.infrastructure.redis_client import (
    RedisManager,
    _configure_redis_manager,
    _get_redis_manager,
    _redis_url_with_configured_password,
)

# ---------------------------------------------------------------------------
# _redis_url_with_configured_password
# ---------------------------------------------------------------------------


class TestRedisUrlPassword:
    def _make_settings(self, redis_password: str = ""):
        return SimpleNamespace(redis_password=redis_password)

    def test_empty_password_returns_original(self):
        url = "redis://localhost:6379"
        result = _redis_url_with_configured_password(url, self._make_settings(""))
        assert result == url

    def test_whitespace_password_returns_original(self):
        url = "redis://localhost:6379"
        result = _redis_url_with_configured_password(url, self._make_settings("   "))
        assert result == url

    def test_password_injected(self):
        url = "redis://localhost:6379"
        result = _redis_url_with_configured_password(url, self._make_settings("secret123"))
        assert "secret123" in result
        assert "@" in result
        assert result.startswith("redis://:")

    def test_existing_auth_preserved(self):
        url = "redis://:existing@localhost:6379"
        result = _redis_url_with_configured_password(url, self._make_settings("newpass"))
        assert result == url

    def test_special_chars_in_password(self):
        url = "redis://localhost:6379"
        result = _redis_url_with_configured_password(url, self._make_settings("p@ss:w0rd!"))
        assert "@localhost" in result


# ---------------------------------------------------------------------------
# RedisManager
# ---------------------------------------------------------------------------


class TestRedisManager:
    def _make_manager(self):
        settings = SimpleNamespace(redis_password="")
        return RedisManager("redis://localhost:6379", settings=settings)

    def test_is_initialized_false(self):
        manager = self._make_manager()
        assert manager.is_initialized is False

    def test_initialize_sets_client(self):
        manager = self._make_manager()
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        with patch("app.infrastructure.redis_client.RedisClient") as MockRedis:
            MockRedis.from_url.return_value = mock_client
            with patch(
                "app.infrastructure.redis_client._redis_url_with_configured_password",
                return_value="redis://localhost:6379",
            ):
                manager.initialize()
                assert manager.is_initialized is True
                mock_client.ping.assert_called()

    def test_initialize_idempotent(self):
        manager = self._make_manager()
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        with patch("app.infrastructure.redis_client.RedisClient") as MockRedis:
            MockRedis.from_url.return_value = mock_client
            with patch(
                "app.infrastructure.redis_client._redis_url_with_configured_password",
                return_value="redis://localhost:6379",
            ):
                manager.initialize()
                manager.initialize()  # second call is noop
                assert MockRedis.from_url.call_count == 1

    def test_health_check_success(self):
        manager = self._make_manager()
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        with patch("app.infrastructure.redis_client.RedisClient") as MockRedis:
            MockRedis.from_url.return_value = mock_client
            with patch(
                "app.infrastructure.redis_client._redis_url_with_configured_password",
                return_value="redis://localhost:6379",
            ):
                assert manager.health_check() is True

    def test_health_check_failure(self):
        manager = self._make_manager()
        with patch("app.infrastructure.redis_client.RedisClient", None):
            with patch(
                "app.infrastructure.redis_client._redis_url_with_configured_password",
                return_value="redis://localhost:6379",
            ):
                assert manager.health_check() is False

    def test_enqueue_json(self):
        manager = self._make_manager()
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        with patch("app.infrastructure.redis_client.RedisClient") as MockRedis:
            MockRedis.from_url.return_value = mock_client
            with patch(
                "app.infrastructure.redis_client._redis_url_with_configured_password",
                return_value="redis://localhost:6379",
            ):
                manager.enqueue_json("myqueue", {"key": "value"})
                mock_client.rpush.assert_called_once()
                call_args = mock_client.rpush.call_args
                assert call_args[0][0] == "myqueue"
                assert '"key"' in call_args[0][1]

    def test_dequeue_json_empty(self):
        manager = self._make_manager()
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_client.blpop.return_value = None
        with patch("app.infrastructure.redis_client.RedisClient") as MockRedis:
            MockRedis.from_url.return_value = mock_client
            with patch(
                "app.infrastructure.redis_client._redis_url_with_configured_password",
                return_value="redis://localhost:6379",
            ):
                result = manager.dequeue_json("myqueue", timeout_seconds=5)
                assert result is None

    def test_dequeue_json_with_payload(self):
        import json

        manager = self._make_manager()
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_client.blpop.return_value = (b"queue", json.dumps({"key": "val"}).encode())
        with patch("app.infrastructure.redis_client.RedisClient") as MockRedis:
            MockRedis.from_url.return_value = mock_client
            with patch(
                "app.infrastructure.redis_client._redis_url_with_configured_password",
                return_value="redis://localhost:6379",
            ):
                result = manager.dequeue_json("myqueue", timeout_seconds=5)
                assert result == {"key": "val"}

    def test_dequeue_json_non_dict_returns_none(self):
        import json

        manager = self._make_manager()
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_client.blpop.return_value = (b"queue", json.dumps([1, 2]).encode())
        with patch("app.infrastructure.redis_client.RedisClient") as MockRedis:
            MockRedis.from_url.return_value = mock_client
            with patch(
                "app.infrastructure.redis_client._redis_url_with_configured_password",
                return_value="redis://localhost:6379",
            ):
                result = manager.dequeue_json("myqueue", timeout_seconds=5)
                assert result is None

    def test_connect_without_redis_raises(self):
        manager = self._make_manager()
        with patch("app.infrastructure.redis_client.RedisClient", None):
            with pytest.raises(RuntimeError, match="Redis support"):
                manager._connect()


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


class TestRedisModuleHelpers:
    def test_configure_redis_manager(self):
        settings = SimpleNamespace(redis_url="redis://localhost:6379", redis_password="")
        _configure_redis_manager(settings)
        # Next _get_redis_manager should create new instance
        manager = _get_redis_manager()
        assert isinstance(manager, RedisManager)

    def test_getattr_redis_manager(self):
        from app.infrastructure import redis_client

        manager = redis_client.__getattr__("redis_manager")
        assert isinstance(manager, RedisManager)

    def test_getattr_unknown_raises(self):
        from app.infrastructure import redis_client

        with pytest.raises(AttributeError):
            redis_client.__getattr__("unknown_attr")
