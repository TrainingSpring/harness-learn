"""Bash Tool 使用的 Session 后台进程内部操作。"""

import os
from typing import Any

from session.ExecutionContext import ExecutionContext
from session.session_process_manager import ProcessManagerError
from tools.shell.execution import ShellExecutionError
from tools.types import ToolResult


def require_process_manager(ctx: ExecutionContext) -> Any:
    """确保 Tool 被装配到一个仍打开的 Session 执行环境。"""
    if ctx.process_manager is None:
        raise ProcessManagerError("PROCESS_MANAGER_UNAVAILABLE")
    return ctx.process_manager


def process_error_result(error: Exception) -> ToolResult:
    """把进程基础设施异常收敛为公开的稳定 Tool 错误。"""
    if isinstance(error, ProcessManagerError):
        messages = {
            "PROCESS_NOT_FOUND": "当前 Session 中不存在该进程",
            "PROCESS_MANAGER_UNAVAILABLE": "当前 Session 未初始化后台进程管理器",
            "SESSION_PROCESS_MANAGER_CLOSED": "当前 Session 已关闭，不能管理后台进程",
            "INVALID_LOG_CURSOR": "日志 cursor 无效，请从头重新读取",
        }
        return ToolResult.failure(
            error.code,
            messages.get(error.code, "后台进程管理失败"),
            retryable=error.code in {"PROCESS_MANAGER_UNAVAILABLE", "SESSION_PROCESS_MANAGER_CLOSED"},
        )
    if isinstance(error, ShellExecutionError):
        messages = {
            "BASH_EXECUTABLE_NOT_FOUND": "当前系统未找到 Bash 或 PowerShell",
            "BASH_START_FAILED": "后台进程无法启动",
        }
        code = error.code if error.code in messages else "BASH_EXECUTION_FAILED"
        return ToolResult.failure(
            code,
            messages.get(code, "后台进程启动失败"),
            retryable=code != "BASH_EXECUTABLE_NOT_FOUND",
        )
    return ToolResult.failure("PROCESS_EXECUTION_FAILED", "后台进程操作失败", retryable=True)


def start(ctx: ExecutionContext, command: str) -> ToolResult:
    """在当前工作目录启动持续服务，启动后立即返回进程标识。"""
    if len(command) > ctx.max_bash_command_chars:
        return ToolResult.failure("INVALID_ARGUMENTS", "command 超过本地字符上限", retryable=True)
    if ctx.project_path is None:
        return ToolResult.failure("PROJECT_NOT_SELECTED", "当前 Session 未选择项目目录")
    if not os.path.isdir(ctx.project_path):
        return ToolResult.failure(
            "WORKSPACE_NOT_FOUND",
            "当前 Session 的工作目录不存在或不是目录",
            retryable=True,
        )
    try:
        return ToolResult.success(require_process_manager(ctx).start(command, cwd=ctx.project_path))
    except Exception as error:
        return process_error_result(error)


def status(ctx: ExecutionContext, process_id: str) -> ToolResult:
    """返回当前 Session 后台进程的状态、PID、退出码和启动时间。"""
    try:
        return ToolResult.success(require_process_manager(ctx).status(process_id))
    except Exception as error:
        return process_error_result(error)


def logs(
    ctx: ExecutionContext,
    process_id: str,
    cursor: str | None = None,
    limit: int | None = None,
) -> ToolResult:
    """用不透明 cursor 读取新增 stdout/stderr，不使用 tail -f。"""
    from session.session_process_manager import decode_log_cursor, encode_log_cursor

    actual_limit = limit or ctx.max_process_log_return_chars
    if actual_limit > ctx.max_process_log_return_chars:
        return ToolResult.failure("INVALID_ARGUMENTS", "limit 超过本地字符上限", retryable=True)
    try:
        cursor_process_id, stdout_offset, stderr_offset = decode_log_cursor(cursor)
        stream_limit = max(1, actual_limit // 2)
        process_logs = require_process_manager(ctx).logs(
            process_id,
            cursor_process_id=cursor_process_id,
            stdout_offset=stdout_offset,
            stderr_offset=stderr_offset,
            limit=stream_limit,
        )
        if process_logs["cursor_expired"]:
            return ToolResult.failure(
                "LOG_CURSOR_EXPIRED",
                "请求的日志 cursor 已被环形缓冲淘汰，请从头重新读取",
                retryable=True,
            )
        stdout = process_logs["stdout"]
        stderr = process_logs["stderr"]
        remaining = actual_limit
        stdout = stdout[:remaining]
        remaining -= len(stdout)
        stderr = stderr[:remaining]
        truncated = (
            process_logs["truncated"]
            or len(stdout) < len(process_logs["stdout"])
            or len(stderr) < len(process_logs["stderr"])
        )
        return ToolResult.success(
            {
                "process_id": process_id,
                "stdout": stdout,
                "stderr": stderr,
                "next_cursor": encode_log_cursor(
                    process_id,
                    process_logs["stdout_offset"],
                    process_logs["stderr_offset"],
                ),
                "truncated": truncated,
                "cursor_expired": False,
            }
        )
    except Exception as error:
        return process_error_result(error)


def wait(
    ctx: ExecutionContext,
    process_id: str,
    timeout: float | None = None,
) -> ToolResult:
    """有限等待后台进程，时间到达时返回当前状态而不阻塞 Agent Loop。"""
    timeout_seconds = timeout or ctx.default_bash_timeout_seconds
    if timeout_seconds > ctx.max_bash_timeout_seconds:
        return ToolResult.failure("INVALID_ARGUMENTS", "timeout 超过本地秒数上限", retryable=True)
    try:
        return ToolResult.success(
            require_process_manager(ctx).wait(process_id, timeout_seconds=timeout_seconds)
        )
    except Exception as error:
        return process_error_result(error)


def stop(ctx: ExecutionContext, process_id: str) -> ToolResult:
    """幂等地停止当前 Session 的目标后台进程树。"""
    try:
        return ToolResult.success(require_process_manager(ctx).stop(process_id))
    except Exception as error:
        return process_error_result(error)
