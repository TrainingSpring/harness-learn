"""运行受本地 timeout、输出和环境边界保护的前台 Shell 命令。"""

import os
from typing import Any, Protocol

from permission.types import PermissionAction, PermissionRequirement
from session.ExecutionContext import ExecutionContext
from tools.shell.execution import ShellExecutionError, ShellExecutor, platform_shell_name
from tools.shell.process import logs, start, status, stop, wait
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
    """校验 Bash 动作及其严格的参数组合。"""
    action = arguments.get("action")
    action_fields = {
        "execute": {"action", "command", "timeout"},
        "start": {"action", "command"},
        "status": {"action", "process_id"},
        "logs": {"action", "process_id", "cursor", "limit"},
        "wait": {"action", "process_id", "timeout"},
        "stop": {"action", "process_id"},
    }
    if action not in action_fields:
        raise ValueError("action 必须是 execute、start、status、logs、wait 或 stop")

    allowed = action_fields[action]
    unknown = set(arguments) - allowed
    if unknown:
        raise ValueError(f"bash 不支持参数: {', '.join(sorted(unknown))}")

    parsed = {"action": action}
    if action in {"execute", "start"}:
        command = arguments.get("command")
        if not isinstance(command, str) or not command.strip():
            raise ValueError("command 必须是非空字符串")
        parsed["command"] = command
    else:
        process_id = arguments.get("process_id")
        if not isinstance(process_id, str) or not process_id.strip():
            raise ValueError("process_id 必须是非空字符串")
        parsed["process_id"] = process_id

    if "timeout" in arguments:
        timeout = arguments["timeout"]
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout <= 0:
            raise ValueError("timeout 必须是正数")
        parsed["timeout"] = float(timeout)
    if "cursor" in arguments:
        cursor = arguments["cursor"]
        if not isinstance(cursor, str) or not cursor:
            raise ValueError("cursor 必须是非空字符串")
        parsed["cursor"] = cursor
    if "limit" in arguments:
        limit = arguments["limit"]
        if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
            raise ValueError("limit 必须是正整数")
        parsed["limit"] = limit
    return parsed


def bash_permission_requirement(arguments: dict[str, Any]) -> PermissionRequirement:
    """为当前 Bash action 返回准确的权限动作。"""
    action = arguments["action"]
    if action in {"execute", "start"}:
        return PermissionRequirement(PermissionAction.BASH_EXECUTE, None)
    if action in {"status", "logs", "wait"}:
        return PermissionRequirement(PermissionAction.PROCESS_INSPECT, None)
    if action == "stop":
        return PermissionRequirement(PermissionAction.PROCESS_STOP, None)
    raise ValueError(f"未知的 bash action: {action}")


def bash(
    ctx: ExecutionContext,
    action: str,
    command: str | None = None,
    process_id: str | None = None,
    timeout: float | None = None,
    cursor: str | None = None,
    limit: int | None = None,
    *,
    executor: ForegroundShellExecutor | None = None,
) -> ToolResult:
    """执行前台命令或管理当前 Session 的后台 Shell 进程。"""
    try:
        raw_arguments = {"action": action}
        for name, value in (("command", command), ("process_id", process_id), ("timeout", timeout), ("cursor", cursor), ("limit", limit)):
            if value is not None:
                raw_arguments[name] = value
        arguments = parse_bash_arguments(raw_arguments)
    except (TypeError, ValueError) as error:
        return ToolResult.failure("INVALID_ARGUMENTS", str(error), retryable=True)

    if arguments["action"] == "start":
        return start(ctx, arguments["command"])
    if arguments["action"] == "status":
        return status(ctx, arguments["process_id"])
    if arguments["action"] == "logs":
        return logs(ctx, arguments["process_id"], arguments.get("cursor"), arguments.get("limit"))
    if arguments["action"] == "wait":
        return wait(ctx, arguments["process_id"], arguments.get("timeout"))
    if arguments["action"] == "stop":
        return stop(ctx, arguments["process_id"])

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
        "description": "执行前台 Shell 命令，或启动、检查、读取日志、等待和停止当前 Session 的后台进程。",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["execute", "start", "status", "logs", "wait", "stop"],
                    "description": "execute 运行前台命令；其余 action 管理当前 Session 的后台进程",
                },
                "command": {
                    "type": "string",
                    "description": "execute 或 start 时要在当前工作目录运行的 Shell 命令",
                },
                "process_id": {"type": "string", "description": "start 返回的后台进程 ID"},
                "timeout": {
                    "type": "number",
                    "exclusiveMinimum": 0,
                    "description": "可选 timeout 秒数；省略时使用本地默认值",
                },
                "cursor": {"type": "string", "description": "logs 上次返回的 next_cursor"},
                "limit": {"type": "integer", "minimum": 1, "description": "logs 单次返回字符上限"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
    },
    bash,
    PermissionRequirement(PermissionAction.BASH_EXECUTE, None),
    argument_parser=parse_bash_arguments,
    permission_resolver=bash_permission_requirement,
)
