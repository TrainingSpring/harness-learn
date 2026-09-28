"""远程 Streamable HTTP MCP Transport。"""

from __future__ import annotations

import itertools
import json
from threading import Event
from typing import Callable, Final

import httpx

from .errors import (
    McpProtocolError,
    McpRequestCancelledError,
    McpSessionExpiredError,
    McpTransportError,
    McpTransportTimeoutError,
)
from .protocol import (
    JsonRpcNotification,
    JsonRpcParams,
    JsonRpcRequest,
    JsonRpcResponse,
    encode_message,
    parse_message,
)
from .transport import NotificationHandler, RequestHandler
from .types import RemoteMcpServerConfig


_DEFAULT_MAX_RESPONSE_BYTES: Final = 4 * 1024 * 1024


class StreamableHttpTransport:
    """按请求 POST 的 Streamable HTTP Transport，保存 Server 分配的 Session ID。

    此类不处理 ``initialize``：收到 404 时只清空过期 Session ID 并抛出
    ``McpSessionExpiredError``，由后续 lifecycle Client 用新的初始化流程恢复。
    """

    def __init__(
        self,
        config: RemoteMcpServerConfig,
        *,
        on_notification: NotificationHandler | None = None,
        max_response_bytes: int = _DEFAULT_MAX_RESPONSE_BYTES,
        client: httpx.Client | None = None,
        access_token_provider: Callable[[], str | None] | None = None,
    ) -> None:
        if not isinstance(config, RemoteMcpServerConfig):
            raise TypeError("config 必须是 RemoteMcpServerConfig")
        if max_response_bytes <= 0:
            raise ValueError("max_response_bytes 必须是正整数")
        self.config = config
        self._on_notification = on_notification
        self._max_response_bytes = max_response_bytes
        self._client = client or httpx.Client()
        self._owns_client = client is None
        self._ids = itertools.count(1)
        self._session_id: str | None = None
        self._protocol_version: str | None = None
        self._closed = False
        self._access_token_provider = access_token_provider
        self._on_request: RequestHandler | None = None

    @property
    def session_id(self) -> str | None:
        """返回当前 Server 分配的 MCP Session ID。"""
        return self._session_id

    def set_protocol_version(self, version: str | None) -> None:
        """由未来的 lifecycle 层在 initialize 成功后写入协商协议版本。"""
        if version is not None and (not isinstance(version, str) or not version.strip()):
            raise ValueError("protocol version 必须是非空字符串或 None")
        self._protocol_version = version

    def request(
        self,
        method: str,
        params: JsonRpcParams | None = None,
        *,
        timeout_ms: int | None = None,
        cancel_event: Event | None = None,
    ) -> JsonRpcResponse:
        """发送 JSON-RPC request，并从 JSON 或 SSE 中等待匹配 ID 的 response。"""
        if cancel_event is not None and cancel_event.is_set():
            raise McpRequestCancelledError("MCP 请求已在发送前取消")
        request = JsonRpcRequest(next(self._ids), method, params)
        try:
            return self._post_request(request, timeout_ms=timeout_ms, cancel_event=cancel_event)
        except httpx.TimeoutException as error:
            raise McpTransportTimeoutError("远程 MCP 请求超时") from error
        except httpx.HTTPError as error:
            raise McpTransportError("远程 MCP 连接失败") from error

    def notify(self, method: str, params: JsonRpcParams | None = None) -> None:
        """发送 JSON-RPC notification，允许 Server 返回 202、204 或空 200。"""
        self._ensure_open()
        notification = JsonRpcNotification(method, params)
        try:
            with self._client.stream(
                "POST",
                self.config.url,
                headers=self._headers(),
                content=encode_message(notification),
                timeout=self._timeout(timeout_ms=None),
            ) as response:
                self._capture_session_id(response)
                if response.status_code == 404:
                    self._session_id = None
                    raise McpSessionExpiredError("远程 MCP Session 已过期")
                if response.status_code not in {200, 202, 204}:
                    raise McpTransportError(f"远程 MCP 通知失败: HTTP {response.status_code}")
        except httpx.HTTPError as error:
            raise McpTransportError("远程 MCP 通知失败") from error

    def close(self) -> None:
        """关闭底层 HTTP Client；外部注入 Client 的所有权仍属于调用方。"""
        self._closed = True
        self._session_id = None
        if self._owns_client:
            self._client.close()

    def set_request_handler(self, handler: RequestHandler | None) -> None:
        """设置 SSE 中 Server request 的处理器；响应通过独立 POST 回传。"""
        self._on_request = handler

    def set_access_token_provider(self, provider: Callable[[], str | None] | None) -> None:
        """注入运行时 token；token 不进入远程 Server 配置或 URL。"""
        self._access_token_provider = provider

    def _post_request(
        self,
        request: JsonRpcRequest,
        *,
        timeout_ms: int | None,
        cancel_event: Event | None,
    ) -> JsonRpcResponse:
        self._ensure_open()
        with self._client.stream(
            "POST",
            self.config.url,
            headers=self._headers(),
            content=encode_message(request),
            timeout=self._timeout(timeout_ms),
        ) as response:
            self._capture_session_id(response)
            if response.status_code == 404:
                self._session_id = None
                raise McpSessionExpiredError("远程 MCP Session 已过期，需要重新初始化")
            if response.status_code != 200:
                raise McpTransportError(f"远程 MCP 请求失败: HTTP {response.status_code}")
            if "text/event-stream" in response.headers.get("content-type", "").lower():
                return self._read_sse_response(response, request.id, cancel_event)
            return self._read_json_response(response, request.id, cancel_event)

    def _read_json_response(
        self,
        response: httpx.Response,
        request_id: int | str,
        cancel_event: Event | None,
    ) -> JsonRpcResponse:
        raw = self._read_response_bytes(response, request_id, cancel_event)
        try:
            message = parse_message(json.loads(raw.decode("utf-8")))
        except (UnicodeDecodeError, ValueError, McpProtocolError) as error:
            raise McpProtocolError("远程 MCP 返回了无效 JSON-RPC 消息") from error
        return self._matching_response(message, request_id)

    def _read_sse_response(
        self,
        response: httpx.Response,
        request_id: int | str,
        cancel_event: Event | None,
    ) -> JsonRpcResponse:
        size = 0
        data_lines: list[str] = []
        for line in response.iter_lines():
            if cancel_event is not None and cancel_event.is_set():
                self._send_cancellation(request_id)
                raise McpRequestCancelledError("MCP 请求已取消")
            size += len(line.encode("utf-8", errors="replace")) + 1
            if size > self._max_response_bytes:
                raise McpProtocolError("远程 MCP SSE 响应超过大小限制")
            if not line:
                matched = self._dispatch_sse_data(data_lines, request_id)
                data_lines.clear()
                if matched is not None:
                    return matched
                continue
            if line.startswith("data:"):
                data_lines.append(line[5:].lstrip())
        matched = self._dispatch_sse_data(data_lines, request_id)
        if matched is not None:
            return matched
        raise McpProtocolError("远程 MCP SSE 在返回匹配 response 前结束")

    def _dispatch_sse_data(
        self,
        data_lines: list[str],
        request_id: int | str,
    ) -> JsonRpcResponse | None:
        if not data_lines:
            return None
        try:
            message = parse_message(json.loads("\n".join(data_lines)))
        except (ValueError, McpProtocolError) as error:
            raise McpProtocolError("远程 MCP SSE data 不是有效 JSON-RPC") from error
        if isinstance(message, JsonRpcNotification):
            if self._on_notification is not None:
                try:
                    self._on_notification(message)
                except Exception:
                    # 观察回调不能改变远程协议请求的结果。
                    pass
            return None
        if isinstance(message, JsonRpcRequest):
            if self._on_request is None:
                raise McpProtocolError("MCP Server request 没有处理器")
            response = self._on_request(message)
            if not isinstance(response, JsonRpcResponse):
                raise McpProtocolError("MCP Server request 处理器必须返回 response")
            self._send_server_response(response)
            return None
        return self._matching_response(message, request_id)

    def _send_server_response(self, response: JsonRpcResponse) -> None:
        """通过同一 MCP endpoint 回送 Server request 的 response。"""
        with self._client.stream(
            "POST", self.config.url, headers=self._headers(),
            content=encode_message(response), timeout=self._timeout(timeout_ms=None),
        ) as result:
            self._capture_session_id(result)
            if result.status_code not in {200, 202, 204}:
                raise McpTransportError(f"MCP Server request response 发送失败: HTTP {result.status_code}")

    @staticmethod
    def _matching_response(message: object, request_id: int | str) -> JsonRpcResponse:
        if not isinstance(message, JsonRpcResponse):
            raise McpProtocolError("远程 MCP 未返回 JSON-RPC response")
        if message.id != request_id:
            raise McpProtocolError("远程 MCP response ID 与请求不匹配")
        return message

    def _read_response_bytes(
        self,
        response: httpx.Response,
        request_id: int | str,
        cancel_event: Event | None,
    ) -> bytes:
        chunks: list[bytes] = []
        size = 0
        for chunk in response.iter_bytes():
            if cancel_event is not None and cancel_event.is_set():
                self._send_cancellation(request_id)
                raise McpRequestCancelledError("MCP 请求已取消")
            size += len(chunk)
            if size > self._max_response_bytes:
                raise McpProtocolError("远程 MCP 响应超过大小限制")
            chunks.append(chunk)
        return b"".join(chunks)

    def _headers(self) -> dict[str, str]:
        headers = {
            **self.config.headers,
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        }
        if self._session_id is not None:
            headers["Mcp-Session-Id"] = self._session_id
        if self._protocol_version is not None:
            headers["MCP-Protocol-Version"] = self._protocol_version
        if self._access_token_provider is not None:
            token = self._access_token_provider()
            if token:
                headers["Authorization"] = f"Bearer {token}"
        return headers

    def _capture_session_id(self, response: httpx.Response) -> None:
        value = response.headers.get("mcp-session-id")
        if value:
            if len(value) > 1024 or "\r" in value or "\n" in value:
                raise McpProtocolError("远程 MCP Session ID 格式无效")
            self._session_id = value

    def _send_cancellation(self, request_id: int | str | None) -> None:
        if request_id is None:
            return
        try:
            self.notify("notifications/cancelled", {"requestId": request_id})
        except McpTransportError:
            pass

    def _timeout(self, timeout_ms: int | None) -> httpx.Timeout:
        value = self.config.request_timeout_ms if timeout_ms is None else timeout_ms
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError("timeout_ms 必须是正整数")
        return httpx.Timeout(value / 1000)

    def _ensure_open(self) -> None:
        if self._closed:
            raise McpTransportError("远程 MCP Transport 已关闭")
