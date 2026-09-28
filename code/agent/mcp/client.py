"""建立在 Transport 之上的 MCP 生命周期、能力和发现 Client。"""

from __future__ import annotations

from enum import StrEnum
from threading import Event, Lock
from typing import Any

from .capabilities import McpImplementation
from .errors import McpCapabilityUnavailableError, McpLifecycleError, McpProtocolError, McpTransportError
from .lifecycle import McpInitialization, initialize_params
from .notifications import McpNotificationDispatcher
from .pagination import collect_pages
from .protocol import JsonRpcNotification, JsonRpcParams
from .transport import McpTransport


class McpClientState(StrEnum):
    """MCP Client 生命周期状态。"""

    NEW = "new"
    CONNECTING = "connecting"
    READY = "ready"
    FAILED = "failed"
    CLOSED = "closed"


class McpClient:
    """一个且仅一个 MCP 连接的同步 Client。

    Client 不知道 Agent、Session 或 Tool；连接归属与释放由
    ``McpConnectionManager`` 管理。调用方必须先 ``connect``，否则不允许
    使用 ping、分页发现或 completion。
    """

    def __init__(
        self,
        transport: McpTransport,
        *,
        client_info: McpImplementation | None = None,
        client_capabilities: dict[str, Any] | None = None,
    ) -> None:
        self.transport = transport
        self.client_info = client_info or McpImplementation("harness-learn", "0.1.0")
        self.client_capabilities = dict(client_capabilities or {})
        self.notifications = McpNotificationDispatcher()
        self._state = McpClientState.NEW
        self._initialization: McpInitialization | None = None
        self._lock = Lock()

    @property
    def state(self) -> McpClientState:
        return self._state

    @property
    def initialization(self) -> McpInitialization:
        if self._initialization is None:
            raise McpLifecycleError("MCP Client 尚未完成 initialize")
        return self._initialization

    def connect(self, *, timeout_ms: int | None = None) -> McpInitialization:
        """执行 initialize 后发送 required 的 initialized 通知。"""
        with self._lock:
            if self._state is McpClientState.READY:
                return self.initialization
            if self._state in {McpClientState.CONNECTING, McpClientState.CLOSED}:
                raise McpLifecycleError(f"MCP Client 当前状态不能连接: {self._state.value}")
            self._state = McpClientState.CONNECTING
        try:
            response = self.transport.request(
                "initialize",
                initialize_params(self.client_info, capabilities=self.client_capabilities),
                timeout_ms=timeout_ms,
            )
            initialization = McpInitialization.from_wire(response.unwrap())
            set_version = getattr(self.transport, "set_protocol_version", None)
            if callable(set_version):
                set_version(initialization.protocol_version)
            self.transport.notify("notifications/initialized")
        except Exception:
            with self._lock:
                self._state = McpClientState.FAILED
            raise
        with self._lock:
            self._initialization = initialization
            self._state = McpClientState.READY
        return initialization

    def ping(
        self,
        *,
        timeout_ms: int | None = None,
        cancel_event: Event | None = None,
    ) -> dict[str, Any]:
        """检测当前已初始化连接是否仍可请求。"""
        result = self._request("ping", timeout_ms=timeout_ms, cancel_event=cancel_event)
        if not isinstance(result, dict):
            raise McpLifecycleError("MCP ping 结果必须是对象")
        return result

    def list_tools(self, *, timeout_ms: int | None = None) -> tuple[dict[str, Any], ...]:
        return self._list("tools", "tools/list", "tools", timeout_ms)

    def list_resources(self, *, timeout_ms: int | None = None) -> tuple[dict[str, Any], ...]:
        return self._list("resources", "resources/list", "resources", timeout_ms)

    def list_prompts(self, *, timeout_ms: int | None = None) -> tuple[dict[str, Any], ...]:
        return self._list("prompts", "prompts/list", "prompts", timeout_ms)

    def complete(
        self,
        params: dict[str, Any],
        *,
        timeout_ms: int | None = None,
        cancel_event: Event | None = None,
    ) -> dict[str, Any]:
        """调用 completion/complete；参数构造和结果语义由阶段 7 接入。"""
        self._require_capability("completions")
        result = self._request(
            "completion/complete",
            params,
            timeout_ms=timeout_ms,
            cancel_event=cancel_event,
        )
        if not isinstance(result, dict):
            raise McpLifecycleError("MCP completion 结果必须是对象")
        return result

    def handle_notification(self, notification: JsonRpcNotification) -> bool:
        """分发 Server 通知；Transport 可把此方法作为回调注入。"""
        return self.notifications.dispatch(notification)

    def close(self) -> None:
        """释放底层传输；关闭动作应由连接管理器按归属调用。"""
        with self._lock:
            if self._state is McpClientState.CLOSED:
                return
            self._state = McpClientState.CLOSED
        self.transport.close()

    def shutdown(self, *, timeout_ms: int | None = None) -> None:
        """按 MCP 生命周期请求 Server 关闭，再无条件释放本地连接。"""
        if self._state is McpClientState.READY:
            try:
                self._request("shutdown", timeout_ms=timeout_ms)
            finally:
                self.close()
            return
        self.close()

    def _list(
        self,
        capability: str,
        method: str,
        item_field: str,
        timeout_ms: int | None,
    ) -> tuple[dict[str, Any], ...]:
        self._require_capability(capability)
        return collect_pages(
            lambda params: self._request(method, params, timeout_ms=timeout_ms),
            item_field=item_field,
        )

    def _request(
        self,
        method: str,
        params: JsonRpcParams | None = None,
        *,
        timeout_ms: int | None = None,
        cancel_event: Event | None = None,
    ) -> Any:
        self._require_ready()
        try:
            return self.transport.request(
                method,
                params,
                timeout_ms=timeout_ms,
                cancel_event=cancel_event,
            ).unwrap()
        except (McpTransportError, McpProtocolError):
            # 连接或协议失效才需要显式重连；不会自动重试可能有副作用的请求。
            with self._lock:
                if self._state is McpClientState.READY:
                    self._state = McpClientState.FAILED
            raise

    def _require_ready(self) -> None:
        if self._state is not McpClientState.READY:
            raise McpLifecycleError(f"MCP Client 当前状态不能请求: {self._state.value}")

    def _require_capability(self, capability: str) -> None:
        self._require_ready()
        if not self.initialization.capabilities.supports(capability):
            raise McpCapabilityUnavailableError(f"MCP Server 未声明 {capability} 能力")
