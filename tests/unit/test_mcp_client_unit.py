"""Unit tests for app.infrastructure.tools.mcp_client — no live MCP server required."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.infrastructure.tools.mcp_client import (
    _normalize_servers,
    _servers_signature,
    _summarize_exception,
    get_mcp_tools_with_fallback,
    retry_interceptor,
)

# ---------------------------------------------------------------------------
# _servers_signature
# ---------------------------------------------------------------------------


class TestServersSignature:
    def test_single_server(self):
        servers = {"s1": {"transport": "sse", "url": "http://localhost:8001"}}
        sig = _servers_signature(servers)
        assert sig == (("s1", "sse", "http://localhost:8001"),)

    def test_multiple_sorted_by_name(self):
        servers = {
            "z_server": {"transport": "sse", "url": "http://z"},
            "a_server": {"transport": "sse", "url": "http://a"},
        }
        sig = _servers_signature(servers)
        assert sig[0][0] == "a_server"
        assert sig[1][0] == "z_server"

    def test_deterministic(self):
        servers = {
            "b": {"transport": "sse", "url": "http://b"},
            "a": {"transport": "sse", "url": "http://a"},
        }
        sig1 = _servers_signature(servers)
        sig2 = _servers_signature(servers)
        assert sig1 == sig2


# ---------------------------------------------------------------------------
# _summarize_exception
# ---------------------------------------------------------------------------


class TestSummarizeException:
    def test_no_cause(self):
        exc = ValueError("direct error")
        assert _summarize_exception(exc) == "direct error"

    def test_with_cause(self):
        try:
            try:
                raise ValueError("root")
            except ValueError as inner:
                raise RuntimeError("wrapper") from inner
        except RuntimeError as e:
            assert _summarize_exception(e) == "root"

    def test_nested_cause_chain(self):
        e1 = ValueError("level1")
        e2 = TypeError("level2")
        e2.__cause__ = e1
        e3 = RuntimeError("level3")
        e3.__cause__ = e2
        assert _summarize_exception(e3) == "level1"


# ---------------------------------------------------------------------------
# _normalize_servers
# ---------------------------------------------------------------------------


class TestNormalizeServers:
    def test_empty_returns_empty(self):
        assert _normalize_servers({}) == {}

    def test_incomplete_entry_skipped(self):
        servers = {"s1": {"transport": "", "url": ""}}
        assert _normalize_servers(servers) == {}

    def test_partial_config_skipped(self):
        servers = {"s1": {"transport": "sse", "url": ""}}
        assert _normalize_servers(servers) == {}

    def test_valid_entry_kept(self):
        servers = {"s1": {"transport": "sse", "url": "http://localhost:8001"}}
        result = _normalize_servers(servers)
        assert "s1" in result

    def test_duplicate_target_deduplicated(self):
        servers = {
            "s1": {"transport": "sse", "url": "http://dup"},
            "s2": {"transport": "sse", "url": "http://dup"},
        }
        result = _normalize_servers(servers)
        assert len(result) == 1
        assert "s1" in result


# ---------------------------------------------------------------------------
# retry_interceptor
# ---------------------------------------------------------------------------


class TestRetryInterceptor:
    @pytest.mark.asyncio
    async def test_success_on_first_try(self):
        request = MagicMock()
        request.name = "test_tool"
        request.server_name = "test_server"
        handler = AsyncMock(return_value="success")
        result = await retry_interceptor(request, handler, max_retries=3, delay=0.01)
        assert result == "success"
        assert handler.call_count == 1

    @pytest.mark.asyncio
    async def test_retry_then_succeed(self):
        request = MagicMock()
        request.name = "test_tool"
        request.server_name = "test_server"
        handler = AsyncMock(side_effect=[RuntimeError("fail"), "ok"])
        result = await retry_interceptor(request, handler, max_retries=3, delay=0.01)
        assert result == "ok"
        assert handler.call_count == 2

    @pytest.mark.asyncio
    async def test_all_retries_fail_returns_error_result(self):
        request = MagicMock()
        request.name = "test_tool"
        request.server_name = "test_server"
        handler = AsyncMock(side_effect=RuntimeError("permanent fail"))
        result = await retry_interceptor(request, handler, max_retries=2, delay=0.01)
        assert result.isError is True
        assert "test_tool" in result.content[0].text
        assert handler.call_count == 2


# ---------------------------------------------------------------------------
# get_mcp_tools_with_fallback
# ---------------------------------------------------------------------------


class TestGetMcpToolsWithFallback:
    @pytest.mark.asyncio
    async def test_empty_servers_returns_empty(self):
        result = await get_mcp_tools_with_fallback(servers={})
        assert result == []

    @pytest.mark.asyncio
    async def test_cache_hit(self):
        from app.infrastructure.tools.mcp_client import _mcp_tools_cache, _servers_signature

        servers = {"s1": {"transport": "sse", "url": "http://test"}}
        sig = _servers_signature(_normalize_servers(servers))
        _mcp_tools_cache[sig] = ["cached_tool"]

        result = await get_mcp_tools_with_fallback(servers=servers, force_refresh=False)
        assert result == ["cached_tool"]

        # Cleanup
        del _mcp_tools_cache[sig]

    @pytest.mark.asyncio
    async def test_force_refresh_skips_cache(self):
        from app.infrastructure.tools.mcp_client import _mcp_tools_cache, _servers_signature

        servers = {"s1": {"transport": "sse", "url": "http://test"}}
        sig = _servers_signature(_normalize_servers(servers))
        _mcp_tools_cache[sig] = ["stale_tool"]

        mock_client = AsyncMock()
        mock_client.get_tools.return_value = ["fresh_tool"]
        with patch(
            "app.infrastructure.tools.mcp_client.get_mcp_client_with_retry",
            new_callable=AsyncMock,
            return_value=mock_client,
        ):
            result = await get_mcp_tools_with_fallback(servers=servers, force_refresh=True)
            assert result == ["fresh_tool"]

        # Cleanup
        _mcp_tools_cache.pop(sig, None)

    @pytest.mark.asyncio
    async def test_server_failure_degrades_gracefully(self):
        servers = {"bad": {"transport": "sse", "url": "http://fail"}}
        with patch(
            "app.infrastructure.tools.mcp_client.get_mcp_client_with_retry",
            new_callable=AsyncMock,
            side_effect=RuntimeError("connection refused"),
        ):
            result = await get_mcp_tools_with_fallback(servers=servers)
            assert result == []
