"""Runtime 对宿主暴露的事件和暂停状态。"""

from dataclasses import dataclass
from typing import Literal

from head.types import LLMResponse
from permission.types import PermissionRequest, PermissionScope
from tools.types import PreparedToolCall


@dataclass(frozen=True)
class PermissionRequiredEvent:
    """通知宿主暂停并向用户询问权限的运行时事件。"""

    type: Literal["permission_required"]
    request: PermissionRequest
    available_scopes: tuple[PermissionScope, ...] = (
        PermissionScope.ONCE,
        PermissionScope.SESSION,
    )


@dataclass(frozen=True)
class PendingToolCall:
    """Runtime 暂停时保存的完整工具调用。"""

    call: PreparedToolCall
    command: str | None


RuntimeEvent = LLMResponse | PermissionRequiredEvent
