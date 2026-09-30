"""MCP Tool 映射、命名空间和 Schema 边界测试。"""

from __future__ import annotations

import pytest

from mcp.tools import McpToolDefinitionError, build_mcp_tools
from tools.tools import Tools
from session.ExecutionContext import ExecutionContext
from permission.types import PermissionAction


class FakeClient:
    def __init__(self, definitions):
        self.definitions = definitions
        self.calls = []

    def list_tools(self):
        return tuple(self.definitions)

    def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        return {"content": [{"type": "text", "text": "ok"}], "isError": False}


def test_mcp_tools_are_namespaced_and_validate_before_call():
    client = FakeClient([
        {
            "name": "search",
            "description": "Search records",
            "inputSchema": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
                "additionalProperties": False,
            },
        }
    ])
    tools = build_mcp_tools("mcp_DEMO00001", client)
    assert tools[0].schema["name"] == "mcp__mcp_DEMO00001__search"
    assert tools[0].permission.action is PermissionAction.MCP_TOOL_CALL

    registered = Tools(ExecutionContext("/workspace", "agent_1", "session_1"))
    registered.replace_source("mcp:mcp_DEMO00001", tools)
    prepared = registered.prepare_call(
        "mcp__mcp_DEMO00001__search", '{"query":"hello"}', "call_1"
    )
    result = registered.execute(prepared)
    assert result.status == "ok"
    assert client.calls == [("search", {"query": "hello"})]

    with pytest.raises(Exception, match="MCP Tool 参数无效"):
        registered.prepare_call("mcp__mcp_DEMO00001__search", "{}", "call_2")


def test_mcp_tool_definition_rejects_invalid_name_or_schema():
    for name in ("tru.android.devices.list", "tru.mouse.double_click", "bad-name"):
        tools = build_mcp_tools("mcp_DEMO00001", FakeClient([{"name": name}]))
        assert tools[0].schema["name"] == f"mcp__mcp_DEMO00001__{name}"

    with pytest.raises(McpToolDefinitionError):
        build_mcp_tools("mcp_DEMO00001", FakeClient([{"name": "bad name"}]))
    with pytest.raises(McpToolDefinitionError):
        build_mcp_tools("mcp_DEMO00001", FakeClient([{"name": "bad,name"}]))
    with pytest.raises(McpToolDefinitionError):
        build_mcp_tools("mcp_DEMO00001", FakeClient([{"name": "x" * 129}]))
    with pytest.raises(McpToolDefinitionError):
        build_mcp_tools(
            "mcp_DEMO00001",
            FakeClient([{"name": "search", "inputSchema": {"type": "not-a-type"}}]),
        )
