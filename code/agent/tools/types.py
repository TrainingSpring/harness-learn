import os
from dataclasses import dataclass
from typing import Any, Callable

from runtime.ExecutionContext import ExecutionContext


@dataclass
class Tool:
    schema:dict
    function:Callable


@dataclass
class ToolOutput:
    """工具的业务结果，以及可选的 Responses 多模态内容。"""
    value: Any = None
    content: list[dict] | None = None


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
