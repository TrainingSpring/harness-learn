"""MCP 日志、进度和资源更新通知的内部事件模型。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class McpLogEvent:
    level: str
    data: Any
    logger: str | None = None


@dataclass(frozen=True)
class McpProgressEvent:
    progress_token: str | int
    progress: float | int
    total: float | int | None = None
    message: str | None = None


@dataclass(frozen=True)
class McpResourceUpdatedEvent:
    uri: str
