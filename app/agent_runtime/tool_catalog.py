"""Tool discovery for the Native Agent runtime."""

from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from typing import Any

from app.agent_runtime.constants import SIDE_EFFECTS_REQUIRING_APPROVAL
from app.infrastructure.tools import ToolScope, tool_registry


@dataclass(frozen=True)
class ToolSchema:
    """Standard tool contract consumed by policy and execution layers."""

    name: str
    description: str
    input_schema: dict[str, Any] | None = None
    output_schema: dict[str, Any] | None = None
    scope: str = "diagnosis"
    risk_level: str = "low"
    capability: str | None = None
    timeout_seconds: float = 30.0
    retry_count: int = 0
    approval_required: bool = False
    owner: str = "SmartSRE"
    data_boundary: str = "workspace"
    side_effect: str = "none"
    fallback_strategy: str = "handoff"
    credential_scope: str = "workspace"
    server_id: str | None = None
    transport: str = "local"
    rate_limit_rpm: int | None = None
    raw_tool: Any = field(default=None, repr=False, compare=False)

    @property
    def args_schema(self) -> dict[str, Any] | None:
        return self.input_schema

    async def ainvoke(self, arguments: dict[str, Any]) -> Any:
        tool = self.raw_tool
        if tool is None:
            return None
        if hasattr(tool, "ainvoke"):
            return await tool.ainvoke(arguments)
        if hasattr(tool, "invoke"):
            return tool.invoke(arguments)
        result = tool(**arguments) if callable(tool) else None
        if inspect.isawaitable(result):
            return await result
        return result


class ToolCatalog:
    """Discover local and MCP tools through the existing registry."""

    def __init__(self) -> None:
        self._dynamic_tools: dict[str, ToolSchema] = {}

    async def get_tools(
        self,
        scope: ToolScope,
        *,
        force_refresh: bool = False,
    ) -> list[ToolSchema]:
        tools = await tool_registry.get_tools(scope, force_refresh=force_refresh)  # type: ignore[attr-defined]
        schemas = [_tool_to_schema(tool, scope=str(scope)) for tool in tools]
        schemas.extend(self._dynamic_tools.values())
        return schemas

    def register_dynamic_tools(self, tool_names: list[str]) -> list[str]:
        """Register tools from skill manifests that aren't already in the catalog.

        Returns names of tools that were registered (skips already-known tools).
        """
        registered: list[str] = []
        for name in tool_names:
            if name in self._dynamic_tools:
                continue
            self._dynamic_tools[name] = ToolSchema(
                name=name,
                description=f"Dynamic tool from skill manifest: {name}",
                scope="diagnosis",
                risk_level="medium",
                approval_required=True,
                side_effect="external_api",
            )
            registered.append(name)
        return registered


def _tool_to_schema(tool: Any, *, scope: str) -> ToolSchema:
    input_schema = _input_schema(tool)
    side_effect = str(getattr(tool, "side_effect", "none") or "none")
    approval_required = bool(getattr(tool, "approval_required", False))
    if side_effect in SIDE_EFFECTS_REQUIRING_APPROVAL:
        approval_required = True
    return ToolSchema(
        name=str(getattr(tool, "name", repr(tool))),
        description=str(getattr(tool, "description", "")),
        input_schema=input_schema,
        output_schema=_output_schema(tool),
        scope=str(getattr(tool, "scope", scope) or scope),
        risk_level=str(getattr(tool, "risk_level", "low") or "low"),
        capability=getattr(tool, "capability", None),
        timeout_seconds=float(getattr(tool, "timeout_seconds", 30.0) or 30.0),
        retry_count=max(int(getattr(tool, "retry_count", 0) or 0), 0),
        approval_required=approval_required,
        owner=str(getattr(tool, "owner", "SmartSRE") or "SmartSRE"),
        data_boundary=str(getattr(tool, "data_boundary", "workspace") or "workspace"),
        side_effect=side_effect,
        fallback_strategy=str(getattr(tool, "fallback_strategy", "handoff") or "handoff"),
        credential_scope=str(getattr(tool, "credential_scope", "workspace") or "workspace"),
        server_id=getattr(tool, "server_id", None),
        transport=str(getattr(tool, "transport", "local") or "local"),
        rate_limit_rpm=getattr(tool, "rate_limit_rpm", None),
        raw_tool=tool,
    )


def _input_schema(tool: Any) -> dict[str, Any] | None:
    args_schema = getattr(tool, "args_schema", None)
    return _schema_to_dict(args_schema)


def _output_schema(tool: Any) -> dict[str, Any] | None:
    output_schema = getattr(tool, "output_schema", None)
    return _schema_to_dict(output_schema)


def _schema_to_dict(schema_source: Any) -> dict[str, Any] | None:
    args_schema = schema_source
    if args_schema is None:
        return None
    if isinstance(args_schema, dict):
        return args_schema
    if hasattr(args_schema, "model_json_schema"):
        schema = args_schema.model_json_schema()
        return schema if isinstance(schema, dict) else None
    if hasattr(args_schema, "schema"):
        schema = args_schema.schema()
        return schema if isinstance(schema, dict) else None
    return None
