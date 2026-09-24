"""运行受本地 timeout、输出和环境边界保护的前台 Shell 命令。"""

import os
from typing import Any, Protocol

from permission.types import PermissionAction, PermissionRequirement
from session.ExecutionContext import ExecutionContext
from tools.shell_execution import ShellExecutionError, ShellExecutor, platform_shell_name
from tools.types import Tool, ToolResult


class ForegroundShellExecutor(Protocol):
    """供 Bash 注入的最小前台执行接口。"""

    def run(
        self,
        command: str,
        *,
        cwd: str,
        timeout_seconds: float,
        output_limit_bytes: int,
    ) -> Any: ...


def parse_bash_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    """校验模型命令参数，禁止无限前台执行和宽松类型转换。"""
    allowed = {"command", "timeout"}
    unknown = set(arguments) - allowed
    if unknown:
        raise ValueError(f"bash 不支持参数: {', '.join(sorted(unknown))}")

    command = arguments.get("command")
    if not isinstance(command, str) or not command.strip():
        raise ValueError("command 必须是非空字符串")

    parsed = {"command": command}
    if "timeout" in arguments:
        timeout = arguments["timeout"]
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout <= 0:
            raise ValueError("timeout 必须是正数")
        parsed["timeout"] = float(timeout)
    return parsed


def bash(
    ctx: ExecutionContext,
    command: str,
    timeout: float | None = None,
    *,
    executor: ForegroundShellExecutor | None = None,
) -> ToolResult:
    """运行一个有限时长的前台 Shell 命令。

    持续服务、worker 和日志监听必须使用 ``process_start`` 及相关 Process
    Tool；Bash 不支持无限等待。命令在当前 Session 工作目录执行，且只继承
    Shell 必需的最小环境变量集合。
    """
    try:
        arguments = parse_bash_arguments(
            {
                "command": command,
                **({"timeout": timeout} if timeout is not None else {}),
            }
        )
    except (TypeError, ValueError) as error:
        return ToolResult.failure("INVALID_ARGUMENTS", str(error), retryable=True)

    if len(arguments["command"]) > ctx.max_bash_command_chars:
        return ToolResult.failure(
            "INVALID_ARGUMENTS",
            "command 超过本地字符上限",
            retryable=True,
            details={"max_bash_command_chars": ctx.max_bash_command_chars},
        )
    timeout_seconds = arguments.get("timeout", ctx.default_bash_timeout_seconds)
    if timeout_seconds > ctx.max_bash_timeout_seconds:
        return ToolResult.failure(
            "INVALID_ARGUMENTS",
            "timeout 超过本地秒数上限",
            retryable=True,
            details={"max_bash_timeout_seconds": ctx.max_bash_timeout_seconds},
        )
    if ctx.project_path is None:
        return ToolResult.failure("PROJECT_NOT_SELECTED", "当前 Session 未选择项目目录")
    if not os.path.isdir(ctx.project_path):
        return ToolResult.failure(
            "WORKSPACE_NOT_FOUND",
            "当前 Session 的工作目录不存在或不是目录",
            retryable=True,
            details={"path": ctx.project_path},
        )

    try:
        result = (executor or ShellExecutor()).run(
            arguments["command"],
            cwd=ctx.project_path,
            timeout_seconds=timeout_seconds,
            output_limit_bytes=ctx.max_bash_output_bytes,
        )
    except ShellExecutionError as error:
        code = error.code
        messages = {
            "BASH_TIMEOUT": "命令执行超过本地 timeout，已终止进程组",
            "BASH_EXECUTABLE_NOT_FOUND": "当前系统未找到 Bash 或 PowerShell",
            "BASH_START_FAILED": "命令进程无法启动",
        }
        return ToolResult.failure(
            code if code in messages else "BASH_EXECUTION_FAILED",
            messages.get(code, "命令执行失败"),
            retryable=code != "BASH_EXECUTABLE_NOT_FOUND",
        )

    return ToolResult.success(
        {
            "command": arguments["command"],
            "shell": platform_shell_name(),
            "cwd": ctx.project_path,
            "exit_code": result["exit_code"] if isinstance(result, dict) else result.exit_code,
            "stdout": result["stdout"] if isinstance(result, dict) else result.stdout,
            "stderr": result["stderr"] if isinstance(result, dict) else result.stderr,
            "stdout_truncated": (
                result["stdout_truncated"] if isinstance(result, dict) else result.stdout_truncated
            ),
            "stderr_truncated": (
                result["stderr_truncated"] if isinstance(result, dict) else result.stderr_truncated
            ),
            "timeout_seconds": timeout_seconds,
        }
    )


REGISTER = Tool(
    {
        "type": "function",
        "name": "bash",
        "description": "执行一次性、有限时长的前台 Bash 或 PowerShell 命令。持续服务、worker 和持续日志请使用 process_* 工具。",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "要在当前工作目录执行的前台 Shell 命令",
                },
                "timeout": {
                    "type": "number",
                    "exclusiveMinimum": 0,
                    "description": "可选 timeout 秒数；省略时使用本地默认值",
                },
            },
            "required": ["command"],
            "additionalProperties": False,
        },
    },
    bash,
    PermissionRequirement(PermissionAction.BASH_EXECUTE, None),
    argument_parser=parse_bash_arguments,
)
