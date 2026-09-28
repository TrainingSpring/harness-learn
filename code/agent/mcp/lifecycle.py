"""握手时代 MCP initialize 生命周期的输入、结果和版本协商。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .capabilities import McpImplementation, McpServerCapabilities
from .errors import McpLifecycleError


# 2026-07-28 改为无状态 lifecycle，不适用于本阶段的 initialize Transport。
SUPPORTED_HANDSHAKE_PROTOCOL_VERSIONS = (
    "2025-11-25",
    "2025-06-18",
    "2025-03-26",
    "2024-11-05",
)


@dataclass(frozen=True)
class McpInitialization:
    """已协商的 Server 信息和能力快照。"""

    protocol_version: str
    capabilities: McpServerCapabilities
    server_info: McpImplementation
    instructions: str | None = None

    @classmethod
    def from_wire(cls, value: object) -> "McpInitialization":
        if not isinstance(value, Mapping):
            raise McpLifecycleError("initialize 结果必须是对象")
        version = value.get("protocolVersion")
        if version not in SUPPORTED_HANDSHAKE_PROTOCOL_VERSIONS:
            raise McpLifecycleError("Server 返回了不兼容的 MCP 协议版本")
        server_info = value.get("serverInfo")
        if not isinstance(server_info, Mapping):
            raise McpLifecycleError("initialize 结果缺少有效 serverInfo")
        instructions = value.get("instructions")
        if instructions is not None and not isinstance(instructions, str):
            raise McpLifecycleError("instructions 必须是字符串")
        return cls(
            protocol_version=version,
            capabilities=McpServerCapabilities.from_wire(value.get("capabilities")),
            server_info=McpImplementation(
                name=server_info.get("name"),
                version=server_info.get("version"),
            ),
            instructions=instructions,
        )


def initialize_params(
    client_info: McpImplementation,
    *,
    capabilities: dict[str, Any] | None = None,
    protocol_version: str = SUPPORTED_HANDSHAKE_PROTOCOL_VERSIONS[0],
) -> dict[str, Any]:
    """构造唯一一次 initialize 请求的无敏感参数。"""
    if protocol_version not in SUPPORTED_HANDSHAKE_PROTOCOL_VERSIONS:
        raise McpLifecycleError("请求的 MCP 协议版本未受支持")
    if capabilities is not None and not isinstance(capabilities, dict):
        raise McpLifecycleError("客户端 capabilities 必须是对象")
    return {
        "protocolVersion": protocol_version,
        "capabilities": dict(capabilities or {}),
        "clientInfo": client_info.to_dict(),
    }
