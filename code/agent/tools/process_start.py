"""启动由当前 Session 持有的后台进程。"""

import os
from typing import Any

from permission.types import PermissionAction, PermissionRequirement
from session.ExecutionContext import ExecutionContext
from tools.process_common import process_error_result, require_process_manager
from tools.types import Tool, ToolResult


def parse_process_start_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    """仅接受一个非空后台命令。"""
    if set(arguments) != {"command"}:
        raise ValueError("process_start 只支持 command 参数")
    command = arguments.get("command")
    if not isinstance(command, str) or not command.strip():
        raise ValueError("command 必须是非空字符串")
    return {"command": command}


def process_start(ctx: ExecutionContext, command: str) -> ToolResult:
    """在当前工作目录启动持续服务，启动后立即返回进程标识。"""
    if len(command) > ctx.max_bash_command_chars:
        return ToolResult.failure("INVALID_ARGUMENTS", "command 超过本地字符上限", retryable=True)
    if ctx.project_path is None:
        return ToolResult.failure("PROJECT_NOT_SELECTED", "当前 Session 未选择项目目录")
    if not os.path.isdir(ctx.project_path):
        return ToolResult.failure("WORKSPACE_NOT_FOUND", "当前 Session 的工作目录不存在或不是目录", retryable=True)
    try:
        return ToolResult.success(require_process_manager(ctx).start(command, cwd=ctx.project_path))
    except Exception as error:
        return process_error_result(error)


REGISTER = Tool(
    {
        "type": "function",
        "name": "process_start",
        "description": "在当前 Session 工作目录启动持续运行的服务或 worker，并立即返回 process_id。",
        "parameters": {
            "type": "object",
            "properties": {"command": {"type": "string", "description": "要后台启动的 Shell 命令"}},
            "required": ["command"],
            "additionalProperties": False,
        },
    },
    process_start,
    PermissionRequirement(PermissionAction.BASH_EXECUTE, None),
    argument_parser=parse_process_start_arguments,
)
