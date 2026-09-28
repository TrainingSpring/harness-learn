"""由 Harness 启动的 MCP stdio Transport。"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import itertools
import json
import os
from pathlib import Path
import subprocess
from threading import Event, Lock, Thread
import time
from typing import Final

from .errors import (
    McpConnectionClosedError,
    McpProtocolError,
    McpRequestCancelledError,
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
from .types import LocalMcpServerConfig


_DEFAULT_MAX_MESSAGE_BYTES: Final = 4 * 1024 * 1024
_DEFAULT_DIAGNOSTIC_BYTES: Final = 64 * 1024
_DEFAULT_REQUEST_TIMEOUT_MS: Final = 30_000


@dataclass
class _PendingResponse:
    """一个已发出请求在后台读线程中的等待状态。"""

    event: Event
    response: JsonRpcResponse | None = None
    error: Exception | None = None


class StdioMcpTransport:
    """通过子进程 stdin/stdout 交换逐行 JSON-RPC 的同步 MCP Transport。

    stdout 仅接收协议消息，stderr 被单独、有界地收集作本地诊断。每个实例
    只服务一个未来的 MCP Client/Session，不能跨 Session 共用同一 stdio 流。
    """

    def __init__(
        self,
        config: LocalMcpServerConfig,
        *,
        on_notification: NotificationHandler | None = None,
        on_request: RequestHandler | None = None,
        max_message_bytes: int = _DEFAULT_MAX_MESSAGE_BYTES,
        diagnostic_bytes: int = _DEFAULT_DIAGNOSTIC_BYTES,
    ) -> None:
        if not isinstance(config, LocalMcpServerConfig):
            raise TypeError("config 必须是 LocalMcpServerConfig")
        if max_message_bytes <= 0 or diagnostic_bytes <= 0:
            raise ValueError("消息和诊断容量必须为正整数")
        self.config = config
        self._on_notification = on_notification
        self._on_request = on_request
        self._max_message_bytes = max_message_bytes
        self._diagnostic_bytes = diagnostic_bytes
        self._pending: dict[int | str, _PendingResponse] = {}
        self._pending_lock = Lock()
        self._write_lock = Lock()
        self._state_lock = Lock()
        self._ids = itertools.count(1)
        self._closed = False
        self._terminal_error: Exception | None = None
        self._stderr_lines: deque[str] = deque()
        self._stderr_size = 0
        self._process = self._start_process()
        self._stdout_thread = Thread(target=self._read_stdout, daemon=True)
        self._stderr_thread = Thread(target=self._read_stderr, daemon=True)
        self._stdout_thread.start()
        self._stderr_thread.start()

    @property
    def diagnostics(self) -> tuple[str, ...]:
        """返回有界 stderr 快照，仅供本地诊断，不能直接暴露到 Web API。"""
        with self._state_lock:
            return tuple(self._stderr_lines)

    def request(
        self,
        method: str,
        params: JsonRpcParams | None = None,
        *,
        timeout_ms: int | None = None,
        cancel_event: Event | None = None,
    ) -> JsonRpcResponse:
        """发送请求，并等待相同 JSON-RPC ID 的 response。"""
        if cancel_event is not None and cancel_event.is_set():
            raise McpRequestCancelledError("MCP 请求已在发送前取消")
        timeout = self._timeout_seconds(timeout_ms)
        request = JsonRpcRequest(next(self._ids), method, params)
        pending = _PendingResponse(Event())
        with self._pending_lock:
            self._raise_if_unavailable()
            self._pending[request.id] = pending
        try:
            self._write(request)
            deadline = time.monotonic() + timeout
            while not pending.event.wait(min(0.05, max(0.0, deadline - time.monotonic()))):
                if cancel_event is not None and cancel_event.is_set():
                    self._cancel(request.id)
                    raise McpRequestCancelledError("MCP 请求已取消")
                if time.monotonic() >= deadline:
                    raise McpTransportTimeoutError("等待 MCP 响应超时")
            if pending.error is not None:
                raise pending.error
            if pending.response is None:
                raise McpProtocolError("MCP 请求结束时缺少响应")
            return pending.response
        finally:
            with self._pending_lock:
                self._pending.pop(request.id, None)

    def notify(self, method: str, params: JsonRpcParams | None = None) -> None:
        """发送无 response 的 JSON-RPC 通知。"""
        with self._state_lock:
            self._raise_if_unavailable()
        self._write(JsonRpcNotification(method, params))

    def close(self) -> None:
        """先关闭 stdin，再按配置依次等待、终止和强制终止子进程。"""
        with self._state_lock:
            if self._closed:
                return
            self._closed = True
        self._fail_pending(McpConnectionClosedError("MCP stdio 连接已关闭"))
        process = self._process
        if process.stdin is not None:
            try:
                process.stdin.close()
            except OSError:
                pass
        timeout = self.config.shutdown_timeout_ms / 1000
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            process.terminate()
            try:
                process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=timeout)
        self._stdout_thread.join(timeout=0.1)
        self._stderr_thread.join(timeout=0.1)

    def set_request_handler(self, handler: RequestHandler | None) -> None:
        self._on_request = handler

    def _start_process(self) -> subprocess.Popen[bytes]:
        environment = os.environ.copy()
        environment.update(self.config.env)
        argv = [self.config.command, *self.config.args]
        try:
            return subprocess.Popen(
                argv,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=self.config.cwd,
                env=environment,
                shell=False,
                bufsize=0,
                close_fds=True,
                start_new_session=os.name != "nt",
            )
        except OSError as error:
            raise McpTransportError("无法启动本地 MCP 服务") from error

    def _write(self, message: JsonRpcRequest | JsonRpcNotification | JsonRpcResponse) -> None:
        data = encode_message(message) + b"\n"
        if len(data) > self._max_message_bytes:
            raise McpProtocolError("MCP 请求超过消息大小限制")
        with self._write_lock:
            self._raise_if_unavailable()
            stdin = self._process.stdin
            if stdin is None:
                raise McpConnectionClosedError("MCP stdio stdin 不可用")
            try:
                stdin.write(data)
                stdin.flush()
            except OSError as error:
                failure = McpConnectionClosedError("MCP stdio 写入失败")
                self._set_terminal_error(failure)
                raise failure from error

    def _read_stdout(self) -> None:
        stdout = self._process.stdout
        if stdout is None:
            self._set_terminal_error(McpConnectionClosedError("MCP stdio stdout 不可用"))
            return
        try:
            while True:
                line = stdout.readline(self._max_message_bytes + 1)
                if not line:
                    break
                if len(line) > self._max_message_bytes or not line.endswith(b"\n"):
                    raise McpProtocolError("MCP stdio 消息超过大小限制或缺少换行符")
                try:
                    decoded = line.decode("utf-8")
                    message = parse_message(json.loads(decoded))
                except (UnicodeDecodeError, ValueError, McpProtocolError) as error:
                    raise McpProtocolError("MCP stdio 返回了无效 JSON-RPC 消息") from error
                self._dispatch(message)
        except Exception as error:
            self._set_terminal_error(error if isinstance(error, McpProtocolError) else McpTransportError("读取 MCP stdio 失败"))
            return
        with self._state_lock:
            closed = self._closed
        if not closed:
            self._set_terminal_error(McpConnectionClosedError("MCP stdio 服务已退出"))

    def _read_stderr(self) -> None:
        stderr = self._process.stderr
        if stderr is None:
            return
        while True:
            line = stderr.readline(self._max_message_bytes + 1)
            if not line:
                return
            text = line[: self._max_message_bytes].decode("utf-8", errors="replace").rstrip("\r\n")
            with self._state_lock:
                self._stderr_lines.append(text)
                self._stderr_size += len(text.encode("utf-8", errors="replace"))
                while self._stderr_size > self._diagnostic_bytes and self._stderr_lines:
                    removed = self._stderr_lines.popleft()
                    self._stderr_size -= len(removed.encode("utf-8", errors="replace"))

    def _dispatch(self, message: object) -> None:
        if isinstance(message, JsonRpcResponse):
            if message.id is None:
                self._set_terminal_error(McpProtocolError("MCP response 不能使用 null id"))
                return
            with self._pending_lock:
                pending = self._pending.get(message.id)
            if pending is not None:
                pending.response = message
                pending.event.set()
            return
        if isinstance(message, JsonRpcNotification):
            if self._on_notification is not None:
                try:
                    self._on_notification(message)
                except Exception:
                    # 外部观察回调不能破坏协议读循环。
                    pass
            return
        if isinstance(message, JsonRpcRequest):
            if self._on_request is None:
                self._set_terminal_error(McpProtocolError("MCP Server request 没有处理器"))
                return
            try:
                response = self._on_request(message)
                if not isinstance(response, JsonRpcResponse):
                    raise McpProtocolError("MCP Server request 处理器必须返回 response")
                self._write(response)
            except Exception as error:
                self._set_terminal_error(error if isinstance(error, McpProtocolError) else McpTransportError("MCP Server request 处理失败"))
            return
        self._set_terminal_error(McpProtocolError("当前 Client 不支持 Server 发起的 JSON-RPC request"))

    def _cancel(self, request_id: int | str) -> None:
        try:
            self.notify("notifications/cancelled", {"requestId": request_id})
        except McpTransportError:
            pass

    def _raise_if_unavailable(self) -> None:
        if self._terminal_error is not None:
            raise self._terminal_error
        if self._closed:
            raise McpConnectionClosedError("MCP stdio 连接已关闭")

    def _set_terminal_error(self, error: Exception) -> None:
        with self._state_lock:
            if self._closed or self._terminal_error is not None:
                return
            self._terminal_error = error
        self._fail_pending(error)

    def _fail_pending(self, error: Exception) -> None:
        with self._pending_lock:
            pending = tuple(self._pending.values())
        for item in pending:
            item.error = error
            item.event.set()

    def _timeout_seconds(self, timeout_ms: int | None) -> float:
        value = _DEFAULT_REQUEST_TIMEOUT_MS if timeout_ms is None else timeout_ms
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError("timeout_ms 必须是正整数")
        return value / 1000
