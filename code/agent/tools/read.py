"""读取文本、目录和图片的基础 Tool。"""

import base64
import json
import os
from typing import Any

from permission.types import PermissionAction, PermissionRequirement
from session.ExecutionContext import ExecutionContext
from tools.file_version import file_version
from tools.types import Attachment, Tool, ToolResult, handle_path


DEFAULT_READ_LIMIT = 200
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
IMAGE_MIME_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
}


class FileChangedError(ValueError):
    """cursor 或读取过程发现资源版本已变化。"""


def parse_read_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    """校验并规范化模型提供的 read 参数。"""
    allowed = {"target_path", "cursor", "start_line", "limit"}
    unknown = set(arguments) - allowed
    if unknown:
        raise ValueError(f"read 不支持参数: {', '.join(sorted(unknown))}")

    target_path = arguments.get("target_path")
    if not isinstance(target_path, str) or not target_path.strip():
        raise ValueError("target_path 必须是非空字符串")

    cursor = arguments.get("cursor")
    if cursor is not None and (not isinstance(cursor, str) or not cursor):
        raise ValueError("cursor 必须是非空字符串或 null")
    if cursor is not None and "start_line" in arguments:
        raise ValueError("cursor 和 start_line 不能同时使用")

    start_line = arguments.get("start_line")
    if cursor is not None:
        if start_line is not None:
            raise ValueError("cursor 和 start_line 不能同时使用")
    elif start_line is not None and not _is_positive_int(start_line):
        raise ValueError("start_line 必须是正整数")

    limit = arguments.get("limit", DEFAULT_READ_LIMIT)
    if not _is_positive_int(limit):
        raise ValueError("limit 必须是正整数")

    parsed = {
        "target_path": target_path,
        "cursor": cursor,
    }
    if start_line is not None:
        parsed["start_line"] = start_line
    if "limit" in arguments:
        parsed["limit"] = limit
    return parsed


def read(
    ctx: ExecutionContext,
    target_path: str,
    *,
    cursor: str | None = None,
    start_line: int | None = None,
    limit: int = DEFAULT_READ_LIMIT,
) -> ToolResult:
    """读取文本文件、目录或图片；文本以本地字符上限分页。"""
    try:
        arguments = parse_read_arguments(
            {
                "target_path": target_path,
                "cursor": cursor,
                **({"start_line": start_line} if start_line is not None else {}),
                **({"limit": limit} if limit != DEFAULT_READ_LIMIT else {}),
            }
        )
    except (TypeError, ValueError) as error:
        return ToolResult.failure("INVALID_ARGUMENTS", str(error), retryable=True)

    path = handle_path(ctx, arguments["target_path"])
    if not os.path.exists(path):
        if arguments["cursor"] is not None:
            return ToolResult.failure(
                "FILE_CHANGED",
                "文件已变化，请重新读取",
                retryable=True,
            )
        return ToolResult.failure(
            "PATH_NOT_FOUND",
            "目标路径不存在",
            details={"path": path},
        )
    if os.path.isfile(path):
        if _is_image(path):
            return _read_image(ctx, path, arguments)
        return _read_text(ctx, path, arguments)
    if os.path.isdir(path):
        return _read_directory(ctx, path, arguments)
    return ToolResult.failure(
        "UNSUPPORTED_FILE_TYPE",
        "仅支持读取文本文件、目录和图片",
        details={"path": path},
    )


