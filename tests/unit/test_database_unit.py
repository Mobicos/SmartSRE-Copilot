"""Unit tests for app.platform.persistence.database — no live DB required."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import app.platform.persistence.database as db_module


@pytest.fixture(autouse=True)
def _reset_engine():
    """Reset module-level globals before and after each test."""
    original_engine = db_module._engine
    original_session = db_module._SessionLocal
    db_module._engine = None
    db_module._SessionLocal = None
    yield
    db_module._engine = original_engine
    db_module._SessionLocal = original_session


# ---------------------------------------------------------------------------
# get_engine — URI normalisation
# ---------------------------------------------------------------------------


class TestGetEngineUriNormalization:
    def test_empty_dsn_raises(self):
        settings = SimpleNamespace(postgres_dsn="", postgres_connect_timeout_seconds=5)
        with patch.object(db_module, "_get_settings", return_value=settings):
            with pytest.raises(RuntimeError, match="POSTGRES_DSN"):
                db_module.get_engine()

    def test_postgresql_plus_psycopg_unchanged(self):
        mock_engine = MagicMock()
        settings = SimpleNamespace(
            postgres_dsn="postgresql+psycopg://user:pass@localhost/db",
            postgres_connect_timeout_seconds=5,
        )
        with patch.object(db_module, "_get_settings", return_value=settings):
            with patch.object(db_module, "create_engine", return_value=mock_engine) as ce:
                with patch.object(db_module, "_install_pool_listeners"):
                    engine = db_module.get_engine()
                    assert engine is mock_engine
                    # URI should NOT be modified since it already has +psycopg
                    call_uri = ce.call_args[0][0]
                    assert "postgresql+psycopg://" in call_uri

    def test_plain_postgresql_gets_psycopg(self):
        mock_engine = MagicMock()
        settings = SimpleNamespace(
            postgres_dsn="postgresql://user:pass@localhost/db",
            postgres_connect_timeout_seconds=5,
        )
        with patch.object(db_module, "_get_settings", return_value=settings):
            with patch.object(db_module, "create_engine", return_value=mock_engine) as ce:
                with patch.object(db_module, "_install_pool_listeners"):
                    db_module.get_engine()
                    call_uri = ce.call_args[0][0]
                    assert call_uri.startswith("postgresql+psycopg://")

    def test_postgres_alias_gets_psycopg(self):
        mock_engine = MagicMock()
        settings = SimpleNamespace(
            postgres_dsn="postgres://user:pass@localhost/db",
            postgres_connect_timeout_seconds=5,
        )
        with patch.object(db_module, "_get_settings", return_value=settings):
            with patch.object(db_module, "create_engine", return_value=mock_engine) as ce:
                with patch.object(db_module, "_install_pool_listeners"):
                    db_module.get_engine()
                    call_uri = ce.call_args[0][0]
                    assert call_uri.startswith("postgresql+psycopg://")


# ---------------------------------------------------------------------------
# get_engine — singleton
# ---------------------------------------------------------------------------


class TestGetEngineSingleton:
    def test_returns_same_engine(self):
        mock_engine = MagicMock()
        settings = SimpleNamespace(
            postgres_dsn="postgresql://user:pass@localhost/db",
            postgres_connect_timeout_seconds=5,
        )
        with patch.object(db_module, "_get_settings", return_value=settings):
            with patch.object(db_module, "create_engine", return_value=mock_engine):
                with patch.object(db_module, "_install_pool_listeners"):
                    first = db_module.get_engine()
                    second = db_module.get_engine()
                    assert first is second


# ---------------------------------------------------------------------------
# reset_for_testing
# ---------------------------------------------------------------------------


class TestResetForTesting:
    def test_disposes_and_clears(self):
        mock_engine = MagicMock()
        db_module._engine = mock_engine
        db_module._SessionLocal = MagicMock()

        db_module.reset_for_testing()

        mock_engine.dispose.assert_called_once()
        assert db_module._engine is None
        assert db_module._SessionLocal is None

    def test_noop_when_engine_is_none(self):
        db_module._engine = None
        db_module._SessionLocal = None
        db_module.reset_for_testing()  # should not raise
        assert db_module._engine is None


# ---------------------------------------------------------------------------
# health_check
# ---------------------------------------------------------------------------


class TestHealthCheck:
    def test_success(self):
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchone.return_value = (1,)
        mock_engine = MagicMock()
        mock_engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)

        with patch.object(db_module, "get_engine", return_value=mock_engine):
            assert db_module.health_check() is True

    def test_failure_returns_false(self):
        with patch.object(db_module, "get_engine", side_effect=RuntimeError("boom")):
            assert db_module.health_check() is False

    def test_null_row_returns_false(self):
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchone.return_value = None
        mock_engine = MagicMock()
        mock_engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)

        with patch.object(db_module, "get_engine", return_value=mock_engine):
            assert db_module.health_check() is False


# ---------------------------------------------------------------------------
# get_pool_status
# ---------------------------------------------------------------------------


class TestGetPoolStatus:
    def test_returns_expected_keys(self):
        mock_pool = MagicMock()
        mock_pool.size.return_value = 5
        mock_pool.checkedout.return_value = 2
        mock_pool.checkedin.return_value = 3
        mock_pool.overflow.return_value = 0

        mock_engine = MagicMock()
        mock_engine.pool = mock_pool

        with patch.object(db_module, "get_engine", return_value=mock_engine):
            with patch("app.platform.persistence.database.cast", return_value=mock_pool):
                status = db_module.get_pool_status()
                assert status["pool_size"] == 5
                assert status["checked_out"] == 2
                assert status["checked_in"] == 3
                assert status["overflow"] == 0


# ---------------------------------------------------------------------------
# get_session_factory
# ---------------------------------------------------------------------------


class TestGetSessionFactory:
    def test_singleton(self):
        mock_engine = MagicMock()
        db_module._engine = mock_engine
        db_module._SessionLocal = None

        factory = db_module.get_session_factory()
        assert factory is not None
        # Second call returns same factory
        assert db_module.get_session_factory() is factory
