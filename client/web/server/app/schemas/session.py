"""固定 Agent 1v1 会话的公开 DTO。"""

from typing import Literal

from pydantic import Field

from .common import ApiModel
from .context import ContextItemResponse


class CreateDirectSessionRequest(ApiModel):
    """首期 Web 客户端创建会话所需的输入。"""

    mode: Literal["DIRECT"]
    agent_id: str
    title: str | None = Field(default=None, max_length=200)


class SessionAgentSummary(ApiModel):
    """会话固定 Agent 的最小展示信息。"""

    id: str
    name: str


class SessionSummary(ApiModel):
    """历史侧栏和会话顶部共享的聚合摘要。"""

    id: str
    title: str | None
    conversation_mode: str
    status: str
    agent: SessionAgentSummary
    last_message: str | None
    last_sequence_no: int | None
    created_at: str | None
    updated_at: str | None


class SessionDetail(SessionSummary):
    """会话摘要及其完整持久化时间线。"""

    messages: list[ContextItemResponse]


class ContextItemList(ApiModel):
    """按 sequenceNo 增量返回的上下文项列表。"""

    items: list[ContextItemResponse]

