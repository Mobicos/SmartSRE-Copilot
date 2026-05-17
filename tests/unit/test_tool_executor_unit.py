"""Unit tests for app.agent_runtime.tool_executor — static helpers and policy logic."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agent_runtime.tool_executor import (
    ToolExecutionResult,
    ToolExecutor,
    ToolPolicyRepositoryAdapter,
    _matches_json_schema_type,
    _validate_json_schema_arguments,
)

# ---------------------------------------------------------------------------
# ToolExecutionResult
# ---------------------------------------------------------------------------


class TestToolExecutionResult:
    def test_basic(self):
        r = ToolExecutionResult(
            tool_name="SearchLog",
            status="success",
            arguments={"query": "x"},
            output="result",
        )
        assert r.decision == "executed"
        assert r.latency_ms is None

    def test_governance_payload(self):
        r = ToolExecutionResult(
            tool_name="X",
            status="success",
            arguments={},
            decision="denied",
            decision_reason="disabled",
            policy={"enabled": False},
        )
        payload = r.governance_payload()
        assert payload["decision"] == "denied"
        assert payload["reason"] == "disabled"
        assert payload["policy"] == {"enabled": False}


# ---------------------------------------------------------------------------
# ToolPolicyRepositoryAdapter
# ---------------------------------------------------------------------------


class TestToolPolicyRepositoryAdapter:
    def test_get_policy(self):
        mock_repo = MagicMock()
        mock_repo.get_policy.return_value = {"tool_name": "X", "enabled": True}
        adapter = ToolPolicyRepositoryAdapter(mock_repo)
        result = adapter.get_policy("X")
        assert result["tool_name"] == "X"
        mock_repo.get_policy.assert_called_once_with("X")


# ---------------------------------------------------------------------------
# ToolExecutor._default_policy
# ---------------------------------------------------------------------------


class TestDefaultPolicy:
    def test_basic_tool(self):
        tool = SimpleNamespace(name="SearchLog")
        policy = ToolExecutor._default_policy("SearchLog", tool=tool)
        assert policy["tool_name"] == "SearchLog"
        assert policy["enabled"] is True
        assert policy["scope"] == "diagnosis"
        assert policy["risk_level"] == "low"
        assert policy["approval_required"] is False

    def test_side_effect_requires_approval(self):
        tool = SimpleNamespace(name="Deploy", side_effect="change")
        policy = ToolExecutor._default_policy("Deploy", tool=tool)
        assert policy["approval_required"] is True
        assert policy["side_effect"] == "change"

    def test_destructive_requires_approval(self):
        tool = SimpleNamespace(name="Delete", side_effect="destructive")
        policy = ToolExecutor._default_policy("Delete", tool=tool)
        assert policy["approval_required"] is True

    def test_tool_attributes(self):
        tool = SimpleNamespace(
            name="X",
            scope="chat",
            risk_level="high",
            capability="run",
            timeout_seconds=60.0,
            retry_count=3,
            owner="team",
            data_boundary="global",
            fallback_strategy="retry",
            approval_required=True,
        )
        policy = ToolExecutor._default_policy("X", tool=tool)
        assert policy["scope"] == "chat"
        assert policy["risk_level"] == "high"
        assert policy["capability"] == "run"
        assert policy["timeout_seconds"] == 60.0
        assert policy["retry_count"] == 3
        assert policy["owner"] == "team"

    def test_none_side_effect(self):
        tool = SimpleNamespace(name="X", side_effect=None)
        policy = ToolExecutor._default_policy("X", tool=tool)
        assert policy["side_effect"] == "none"


# ---------------------------------------------------------------------------
# ToolExecutor._has_capability
# ---------------------------------------------------------------------------


class TestHasCapability:
    def test_wildcard(self):
        assert ToolExecutor._has_capability("admin", "run") is True

    def test_specific_capability(self):
        assert ToolExecutor._has_capability("operator", "aiops:run") is True

    def test_missing_capability(self):
        assert ToolExecutor._has_capability("viewer", "aiops:run") is False

    def test_unknown_role(self):
        assert ToolExecutor._has_capability("unknown", "run") is False


# ---------------------------------------------------------------------------
# ToolExecutor._tool_name
# ---------------------------------------------------------------------------


class TestToolName:
    def test_with_name(self):
        tool = SimpleNamespace(name="SearchLog")
        assert ToolExecutor._tool_name(tool) == "SearchLog"

    def test_without_name(self):
        assert ToolExecutor._tool_name("plain") == repr("plain")


# ---------------------------------------------------------------------------
# ToolExecutor._validate_arguments
# ---------------------------------------------------------------------------


class TestValidateArguments:
    def test_no_schema(self):
        tool = SimpleNamespace()
        assert ToolExecutor._validate_arguments(tool, {}) is None

    def test_pydantic_model_valid(self):
        mock_schema = MagicMock()
        mock_schema.model_validate.return_value = True
        tool = SimpleNamespace(args_schema=mock_schema)
        assert ToolExecutor._validate_arguments(tool, {"q": "x"}) is None

    def test_pydantic_model_invalid(self):
        mock_schema = MagicMock()
        mock_schema.model_validate.side_effect = ValueError("bad")
        tool = SimpleNamespace(args_schema=mock_schema)
        result = ToolExecutor._validate_arguments(tool, {"q": "x"})
        assert "bad" in result

    def test_json_schema_valid(self):
        tool = SimpleNamespace(
            args_schema={
                "type": "object",
                "properties": {"q": {"type": "string"}},
                "required": ["q"],
            }
        )
        assert ToolExecutor._validate_arguments(tool, {"q": "x"}) is None

    def test_json_schema_missing_required(self):
        tool = SimpleNamespace(args_schema={"type": "object", "required": ["q"]})
        result = ToolExecutor._validate_arguments(tool, {})
        assert "缺少必需参数" in result

    def test_json_schema_wrong_type(self):
        tool = SimpleNamespace(
            args_schema={
                "type": "object",
                "properties": {"q": {"type": "string"}},
            }
        )
        result = ToolExecutor._validate_arguments(tool, {"q": 123})
        assert "必须为 string" in result


# ---------------------------------------------------------------------------
# ToolExecutor._validate_output
# ---------------------------------------------------------------------------


class TestValidateOutput:
    def test_no_schema(self):
        tool = SimpleNamespace()
        assert ToolExecutor._validate_output(tool, "ok") is None

    def test_non_dict_schema(self):
        tool = SimpleNamespace(output_schema="invalid")
        assert ToolExecutor._validate_output(tool, "ok") is None

    def test_object_type_non_dict(self):
        tool = SimpleNamespace(output_schema={"type": "object"})
        result = ToolExecutor._validate_output(tool, "string")
        assert "Output must be object" in result

    def test_object_type_dict_valid(self):
        tool = SimpleNamespace(
            output_schema={"type": "object", "properties": {"x": {"type": "string"}}}
        )
        assert ToolExecutor._validate_output(tool, {"x": "hello"}) is None


# ---------------------------------------------------------------------------
# _validate_json_schema_arguments
# ---------------------------------------------------------------------------


class TestValidateJsonSchemaArguments:
    def test_valid(self):
        schema = {"type": "object", "required": ["q"], "properties": {"q": {"type": "string"}}}
        assert _validate_json_schema_arguments(schema, {"q": "hello"}) is None

    def test_missing_required(self):
        schema = {"type": "object", "required": ["q", "k"]}
        result = _validate_json_schema_arguments(schema, {"q": "x"})
        assert "q" in result or "k" in result

    def test_type_mismatch(self):
        schema = {"properties": {"q": {"type": "integer"}}}
        result = _validate_json_schema_arguments(schema, {"q": "x"})
        assert "integer" in result

    def test_no_properties(self):
        schema = {"type": "object"}
        assert _validate_json_schema_arguments(schema, {"q": "x"}) is None


# ---------------------------------------------------------------------------
# _matches_json_schema_type
# ---------------------------------------------------------------------------


class TestMatchesJsonSchemaType:
    def test_string(self):
        assert _matches_json_schema_type("hello", "string") is True
        assert _matches_json_schema_type(123, "string") is False

    def test_integer(self):
        assert _matches_json_schema_type(42, "integer") is True
        assert _matches_json_schema_type(3.14, "integer") is False
        assert _matches_json_schema_type(True, "integer") is False

    def test_number(self):
        assert _matches_json_schema_type(42, "number") is True
        assert _matches_json_schema_type(3.14, "number") is True
        assert _matches_json_schema_type(True, "number") is False

    def test_boolean(self):
        assert _matches_json_schema_type(True, "boolean") is True
        assert _matches_json_schema_type(1, "boolean") is False

    def test_object(self):
        assert _matches_json_schema_type({}, "object") is True
        assert _matches_json_schema_type([], "object") is False

    def test_array(self):
        assert _matches_json_schema_type([], "array") is True
        assert _matches_json_schema_type({}, "array") is False

    def test_unknown_type(self):
        assert _matches_json_schema_type("anything", "custom") is True


# ---------------------------------------------------------------------------
# ToolExecutor._invoke_tool
# ---------------------------------------------------------------------------


class TestInvokeTool:
    @pytest.mark.asyncio
    async def test_ainvoke(self):
        tool = AsyncMock()
        tool.ainvoke.return_value = "result"
        result = await ToolExecutor._invoke_tool(tool, {"q": "x"})
        assert result == "result"

    @pytest.mark.asyncio
    async def test_invoke_fallback(self):
        tool = MagicMock()
        tool.ainvoke = None  # type: ignore
        del tool.ainvoke
        tool.invoke.return_value = "result"
        result = await ToolExecutor._invoke_tool(tool, {"q": "x"})
        assert result == "result"

    @pytest.mark.asyncio
    async def test_callable(self):
        def my_func(**kwargs):
            return "called"

        result = await ToolExecutor._invoke_tool(my_func, {})
        assert result == "called"
