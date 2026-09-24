"""当前打开 Session 内后台进程的生命周期和日志管理。"""

import base64
import json
import secrets
import subprocess
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

from tools.shell_execution import (
    ShellExecutor,
    decode_output,
    platform_shell_name,
    start_process_stream_readers,
    terminate_process_tree,
)


class ProcessState(StrEnum):
    """Session 内进程的可观察状态。"""

    STARTING = "starting"
    RUNNING = "running"
    EXITED = "exited"
    FAILED = "failed"
    STOPPED = "stopped"


class ProcessManagerError(ValueError):
    """进程管理器向 Tool 暴露的稳定业务错误。"""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class _RingLogBuffer:
    """以绝对字节 offset 读取的有界日志环。"""

    def __init__(self, max_bytes: int) -> None:
        self._max_bytes = max_bytes
        self._data = bytearray()
        self._start_offset = 0
        self._end_offset = 0
        self._lock = threading.Lock()

    def append(self, chunk: bytes) -> None:
        with self._lock:
            self._data.extend(chunk)
            self._end_offset += len(chunk)
            overflow = len(self._data) - self._max_bytes
            if overflow > 0:
                del self._data[:overflow]
                self._start_offset += overflow

    def read(self, offset: int, limit: int) -> tuple[bytes, int, bool, bool]:
        with self._lock:
            expired = offset < self._start_offset
            if expired:
                offset = self._start_offset
            offset = min(max(offset, self._start_offset), self._end_offset)
            end_offset = min(offset + limit, self._end_offset)
            return (
                bytes(self._data[offset - self._start_offset : end_offset - self._start_offset]),
                end_offset,
                expired,
                end_offset < self._end_offset,
            )


@dataclass
class _ProcessRecord:
    """仅在内存保存的进程句柄及其 Session 级元数据。"""

    process_id: str
    command: str
    cwd: str
    process: subprocess.Popen[bytes]
    stdout: _RingLogBuffer
    stderr: _RingLogBuffer
    started_at: str
    state: ProcessState = ProcessState.STARTING
    exit_code: int | None = None
    ended_at: str | None = None
    readers: tuple[threading.Thread, threading.Thread] = field(default_factory=tuple)


