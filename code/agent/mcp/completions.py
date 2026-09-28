"""MCP Completion 请求和响应边界。"""

from __future__ import annotations

from typing import Any, Mapping

from .errors import McpProtocolError


def validate_completion_params(params: object) -> dict[str, Any]:
    if not isinstance(params, Mapping):
        raise McpProtocolError("MCP completion 参数必须是对象")
    ref = params.get("ref")
    argument = params.get("argument")
    if not isinstance(ref, Mapping) or not isinstance(ref.get("type"), str):
        raise McpProtocolError("MCP completion ref 格式无效")
    if not isinstance(argument, Mapping) or not isinstance(argument.get("name"), str) or not isinstance(argument.get("value"), str):
        raise McpProtocolError("MCP completion argument 格式无效")
    return dict(params)


def validate_completion_result(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise McpProtocolError("MCP completion 结果必须是对象")
    completion = value.get("completion")
    if not isinstance(completion, Mapping) or not isinstance(completion.get("values"), list):
        raise McpProtocolError("MCP completion 结果缺少 values 数组")
    if not all(isinstance(item, str) for item in completion["values"]):
        raise McpProtocolError("MCP completion values 必须是字符串数组")
    return dict(value)
