"""MCP sampling Server request 的协议边界，不执行模型调用。"""

from __future__ import annotations

from typing import Any, Mapping

from .errors import McpProtocolError


def validate_sampling_request(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise McpProtocolError("MCP sampling/createMessage 参数必须是对象")
    messages = value.get("messages")
    if not isinstance(messages, list) or not messages:
        raise McpProtocolError("MCP sampling/createMessage 必须包含非空 messages")
    for message in messages:
        if not isinstance(message, Mapping) or message.get("role") not in {"user", "assistant"}:
            raise McpProtocolError("MCP sampling message role 无效")
        if not isinstance(message.get("content"), Mapping):
            raise McpProtocolError("MCP sampling message content 必须是对象")
    return dict(value)


def validate_sampling_result(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise McpProtocolError("MCP sampling/createMessage 响应必须是对象")
    if not isinstance(value.get("role"), str) or not isinstance(value.get("content"), Mapping):
        raise McpProtocolError("MCP sampling 响应缺少 role 或 content")
    model = value.get("model")
    if model is not None and not isinstance(model, str):
        raise McpProtocolError("MCP sampling model 必须是字符串")
    stop_reason = value.get("stopReason")
    if stop_reason is not None and not isinstance(stop_reason, str):
        raise McpProtocolError("MCP sampling stopReason 必须是字符串")
    return dict(value)
