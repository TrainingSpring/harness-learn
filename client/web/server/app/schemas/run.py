"""对话运行和权限确认的 Web 契约。"""

from typing import Any, Literal

from pydantic import Field, field_validator

from .common import ApiModel


class SendMessageRequest(ApiModel):
    """开始一次对话运行的用户文本。"""

    text: str = Field(min_length=1, max_length=100_000)

    @field_validator("text")
    @classmethod
    def reject_blank_text(cls, value: str) -> str:
        """拒绝仅包含空白字符的消息。"""
        if not value.strip():
            raise ValueError("消息文本不能为空")
        return value


class PermissionDecisionRequest(ApiModel):
    """浏览器恢复 pending Runtime 所需的最小确认数据。"""

    call_id: str = Field(min_length=1, max_length=200)
    decision: Literal["allow", "deny"]
    scope: Literal["once", "session"]


class ServerEvent(ApiModel):
    """SSE data 字段统一承载的判别式事件。"""

    type: str
    run_id: str
    session_id: str
    data: dict[str, Any]
