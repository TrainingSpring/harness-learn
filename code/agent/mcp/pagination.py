"""MCP list 响应的有界 cursor 分页收集。"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from .errors import McpPaginationError


_MAX_PAGES = 100


def collect_pages(
    request: Callable[[dict[str, str] | None], object],
    *,
    item_field: str,
    max_pages: int = _MAX_PAGES,
) -> tuple[dict[str, Any], ...]:
    """读取所有分页，拒绝重复 cursor、畸形项目和无界结果集。"""
    if not isinstance(max_pages, int) or isinstance(max_pages, bool) or max_pages <= 0:
        raise ValueError("max_pages 必须是正整数")
    cursor: str | None = None
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for _ in range(max_pages):
        page = request(None if cursor is None else {"cursor": cursor})
        if not isinstance(page, Mapping):
            raise McpPaginationError("MCP list 结果必须是对象")
        items = page.get(item_field)
        if not isinstance(items, list) or not all(isinstance(item, Mapping) for item in items):
            raise McpPaginationError(f"MCP list 结果的 {item_field} 必须是对象数组")
        result.extend(dict(item) for item in items)
        next_cursor = page.get("nextCursor")
        if next_cursor is None:
            return tuple(result)
        if not isinstance(next_cursor, str) or not next_cursor:
            raise McpPaginationError("MCP nextCursor 必须是非空字符串或 null")
        if next_cursor in seen:
            raise McpPaginationError("MCP 分页 cursor 重复，已停止读取")
        seen.add(next_cursor)
        cursor = next_cursor
    raise McpPaginationError("MCP 分页超过最大页数")
