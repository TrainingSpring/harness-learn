"""MCP Server 配置的只读注册表视图。"""

from __future__ import annotations

from .config_store import McpConfigStore
from .errors import McpServerDisabledError, McpServerNotFoundError
from .types import McpServerConfig


class McpServerRegistry:
    """每次查询读取最新配置，不缓存 Server 配置或运行时状态。"""

    def __init__(self, config_store: McpConfigStore) -> None:
        self.config_store = config_store

    def list(self) -> tuple[McpServerConfig, ...]:
        """返回当前注册的全部 Server，包括 disabled 项。"""
        return self.config_store.read().document.servers

    def get(self, server_id: str) -> McpServerConfig:
        """按稳定 ID 获取 Server，不存在时抛出明确错误。"""
        for server in self.list():
            if server.id == server_id:
                return server
        raise McpServerNotFoundError(f"MCP Server 不存在: {server_id}")

    def require_enabled(self, server_id: str) -> McpServerConfig:
        """获取可供新 Agent 连接的 Server。"""
        server = self.get(server_id)
        if not server.enabled:
            raise McpServerDisabledError(f"MCP Server 已禁用: {server_id}")
        return server

    def validate_ids(self, server_ids: list[str] | tuple[str, ...]) -> list[str]:
        """验证 Agent 引用并去重保序；disabled 引用仍然有效。"""
        if not isinstance(server_ids, (list, tuple)):
            raise ValueError("mcp_server_ids 必须是字符串列表")
        registered = {server.id for server in self.list()}
        result: list[str] = []
        seen: set[str] = set()
        for server_id in server_ids:
            if not isinstance(server_id, str) or not server_id.strip():
                raise ValueError("mcp_server_ids 中的 ID 必须是非空字符串")
            if server_id not in registered:
                raise McpServerNotFoundError(f"MCP Server 不存在: {server_id}")
            if server_id not in seen:
                result.append(server_id)
                seen.add(server_id)
        return result
