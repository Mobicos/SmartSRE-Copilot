"""Unit tests for app.main — FastAPI app setup, middleware, exception handlers."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient

from app.core.exceptions import AppException, DomainException, InfrastructureException
from app.main import (
    _generate_operation_id,
    _init_otel,
    _write_audit_log,
    app,
    app_exception_handler,
    http_exception_handler,
    request_validation_exception_handler,
    unhandled_exception_handler,
)

# ---------------------------------------------------------------------------
# _generate_operation_id
# ---------------------------------------------------------------------------


class TestGenerateOperationId:
    def test_with_tag_and_methods(self):
        route = MagicMock()
        route.tags = ["Health"]
        route.methods = {"GET", "POST"}
        route.name = "health_check"
        route.path_format = "/health"
        result = _generate_operation_id(route)
        assert result == "Health-health_check-get-health"

    def test_no_tags(self):
        route = MagicMock()
        route.tags = []
        route.methods = {"GET"}
        route.name = "root"
        route.path_format = "/"
        result = _generate_operation_id(route)
        assert "Default" in result
        assert "root" in result

    def test_path_with_params(self):
        route = MagicMock()
        route.tags = ["API"]
        route.methods = {"GET"}
        route.name = "get_item"
        route.path_format = "/items/{item_id}"
        result = _generate_operation_id(route)
        assert "items_item_id" in result

    def test_no_methods(self):
        route = MagicMock()
        route.tags = ["X"]
        route.methods = None
        route.name = "noop"
        route.path_format = "/test"
        result = _generate_operation_id(route)
        assert "get" in result


# ---------------------------------------------------------------------------
# _init_otel
# ---------------------------------------------------------------------------


class TestInitOtel:
    @patch.dict("os.environ", {"OTEL_ENABLED": ""})
    def test_disabled(self):
        # Should not raise
        _init_otel()

    @patch.dict("os.environ", {"OTEL_ENABLED": "false"})
    def test_disabled_false(self):
        _init_otel()

    @patch.dict("os.environ", {"OTEL_ENABLED": "1"})
    def test_import_error_graceful(self):
        with patch.dict("sys.modules", {"opentelemetry": None}):
            _init_otel()  # should not raise

    @patch.dict("os.environ", {"OTEL_ENABLED": "true"})
    def test_initialization_failure(self):
        import builtins

        _real_import = builtins.__import__

        def _fail_import(name, *args, **kwargs):
            if name.startswith("opentelemetry"):
                raise ImportError("no module")
            return _real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=_fail_import):
            _init_otel()


# ---------------------------------------------------------------------------
# Exception handlers
# ---------------------------------------------------------------------------


def _make_request(path: str = "/test", request_id: str | None = None):
    request = MagicMock(spec=Request)
    request.state = SimpleNamespace(request_id=request_id)
    request.client = SimpleNamespace(host="127.0.0.1")
    request.method = "GET"
    request.url = SimpleNamespace(path=path)
    request.headers = {"user-agent": "test-agent"}
    return request


class TestAppExceptionHandler:
    @pytest.mark.asyncio
    async def test_app_exception(self):
        request = _make_request()
        exc = AppException("something broke", code="test_error", status_code=422)
        with patch("app.main.error_response") as mock_resp:
            mock_resp.return_value = MagicMock(status_code=422)
            await app_exception_handler(request, exc)
            mock_resp.assert_called_once()
            call_kwargs = mock_resp.call_args[1]
            assert call_kwargs["status_code"] == 422
            assert call_kwargs["code"] == "test_error"
            assert call_kwargs["message"] == "something broke"

    @pytest.mark.asyncio
    async def test_domain_exception(self):
        request = _make_request()
        exc = DomainException("bad input")
        with patch("app.main.error_response") as mock_resp:
            mock_resp.return_value = MagicMock(status_code=400)
            await app_exception_handler(request, exc)
            call_kwargs = mock_resp.call_args[1]
            assert call_kwargs["status_code"] == 400

    @pytest.mark.asyncio
    async def test_infrastructure_exception(self):
        request = _make_request()
        exc = InfrastructureException()
        with patch("app.main.error_response") as mock_resp:
            mock_resp.return_value = MagicMock(status_code=500)
            await app_exception_handler(request, exc)
            call_kwargs = mock_resp.call_args[1]
            assert call_kwargs["code"] == "infrastructure_error"


class TestHttpExceptionHandler:
    @pytest.mark.asyncio
    async def test_string_detail(self):
        request = _make_request()
        exc = HTTPException(status_code=404, detail="not found")
        with patch("app.main.error_response") as mock_resp:
            mock_resp.return_value = MagicMock(status_code=404)
            await http_exception_handler(request, exc)
            call_kwargs = mock_resp.call_args[1]
            assert call_kwargs["status_code"] == 404
            assert call_kwargs["code"] == "not found"

    @pytest.mark.asyncio
    async def test_non_string_detail(self):
        request = _make_request()
        exc = HTTPException(status_code=422, detail={"error": "validation"})
        with patch("app.main.error_response") as mock_resp:
            mock_resp.return_value = MagicMock(status_code=422)
            await http_exception_handler(request, exc)
            call_kwargs = mock_resp.call_args[1]
            assert call_kwargs["code"] == "request_error"


class TestRequestValidationExceptionHandler:
    @pytest.mark.asyncio
    async def test_validation_error(self):
        request = _make_request()
        exc = RequestValidationError(errors=[{"loc": ("body",), "msg": "required"}])
        with patch("app.main.error_response") as mock_resp:
            mock_resp.return_value = MagicMock(status_code=422)
            await request_validation_exception_handler(request, exc)
            call_kwargs = mock_resp.call_args[1]
            assert call_kwargs["status_code"] == 422
            assert call_kwargs["code"] == "validation_error"


class TestUnhandledExceptionHandler:
    @pytest.mark.asyncio
    async def test_unhandled(self):
        request = _make_request()
        exc = RuntimeError("oops")
        with patch("app.main.error_response") as mock_resp:
            mock_resp.return_value = MagicMock(status_code=500)
            await unhandled_exception_handler(request, exc)
            call_kwargs = mock_resp.call_args[1]
            assert call_kwargs["status_code"] == 500
            assert call_kwargs["code"] == "internal_error"


# ---------------------------------------------------------------------------
# _write_audit_log
# ---------------------------------------------------------------------------


class TestWriteAuditLog:
    def test_writes_log(self):
        request = _make_request()
        request.state.principal = SimpleNamespace(subject="user1", role="admin")
        with patch("app.main.audit_log_repository") as mock_repo:
            _write_audit_log(request, request_id="req-1", status_code=200)
            mock_repo.log_request.assert_called_once()

    def test_no_principal(self):
        request = _make_request()
        request.state.principal = None
        with patch("app.main.audit_log_repository") as mock_repo:
            _write_audit_log(request, request_id="req-1", status_code=200)
            call_kwargs = mock_repo.log_request.call_args[1]
            assert call_kwargs["subject"] is None

    def test_no_client(self):
        request = _make_request()
        request.client = None
        with patch("app.main.audit_log_repository") as mock_repo:
            _write_audit_log(request, request_id="req-1", status_code=200)
            call_kwargs = mock_repo.log_request.call_args[1]
            assert call_kwargs["client_ip"] is None

    def test_with_error_message(self):
        request = _make_request()
        with patch("app.main.audit_log_repository") as mock_repo:
            _write_audit_log(request, request_id="req-1", status_code=500, error_message="crash")
            call_kwargs = mock_repo.log_request.call_args[1]
            assert call_kwargs["error_message"] == "crash"

    def test_exception_in_audit_log(self):
        request = _make_request()
        with patch("app.main.audit_log_repository") as mock_repo:
            mock_repo.log_request.side_effect = RuntimeError("db down")
            # Should not raise
            _write_audit_log(request, request_id="req-1", status_code=200)


# ---------------------------------------------------------------------------
# Root endpoint (via TestClient)
# ---------------------------------------------------------------------------


class TestRootEndpoint:
    def test_root(self):
        with patch("app.main.config") as mock_config:
            mock_config.app_name = "SmartSRE"
            mock_config.app_version = "1.0.0"
            mock_config.cors_origins = ["*"]
            mock_config.task_dispatcher_mode = "detached"
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get("/")
            assert resp.status_code == 200
            data = resp.json()
            assert "SmartSRE" in data["message"]
            assert data["version"] == "1.0.0"

    def test_request_context_middleware(self):
        with patch("app.main.config") as mock_config:
            mock_config.app_name = "SmartSRE"
            mock_config.app_version = "1.0.0"
            mock_config.cors_origins = ["*"]
            mock_config.task_dispatcher_mode = "detached"
            with patch("app.main.audit_log_repository"):
                client = TestClient(app, raise_server_exceptions=False)
                resp = client.get("/", headers={"X-Request-ID": "test-req-123"})
                assert resp.status_code == 200
                assert resp.headers.get("X-Request-ID") == "test-req-123"

    def test_404_handler(self):
        with patch("app.main.config") as mock_config:
            mock_config.app_name = "SmartSRE"
            mock_config.app_version = "1.0.0"
            mock_config.cors_origins = ["*"]
            mock_config.task_dispatcher_mode = "detached"
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get("/nonexistent-path")
            assert resp.status_code == 404
