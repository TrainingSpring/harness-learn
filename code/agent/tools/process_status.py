"""读取当前 Session 后台进程的状态。"""

from typing import Any

from permission.types import PermissionAction, PermissionRequirement
from session.ExecutionContext import ExecutionContext
from tools.process_common import parse_process_id, process_error_result, require_process_manager
from tools.types import Tool, ToolResult


def parse_process_status_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    return parse_process_id(arguments, allowed={"process_id"})


def process_status(ctx: ExecutionContext, process_id: str) -> ToolResult:
    """返回进程当前状态、PID、退出码和启动时间。"""
    try:
        return ToolResult.success(require_process_manager(ctx).status(process_id))
    except Exception as error:
        return process_error_result(error)


REGISTER = Tool(
    {
        "type": "function",
        "name": "process_status",
        "description": "查询当前 Session 已启动后台进程的状态。",
        "parameters": {
            "type": "object",
            "properties": {"process_id": {"type": "string", "description": "process_start 返回的进程 ID"}},
            "required": ["process_id"],
            "additionalProperties": False,
        },
    },
    process_status,
    PermissionRequirement(PermissionAction.PROCESS_INSPECT, None),
    argument_parser=parse_process_status_arguments,
)
