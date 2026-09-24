"""基于已读取文件版本进行受限文本替换的 Tool。"""

import os
from typing import Any

from permission.types import PermissionAction, PermissionRequirement
from session.ExecutionContext import ExecutionContext
from tools.file_mutation import FileMutationError, commit_file
from tools.file_version import file_version
from tools.types import Tool, ToolResult, handle_path


class EditApplicationError(ValueError):
    """内存文本变换不能应用时携带稳定错误码。"""

    def __init__(self, code: str, edit_index: int, match_count: int = 0):
        super().__init__(code)
        self.code = code
        self.edit_index = edit_index
        self.match_count = match_count


def parse_edit_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    """严格校验 Edit 参数，使权限检查只接收可信的路径参数。"""
    allowed = {"target_path", "expected_version", "edits"}
    unknown = set(arguments) - allowed
    if unknown:
        raise ValueError(f"edit 不支持参数: {', '.join(sorted(unknown))}")

    target_path = arguments.get("target_path")
    if not isinstance(target_path, str) or not target_path.strip():
        raise ValueError("target_path 必须是非空字符串")

    expected_version = arguments.get("expected_version")
    if not isinstance(expected_version, str) or not expected_version:
        raise ValueError("expected_version 必须是非空字符串")

    edits = arguments.get("edits")
    if not isinstance(edits, list) or not edits:
        raise ValueError("edits 必须是非空数组")

    parsed_edits: list[dict[str, Any]] = []
    allowed_edit_fields = {"old_text", "new_text", "replace_all"}
    for index, item in enumerate(edits):
        if not isinstance(item, dict):
            raise ValueError(f"edits[{index}] 必须是对象")
        item_unknown = set(item) - allowed_edit_fields
        if item_unknown:
            raise ValueError(
                f"edits[{index}] 不支持参数: {', '.join(sorted(item_unknown))}"
            )
        if "old_text" not in item or not isinstance(item["old_text"], str) or not item["old_text"]:
            raise ValueError(f"edits[{index}].old_text 必须是非空字符串")
        if "new_text" not in item or not isinstance(item["new_text"], str):
            raise ValueError(f"edits[{index}].new_text 必须是字符串")
        replace_all = item.get("replace_all", False)
        if not isinstance(replace_all, bool):
            raise ValueError(f"edits[{index}].replace_all 必须是布尔值")
        parsed_edits.append(
            {
                "old_text": item["old_text"],
                "new_text": item["new_text"],
                "replace_all": replace_all,
            }
        )

    return {
        "target_path": target_path,
        "expected_version": expected_version,
        "edits": parsed_edits,
    }


