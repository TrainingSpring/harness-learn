"""MCP logging 能力的协议边界。"""

from __future__ import annotations

from typing import Any, Mapping

from .errors import McpProtocolError
from .events import McpLogEvent


LOG_LEVELS = frozenset({
    "debug", "info", "notice", "warning", "error", "critical", "alert", "emergency",
})
_MAX_LOG_TEXT = 8192
_SENSITIVE_KEYS = frozenset({"authorization", "api_key", "password", "secret", "token"})


def _sanitize(value: Any, *, depth: int = 0) -> Any:
    if depth > 4:
        return "[TRUNCATED]"
    if isinstance(value, str):
        return value if len(value) <= _MAX_LOG_TEXT else value[:_MAX_LOG_TEXT] + "...[TRUNCATED]"
    if isinstance(value, Mapping):
        return {
            str(key): "[REDACTED]" if str(key).casefold() in _SENSITIVE_KEYS else _sanitize(item, depth=depth + 1)
            for key, item in list(value.items())[:128]
        }
    if isinstance(value, list):
        return [_sanitize(item, depth=depth + 1) for item in value[:128]]
    return value


def parse_log_event(value: object) -> McpLogEvent:
    if not isinstance(value, Mapping):
        raise McpProtocolError("MCP logging notification 参数必须是对象")
    level = value.get("level", "info")
    logger = value.get("logger")
    if level not in LOG_LEVELS:
        raise McpProtocolError("MCP logging level 无效")
    if logger is not None and not isinstance(logger, str):
        raise McpProtocolError("MCP logging logger 必须是字符串")
    return McpLogEvent(level=level, data=_sanitize(value.get("data")), logger=logger)


def validate_logging_result(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise McpProtocolError("MCP logging/setLevel 结果必须是对象")
    return dict(value)
