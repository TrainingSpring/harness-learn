"""本地 MCP Server 进程生命周期管理。"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, replace
from enum import StrEnum
import os
from pathlib import Path
import signal
import subprocess
from threading import Lock, Thread
from datetime import datetime, timezone
from typing import Callable, Final
import uuid

from .errors import (
    McpLocalServerError,
    McpProcessManagerClosedError,
    McpRemoteLifecycleError,
)
from .registry import McpServerRegistry
from .types import LocalMcpServerConfig


_DEFAULT_STARTUP_PROBE_MS: Final = 100
_MAX_DIAGNOSTIC_LINES: Final = 100


class McpLocalServerState(StrEnum):
    """本地 MCP Server 的可观察进程状态。"""

    NOT_RUNNING = "not_running"
    STARTING = "starting"
    RUNNING = "running"
    EXITED = "exited"
    FAILED = "failed"
    STOPPED = "stopped"


@dataclass(frozen=True)
class McpLocalServerStatus:
    """不包含进程对象和敏感环境变量的状态快照。"""

    server_id: str
    instance_id: str | None
    state: McpLocalServerState
    pid: int | None = None
    command: str | None = None
    cwd: str | None = None
    started_at: str | None = None
    ended_at: str | None = None
    exit_code: int | None = None
    diagnostic_code: str | None = None
    diagnostics: tuple[str, ...] = ()


@dataclass
class _ProcessRecord:
    status: McpLocalServerStatus
    process: subprocess.Popen[bytes]
    shutdown_timeout_ms: int
    diagnostics: deque[str]


StatusListener = Callable[[McpLocalServerStatus], None]


class McpProcessManager:
    """管理显式启动的本地 MCP 进程，不共享其 stdio 通道给 Session。

    每个注册 Server 最多有一个由该管理器持有的控制实例。阶段 5 的
    ``McpConnectionManager`` 会为具体 Session 另起独立 stdio 实例，避免多个
    会话竞争一条 stdin/stdout JSON-RPC 流。
    """

    def __init__(
        self,
        registry: McpServerRegistry,
        *,
        startup_probe_ms: int = _DEFAULT_STARTUP_PROBE_MS,
    ) -> None:
        if not isinstance(registry, McpServerRegistry):
            raise TypeError("registry 必须是 McpServerRegistry")
        if isinstance(startup_probe_ms, bool) or not isinstance(startup_probe_ms, int) or startup_probe_ms <= 0:
            raise ValueError("startup_probe_ms 必须是正整数")
        self.registry = registry
        self._startup_probe_ms = startup_probe_ms
        self._records: dict[str, _ProcessRecord] = {}
        self._listeners: list[StatusListener] = []
        self._lock = Lock()
        self._listeners_lock = Lock()
        self._closed = False

    def subscribe(self, listener: StatusListener) -> Callable[[], None]:
        """订阅生命周期状态事件，并返回取消订阅函数。"""
        if not callable(listener):
            raise TypeError("listener 必须可调用")
        with self._listeners_lock:
            self._listeners.append(listener)

        def unsubscribe() -> None:
            with self._listeners_lock:
                if listener in self._listeners:
                    self._listeners.remove(listener)

        return unsubscribe

    def start(self, server_id: str) -> McpLocalServerStatus:
        """启动本地 Server；已在运行时返回当前实例快照。"""
        config = self._local_config(server_id)
        events: list[McpLocalServerStatus] = []
        with self._lock:
            self._raise_if_closed()
            current = self._records.get(server_id)
            if current is not None and current.process.poll() is None:
                return current.status
            if current is not None:
                finished = self._mark_finished_locked(current)
                if finished is not None:
                    events.append(finished)
            process = self._spawn(config)
            instance_id = f"mcp_instance_{uuid.uuid4().hex}"
            status = McpLocalServerStatus(
                server_id=server_id,
                instance_id=instance_id,
                state=McpLocalServerState.STARTING,
                pid=process.pid,
                command=config.command,
                cwd=config.cwd,
                started_at=_timestamp(),
            )
            record = _ProcessRecord(
                status=status,
                process=process,
                shutdown_timeout_ms=config.shutdown_timeout_ms,
                diagnostics=deque(maxlen=_MAX_DIAGNOSTIC_LINES),
            )
            self._records[server_id] = record
            events.append(status)
            Thread(target=self._watch, args=(server_id, record), daemon=True).start()
            self._drain_pipes(record)
            probed = self._probe_startup_locked(record)
            if probed is not None:
                events.append(probed)
            result = record.status
        for event in events:
            self._emit(event)
        return result

    def stop(self, server_id: str) -> McpLocalServerStatus:
        """停止本地 Server；不存在运行实例时返回稳定错误。"""
        event: McpLocalServerStatus | None = None
        with self._lock:
            self._raise_if_closed()
            record = self._records.get(server_id)
            if record is None:
                raise McpLocalServerError("MCP Server 未运行")
            if record.process.poll() is not None:
                event = self._mark_finished_locked(record)
                result = record.status
            else:
                self._terminate(record.process)
                self._wait_for_exit(record)
                record.status = replace(
                    record.status,
                    state=McpLocalServerState.STOPPED,
                    ended_at=record.status.ended_at or _timestamp(),
                    exit_code=record.process.returncode,
                    diagnostics=tuple(record.diagnostics),
                )
                result = record.status
                event = result
        if event is not None:
            self._emit(event)
        return result

    def restart(self, server_id: str) -> McpLocalServerStatus:
        """停止当前实例后启动全新的本地 Server 实例。"""
        with self._lock:
            record = self._records.get(server_id)
            running = record is not None and record.process.poll() is None
        if running:
            self.stop(server_id)
        return self.start(server_id)

    def status(self, server_id: str) -> McpLocalServerStatus:
        """读取当前状态，并刷新已退出进程的结束信息。"""
        event: McpLocalServerStatus | None = None
        with self._lock:
            self._raise_if_closed()
            record = self._records.get(server_id)
            if record is None:
                config = self.registry.get(server_id)
                if not config.is_local:
                    raise McpRemoteLifecycleError("远程 MCP Server 没有本地进程状态")
                return McpLocalServerStatus(server_id=server_id, instance_id=None, state=McpLocalServerState.NOT_RUNNING)
            if record.process.poll() is not None:
                event = self._mark_finished_locked(record)
            result = record.status
        if event is not None:
            self._emit(event)
        return result

    def close(self) -> None:
        """停止所有仍运行的进程并拒绝后续操作。"""
        with self._lock:
            if self._closed:
                return
            ids = [server_id for server_id, record in self._records.items() if record.process.poll() is None]
            self._closed = True
        for server_id in ids:
            record = self._records.get(server_id)
            if record is None:
                continue
            self._terminate(record.process)
            self._wait_for_exit(record)
        with self._lock:
            for record in self._records.values():
                if record.process.poll() is not None and record.status.state is not McpLocalServerState.STOPPED:
                    record.status = replace(record.status, state=McpLocalServerState.STOPPED, ended_at=record.status.ended_at or _timestamp(), exit_code=record.process.returncode)

    def _local_config(self, server_id: str) -> LocalMcpServerConfig:
        config = self.registry.require_enabled(server_id)
        if not isinstance(config, LocalMcpServerConfig):
            raise McpRemoteLifecycleError("远程 MCP Server 不支持本地启动、停止或重启")
        return config

    @staticmethod
    def _spawn(config: LocalMcpServerConfig) -> subprocess.Popen[bytes]:
        environment = os.environ.copy()
        environment.update(config.env)
        try:
            return subprocess.Popen(
                [config.command, *config.args],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=config.cwd,
                env=environment,
                shell=False,
                bufsize=0,
                close_fds=True,
                start_new_session=os.name != "nt",
                creationflags=(subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0),
            )
        except OSError as error:
            raise McpLocalServerError("MCP Server 启动失败") from error

    def _probe_startup_locked(self, record: _ProcessRecord) -> McpLocalServerStatus | None:
        try:
            record.process.wait(timeout=self._startup_probe_ms / 1000)
        except subprocess.TimeoutExpired:
            record.status = replace(record.status, state=McpLocalServerState.RUNNING)
            return record.status
        return self._mark_finished_locked(record)

    def _mark_finished_locked(self, record: _ProcessRecord) -> McpLocalServerStatus | None:
        code = record.process.returncode
        if code is None:
            return None
        state = McpLocalServerState.EXITED if code == 0 else McpLocalServerState.FAILED
        record.status = replace(
            record.status,
            state=state,
            ended_at=record.status.ended_at or _timestamp(),
            exit_code=code,
            diagnostic_code="MCP_CONNECTION_CLOSED" if code != 0 else None,
            diagnostics=tuple(record.diagnostics),
        )
        return record.status

    def _watch(self, server_id: str, record: _ProcessRecord) -> None:
        try:
            record.process.wait()
        except OSError:
            return
        event: McpLocalServerStatus | None = None
        with self._lock:
            if self._records.get(server_id) is record and record.status.state is not McpLocalServerState.STOPPED:
                event = self._mark_finished_locked(record)
        if event is not None:
            self._emit(event)

    @staticmethod
    def _drain_pipes(record: _ProcessRecord) -> None:
        def drain(stream, capture: bool) -> None:
            if stream is None:
                return
            try:
                while chunk := stream.read(64 * 1024):
                    if capture:
                        text = chunk.decode("utf-8", errors="replace")
                        record.diagnostics.extend(text.splitlines()[-_MAX_DIAGNOSTIC_LINES:])
            finally:
                stream.close()

        Thread(target=drain, args=(record.process.stdout, False), daemon=True).start()
        Thread(target=drain, args=(record.process.stderr, True), daemon=True).start()

    def _wait_for_exit(self, record: _ProcessRecord) -> None:
        try:
            record.process.wait(timeout=record.shutdown_timeout_ms / 1000)
        except subprocess.TimeoutExpired:
            try:
                record.process.kill()
                record.process.wait(timeout=record.shutdown_timeout_ms / 1000)
            except (OSError, subprocess.TimeoutExpired) as error:
                raise McpLocalServerError("MCP Server 停止超时") from error

    @staticmethod
    def _terminate(process: subprocess.Popen[bytes]) -> None:
        if process.poll() is not None:
            return
        try:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill.exe", "/PID", str(process.pid), "/T", "/F"],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                    timeout=5,
                )
            else:
                os.killpg(os.getpgid(process.pid), signal.SIGTERM)
        except (OSError, subprocess.TimeoutExpired):
            try:
                process.terminate()
            except OSError:
                pass

    def _raise_if_closed(self) -> None:
        if self._closed:
            raise McpProcessManagerClosedError("MCP 进程管理器已关闭")

    def _emit(self, status: McpLocalServerStatus) -> None:
        with self._listeners_lock:
            listeners = tuple(self._listeners)
        for listener in listeners:
            try:
                listener(status)
            except Exception:
                pass


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()
