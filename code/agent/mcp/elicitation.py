"""MCP elicitation Server request 的协议边界，不直接处理 UI。"""

from __future__ import annotations

from typing import Any, Mapping

from .errors import McpProtocolError


def validate_elicitation_request(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise McpProtocolError("MCP elicitation/create 参数必须是对象")
    if not isinstance(value.get("message"), str) or not value["message"].strip():
        raise McpProtocolError("MCP elicitation message 必须是非空字符串")
    mode = value.get("mode", "form")
    if mode not in {"form", "url"}:
        raise McpProtocolError("MCP elicitation mode 无效")
    if mode == "form" and not isinstance(value.get("requestedSchema"), Mapping):
        raise McpProtocolError("MCP form elicitation 必须包含 requestedSchema")
    return dict(value)


def validate_elicitation_result(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise McpProtocolError("MCP elicitation/create 响应必须是对象")
    if value.get("action") not in {"accept", "decline", "cancel"}:
        raise McpProtocolError("MCP elicitation action 无效")
    content = value.get("content")
    if content is not None and not isinstance(content, Mapping):
        raise McpProtocolError("MCP elicitation content 必须是对象")
    return dict(value)
