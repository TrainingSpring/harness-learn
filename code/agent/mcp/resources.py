"""MCP Resource、ResourceTemplate 和结果边界模型。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping
from urllib.parse import urlsplit

from .errors import McpProtocolError


def _uri(value: object, field: str = "uri") -> str:
    if not isinstance(value, str) or not value.strip() or not urlsplit(value).scheme:
        raise McpProtocolError(f"MCP {field} 必须是带 scheme 的 URI")
    return value


@dataclass(frozen=True)
class McpResource:
    uri: str
    name: str
    description: str = ""
    mime_type: str | None = None

    @classmethod
    def from_wire(cls, value: object) -> "McpResource":
        if not isinstance(value, Mapping):
            raise McpProtocolError("MCP Resource 必须是对象")
        name = value.get("name")
        if not isinstance(name, str) or not name:
            raise McpProtocolError("MCP Resource name 必须是非空字符串")
        description = value.get("description", "")
        mime_type = value.get("mimeType")
        if not isinstance(description, str) or (mime_type is not None and not isinstance(mime_type, str)):
            raise McpProtocolError("MCP Resource 描述字段格式无效")
        return cls(_uri(value.get("uri")), name, description, mime_type)


@dataclass(frozen=True)
class McpResourceTemplate:
    uri_template: str
    name: str
    description: str = ""

    @classmethod
    def from_wire(cls, value: object) -> "McpResourceTemplate":
        if not isinstance(value, Mapping):
            raise McpProtocolError("MCP ResourceTemplate 必须是对象")
        uri_template = value.get("uriTemplate")
        name = value.get("name")
        if not isinstance(uri_template, str) or not uri_template or not isinstance(name, str) or not name:
            raise McpProtocolError("MCP ResourceTemplate 字段格式无效")
        description = value.get("description", "")
        if not isinstance(description, str):
            raise McpProtocolError("MCP ResourceTemplate description 必须是字符串")
        return cls(uri_template, name, description)


def validate_resource_result(value: object) -> dict[str, Any]:
    if not isinstance(value, dict) or not isinstance(value.get("contents"), list):
        raise McpProtocolError("MCP resources/read 结果必须包含 contents 数组")
    for item in value["contents"]:
        if not isinstance(item, Mapping) or not isinstance(item.get("uri"), str):
            raise McpProtocolError("MCP Resource 内容必须包含 uri")
        if "text" not in item and "blob" not in item:
            raise McpProtocolError("MCP Resource 内容必须包含 text 或 blob")
    return value
