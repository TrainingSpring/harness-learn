"""文件工具共享的版本检查与原子提交能力。"""

import os
import stat
import tempfile
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator

from tools.file_version import file_version


class FileMutationError(OSError):
    """文件提交失败时携带不会泄露底层异常的稳定错误码。"""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


_UNSET = object()
_LOCKS_GUARD = threading.Lock()


@dataclass
class _PathLock:
    lock: threading.Lock
    holders: int = 0


_PATH_LOCKS: dict[str, _PathLock] = {}


@contextmanager
def acquire_file_mutation_lock(
    path: str,
    *,
    timeout_seconds: float,
) -> Iterator[None]:
    """为一个真实绝对路径获取带超时的进程内提交锁。"""
    real_path = os.path.realpath(os.path.abspath(path))
    with _LOCKS_GUARD:
        entry = _PATH_LOCKS.get(real_path)
        if entry is None:
            entry = _PathLock(threading.Lock())
            _PATH_LOCKS[real_path] = entry
        entry.holders += 1

    acquired = entry.lock.acquire(timeout=timeout_seconds)
    if not acquired:
        _release_path_lock_reference(real_path, entry)
        raise FileMutationError("FILE_BUSY")
    try:
        yield
    finally:
        entry.lock.release()
        _release_path_lock_reference(real_path, entry)


def _release_path_lock_reference(real_path: str, entry: _PathLock) -> None:
    with _LOCKS_GUARD:
        entry.holders -= 1
        if entry.holders == 0 and _PATH_LOCKS.get(real_path) is entry:
            del _PATH_LOCKS[real_path]


def existing_file_version(path: str) -> str | None:
    """返回普通文件版本；文件不存在时返回 None。"""
    try:
        return file_version(path)
    except FileNotFoundError:
        return None


def commit_file(
    path: str,
    content: bytes,
    *,
    expected_version: str | None | object = _UNSET,
    lock_timeout_seconds: float = 5.0,
) -> dict[str, object]:
    """以临时文件和原子替换提交 bytes，并在提交前后校验版本。

    ``_UNSET`` 表示调用方没有提供前置条件；显式的 ``None`` 表示要求
    目标保持不存在，供 write 的创建语义使用。
    """
    with acquire_file_mutation_lock(path, timeout_seconds=lock_timeout_seconds):
        return _commit_locked_file(path, content, expected_version=expected_version)


def _commit_locked_file(
    path: str,
    content: bytes,
    *,
    expected_version: str | None | object,
) -> dict[str, object]:
    if os.path.isdir(path):
        raise FileMutationError("TARGET_IS_DIRECTORY")

    temporary_path: str | None = None
    try:
        initial_version = existing_file_version(path)
        if expected_version is not _UNSET and initial_version != expected_version:
            raise FileMutationError("FILE_CHANGED")

        original_mode = _existing_file_mode(path)
        parent_dir = os.path.dirname(path)
        descriptor, temporary_path = tempfile.mkstemp(
            prefix=f".{os.path.basename(path)}.",
            suffix=".tmp",
            dir=parent_dir,
        )
        if original_mode is not None:
            os.chmod(temporary_path, original_mode)
        with os.fdopen(descriptor, "wb") as file:
            file.write(content)
            file.flush()
            os.fsync(file.fileno())

        if existing_file_version(path) != initial_version:
            raise FileMutationError("FILE_CHANGED")
        os.replace(temporary_path, path)
        temporary_path = None
        return {
            "operation": "replaced" if initial_version is not None else "created",
            "version": file_version(path),
        }
    except FileMutationError:
        raise
    except OSError as error:
        raise FileMutationError("FILE_MUTATION_FAILED") from error
    finally:
        if temporary_path is not None:
            try:
                os.unlink(temporary_path)
            except FileNotFoundError:
                pass


def _existing_file_mode(path: str) -> int | None:
    try:
        return stat.S_IMODE(os.stat(path).st_mode)
    except FileNotFoundError:
        return None
