"""跨 API 资源共享的基础 DTO。"""

from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict


def to_camel(value: str) -> str:
    """把内部 snake_case 字段名转换为 camelCase。"""
    head, *tail = value.split("_")
    return head + "".join(part.capitalize() for part in tail)


class ApiModel(BaseModel):
    """统一启用 camelCase 序列化的 API 模型基类。"""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class Pagination(ApiModel):
    """列表接口的偏移分页信息。"""

    limit: int
    offset: int
    has_more: bool


ItemT = TypeVar("ItemT")


class ListResponse(ApiModel, Generic[ItemT]):
    """统一的分页列表响应。"""

    items: list[ItemT]
    pagination: Pagination

