"""Unit tests for app.security.auth — no live DB or network required."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app.security.auth import (
    _clear_auth_caches,
    _has_capability,
    get_current_principal,
    is_auth_configured,
    load_api_key_roles,
    load_api_key_subjects,
    require_capability,
    validate_security_configuration,
)


def _make_settings(**overrides) -> SimpleNamespace:
    defaults = {
        "app_api_key": "",
        "api_keys_json": "",
        "environment": "local",
        "is_production": False,
        "cors_origins": lambda: ["http://localhost:3000"],
        "agent_decision_provider": "deterministic",
        "dashscope_api_key": "",
        "task_queue_backend": "database",
        "redis_url": "redis://localhost:6379",
        "redis_password": "",
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


@pytest.fixture(autouse=True)
def _reset_caches():
    _clear_auth_caches()
    yield
    _clear_auth_caches()


# ---------------------------------------------------------------------------
# is_auth_configured
# ---------------------------------------------------------------------------


class TestIsAuthConfigured:
    def test_configured_with_api_key(self):
        settings = _make_settings(app_api_key="secret-key")
        assert is_auth_configured(settings) is True

    def test_configured_with_keys_json(self):
        settings = _make_settings(api_keys_json='{"key1": "admin"}')
        assert is_auth_configured(settings) is True

    def test_not_configured(self):
        settings = _make_settings(app_api_key="", api_keys_json="")
        assert is_auth_configured(settings) is False


# ---------------------------------------------------------------------------
# load_api_key_roles
# ---------------------------------------------------------------------------


class TestLoadApiKeyRoles:
    def test_app_api_key_defaults_to_admin(self):
        settings = _make_settings(app_api_key="my-secret")
        roles = load_api_key_roles(settings)
        assert roles["my-secret"] == "admin"

    def test_json_keys_mapped_to_roles(self):
        mapping = {"key1": "operator", "key2": "viewer"}
        settings = _make_settings(api_keys_json=json.dumps(mapping))
        roles = load_api_key_roles(settings)
        assert roles["key1"] == "operator"
        assert roles["key2"] == "viewer"

    def test_unknown_role_skipped(self):
        mapping = {"key1": "nonexistent_role"}
        settings = _make_settings(api_keys_json=json.dumps(mapping))
        roles = load_api_key_roles(settings)
        assert "key1" not in roles

    def test_non_dict_json_returns_empty(self):
        settings = _make_settings(api_keys_json="[1, 2, 3]")
        roles = load_api_key_roles(settings)
        assert roles == {}

    def test_invalid_json_returns_empty(self):
        settings = _make_settings(api_keys_json="not-json")
        roles = load_api_key_roles(settings)
        assert roles == {}

    def test_cache_hit_returns_empty(self):
        settings = _make_settings(app_api_key="k")
        first = load_api_key_roles(settings)
        assert first == {"k": "admin"}
        # Second call with same cache key → empty dict (cached)
        second = load_api_key_roles(settings)
        assert second == {}

    def test_combined_json_and_app_key(self):
        mapping = {"key1": "viewer"}
        settings = _make_settings(
            app_api_key="admin-key",
            api_keys_json=json.dumps(mapping),
        )
        roles = load_api_key_roles(settings)
        assert roles["admin-key"] == "admin"
        assert roles["key1"] == "viewer"


# ---------------------------------------------------------------------------
# load_api_key_subjects
# ---------------------------------------------------------------------------


class TestLoadApiKeySubjects:
    def test_app_api_key_default_subject(self):
        settings = _make_settings(app_api_key="my-key")
        subjects = load_api_key_subjects(settings)
        assert subjects["my-key"] == "key:primary"

    def test_json_keys_sequential_subjects(self):
        mapping = {"k1": "operator", "k2": "viewer"}
        settings = _make_settings(api_keys_json=json.dumps(mapping))
        subjects = load_api_key_subjects(settings)
        assert subjects["k1"] == "key:configured-1"
        assert subjects["k2"] == "key:configured-2"

    def test_non_dict_json_returns_empty(self):
        settings = _make_settings(api_keys_json='"just-a-string"')
        subjects = load_api_key_subjects(settings)
        assert subjects == {}

    def test_cache_hit_returns_empty(self):
        settings = _make_settings(app_api_key="k")
        first = load_api_key_subjects(settings)
        assert first == {"k": "key:primary"}
        second = load_api_key_subjects(settings)
        assert second == {}


# ---------------------------------------------------------------------------
# validate_security_configuration
# ---------------------------------------------------------------------------


class TestValidateSecurityConfiguration:
    def test_qwen_without_dashscope_key_raises(self):
        settings = _make_settings(
            is_production=True,
            agent_decision_provider="qwen",
            dashscope_api_key="",
            app_api_key="k",
            cors_origins=lambda: ["https://example.com"],
        )
        with pytest.raises(RuntimeError, match="DASHSCOPE_API_KEY"):
            validate_security_configuration(settings)

    def test_redis_without_password_raises(self):
        settings = _make_settings(
            is_production=True,
            app_api_key="k",
            cors_origins=lambda: ["https://example.com"],
            task_queue_backend="redis",
            redis_url="redis://localhost:6379",
            redis_password="",
        )
        with pytest.raises(RuntimeError, match="REDIS_PASSWORD"):
            validate_security_configuration(settings)

    def test_production_no_api_key_raises(self):
        settings = _make_settings(
            is_production=True,
            app_api_key="",
            cors_origins=lambda: ["https://example.com"],
        )
        with pytest.raises(RuntimeError, match="APP_API_KEY"):
            validate_security_configuration(settings)

    def test_production_wildcard_cors_raises(self):
        settings = _make_settings(
            is_production=True,
            app_api_key="k",
            cors_origins=lambda: ["*"],
        )
        with pytest.raises(RuntimeError, match="CORS_ALLOWED_ORIGINS"):
            validate_security_configuration(settings)

    def test_non_production_passes(self):
        settings = _make_settings(is_production=False)
        validate_security_configuration(settings)  # no exception


# ---------------------------------------------------------------------------
# get_current_principal
# ---------------------------------------------------------------------------


class TestGetCurrentPrincipal:
    def _make_request(self) -> SimpleNamespace:
        return SimpleNamespace(state=SimpleNamespace())

    @pytest.mark.asyncio
    async def test_local_dev_no_keys_gets_admin(self):
        settings = _make_settings(app_api_key="", api_keys_json="")
        request = self._make_request()
        principal = await get_current_principal(request, x_api_key=None, settings=settings)
        assert principal.role == "admin"
        assert principal.subject == "local-dev"

    @pytest.mark.asyncio
    async def test_valid_api_key_returns_principal(self):
        mapping = {"secret-key": "operator"}
        settings = _make_settings(
            api_keys_json=json.dumps(mapping),
            app_api_key="admin-key",
        )
        request = self._make_request()
        principal = await get_current_principal(request, x_api_key="secret-key", settings=settings)
        assert principal.role == "operator"

    @pytest.mark.asyncio
    async def test_invalid_key_raises_401(self):
        settings = _make_settings(app_api_key="real-key")
        request = self._make_request()
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await get_current_principal(request, x_api_key="wrong-key", settings=settings)
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_production_no_keys_raises_401(self):
        settings = _make_settings(
            is_production=True,
            app_api_key="",
            api_keys_json="",
        )
        request = self._make_request()
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await get_current_principal(request, x_api_key=None, settings=settings)
        assert exc_info.value.status_code == 401


# ---------------------------------------------------------------------------
# require_capability
# ---------------------------------------------------------------------------


class TestRequireCapability:
    def _make_request(self) -> SimpleNamespace:
        return SimpleNamespace(state=SimpleNamespace())

    @pytest.mark.asyncio
    async def test_has_capability_returns_principal(self):
        settings = _make_settings(api_keys_json=json.dumps({"k1": "operator"}))
        dep = require_capability("aiops:run", settings=settings)
        request = self._make_request()
        result = await dep(request=request, x_api_key="k1")
        assert result.role == "operator"

    @pytest.mark.asyncio
    async def test_lacks_capability_raises_403(self):
        settings = _make_settings(api_keys_json=json.dumps({"k1": "viewer"}))
        dep = require_capability("aiops:run", settings=settings)
        request = self._make_request()
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await dep(request=request, x_api_key="k1")
        assert exc_info.value.status_code == 403


# ---------------------------------------------------------------------------
# _has_capability
# ---------------------------------------------------------------------------


class TestHasCapability:
    def test_wildcard_admin(self):
        assert _has_capability("admin", "anything") is True

    def test_matching_capability(self):
        assert _has_capability("operator", "aiops:run") is True

    def test_missing_capability(self):
        assert _has_capability("viewer", "aiops:run") is False

    def test_unknown_role(self):
        assert _has_capability("nonexistent", "chat:read") is False
