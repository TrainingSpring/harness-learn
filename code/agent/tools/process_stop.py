"""停止当前 Session 持有的后台进程。"""

from typing import Any

from permission.types import PermissionAction, PermissionRequirement
from session.ExecutionContext import ExecutionContext
from tools.process_common import parse_process_id, process_error_result, require_process_manager
from tools.types import Tool, ToolResult


def parse_process_stop_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    return parse_process_id(arguments, allowed={"process_id"})


def process_stop(ctx: ExecutionContext, process_id: str) -> ToolResult:
    """幂等地停止当前 Session 的目标后台进程树。"""
    try:
        return ToolResult.success(require_process_manager(ctx).stop(process_id))
    except Exception as error:
        return process_error_result(error)


REGISTER = Tool(
    {
        "type": "function",
        "name": "process_stop",
        "description": "停止当前 Session 已启动的一个后台进程；重复停止保持幂等。",
        "parameters": {
            "type": "object",
            "properties": {"process_id": {"type": "string", "description": "process_start 返回的进程 ID"}},
            "required": ["process_id"],
            "additionalProperties": False,
        },
    },
    process_stop,
    PermissionRequirement(PermissionAction.PROCESS_STOP, None),
    argument_parser=parse_process_stop_arguments,
)
