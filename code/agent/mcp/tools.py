"""把 MCP Server tools/list 结果适配为 Harness Tool。"""

from __future__ import annotations

import json
import re
from typing import Any

from jsonschema import Draft202012Validator, SchemaError, ValidationError

from permission.types import PermissionAction, PermissionRequirement
from tools.types import Tool, ToolResult

from .client import McpClient
from .errors import McpProtocolError, McpRemoteError


_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_MAX_RESULT_BYTES = 4 * 1024 * 1024


class McpToolDefinitionError(McpProtocolError):
    """MCP Tool 描述或 Schema 不符合可暴露给模型的边界。"""

    code = "MCP_TOOL_INVALID"


def _tool_schema(server_id: str, raw: dict[str, Any]) -> tuple[str, str, dict[str, Any]]:
    name = raw.get("name")
    if not isinstance(name, str) or _NAME.fullmatch(name) is None:
        raise McpToolDefinitionError("MCP Tool name 格式无效")
    description = raw.get("description", "")
    if not isinstance(description, str):
        raise McpToolDefinitionError("MCP Tool description 必须是字符串")
    input_schema = raw.get("inputSchema", {"type": "object"})
    if not isinstance(input_schema, dict):
        raise McpToolDefinitionError("MCP Tool inputSchema 必须是对象")
    try:
        Draft202012Validator.check_schema(input_schema)
    except SchemaError as error:
        raise McpToolDefinitionError("MCP Tool inputSchema 不是有效 JSON Schema") from error
    exposed_name = f"mcp__{server_id}__{name}"
    return exposed_name, name, {
        "type": "function",
        "name": exposed_name,
        "description": description,
        "parameters": input_schema,
    }


def build_mcp_tools(server_id: str, client: McpClient) -> list[Tool]:
    """读取并校验 Server tools/list，转换成可注册的动态 Tool 列表。"""
    raw_tools = client.list_tools()
    result: list[Tool] = []
    seen: set[str] = set()
    for raw in raw_tools:
        if not isinstance(raw, dict):
            raise McpToolDefinitionError("MCP tools/list 项必须是对象")
        exposed_name, remote_name, schema = _tool_schema(server_id, raw)
        if exposed_name in seen:
            raise McpToolDefinitionError(f"MCP Tool 名称重复: {exposed_name}")
        seen.add(exposed_name)

        def invoke(_ctx, *, _client=client, _remote_name=remote_name, **arguments) -> ToolResult:
            try:
                response = _client.call_tool(_remote_name, arguments)
                encoded = json.dumps(response, ensure_ascii=False, separators=(",", ":"))
                if len(encoded.encode("utf-8")) > _MAX_RESULT_BYTES:
                    return ToolResult.failure("MCP_EXTERNAL_DATA_LIMIT", "MCP Tool 结果超过大小限制")
                return ToolResult.success(response)
            except McpRemoteError as error:
                return ToolResult.failure("MCP_REMOTE_ERROR", str(error), details={"remote_code": error.remote_code})
            except Exception as error:
                return ToolResult.failure("MCP_TOOL_CALL_FAILED", str(error), retryable=True)

        def validate(arguments: dict[str, Any], *, _schema=schema["parameters"]) -> dict[str, Any]:
            try:
                Draft202012Validator(_schema).validate(arguments)
            except ValidationError as error:
                raise ValueError(f"MCP Tool 参数无效: {error.message}") from error
            return arguments

        result.append(
            Tool(
                schema=schema,
                function=invoke,
                permission=PermissionRequirement(PermissionAction.MCP_TOOL_CALL, None),
                argument_parser=validate,
                source_id=f"mcp:{server_id}",
            )
        )
    return result
