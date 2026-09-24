"""跨平台 Shell 进程启动、受限输出读取和进程组终止。"""

import locale
import os
import signal
import subprocess
import threading
from dataclasses import dataclass
from collections.abc import Callable
from typing import BinaryIO


class ShellExecutionError(OSError):
    """Shell 基础设施失败时携带稳定错误码。"""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class ShellRunResult:
    """一次前台 Shell 命令的受限执行结果。"""

    exit_code: int
    stdout: str
    stderr: str
    stdout_truncated: bool
    stderr_truncated: bool


class BoundedByteBuffer:
    """保留输出头尾的有界字节缓冲，避免输出量决定内存占用。"""

    def __init__(self, limit: int) -> None:
        self._limit = limit
        self._head_limit = (limit + 1) // 2
        self._tail_limit = limit - self._head_limit
        self._complete = bytearray()
        self._head = bytearray()
        self._tail = bytearray()
        self.total_bytes = 0
        self.truncated = False

    def append(self, chunk: bytes) -> None:
        self.total_bytes += len(chunk)
        if not self.truncated:
            remaining_complete = self._limit - len(self._complete)
            if len(chunk) <= remaining_complete:
                self._complete.extend(chunk)
                return
            self._complete.extend(chunk[:remaining_complete])
            self._head.extend(self._complete[: self._head_limit])
            self._tail.extend(self._complete[self._head_limit :])
            self._complete.clear()
            self.truncated = True
            chunk = chunk[remaining_complete:]
        if self._tail_limit == 0:
            return
        self._tail.extend(chunk)
        if len(self._tail) > self._tail_limit:
            del self._tail[: len(self._tail) - self._tail_limit]

    def content(self) -> bytes:
        if not self.truncated:
            return bytes(self._complete)
        marker = b"\n... output truncated ...\n"
        return bytes(self._head) + marker + bytes(self._tail)


def platform_shell_name() -> str:
    """返回公开结果使用的 Shell 名称。"""
    return "powershell" if os.name == "nt" else "bash"


def build_shell_argv(command: str) -> list[str]:
    """将原始命令包装为平台 Shell 的 argv，避免 Windows 字符串拼接。"""
    if os.name == "nt":
        return ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command]
    return ["bash", "-lc", command]


def build_minimal_environment() -> dict[str, str]:
    """仅继承启动 Shell 所需变量，不自动泄露宿主凭据。"""
    allowed = (
        ("SystemRoot", "ComSpec", "PATH", "PATHEXT", "TEMP", "TMP", "USERPROFILE")
        if os.name == "nt"
        else ("PATH", "HOME", "USER", "LANG", "LC_ALL", "TMPDIR")
    )
    return {name: os.environ[name] for name in allowed if name in os.environ}


def decode_output(data: bytes) -> str:
    """按常见终端编码解码已受限的输出字节。"""
    preferred_encoding = locale.getpreferredencoding(False)
    for encoding in ("utf-8-sig", "utf-8", preferred_encoding, "gb18030"):
        try:
            return data.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    return data.decode("utf-8", errors="replace")


class ShellExecutor:
    """以前台模式执行命令，并确保超时会进入进程组终止流程。"""

    def run(
        self,
        command: str,
        *,
        cwd: str,
        timeout_seconds: float,
        output_limit_bytes: int,
    ) -> ShellRunResult:
        process = self.start(command, cwd=cwd)
        stdout_buffer = BoundedByteBuffer(output_limit_bytes)
        stderr_buffer = BoundedByteBuffer(output_limit_bytes)
        readers = _start_readers(process, stdout_buffer, stderr_buffer)
        try:
            process.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired as error:
            terminate_process_tree(process)
            _join_readers(readers)
            raise ShellExecutionError("BASH_TIMEOUT") from error
        _join_readers(readers)
        return ShellRunResult(
            exit_code=process.returncode,
            stdout=decode_output(stdout_buffer.content()),
            stderr=decode_output(stderr_buffer.content()),
            stdout_truncated=stdout_buffer.truncated,
            stderr_truncated=stderr_buffer.truncated,
        )

    def start(self, command: str, *, cwd: str) -> subprocess.Popen[bytes]:
        """启动独立进程组，供前台和 Session 后台进程共用。"""
        try:
            return subprocess.Popen(
                build_shell_argv(command),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=cwd,
                env=build_minimal_environment(),
                start_new_session=os.name != "nt",
                creationflags=(
                    subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
                ),
            )
        except FileNotFoundError as error:
            raise ShellExecutionError("BASH_EXECUTABLE_NOT_FOUND") from error
        except OSError as error:
            raise ShellExecutionError("BASH_START_FAILED") from error


def terminate_process_tree(process: subprocess.Popen[bytes]) -> None:
    """尽力结束目标进程及其后代；重复调用保持安全。"""
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
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
    except (OSError, subprocess.TimeoutExpired):
        return


def _start_readers(
    process: subprocess.Popen[bytes],
    stdout_buffer: BoundedByteBuffer,
    stderr_buffer: BoundedByteBuffer,
) -> tuple[threading.Thread, threading.Thread]:
    if process.stdout is None or process.stderr is None:
        raise ShellExecutionError("BASH_START_FAILED")
    return start_process_stream_readers(process, stdout_buffer.append, stderr_buffer.append)


def start_process_stream_readers(
    process: subprocess.Popen[bytes],
    stdout_consumer: Callable[[bytes], None],
    stderr_consumer: Callable[[bytes], None],
) -> tuple[threading.Thread, threading.Thread]:
    """并行消费进程输出，供前台执行和 Session 后台进程共用。"""
    if process.stdout is None or process.stderr is None:
        raise ShellExecutionError("BASH_START_FAILED")
    readers = (
        threading.Thread(target=_consume_stream, args=(process.stdout, stdout_consumer), daemon=True),
        threading.Thread(target=_consume_stream, args=(process.stderr, stderr_consumer), daemon=True),
    )
    for reader in readers:
        reader.start()
    return readers


def _consume_stream(stream: BinaryIO, consumer: Callable[[bytes], None]) -> None:
    try:
        while chunk := stream.read(64 * 1024):
            consumer(chunk)
    finally:
        stream.close()


def _join_readers(readers: tuple[threading.Thread, threading.Thread]) -> None:
    for reader in readers:
        reader.join(timeout=5)