def _read_text(
    ctx: ExecutionContext,
    path: str,
    arguments: dict[str, Any],
) -> ToolResult:
    try:
        version = file_version(path)
        state = _text_read_state(path, version, arguments)
    except FileChangedError:
        return ToolResult.failure(
            "FILE_CHANGED",
            "文件已变化，请重新读取",
            retryable=True,
        )
    except ValueError as error:
        return ToolResult.failure("INVALID_CURSOR", str(error), retryable=True)
    except OSError:
        return ToolResult.failure("READ_FILE_FAILED", "读取文件失败", retryable=True)

    effective_limit = min(arguments.get("limit", DEFAULT_READ_LIMIT), ctx.max_read_lines)
    chunks: list[str] = []
    segment_count = 0
    last_line: int | None = None
    current_line = state["line"]

    try:
        with open(path, "r", encoding="utf-8-sig", newline="") as file:
            file.seek(state["position"])
            if arguments["cursor"] is None:
                _skip_to_line(file, current_line)

            while segment_count < effective_limit:
                remaining = ctx.max_tool_call_length - sum(map(len, chunks))
                if remaining <= 0:
                    break
                part = file.readline(remaining)
                if not part:
                    break
                if "\x00" in part:
                    return ToolResult.failure(
                        "UNSUPPORTED_FILE_TYPE",
                        "目标不是可读取的文本文件",
                        details={"path": path},
                    )
                chunks.append(part)
                segment_count += 1
                last_line = current_line
                if _ends_line(part):
                    current_line += 1

            position = file.tell()
            has_more = _has_more(file, position)
    except UnicodeDecodeError:
        return ToolResult.failure(
            "UNSUPPORTED_TEXT_ENCODING",
            "仅支持 UTF-8 文本文件",
            details={"path": path},
        )
    except OSError:
        return ToolResult.failure("READ_FILE_FAILED", "读取文件失败", retryable=True)

    try:
        if file_version(path) != version:
            return ToolResult.failure(
                "FILE_CHANGED",
                "文件在读取过程中发生变化，请重新读取",
                retryable=True,
            )
    except OSError:
        return ToolResult.failure(
            "FILE_CHANGED",
            "文件在读取过程中发生变化，请重新读取",
            retryable=True,
        )

    content = "".join(chunks)
    truncated = has_more
    reason = None
    if truncated:
        reason = "max_chars" if len(content) >= ctx.max_tool_call_length else "max_lines"
    continues_line = bool(truncated and content and not _ends_line(content))
    next_cursor = (
        _encode_cursor(
            path=path,
            version=version,
            position=position,
            line=current_line,
            continues_line=continues_line,
        )
        if truncated
        else None
    )
    return ToolResult.success(
        {
            "type": "text",
            "path": path,
            "content": content,
            "start_line": state["line"],
            "end_line": last_line,
            "returned_line_segments": segment_count,
            "effective_limit": effective_limit,
            "truncated": truncated,
            "truncation_reason": reason,
            "continues_line": continues_line,
            "next_cursor": next_cursor,
            "version": version,
        }
    )


def _text_read_state(
    path: str,
    version: str,
    arguments: dict[str, Any],
) -> dict[str, int]:
    cursor = arguments["cursor"]
    if cursor is None:
        return {"position": 0, "line": arguments.get("start_line", 1)}
    payload = _decode_token(cursor)
    if payload.get("kind") != "text" or payload.get("path") != path:
        raise ValueError("cursor 不属于当前文本文件")
    if payload.get("version") != version:
        raise FileChangedError("文件已变化，请重新读取")
    position = payload.get("position")
    line = payload.get("line")
    if not _is_non_negative_int(position) or not _is_positive_int(line):
        raise ValueError("cursor 位置无效")
    return {"position": position, "line": line}


def _skip_to_line(file, start_line: int) -> None:
    """以固定块跳过前置行，避免超长单行被整体加载。"""
    lines_to_skip = start_line - 1
    while lines_to_skip:
        part = file.readline(8192)
        if not part:
            return
        if _ends_line(part):
            lines_to_skip -= 1


def _has_more(file, position: int) -> bool:
    probe = file.read(1)
    file.seek(position)
    return bool(probe)


def _ends_line(text: str) -> bool:
    return text.endswith("\n") or text.endswith("\r")


