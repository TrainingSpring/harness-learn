"""Agent 发现和创建接口 DTO。"""

from typing import Annotated

from pydantic import ConfigDict, Field, field_validator

from .common import ApiModel


class AgentSummary(ApiModel):
    """角色列表和会话选择需要的公开 Agent 信息。"""

    id: str
    name: str
    description: str
    personality: str
    expertise: list[str]
    tools: list[str]
    is_enabled: bool


class CreateAgentRequest(ApiModel):
    """创建角色时由浏览器提交的配置。

    ID 不属于请求体，由服务端生成，避免客户端伪造或覆盖已有角色。
    """

    name: str = Field(min_length=1)
    description: str = ""
    personality: str = ""
    expertise: list[str] = Field(default_factory=list)
    llm_profile_id: str
    tools: list[str] = Field(default_factory=list)
    permission_mode: str = "BUILD"
    is_enabled: bool = True


class AgentProfileSuggestionRequest(ApiModel):
    """请求 AI 根据一段原始描述生成角色草案。"""

    description: str = Field(min_length=1, max_length=4000)
    llm_profile_id: str

    @field_validator("description")
    @classmethod
    def validate_description(cls, value: str) -> str:
        """去除首尾空白，并拒绝只包含空白的描述。"""
        stripped = value.strip()
        if not stripped:
            raise ValueError("description 不能为空")
        return stripped


SuggestionExpertise = Annotated[str, Field(min_length=1, max_length=80)]


class AgentProfileSuggestion(ApiModel):
    """AI 返回并经过服务端严格校验的角色草案。"""

    # 继承 ApiModel 的 camelCase 序列化配置，只在此处补充严格拒绝未知字段。
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=1, max_length=1000)
    personality: str = Field(min_length=1, max_length=500)
    expertise: list[SuggestionExpertise] = Field(min_length=1, max_length=12)


class AgentDetail(AgentSummary):
    """角色详情额外公开的运行配置引用。"""

    llm_profile_id: str
    permission_mode: str
