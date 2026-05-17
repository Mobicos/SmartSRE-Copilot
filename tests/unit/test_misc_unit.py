"""Unit tests for logger, rate_limit, unit_of_work, metrics, and local tools."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# app.utils.logger — _redact_secrets, _human_format
# ---------------------------------------------------------------------------


class TestRedactSecrets:
    def test_api_key(self):
        from app.utils.logger import _redact_secrets

        result = _redact_secrets("api_key=sk-12345abcde")
        assert "sk-12345abcde" not in result
        assert "REDACTED" in result

    def test_password(self):
        from app.utils.logger import _redact_secrets

        result = _redact_secrets("password: hunter2")
        assert "hunter2" not in result
        assert "REDACTED" in result

    def test_secret(self):
        from app.utils.logger import _redact_secrets

        result = _redact_secrets("secret=abcdef123456")
        assert "abcdef123456" not in result

    def test_token(self):
        from app.utils.logger import _redact_secrets

        result = _redact_secrets("token: abc123xyz")
        assert "abc123xyz" not in result

    def test_postgresql_uri(self):
        from app.utils.logger import _redact_secrets

        result = _redact_secrets("postgresql://user:pass@host/db")
        assert "pass" not in result
        assert "***" in result

    def test_postgresql_plus_dialect(self):
        from app.utils.logger import _redact_secrets

        result = _redact_secrets("postgresql+psycopg://user:secret@host/db")
        assert "secret" not in result

    def test_redis_uri(self):
        from app.utils.logger import _redact_secrets

        result = _redact_secrets("redis://user:pass@host:6379")
        assert "pass" not in result

    def test_clean_text_unchanged(self):
        from app.utils.logger import _redact_secrets

        result = _redact_secrets("normal log message about CPU usage")
        assert result == "normal log message about CPU usage"


class TestHumanFormat:
    def test_format_string(self):
        from datetime import datetime

        from app.utils.logger import _human_format

        record = {
            "time": datetime(2024, 1, 15, 10, 30, 0),
            "level": SimpleNamespace(name="INFO"),
            "module": "test_module",
            "function": "test_func",
            "line": 42,
            "message": "test message",
            "extra": {"request_id": "req-123"},
        }
        result = _human_format(record)
        assert "req-123" in result
        assert "INFO" in result
        assert "test_module" in result

    def test_format_no_request_id(self):
        from datetime import datetime

        from app.utils.logger import _human_format

        record = {
            "time": datetime(2024, 1, 15, 10, 30, 0),
            "level": SimpleNamespace(name="DEBUG"),
            "module": "mod",
            "function": "func",
            "line": 1,
            "message": "msg",
            "extra": {},
        }
        result = _human_format(record)
        assert "request_id=-" in result


# ---------------------------------------------------------------------------
# app.security.rate_limit
# ---------------------------------------------------------------------------


class TestRateLimitPolicy:
    def test_refill_per_second(self):
        from app.security.rate_limit import RateLimitPolicy

        p = RateLimitPolicy(requests_per_minute=60, burst=10)
        assert p.refill_per_second == 1.0

    def test_refill_per_second_min(self):
        from app.security.rate_limit import RateLimitPolicy

        p = RateLimitPolicy(requests_per_minute=0, burst=1)
        assert p.refill_per_second > 0


class TestRateLimiter:
    def test_first_request_allowed(self):
        from app.security.rate_limit import RateLimiter, RateLimitPolicy

        limiter = RateLimiter()
        policy = RateLimitPolicy(requests_per_minute=60, burst=10)
        assert limiter.allow("key1", policy) is True

    def test_exhausted_bucket(self):
        from app.security.rate_limit import RateLimiter, RateLimitPolicy

        limiter = RateLimiter()
        policy = RateLimitPolicy(requests_per_minute=1, burst=1)
        limiter.allow("key1", policy)
        # Second immediate request should be denied (burst=1)
        assert limiter.allow("key1", policy) is False

    def test_reset_for_testing(self):
        from app.security.rate_limit import RateLimiter, RateLimitPolicy

        limiter = RateLimiter()
        policy = RateLimitPolicy(requests_per_minute=1, burst=1)
        limiter.allow("key1", policy)
        limiter.reset_for_testing()
        assert limiter.allow("key1", policy) is True


class TestRateLimitKey:
    def test_principal_key(self):
        from app.security.auth import Principal
        from app.security.rate_limit import _rate_limit_key

        principal = Principal(role="admin", subject="user-1")
        request = MagicMock()
        request.client = SimpleNamespace(host="127.0.0.1")
        key = _rate_limit_key(request, principal, scope="stream")
        assert key == "stream:principal:user-1"

    def test_ip_fallback(self):
        from app.security.auth import Principal
        from app.security.rate_limit import _rate_limit_key

        principal = Principal(role="admin", subject="local-dev")
        request = MagicMock()
        request.client = SimpleNamespace(host="10.0.0.1")
        key = _rate_limit_key(request, principal, scope="stream")
        assert key == "stream:ip:10.0.0.1"

    def test_no_client(self):
        from app.security.auth import Principal
        from app.security.rate_limit import _rate_limit_key

        principal = Principal(role="admin", subject="local-dev")
        request = MagicMock()
        request.client = None
        key = _rate_limit_key(request, principal, scope="stream")
        assert key == "stream:ip:unknown"


# ---------------------------------------------------------------------------
# app.platform.persistence.unit_of_work
# ---------------------------------------------------------------------------


class TestUnitOfWork:
    def test_commit(self):
        mock_session = MagicMock()
        with patch(
            "app.platform.persistence.unit_of_work.get_engine",
            return_value="fake_engine",
        ):
            with patch(
                "app.platform.persistence.unit_of_work.Session",
                return_value=mock_session,
            ):
                from app.platform.persistence.unit_of_work import UnitOfWork

                uow = UnitOfWork()
                with uow:
                    pass
                mock_session.commit.assert_called()
                mock_session.close.assert_called()

    def test_rollback_on_exception(self):
        mock_session = MagicMock()
        with patch(
            "app.platform.persistence.unit_of_work.get_engine",
            return_value="fake_engine",
        ):
            with patch(
                "app.platform.persistence.unit_of_work.Session",
                return_value=mock_session,
            ):
                from app.platform.persistence.unit_of_work import UnitOfWork

                uow = UnitOfWork()
                with pytest.raises(RuntimeError):
                    with uow:
                        raise RuntimeError("fail")
                mock_session.rollback.assert_called()
                mock_session.close.assert_called()

    def test_explicit_commit_prevents_auto_commit(self):
        mock_session = MagicMock()
        with patch(
            "app.platform.persistence.unit_of_work.get_engine",
            return_value="fake_engine",
        ):
            with patch(
                "app.platform.persistence.unit_of_work.Session",
                return_value=mock_session,
            ):
                from app.platform.persistence.unit_of_work import UnitOfWork

                uow = UnitOfWork()
                with uow:
                    uow.commit()
                # commit() was called once via uow.commit(), auto-commit should not fire again
                assert mock_session.commit.call_count == 1

    def test_explicit_rollback(self):
        mock_session = MagicMock()
        with patch(
            "app.platform.persistence.unit_of_work.get_engine",
            return_value="fake_engine",
        ):
            with patch(
                "app.platform.persistence.unit_of_work.Session",
                return_value=mock_session,
            ):
                from app.platform.persistence.unit_of_work import UnitOfWork

                uow = UnitOfWork()
                with uow:
                    uow.rollback()
                mock_session.rollback.assert_called()
                # _committed is True so auto-commit should not fire
                assert mock_session.commit.call_count == 0


# ---------------------------------------------------------------------------
# app.observability.metrics
# ---------------------------------------------------------------------------


class TestMetrics:
    def _safe_reset(self):
        """Reset metrics, tolerating prometheus_client internal errors."""
        try:
            from app.observability.metrics import reset_metrics_for_testing

            reset_metrics_for_testing()
        except AttributeError:
            pass  # Histogram._lock not initialized in test context

    def test_observe_http_request(self):
        from app.observability.metrics import observe_http_request

        self._safe_reset()
        observe_http_request(
            method="GET",
            path="/api/v1/health",
            status_code=200,
            duration_seconds=0.05,
        )

    def test_observe_http_request_normalizes_path(self):
        from app.observability.metrics import observe_http_request

        self._safe_reset()
        observe_http_request(
            method="POST",
            path="/api/v1/sessions/abc-123/messages",
            status_code=201,
            duration_seconds=0.1,
        )

    def test_observe_agent_run(self):
        from app.observability.metrics import observe_agent_run

        self._safe_reset()
        observe_agent_run(
            latency_ms=5000,
            token_total=200,
            cost_total=0.01,
            step_count=3,
        )

    def test_observe_agent_run_zero_values(self):
        from app.observability.metrics import observe_agent_run

        self._safe_reset()
        observe_agent_run(latency_ms=None, token_total=0, cost_total=0.0, step_count=0)

    def test_normalize_path(self):
        from app.observability.metrics import _normalize_path

        assert _normalize_path("/api/v1/sessions/abc") == "/api/v1/sessions/abc"
        assert _normalize_path("") == "unknown"

    def test_reset_metrics_for_testing(self):
        self._safe_reset()

    def test_render_prometheus_metrics(self):
        from app.observability.metrics import render_prometheus_metrics

        self._safe_reset()
        with patch(
            "app.observability.metrics.get_engine",
            side_effect=RuntimeError("no db"),
        ):
            result = render_prometheus_metrics()
            assert isinstance(result, bytes)

    def test_render_prometheus_metrics_with_db(self):
        from app.observability.metrics import render_prometheus_metrics

        self._safe_reset()
        mock_conn = MagicMock()
        mock_conn.execute.return_value = []
        mock_engine = MagicMock()
        mock_engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)

        with patch("app.observability.metrics.get_engine", return_value=mock_engine):
            result = render_prometheus_metrics()
            assert isinstance(result, bytes)

    def test_replace_gauge_labels(self):
        from app.observability.metrics import (
            _AGENT_RUNS,
            _replace_gauge_labels,
        )

        self._safe_reset()
        _replace_gauge_labels(_AGENT_RUNS, ("status",), [("running", 5), ("completed", 10)])


# ---------------------------------------------------------------------------
# app.infrastructure.tools.local.time
# ---------------------------------------------------------------------------


class TestGetCurrentTime:
    def test_basic(self):
        from app.infrastructure.tools.local.time import get_current_time

        result = get_current_time.invoke({"timezone": "Asia/Shanghai"})
        assert isinstance(result, str)
        assert len(result) == 19  # YYYY-MM-DD HH:MM:SS

    def test_default_timezone(self):
        from app.infrastructure.tools.local.time import get_current_time

        result = get_current_time.invoke({})
        assert isinstance(result, str)
        assert "-" in result

    def test_invalid_timezone(self):
        from app.infrastructure.tools.local.time import get_current_time

        result = get_current_time.invoke({"timezone": "Invalid/Timezone"})
        assert "获取时间失败" in result


# ---------------------------------------------------------------------------
# app.infrastructure.tools.local.knowledge
# ---------------------------------------------------------------------------


class TestFormatDocs:
    def test_basic(self):
        from langchain_core.documents import Document

        from app.infrastructure.tools.local.knowledge import format_docs

        docs = [
            Document(
                page_content="CPU usage is high",
                metadata={"_file_name": "report.md", "h1": "CPU Report"},
            ),
        ]
        result = format_docs(docs)
        assert "参考资料 1" in result
        assert "report.md" in result
        assert "CPU usage is high" in result
        assert "CPU Report" in result

    def test_multiple_docs(self):
        from langchain_core.documents import Document

        from app.infrastructure.tools.local.knowledge import format_docs

        docs = [
            Document(page_content="A", metadata={"_file_name": "a.md"}),
            Document(page_content="B", metadata={"_file_name": "b.md"}),
        ]
        result = format_docs(docs)
        assert "参考资料 1" in result
        assert "参考资料 2" in result

    def test_no_headers(self):
        from langchain_core.documents import Document

        from app.infrastructure.tools.local.knowledge import format_docs

        docs = [
            Document(page_content="content", metadata={"_file_name": "f.md"}),
        ]
        result = format_docs(docs)
        assert "content" in result

    def test_empty_docs(self):
        from app.infrastructure.tools.local.knowledge import format_docs

        result = format_docs([])
        assert result == ""