def _read_directory(
    ctx: ExecutionContext,
    path: str,
    arguments: dict[str, Any],
) -> ToolResult:
    """以稳定顺序分页读取目录，并在续读前验证目录版本。"""
    if "start_line" in arguments:
        return ToolResult.failure(
            "INVALID_ARGUMENTS",
            "目录读取不支持 start_line",
        )

    try:
        version = file_version(path)
        with os.scandir(path) as scanned:
            entries = sorted(
                scanned,
                key=lambda entry: (entry.name.casefold(), entry.name),
            )
    except OSError:
        return ToolResult.failure("READ_FILE_FAILED", "读取目录失败", retryable=True)

    try:
        start_index = _directory_read_index(path, version, arguments["cursor"])
    except FileChangedError:
        return ToolResult.failure(
            "FILE_CHANGED",
            "目录已变化，请重新读取",
            retryable=True,
        )
    except ValueError as error:
        return ToolResult.failure("INVALID_CURSOR", str(error), retryable=True)

    effective_limit = min(
        arguments.get("limit", DEFAULT_READ_LIMIT),
        ctx.max_directory_entries,
    )
    page: list[dict[str, str]] = []
    entry_chars = 0
    index = start_index
    while index < len(entries) and len(page) < effective_limit:
        data = _directory_entry(entries[index])
        serialized_length = len(json.dumps(data, ensure_ascii=False, separators=(",", ":")))
        if entry_chars + serialized_length > ctx.max_tool_call_length:
            if not page:
                return ToolResult.failure(
                    "FILE_TOO_LARGE",
                    "单个目录条目超过本地输出上限",
                    details={"path": path},
                )
            break
        page.append(data)
        entry_chars += serialized_length
        index += 1

    try:
        if file_version(path) != version:
            return ToolResult.failure(
                "FILE_CHANGED",
                "目录在读取过程中发生变化，请重新读取",
                retryable=True,
            )
    except OSError:
        return ToolResult.failure(
            "FILE_CHANGED",
            "目录在读取过程中发生变化，请重新读取",
            retryable=True,
        )

    truncated = index < len(entries)
    reason = None
    if truncated:
        reason = "max_entries" if len(page) >= effective_limit else "max_chars"
    next_cursor = (
        _encode_directory_cursor(path, version, index) if truncated else None
    )
    return ToolResult.success(
        {
            "type": "directory",
            "path": path,
            "entries": page,
            "returned": len(page),
            "effective_limit": effective_limit,
            "truncated": truncated,
            "truncation_reason": reason,
            "next_cursor": next_cursor,
            "version": version,
        }
    )


def _read_image(
    ctx: ExecutionContext,
    path: str,
    arguments: dict[str, Any],
) -> ToolResult:
    """校验图片大小与签名后，才将二进制内容作为附件返回。"""
    if arguments["cursor"] is not None or "start_line" in arguments or "limit" in arguments:
        return ToolResult.failure(
            "INVALID_ARGUMENTS",
            "图片读取不支持 cursor、start_line 或 limit",
        )

    extension = os.path.splitext(path)[1].lower()
    mime_type = IMAGE_MIME_TYPES.get(extension)
    if mime_type is None:
        return ToolResult.failure("UNSUPPORTED_IMAGE_FORMAT", "图片格式未知", details={"path": path})
    try:
        version = file_version(path)
        size_bytes = os.stat(path).st_size
    except OSError:
        return ToolResult.failure("READ_FILE_FAILED", "读取图片失败", retryable=True)
    if size_bytes > ctx.max_image_bytes:
        return ToolResult.failure(
            "FILE_TOO_LARGE",
            "图片超过本地读取大小上限",
            details={"path": path, "max_image_bytes": ctx.max_image_bytes},
        )
    try:
        with open(path, "rb") as file:
            signature = file.read(12)
            if not _matches_image_signature(extension, signature):
                return ToolResult.failure(
                    "UNSUPPORTED_IMAGE_FORMAT",
                    "图片扩展名与文件内容不匹配",
                    details={"path": path},
                )
            file.seek(0)
            image_bytes = file.read()
    except OSError:
        return ToolResult.failure("READ_FILE_FAILED", "读取图片失败", retryable=True)
    try:
        if file_version(path) != version:
            return ToolResult.failure(
                "FILE_CHANGED",
                "图片在读取过程中发生变化，请重新读取",
                retryable=True,
            )
    except OSError:
        return ToolResult.failure(
            "FILE_CHANGED",
            "图片在读取过程中发生变化，请重新读取",
            retryable=True,
        )
    return ToolResult.success(
        data={
            "type": "image",
            "path": path,
            "mime_type": mime_type,
            "size_bytes": size_bytes,
            "version": version,
        },
        attachments=[Attachment(mime_type, "bytes", image_bytes)],
    )


