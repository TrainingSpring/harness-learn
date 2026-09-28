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
from .server_requests import McpServerRequestHandler


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
        self.server_requests = McpServerRequestHandler()
        set_handler = getattr(self.transport, "set_request_handler", None)
        if callable(set_handler):
            set_handler(self.server_requests.handle)

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

    def list_roots(self, *, workspace: str | None = None) -> dict[str, Any]:
        """生成 Server 请求 roots/list 时可返回的当前工作目录描述。"""
        from .roots import roots_for_workspace
        return {"roots": [root.to_dict() for root in roots_for_workspace(workspace)]}

    def configure_server_requests(
        self,
        *,
        workspace: str | None = None,
        sampling: Any | None = None,
        elicitation: Any | None = None,
    ) -> None:
        """配置 Server request 回调；未配置的请求会收到稳定错误。"""
        self.server_requests.workspace = workspace
        if sampling is not None:
            self.server_requests.register("sampling/createMessage", sampling)
        if elicitation is not None:
            self.server_requests.register("elicitation/create", elicitation)

    def list_resource_templates(self, *, timeout_ms: int | None = None) -> tuple[dict[str, Any], ...]:
        self._require_capability("resources")
        return collect_pages(
            lambda params: self._request("resources/templates/list", params, timeout_ms=timeout_ms),
            item_field="resourceTemplates",
        )

    def call_tool(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
        *,
        timeout_ms: int | None = None,
        cancel_event: Event | None = None,
    ) -> dict[str, Any]:
        """调用 Server Tool；业务错误保留在 MCP CallToolResult 中。"""
        self._require_capability("tools")
        if not isinstance(name, str) or not name:
            raise McpLifecycleError("MCP Tool name 必须是非空字符串")
        if arguments is not None and not isinstance(arguments, dict):
            raise McpLifecycleError("MCP Tool arguments 必须是对象")
        result = self._request(
            "tools/call",
            {"name": name, "arguments": arguments or {}},
            timeout_ms=timeout_ms,
            cancel_event=cancel_event,
        )
        if not isinstance(result, dict) or not isinstance(result.get("content"), list):
            raise McpProtocolError("MCP tools/call 结果必须包含 content 数组")
        if "isError" in result and not isinstance(result["isError"], bool):
            raise McpProtocolError("MCP tools/call isError 必须是布尔值")
        return result

    def read_resource(
        self,
        uri: str,
        *,
        timeout_ms: int | None = None,
        cancel_event: Event | None = None,
    ) -> dict[str, Any]:
        self._require_capability("resources")
        if not isinstance(uri, str) or not uri:
            raise McpLifecycleError("MCP Resource URI 必须是非空字符串")
        result = self._request(
            "resources/read", {"uri": uri}, timeout_ms=timeout_ms, cancel_event=cancel_event
        )
        from .resources import validate_resource_result
        return validate_resource_result(result)

    def subscribe_resource(
        self,
        uri: str,
        *,
        timeout_ms: int | None = None,
    ) -> dict[str, Any]:
        if not self.initialization.capabilities.supports_subscriptions():
            raise McpCapabilityUnavailableError("MCP Server 未声明 resources.subscribe 能力")
        return self._resource_subscription("resources/subscribe", uri, timeout_ms)

    def unsubscribe_resource(
        self,
        uri: str,
        *,
        timeout_ms: int | None = None,
    ) -> dict[str, Any]:
        if not self.initialization.capabilities.supports_subscriptions():
            raise McpCapabilityUnavailableError("MCP Server 未声明 resources.subscribe 能力")
        return self._resource_subscription("resources/unsubscribe", uri, timeout_ms)

    def get_prompt(
        self,
        name: str,
        arguments: dict[str, str] | None = None,
        *,
        timeout_ms: int | None = None,
    ) -> dict[str, Any]:
        self._require_capability("prompts")
        if not isinstance(name, str) or not name:
            raise McpLifecycleError("MCP Prompt name 必须是非空字符串")
        if arguments is not None and (
            not isinstance(arguments, dict)
            or any(not isinstance(key, str) or not isinstance(value, str) for key, value in arguments.items())
        ):
            raise McpLifecycleError("MCP Prompt arguments 必须是字符串映射")
        result = self._request(
            "prompts/get",
            {"name": name, "arguments": arguments or {}},
            timeout_ms=timeout_ms,
        )
        from .prompts import parse_prompt_result
        parse_prompt_result(result)
        return result

    def set_logging_level(self, level: str, *, timeout_ms: int | None = None) -> dict[str, Any]:
        self._require_capability("logging")
        if level not in {"debug", "info", "notice", "warning", "error", "critical", "alert", "emergency"}:
            raise McpLifecycleError("MCP logging level 无效")
        result = self._request("logging/setLevel", {"level": level}, timeout_ms=timeout_ms)
        from .logging import validate_logging_result
        return validate_logging_result(result)

    def complete(
        self,
        params: dict[str, Any],
        *,
        timeout_ms: int | None = None,
        cancel_event: Event | None = None,
    ) -> dict[str, Any]:
        """调用 completion/complete；参数构造和结果语义由阶段 7 接入。"""
        self._require_capability("completions")
        from .completions import validate_completion_params, validate_completion_result
        result = self._request(
            "completion/complete",
            validate_completion_params(params),
            timeout_ms=timeout_ms,
            cancel_event=cancel_event,
        )
        return validate_completion_result(result)

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

    def _resource_subscription(
        self,
        method: str,
        uri: str,
        timeout_ms: int | None,
    ) -> dict[str, Any]:
        self._require_ready()
        if not isinstance(uri, str) or not uri:
            raise McpLifecycleError("MCP Resource URI 必须是非空字符串")
        result = self._request(method, {"uri": uri}, timeout_ms=timeout_ms)
        if not isinstance(result, dict):
            raise McpProtocolError(f"MCP {method} 结果必须是对象")
        return result

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
