"""MCP 传输层的最小同步接口，不包含生命周期或能力协商。"""

from __future__ import annotations

from typing import Callable, Protocol
from threading import Event

from .protocol import JsonRpcNotification, JsonRpcParams, JsonRpcRequest, JsonRpcResponse


NotificationHandler = Callable[[JsonRpcNotification], None]
RequestHandler = Callable[[JsonRpcRequest], JsonRpcResponse]


class McpTransport(Protocol):
    """向 MCP Server 发送 JSON-RPC 请求、通知并关闭传输资源。"""

    def request(
        self,
        method: str,
        params: JsonRpcParams | None = None,
        *,
        timeout_ms: int | None = None,
        cancel_event: Event | None = None,
    ) -> JsonRpcResponse:
        """发送请求并返回 ID 严格关联的响应。"""

    def notify(self, method: str, params: JsonRpcParams | None = None) -> None:
        """发送无需响应的通知。"""

    def close(self) -> None:
        """释放连接、子进程和后台读取资源。"""

    def set_request_handler(self, handler: RequestHandler | None) -> None:
        """设置 Server -> Client request 的响应处理器。"""
