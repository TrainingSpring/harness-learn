"""MCP 初始化结果中的 Server 身份和能力模型。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .errors import McpLifecycleError


def _mapping(value: object, field_name: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise McpLifecycleError(f"{field_name} 必须是对象")
    return dict(value)


@dataclass(frozen=True)
class McpImplementation:
    """MCP Client 或 Server 的公开实现身份。"""

    name: str
    version: str

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise McpLifecycleError("implementation.name 必须是非空字符串")
        if not isinstance(self.version, str) or not self.version.strip():
            raise McpLifecycleError("implementation.version 必须是非空字符串")

    def to_dict(self) -> dict[str, str]:
        return {"name": self.name, "version": self.version}


@dataclass(frozen=True)
class McpServerCapabilities:
    """保留 Server 声明能力原文，并提供当前已实现能力的查询。"""

    raw: dict[str, Any]

    @classmethod
    def from_wire(cls, value: object) -> "McpServerCapabilities":
        return cls(_mapping(value, "capabilities"))

    def supports(self, capability: str) -> bool:
        return capability in self.raw and self.raw[capability] is not None

    def supports_list_changed(self, capability: str) -> bool:
        value = self.raw.get(capability)
        return isinstance(value, Mapping) and value.get("listChanged") is True
