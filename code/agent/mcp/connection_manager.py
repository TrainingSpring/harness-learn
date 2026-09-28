"""按 Session、Agent、MCP Server 隔离 Client 连接。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from threading import Lock

from .client import McpClient
from .errors import McpConnectionManagerClosedError, McpServerDisabledError
from .http_transport import StreamableHttpTransport
from .protocol import JsonRpcNotification
from .stdio_transport import StdioMcpTransport
from .transport import McpTransport
from .types import LocalMcpServerConfig, McpServerConfig, RemoteMcpServerConfig


@dataclass(frozen=True)
class McpConnectionKey:
    """一个 MCP Client 的所属身份，确保 stdio 通道不跨 Session 共享。"""

    session_id: str
    agent_id: str
    server_id: str

    def __post_init__(self) -> None:
        for field in (self.session_id, self.agent_id, self.server_id):
            if not isinstance(field, str) or not field:
                raise ValueError("连接键必须由非空字符串构成")


TransportFactory = Callable[[McpServerConfig, Callable[[JsonRpcNotification], None]], McpTransport]


class McpConnectionManager:
    """保存当前进程的连接对象并按 Session/Agent 生命周期显式释放。"""

    def __init__(self, *, transport_factory: TransportFactory | None = None) -> None:
        self._transport_factory = transport_factory or _default_transport_factory
        self._connections: dict[McpConnectionKey, McpClient] = {}
        self._lock = Lock()
        self._closed = False

    def connect(self, key: McpConnectionKey, config: McpServerConfig) -> McpClient:
        """返回已就绪连接，或创建、initialize 并登记一个新连接。"""
        if not config.enabled:
            raise McpServerDisabledError(f"MCP Server 已禁用: {config.id}")
        with self._lock:
            self._raise_if_closed()
            existing = self._connections.get(key)
            if existing is not None:
                return existing
        holder: dict[str, McpClient] = {}

        def notification_handler(notification: JsonRpcNotification) -> None:
            client = holder.get("client")
            if client is not None:
                client.handle_notification(notification)

        transport = self._transport_factory(config, notification_handler)
        client = McpClient(transport)
        holder["client"] = client
        try:
            client.connect()
        except Exception:
            client.close()
            raise
        with self._lock:
            closed = self._closed
            race = self._connections.get(key)
            if not closed and race is None:
                self._connections[key] = client
                return client
        client.close()
        if closed:
            raise McpConnectionManagerClosedError("MCP 连接管理器已关闭")
        assert race is not None
        return race

    def get(self, key: McpConnectionKey) -> McpClient | None:
        with self._lock:
            return self._connections.get(key)

    def reconnect(self, key: McpConnectionKey, config: McpServerConfig) -> McpClient:
        """关闭旧连接后创建全新连接；不会重试旧请求。"""
        self.close_connection(key)
        return self.connect(key, config)

    def close_connection(self, key: McpConnectionKey) -> None:
        with self._lock:
            client = self._connections.pop(key, None)
        if client is not None:
            client.close()

    def close_session(self, session_id: str) -> None:
        self._close_matching(lambda key: key.session_id == session_id)

    def close_agent(self, agent_id: str) -> None:
        self._close_matching(lambda key: key.agent_id == agent_id)

    def close_server(self, server_id: str) -> None:
        self._close_matching(lambda key: key.server_id == server_id)

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            clients = tuple(self._connections.values())
            self._connections.clear()
        for client in clients:
            client.close()

    def _close_matching(self, predicate: Callable[[McpConnectionKey], bool]) -> None:
        with self._lock:
            keys = [key for key in self._connections if predicate(key)]
            clients = [self._connections.pop(key) for key in keys]
        for client in clients:
            client.close()

    def _raise_if_closed(self) -> None:
        if self._closed:
            raise McpConnectionManagerClosedError("MCP 连接管理器已关闭")


def _default_transport_factory(
    config: McpServerConfig,
    notification_handler: Callable[[JsonRpcNotification], None],
) -> McpTransport:
    if isinstance(config, LocalMcpServerConfig):
        return StdioMcpTransport(config, on_notification=notification_handler)
    if isinstance(config, RemoteMcpServerConfig):
        return StreamableHttpTransport(config, on_notification=notification_handler)
    raise TypeError("未知 MCP Server 配置类型")
