"""Session Process Tool 共用的参数和受控错误映射。"""

from typing import Any

from session.ExecutionContext import ExecutionContext
from session.session_process_manager import ProcessManagerError
from tools.shell_execution import ShellExecutionError
from tools.types import ToolResult


def parse_process_id(arguments: dict[str, Any], *, allowed: set[str]) -> dict[str, Any]:
    """验证所有进程操作共有的 ID 和严格字段白名单。"""
    unknown = set(arguments) - allowed
    if unknown:
        raise ValueError(f"process 工具不支持参数: {', '.join(sorted(unknown))}")
    process_id = arguments.get("process_id")
    if not isinstance(process_id, str) or not process_id.strip():
        raise ValueError("process_id 必须是非空字符串")
    return {"process_id": process_id}


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
