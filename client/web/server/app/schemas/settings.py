"""设置页面的查询和创建 DTO。"""

from typing import Any, Literal

from pydantic import Field

from .common import ApiModel


class LLMProfileSummary(ApiModel):
    """不含 API Key 的 LLM 配置摘要。"""

    id: str
    name: str
    provider: str
    base_url: str | None
    model: str
    has_api_key: bool
    options: dict[str, Any]


class CreateLLMProfileRequest(ApiModel):
    """创建 LLM 配置时提交并持久化的连接参数。"""

    name: str = Field(min_length=1)
    provider: Literal["openai"]
    base_url: str | None = None
    model: str = Field(min_length=1)
    api_key: str = Field(min_length=1)
    options: dict[str, Any] = Field(default_factory=dict)


class UpdateLLMProfileRequest(ApiModel):
    """更新 LLM 配置时提交的字段。

    ``api_key`` 是可选字段，编辑时留空表示沿用数据库中的原密钥。
    """

    name: str = Field(min_length=1)
    provider: Literal["openai"]
    base_url: str | None = None
    model: str = Field(min_length=1)
    api_key: str | None = None
    options: dict[str, Any] = Field(default_factory=dict)


class ModelDiscoveryRequest(ApiModel):
    """根据尚未保存的表单连接参数读取模型列表。"""

    provider: Literal["openai"]
    base_url: str | None = None
    api_key: str = Field(min_length=1)


class ModelListResponse(ApiModel):
    """服务商返回的可选模型 ID。"""

    models: list[str]


class ToolSummary(ApiModel):
    """供设置页展示的受信任工具元数据。"""

    name: str
    description: str
    input_schema: dict[str, Any]
    permission_action: str
