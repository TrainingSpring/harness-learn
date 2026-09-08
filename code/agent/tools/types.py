import os
from dataclasses import dataclass, field
from typing import Any, Callable, Literal

from runtime.ExecutionContext import ExecutionContext


@dataclass
class ToolError:
    code: str
    message: str
    retryable: bool = False
    details: dict[str, Any] | None = None


@dataclass
class ImageAttachment:
    url: str
    mime_type: str
    detail: str = "auto"


@dataclass
class ToolResult:
    """所有工具统一返回的内部结果契约。"""
    status: Literal["ok", "error"]
    data: Any = None
    attachments: list[ImageAttachment] = field(default_factory=list)
    error: ToolError | None = None

    def __post_init__(self):
        if self.status not in ("ok", "error"):
            raise ValueError(f"未知的 ToolResult 状态: {self.status}")
        if self.status == "ok" and self.error is not None:
            raise ValueError("成功的 ToolResult 不能包含 error")
        if self.status == "error" and self.error is None:
            raise ValueError("失败的 ToolResult 必须包含 error")
        if self.status == "error" and self.data is not None:
            raise ValueError("失败的 ToolResult 不能包含 data")
        if not all(isinstance(item, ImageAttachment) for item in self.attachments):
            raise TypeError("attachments 必须全部是 ImageAttachment")

    @classmethod
    def success(
        cls,
        data: Any = None,
        attachments: list[ImageAttachment] | None = None,
    ) -> "ToolResult":
        return cls(status="ok", data=data, attachments=list(attachments or []))

    @classmethod
    def failure(
        cls,
        code: str,
        message: str,
        retryable: bool = False,
        details: dict[str, Any] | None = None,
    ) -> "ToolResult":
        return cls(
            status="error",
            error=ToolError(code, message, retryable, details),
        )


@dataclass
class Tool:
    schema:dict
    function:Callable[..., ToolResult]


def handle_path(ctx:ExecutionContext,target_path:str):
    """
    处理路径,
    如果是相对路径，则返回绝对路径，否则返回原路径
    :param ctx: ExecutionContext
    :param target_path: 目标路径
    """
    if not os.path.isabs(target_path):
        if os.name == "nt" and target_path.startswith("/"):
            target_path = target_path[1:]
        return os.path.join(ctx.workspace, target_path)
    return target_path