def edit(
    ctx: ExecutionContext,
    target_path: str,
    expected_version: str,
    edits: list[dict[str, Any]],
) -> ToolResult:
    """在内存中验证全部替换后，基于当前版本将文本写回既有文件。"""
    try:
        arguments = parse_edit_arguments(
            {
                "target_path": target_path,
                "expected_version": expected_version,
                "edits": edits,
            }
        )
    except (TypeError, ValueError) as error:
        return ToolResult.failure("INVALID_ARGUMENTS", str(error), retryable=True)

    if len(arguments["edits"]) > ctx.max_edit_operations:
        return ToolResult.failure(
            "INVALID_ARGUMENTS",
            "edits 超过单次调用上限",
            retryable=True,
            details={"max_edit_operations": ctx.max_edit_operations},
        )

    path = handle_path(ctx, arguments["target_path"])
    if os.path.isdir(path):
        return ToolResult.failure(
            "TARGET_IS_DIRECTORY",
            "目标路径是目录，不能编辑",
            retryable=True,
            details={"path": path},
        )
    if not os.path.isfile(path):
        return ToolResult.failure(
            "FILE_NOT_FOUND",
            "目标文件不存在或不是普通文件",
            retryable=True,
            details={"path": path},
        )

    try:
        source_size = os.stat(path).st_size
    except OSError:
        return ToolResult.failure(
            "EDIT_FILE_FAILED", "读取目标文件失败", retryable=True, details={"path": path}
        )
    if source_size > ctx.max_edit_source_bytes:
        return ToolResult.failure(
            "FILE_TOO_LARGE",
            "源文件超过 Edit 本地字节上限",
            retryable=True,
            details={"max_edit_source_bytes": ctx.max_edit_source_bytes},
        )

    try:
        initial_version = file_version(path)
    except OSError:
        return ToolResult.failure(
            "FILE_CHANGED", "目标文件已变化，请重新读取后再编辑", retryable=True
        )
    if initial_version != arguments["expected_version"]:
        return ToolResult.failure(
            "FILE_CHANGED",
            "目标文件已变化，请重新读取后再编辑",
            retryable=True,
            details={"path": path},
        )

    try:
        source = _read_utf8_source(path)
    except UnicodeDecodeError:
        return ToolResult.failure(
            "UNSUPPORTED_TEXT_ENCODING",
            "仅支持 UTF-8 文本文件",
            details={"path": path},
        )
    except ValueError:
        return ToolResult.failure(
            "UNSUPPORTED_FILE_TYPE",
            "目标不是可编辑的文本文件",
            details={"path": path},
        )
    except OSError:
        return ToolResult.failure(
            "EDIT_FILE_FAILED", "读取目标文件失败", retryable=True, details={"path": path}
        )

    try:
        if file_version(path) != initial_version:
            return ToolResult.failure(
                "FILE_CHANGED", "目标文件已变化，请重新读取后再编辑", retryable=True
            )
    except OSError:
        return ToolResult.failure(
            "FILE_CHANGED", "目标文件已变化，请重新读取后再编辑", retryable=True
        )

    try:
        content, replacement_count = _apply_edits(source, arguments["edits"])
    except EditApplicationError as error:
        return ToolResult.failure(
            error.code,
            "指定文本未找到" if error.code == "EDIT_TEXT_NOT_FOUND" else "指定文本匹配不唯一",
            retryable=True,
            details={"path": path, "edit_index": error.edit_index, "match_count": error.match_count},
        )

    encoded_content = content.encode("utf-8")
    if len(encoded_content) > ctx.max_write_bytes:
        return ToolResult.failure(
            "FILE_TOO_LARGE",
            "编辑后的内容超过本地字节上限",
            retryable=True,
            details={"max_write_bytes": ctx.max_write_bytes},
        )

    try:
        mutation = commit_file(
            path,
            encoded_content,
            expected_version=initial_version,
            lock_timeout_seconds=ctx.file_mutation_lock_timeout_seconds,
        )
    except FileMutationError as error:
        if error.code == "FILE_CHANGED":
            return ToolResult.failure(
                "FILE_CHANGED", "目标文件已变化，请重新读取后再编辑", retryable=True
            )
        if error.code == "FILE_BUSY":
            return ToolResult.failure(
                "FILE_BUSY",
                "目标文件正在被另一项提交处理，请稍后重试",
                retryable=True,
                details={"path": path},
            )
        return ToolResult.failure(
            "EDIT_FILE_FAILED", "编辑文件失败", retryable=True, details={"path": path}
        )

    return ToolResult.success(
        {
            "operation": "edited",
            "path": path,
            "edit_count": len(arguments["edits"]),
            "replacement_count": replacement_count,
            "bytes_written": len(encoded_content),
            "version": mutation["version"],
            "precondition_checked": True,
        }
    )


def _read_utf8_source(path: str) -> str:
    with open(path, "rb") as source_file:
        source = source_file.read()
    content = source.decode("utf-8")
    if "\x00" in content:
        raise ValueError("NUL")
    return content


def _apply_edits(content: str, edits: list[dict[str, Any]]) -> tuple[str, int]:
    replacement_count = 0
    for index, item in enumerate(edits):
        old_text = item["old_text"]
        match_count = content.count(old_text)
        if match_count == 0:
            raise EditApplicationError("EDIT_TEXT_NOT_FOUND", index)
        if not item["replace_all"] and match_count != 1:
            raise EditApplicationError("EDIT_TEXT_AMBIGUOUS", index, match_count)
        replacement_count += match_count if item["replace_all"] else 1
        content = content.replace(old_text, item["new_text"], -1 if item["replace_all"] else 1)
    return content, replacement_count


REGISTER = Tool(
    {
        "type": "function",
        "name": "edit",
        "description": "基于 read 返回的 version 对已有 UTF-8 文本文件做局部替换。必须先读取目标文件，再传入 expected_version；不支持创建文件。",
        "parameters": {
            "type": "object",
            "properties": {
                "target_path": {
                    "type": "string",
                    "description": "相对工作目录或绝对目标文件路径",
                },
                "expected_version": {
                    "type": "string",
                    "description": "read 返回的当前文件 version；不匹配时拒绝编辑",
                },
                "edits": {
                    "type": "array",
                    "minItems": 1,
                    "items": {
                        "type": "object",
                        "properties": {
                            "old_text": {"type": "string", "minLength": 1},
                            "new_text": {"type": "string"},
                            "replace_all": {"type": "boolean", "default": False},
                        },
                        "required": ["old_text", "new_text"],
                        "additionalProperties": False,
                    },
                    "description": "按数组顺序执行的文本替换列表",
                },
            },
            "required": ["target_path", "expected_version", "edits"],
            "additionalProperties": False,
        },
    },
    edit,
    PermissionRequirement(PermissionAction.FILE_WRITE, "target_path"),
    argument_parser=parse_edit_arguments,
)
