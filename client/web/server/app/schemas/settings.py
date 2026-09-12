"""只读设置页面 DTO。"""

from typing import Any

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


class ToolSummary(ApiModel):
    """供设置页展示的受信任工具元数据。"""

    name: str
    description: str
    input_schema: dict[str, Any]
    permission_action: str

