"""设置页面的查询和创建 DTO。"""

from typing import Any

from pydantic import Field

from .common import ApiModel


class LLMProfileSummary(ApiModel):
    """不含凭据引用和值的 LLM 配置摘要。"""

    id: str
    name: str
    provider: str
    base_url: str | None
    model: str
    has_credential: bool
    options: dict[str, Any]


class CreateLLMProfileRequest(ApiModel):
    """创建 LLM 配置时提交的连接参数。

    credential_ref 只接受凭据引用，例如 ``env:OPENAI_API_KEY``；实际密钥
    不应通过这个 Web 接口传输或写入数据库。
    """

    name: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    base_url: str | None = None
    model: str = Field(min_length=1)
    credential_ref: str = Field(min_length=1)
    options: dict[str, Any] = Field(default_factory=dict)


class ToolSummary(ApiModel):
    """供设置页展示的受信任工具元数据。"""

    name: str
    description: str
    input_schema: dict[str, Any]
    permission_action: str
