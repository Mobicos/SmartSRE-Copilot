"""Unit tests for app.infrastructure.tools.registry — no live MCP server required."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.infrastructure.tools.registry import ToolRegistry

# ---------------------------------------------------------------------------
# ToolRegistry._tool_name
# ---------------------------------------------------------------------------


class TestToolName:
    def test_with_name_attribute(self):
        tool = SimpleNamespace(name="SearchLog")
        assert ToolRegistry._tool_name(tool) == "SearchLog"

    def test_without_name_attribute(self):
        tool = "just_a_string"
        result = ToolRegistry._tool_name(tool)
        assert "just_a_string" in result

    def test_none_tool(self):
        result = ToolRegistry._tool_name(None)
        assert "None" in result


# ---------------------------------------------------------------------------
# ToolRegistry._merge_tools
# ---------------------------------------------------------------------------


class TestMergeTools:
    def _make_tool(self, name: str):
        return SimpleNamespace(name=name)

    def test_deduplication(self):
        t1 = self._make_tool("A")
        t2 = self._make_tool("B")
        t3 = self._make_tool("A")  # duplicate
        merged = ToolRegistry(None)._merge_tools([t1, t2], [t3])
        assert len(merged) == 2
        assert merged[0].name == "A"
        assert merged[1].name == "B"

    def test_preserves_order(self):
        tools = [self._make_tool("C"), self._make_tool("A"), self._make_tool("B")]
        merged = ToolRegistry(None)._merge_tools(tools)
        names = [t.name for t in merged]
        assert names == ["C", "A", "B"]

    def test_empty_groups(self):
        merged = ToolRegistry(None)._merge_tools([], [])
        assert merged == []


# ---------------------------------------------------------------------------
# ToolRegistry.get_tools — include_mcp=False
# ---------------------------------------------------------------------------


class TestGetToolsNoMCP:
    @pytest.mark.asyncio
    async def test_include_mcp_false_returns_local_only(self):
        settings = SimpleNamespace(
            mcp_tools_load_timeout_seconds=5,
            mcp_servers=lambda: {},
        )
        registry = ToolRegistry(settings)
        tools = await registry.get_tools("chat", include_mcp=False)
        # Should return only local tools (2 tools for chat scope)
        assert len(tools) == 2


# ---------------------------------------------------------------------------
# ToolRegistry.get_chat_tools
# ---------------------------------------------------------------------------


class TestGetChatTools:
    @pytest.mark.asyncio
    async def test_delegates_to_get_tools(self):
        settings = SimpleNamespace(
            mcp_tools_load_timeout_seconds=5,
            mcp_servers=lambda: {},
        )
        registry = ToolRegistry(settings)
        tools = await registry.get_chat_tools()
        assert len(tools) == 2


# ---------------------------------------------------------------------------
# ToolRegistry.get_local_tools
# ---------------------------------------------------------------------------


class TestGetLocalTools:
    def test_chat_scope(self):
        registry = ToolRegistry(None)
        tools = registry.get_local_tools("chat")
        assert len(tools) == 2

    def test_diagnosis_scope(self):
        registry = ToolRegistry(None)
        tools = registry.get_local_tools("diagnosis")
        assert len(tools) == 2