class SessionProcessManager:
    """管理一个已打开 Session 的后台进程，绝不持久化 OS 进程句柄。"""

    def __init__(
        self,
        session_id: str,
        *,
        shell_executor: ShellExecutor | None = None,
        terminate_process=terminate_process_tree,
        max_log_bytes: int = 4 * 1024 * 1024,
        startup_probe_seconds: float = 0.2,
    ) -> None:
        if not session_id:
            raise ValueError("session_id 不能为空")
        if max_log_bytes <= 0:
            raise ValueError("max_log_bytes 必须大于 0")
        if startup_probe_seconds <= 0:
            raise ValueError("startup_probe_seconds 必须大于 0")
        self.session_id = session_id
        self._executor = shell_executor or ShellExecutor()
        self._terminate_process = terminate_process
        self._max_log_bytes = max_log_bytes
        self._startup_probe_seconds = startup_probe_seconds
        self._records: dict[str, _ProcessRecord] = {}
        self._lock = threading.RLock()
        self._closed = False

    def start(self, command: str, *, cwd: str) -> dict:
        """后台启动命令，立即返回该 Session 唯一的进程记录。"""
        with self._lock:
            if self._closed:
                raise ProcessManagerError("SESSION_PROCESS_MANAGER_CLOSED")
        process = self._executor.start(command, cwd=cwd)
        record = _ProcessRecord(
            process_id=f"proc_{secrets.token_urlsafe(12)}",
            command=command,
            cwd=cwd,
            process=process,
            stdout=_RingLogBuffer(self._max_log_bytes),
            stderr=_RingLogBuffer(self._max_log_bytes),
            started_at=_timestamp(),
        )
        record.readers = start_process_stream_readers(
            process,
            record.stdout.append,
            record.stderr.append,
        )
        with self._lock:
            if self._closed:
                self._terminate_process(process)
                raise ProcessManagerError("SESSION_PROCESS_MANAGER_CLOSED")
            self._records[record.process_id] = record
            self._probe_startup_locked(record)
            if record.state is ProcessState.RUNNING:
                threading.Thread(
                    target=self._watch,
                    args=(record.process_id,),
                    daemon=True,
                ).start()
            return self._snapshot(record)

    def status(self, process_id: str) -> dict:
        """读取本 Session 记录的最新进程状态。"""
        with self._lock:
            record = self._record_for(process_id)
            self._refresh_completion_locked(record)
            return self._snapshot(record)

    def stop(self, process_id: str) -> dict:
        """终止本 Session 的一个进程树；已退出记录保持幂等。"""
        with self._lock:
            record = self._record_for(process_id)
            self._refresh_completion_locked(record)
            if record.state in {ProcessState.EXITED, ProcessState.FAILED, ProcessState.STOPPED}:
                return self._snapshot(record)
            self._terminate_process(record.process)
            record.exit_code = record.process.returncode
            record.ended_at = _timestamp()
            record.state = ProcessState.STOPPED
            return self._snapshot(record)

    def stop_all(self) -> None:
        """停止当前打开 Session 尚在运行的全部后台进程。"""
        with self._lock:
            records = tuple(self._records.values())
            self._closed = True
        for record in records:
            try:
                self.stop(record.process_id)
            except ProcessManagerError:
                continue

    def wait(self, process_id: str, *, timeout_seconds: float) -> dict:
        """最多等待指定秒数；时间到达时返回仍在运行的当前快照。"""
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds 必须大于 0")
        with self._lock:
            record = self._record_for(process_id)
            self._refresh_completion_locked(record)
            if record.state is not ProcessState.RUNNING:
                return self._snapshot(record)
        try:
            record.process.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            pass
        with self._lock:
            self._refresh_completion_locked(record)
            return self._snapshot(record)

    def logs(self, process_id: str, *, stdout_offset: int, stderr_offset: int, limit: int) -> dict:
        """从两个流的绝对 offset 读取新增日志，供后续 Tool 生成 cursor。"""
        if limit <= 0:
            raise ValueError("limit 必须大于 0")
        with self._lock:
            record = self._record_for(process_id)
            stdout, next_stdout, stdout_expired, stdout_more = record.stdout.read(
                stdout_offset,
                limit,
            )
            stderr, next_stderr, stderr_expired, stderr_more = record.stderr.read(
                stderr_offset,
                limit,
            )
            return {
                "stdout": decode_output(stdout),
                "stderr": decode_output(stderr),
                "stdout_offset": next_stdout,
                "stderr_offset": next_stderr,
                "cursor_expired": stdout_expired or stderr_expired,
                "truncated": stdout_more or stderr_more,
            }

    def _record_for(self, process_id: str) -> _ProcessRecord:
        if not isinstance(process_id, str) or not process_id:
            raise ProcessManagerError("PROCESS_NOT_FOUND")
        record = self._records.get(process_id)
        if record is None:
            raise ProcessManagerError("PROCESS_NOT_FOUND")
        return record

    def _probe_startup_locked(self, record: _ProcessRecord) -> None:
        try:
            record.process.wait(timeout=self._startup_probe_seconds)
        except subprocess.TimeoutExpired:
            record.state = ProcessState.RUNNING
            return
        self._mark_completed_locked(record)

    def _refresh_completion_locked(self, record: _ProcessRecord) -> None:
        if record.state is not ProcessState.RUNNING:
            return
        if record.process.poll() is not None:
            self._mark_completed_locked(record)

    def _mark_completed_locked(self, record: _ProcessRecord) -> None:
        if record.state is ProcessState.STOPPED:
            return
        record.exit_code = record.process.returncode
        record.ended_at = _timestamp()
        record.state = (
            ProcessState.EXITED if record.exit_code == 0 else ProcessState.FAILED
        )

    def _watch(self, process_id: str) -> None:
        with self._lock:
            record = self._records.get(process_id)
        if record is None:
            return
        try:
            record.process.wait()
        except OSError:
            pass
        with self._lock:
            if self._records.get(process_id) is record:
                self._mark_completed_locked(record)

    @staticmethod
    def _snapshot(record: _ProcessRecord) -> dict:
        return {
            "process_id": record.process_id,
            "state": record.state.value,
            "pid": record.process.pid,
            "command": record.command,
            "shell": platform_shell_name(),
            "cwd": record.cwd,
            "started_at": record.started_at,
            "exit_code": record.exit_code,
            "ended_at": record.ended_at,
        }


def encode_log_cursor(stdout_offset: int, stderr_offset: int) -> str:
    """将日志绝对位置编码为不依赖进程 PID 的不透明 cursor。"""
    payload = json.dumps([stdout_offset, stderr_offset], separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(payload).decode("ascii")


def decode_log_cursor(cursor: str | None) -> tuple[int, int]:
    """解析由本模块签发的日志 cursor。"""
    if cursor is None:
        return 0, 0
    try:
        payload = base64.urlsafe_b64decode(cursor.encode("ascii"))
        stdout_offset, stderr_offset = json.loads(payload)
    except (UnicodeEncodeError, ValueError, json.JSONDecodeError) as error:
        raise ProcessManagerError("INVALID_LOG_CURSOR") from error
    if (
        isinstance(stdout_offset, bool)
        or isinstance(stderr_offset, bool)
        or not isinstance(stdout_offset, int)
        or not isinstance(stderr_offset, int)
        or stdout_offset < 0
        or stderr_offset < 0
    ):
        raise ProcessManagerError("INVALID_LOG_CURSOR")
    return stdout_offset, stderr_offset


def _timestamp() -> str:
    return datetime.now(UTC).isoformat()
