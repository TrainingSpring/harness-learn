"""有限等待当前 Session 后台进程。"""

from typing import Any

from permission.types import PermissionAction, PermissionRequirement
from session.ExecutionContext import ExecutionContext
from tools.process_common import parse_process_id, process_error_result, require_process_manager
from tools.types import Tool, ToolResult


def parse_process_wait_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    parsed = parse_process_id(arguments, allowed={"process_id", "timeout"})
    if "timeout" in arguments:
        timeout = arguments["timeout"]
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout <= 0:
            raise ValueError("timeout 必须是正数")
        parsed["timeout"] = float(timeout)
    return parsed


def process_wait(
    ctx: ExecutionContext,
    process_id: str,
    timeout: float | None = None,
) -> ToolResult:
    """最多等待有限时间，超时后返回仍在运行的状态而非阻塞 Agent Loop。"""
    timeout_seconds = timeout or ctx.default_bash_timeout_seconds
    if timeout_seconds > ctx.max_bash_timeout_seconds:
        return ToolResult.failure("INVALID_ARGUMENTS", "timeout 超过本地秒数上限", retryable=True)
    try:
        return ToolResult.success(
            require_process_manager(ctx).wait(process_id, timeout_seconds=timeout_seconds)
        )
    except Exception as error:
        return process_error_result(error)


REGISTER = Tool(
    {
        "type": "function",
        "name": "process_wait",
        "description": "最多等待指定时间后返回当前 Session 后台进程的最新状态，不会无限阻塞。",
        "parameters": {
            "type": "object",
            "properties": {
                "process_id": {"type": "string", "description": "process_start 返回的进程 ID"},
                "timeout": {"type": "number", "exclusiveMinimum": 0, "description": "可选等待秒数；省略时使用本地默认值"},
            },
            "required": ["process_id"],
            "additionalProperties": False,
        },
    },
    process_wait,
    PermissionRequirement(PermissionAction.PROCESS_INSPECT, None),
    argument_parser=parse_process_wait_arguments,
)
