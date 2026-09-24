"""原子创建或完整替换 UTF-8 文本文件的 Tool。"""

import os
from typing import Any

from permission.types import PermissionAction, PermissionRequirement
from session.ExecutionContext import ExecutionContext
from tools.files.mutation import FileMutationError, _UNSET, commit_file
from tools.types import Tool, ToolResult, handle_path


def parse_write_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    """校验模型提供的 write 参数，并拒绝不属于当前契约的字段。"""
    allowed = {"target_path", "content", "expected_version"}
    unknown = set(arguments) - allowed
    if unknown:
        raise ValueError(f"write 不支持参数: {', '.join(sorted(unknown))}")

    target_path = arguments.get("target_path")
    if not isinstance(target_path, str) or not target_path.strip():
        raise ValueError("target_path 必须是非空字符串")
    if "content" not in arguments or not isinstance(arguments["content"], str):
        raise ValueError("content 必须是字符串")

    parsed = {"target_path": target_path, "content": arguments["content"]}
    if "expected_version" in arguments:
        expected_version = arguments["expected_version"]
        if not isinstance(expected_version, str) or not expected_version:
            raise ValueError("expected_version 必须是非空字符串")
        parsed["expected_version"] = expected_version
    return parsed


def write(
    ctx: ExecutionContext,
    target_path: str,
    content: str,
    *,
    expected_version: str | None = None,
) -> ToolResult:
    """原子地创建或完整替换一个受本地字节上限保护的文本文件。"""
    try:
        arguments = parse_write_arguments(
            {
                "target_path": target_path,
                "content": content,
                **(
                    {"expected_version": expected_version}
                    if expected_version is not None
                    else {}
                ),
            }
        )
    except (TypeError, ValueError) as error:
        return ToolResult.failure("INVALID_ARGUMENTS", str(error), retryable=True)

    encoded_content = arguments["content"].encode("utf-8")
    if len(encoded_content) > ctx.max_write_bytes:
        return ToolResult.failure(
            "FILE_TOO_LARGE",
            "写入内容超过本地字节上限",
            details={"max_write_bytes": ctx.max_write_bytes},
        )

    target_path = handle_path(ctx, arguments["target_path"])
    try:
        parent_dir = os.path.dirname(target_path)
        os.makedirs(parent_dir, exist_ok=True)
    except OSError:
        return ToolResult.failure(
            "CREATE_DIRECTORY_FAILED",
            "创建目标父目录失败",
            details={"path": target_path},
        )

    if os.path.isdir(target_path):
        return ToolResult.failure(
            "TARGET_IS_DIRECTORY",
            "目标路径是目录，不能写入文件",
            details={"path": target_path},
        )

    try:
        mutation = commit_file(
            target_path,
            encoded_content,
            expected_version=(
                arguments["expected_version"]
                if "expected_version" in arguments
                else _UNSET
            ),
            lock_timeout_seconds=ctx.file_mutation_lock_timeout_seconds,
        )
        return ToolResult.success(
            {
                "operation": mutation["operation"],
                "path": target_path,
                "bytes_written": len(encoded_content),
                "version": mutation["version"],
                "precondition_checked": "expected_version" in arguments,
            }
        )
    except FileMutationError as error:
        if error.code == "FILE_CHANGED":
            return ToolResult.failure(
                "FILE_CHANGED",
                "目标文件已变化，请重新读取后再写入",
                retryable=True,
                details={"path": target_path},
            )
        if error.code == "TARGET_IS_DIRECTORY":
            return ToolResult.failure(
                "TARGET_IS_DIRECTORY",
                "目标路径是目录，不能写入文件",
                details={"path": target_path},
            )
        if error.code == "FILE_BUSY":
            return ToolResult.failure(
                "FILE_BUSY",
                "目标文件正在被另一项提交处理，请稍后重试",
                retryable=True,
                details={"path": target_path},
            )
        return ToolResult.failure(
            "WRITE_FILE_FAILED",
            "文件写入或原子替换失败",
            details={"path": target_path},
        )
    except OSError:
        return ToolResult.failure(
            "WRITE_FILE_FAILED",
            "文件写入或原子替换失败",
            details={"path": target_path},
        )


REGISTER = Tool(
    {
        "type": "function",
        "name": "write",
        "description": "创建或完整替换 UTF-8 文本文件。会自动创建父目录，不支持创建空目录；写入受本地大小上限和原子替换保护。",
        "parameters": {
            "type": "object",
            "properties": {
                "target_path": {
                    "type": "string",
                    "description": "相对工作目录或绝对目标文件路径",
                },
                "content": {
                    "type": "string",
                    "description": "要写入的完整文本内容，允许为空字符串",
                },
                "expected_version": {
                    "type": "string",
                    "description": "可选的 read 返回文件版本；不匹配时拒绝覆盖",
                },
            },
            "required": ["target_path", "content"],
            "additionalProperties": False,
        },
    },
    write,
    PermissionRequirement(PermissionAction.FILE_WRITE, "target_path"),
    argument_parser=parse_write_arguments,
)
