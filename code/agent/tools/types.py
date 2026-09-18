import os
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Literal

from permission.types import PermissionRequest, PermissionRequirement
from session.ExecutionContext import ExecutionContext


@dataclass
class ToolError:
    """工具失败时返回给调用方和模型的稳定错误信息。"""
    code: str
    message: str
    retryable: bool = False
    details: dict[str, Any] | None = None


class ToolCallPreparationError(Exception):
    """工具调用准备失败时携带稳定 ToolError 的内部异常。

    解析参数和构造权限请求发生在工具执行前，尚未有 ToolResult 可返回；
    Runtime 捕获此异常后会将其中的 ToolError 转换为 ToolResult.failure。
    """

    def __init__(self, error: ToolError):
        """保存供 Runtime 转换的结构化错误。"""
        super().__init__(error.message)
        self.error = error


@dataclass
class Attachment:
    """通用媒体附件，不包含模型厂商的协议字段。

    source_kind 决定 source 的类型：bytes 表示本地二进制内容，url
    表示可直接引用的远程资源地址。Base64 只在协议适配阶段生成。
    """
    media_type: str
    source_kind: Literal["bytes", "url"]
    source: bytes | str
    filename: str | None = None

    def __post_init__(self):
        if not re.fullmatch(r"[^/\s]+/[^/\s]+", self.media_type):
            raise ValueError("media_type 必须是合法的 MIME 类型")
        if self.source_kind == "bytes" and not isinstance(self.source, bytes):
            raise TypeError("bytes 来源必须传入 bytes")
        if self.source_kind == "url" and not isinstance(self.source, str):
            raise TypeError("url 来源必须传入字符串")
        if self.source_kind not in ("bytes", "url"):
            raise ValueError(f"未知的附件来源类型: {self.source_kind}")


@dataclass
class ToolResult:
    """所有工具统一返回的内部结果契约。

    ToolResult 只表达工具执行的业务语义。Responses 等模型协议的
    序列化由 Tools 负责，避免工具实现依赖某个模型厂商的字段。
    """
    status: Literal["ok", "error"]
    data: Any = None
    attachments: list[Attachment] = field(default_factory=list)
    error: ToolError | None = None

    def __post_init__(self):
        # 在创建结果时立即拦截不完整或自相矛盾的工具结果。
        if self.status not in ("ok", "error"):
            raise ValueError(f"未知的 ToolResult 状态: {self.status}")
        if self.status == "ok" and self.error is not None:
            raise ValueError("成功的 ToolResult 不能包含 error")
        if self.status == "error" and self.error is None:
            raise ValueError("失败的 ToolResult 必须包含 error")
        if self.status == "error" and self.data is not None:
            raise ValueError("失败的 ToolResult 不能包含 data")
        if not all(isinstance(item, Attachment) for item in self.attachments):
            raise TypeError("attachments 必须全部是 Attachment")

    @classmethod
    def success(
        cls,
        data: Any = None,
        attachments: list[Attachment] | None = None,
    ) -> "ToolResult":
        """创建成功结果；附件与业务数据一同描述本次工具调用。"""
        return cls(status="ok", data=data, attachments=list(attachments or []))

    @classmethod
    def failure(
        cls,
        code: str,
        message: str,
        retryable: bool = False,
        details: dict[str, Any] | None = None,
    ) -> "ToolResult":
        """创建失败结果；失败结果不携带可能被误用的业务数据。"""
        return cls(
            status="error",
            error=ToolError(code, message, retryable, details),
        )


@dataclass
class Tool:
    """工具定义及其执行契约。

    Attributes:
        schema: 传给模型的工具 JSON Schema。
        function: 实际执行函数，签名为 ``function(ctx, **arguments)``，且
            必须返回 ToolResult。
        permission: 工具静态声明的权限需求；它不是用户已授予的规则。
    """
    schema: dict
    function: Callable[..., ToolResult]
    permission: PermissionRequirement


@dataclass(frozen=True)
class PreparedToolCall:
    """经过解析、查找和权限请求构造后的待执行工具调用。

    Attributes:
        call_id: 模型 function_call 的标识。
        tool_name: 已注册工具名称。
        tool: 已解析出的 Tool 定义。
        arguments: 只解析一次后的 JSON 对象参数。
        permission_request: 根据工具声明和参数生成的实际权限请求。
    """

    call_id: str
    tool_name: str
    tool: Tool
    arguments: dict[str, Any]
    permission_request: PermissionRequest


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
