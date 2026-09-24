"""分页读取当前 Session 后台进程的新增日志。"""

from typing import Any

from permission.types import PermissionAction, PermissionRequirement
from session.ExecutionContext import ExecutionContext
from session.session_process_manager import decode_log_cursor, encode_log_cursor
from tools.process_common import parse_process_id, process_error_result, require_process_manager
from tools.types import Tool, ToolResult


def parse_process_logs_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    """校验日志 ID、可选 cursor 和受限返回长度。"""
    parsed = parse_process_id(arguments, allowed={"process_id", "cursor", "limit"})
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


def process_logs(
    ctx: ExecutionContext,
    process_id: str,
    cursor: str | None = None,
    limit: int | None = None,
) -> ToolResult:
    """用不透明 cursor 读取新增 stdout/stderr，不使用 tail -f。"""
    actual_limit = limit or ctx.max_process_log_return_chars
    if actual_limit > ctx.max_process_log_return_chars:
        return ToolResult.failure("INVALID_ARGUMENTS", "limit 超过本地字符上限", retryable=True)
    try:
        stdout_offset, stderr_offset = decode_log_cursor(cursor)
        stream_limit = max(1, actual_limit // 2)
        logs = require_process_manager(ctx).logs(
            process_id,
            stdout_offset=stdout_offset,
            stderr_offset=stderr_offset,
            limit=stream_limit,
        )
        if logs["cursor_expired"]:
            return ToolResult.failure(
                "LOG_CURSOR_EXPIRED",
                "请求的日志 cursor 已被环形缓冲淘汰，请从头重新读取",
                retryable=True,
            )
        return ToolResult.success(
            {
                "process_id": process_id,
                "stdout": logs["stdout"],
                "stderr": logs["stderr"],
                "next_cursor": encode_log_cursor(logs["stdout_offset"], logs["stderr_offset"]),
                "truncated": logs["truncated"],
                "cursor_expired": False,
            }
        )
    except Exception as error:
        return process_error_result(error)


REGISTER = Tool(
    {
        "type": "function",
        "name": "process_logs",
        "description": "分页读取当前 Session 后台进程的新增日志；使用 next_cursor 继续读取。",
        "parameters": {
            "type": "object",
            "properties": {
                "process_id": {"type": "string", "description": "process_start 返回的进程 ID"},
                "cursor": {"type": "string", "description": "上次返回的 next_cursor；省略时从可用日志起点读取"},
                "limit": {"type": "integer", "minimum": 1, "description": "单次日志返回字符上限"},
            },
            "required": ["process_id"],
            "additionalProperties": False,
        },
    },
    process_logs,
    PermissionRequirement(PermissionAction.PROCESS_INSPECT, None),
    argument_parser=parse_process_logs_arguments,
)
