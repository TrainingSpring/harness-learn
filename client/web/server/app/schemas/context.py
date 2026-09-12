"""会话业务时间线的公开 DTO。"""

from typing import Any

from .common import ApiModel


class ContextItemResponse(ApiModel):
    """一条持久化消息或工具执行事件。"""

    id: str
    sequence_no: int
    kind: str
    author_agent_id: str | None
    visibility: str
    payload: dict[str, Any]
    call_id: str | None
    caused_by_item_id: str | None
    created_at: str | None

