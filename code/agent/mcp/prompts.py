"""MCP Prompt 消息的结构校验和 Context 无关转换。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .errors import McpProtocolError


@dataclass(frozen=True)
class McpPromptMessage:
    role: str
    content: dict[str, Any]

    @classmethod
    def from_wire(cls, value: object) -> "McpPromptMessage":
        if not isinstance(value, Mapping):
            raise McpProtocolError("MCP Prompt message 必须是对象")
        role = value.get("role")
        content = value.get("content")
        if role not in {"user", "assistant"} or not isinstance(content, Mapping):
            raise McpProtocolError("MCP Prompt message 的 role/content 无效")
        content_dict = dict(content)
        if content_dict.get("type") not in {"text", "image", "audio", "resource"}:
            raise McpProtocolError("MCP Prompt content type 无效")
        return cls(role, content_dict)


def parse_prompt_result(value: object) -> tuple[str | None, tuple[McpPromptMessage, ...]]:
    if not isinstance(value, Mapping) or not isinstance(value.get("messages"), list):
        raise McpProtocolError("MCP prompts/get 结果必须包含 messages 数组")
    description = value.get("description")
    if description is not None and not isinstance(description, str):
        raise McpProtocolError("MCP Prompt description 必须是字符串")
    return description, tuple(McpPromptMessage.from_wire(item) for item in value["messages"])