def _directory_read_index(path: str, version: str, cursor: str | None) -> int:
    if cursor is None:
        return 0
    payload = _decode_token(cursor)
    if payload.get("kind") != "directory" or payload.get("path") != path:
        raise ValueError("cursor 不属于当前目录")
    if payload.get("version") != version:
        raise FileChangedError("目录已变化，请重新读取")
    index = payload.get("index")
    if not _is_non_negative_int(index):
        raise ValueError("cursor 位置无效")
    return index


def _encode_directory_cursor(path: str, version: str, index: int) -> str:
    return _encode_token(
        {
            "v": 1,
            "kind": "directory",
            "path": path,
            "version": version,
            "index": index,
        }
    )


def _directory_entry(entry: os.DirEntry[str]) -> dict[str, str]:
    if entry.is_symlink():
        entry_type = "symlink"
    elif entry.is_dir(follow_symlinks=False):
        entry_type = "directory"
    elif entry.is_file(follow_symlinks=False):
        entry_type = "file"
    else:
        entry_type = "other"
    return {"type": entry_type, "name": entry.name, "path": entry.path}


def _matches_image_signature(extension: str, signature: bytes) -> bool:
    if extension == ".png":
        return signature.startswith(b"\x89PNG\r\n\x1a\n")
    if extension in {".jpg", ".jpeg"}:
        return signature.startswith(b"\xff\xd8\xff")
    if extension == ".gif":
        return signature.startswith((b"GIF87a", b"GIF89a"))
    if extension == ".webp":
        return signature.startswith(b"RIFF") and signature[8:12] == b"WEBP"
    if extension == ".bmp":
        return signature.startswith(b"BM")
    return False


def _is_image(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in IMAGE_EXTENSIONS


def _encode_cursor(
    *,
    path: str,
    version: str,
    position: int,
    line: int,
    continues_line: bool,
) -> str:
    return _encode_token(
        {
            "v": 1,
            "kind": "text",
            "path": path,
            "version": version,
            "position": position,
            "line": line,
            "continues_line": continues_line,
        }
    )


def _encode_token(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(encoded).decode("ascii").rstrip("=")


def _decode_token(token: str) -> dict[str, Any]:
    try:
        padded = token + "=" * (-len(token) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
    except (UnicodeError, ValueError, json.JSONDecodeError) as error:
        raise ValueError("cursor 无效") from error
    if not isinstance(payload, dict) or payload.get("v") != 1:
        raise ValueError("cursor 无效")
    return payload


def _is_positive_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _is_non_negative_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


REGISTER = Tool(
    {
        "type": "function",
        "name": "read",
        "description": "读取 UTF-8 文本、目录或图片。文本按行读取，但始终受本地字符上限限制；结果中的 cursor 可用于继续读取。",
        "parameters": {
            "type": "object",
            "properties": {
                "target_path": {
                    "type": "string",
                    "description": "相对工作目录或绝对目标路径",
                },
                "cursor": {
                    "type": ["string", "null"],
                    "description": "上一次 read 返回的 next_cursor；与 start_line 不能同时传递",
                },
                "start_line": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "首次读取文本时的起始行，默认从第 1 行开始",
                },
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "文本最多读取的行片段数或目录最多读取的条目数，实际值受本地上限限制",
                },
            },
            "required": ["target_path"],
            "additionalProperties": False,
        },
    },
    read,
    PermissionRequirement(PermissionAction.FILE_READ, "target_path"),
    argument_parser=parse_read_arguments,
)
