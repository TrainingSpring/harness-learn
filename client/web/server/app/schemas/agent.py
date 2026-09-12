"""Agent 发现和创建接口 DTO。"""

from pydantic import Field

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


class AgentDetail(AgentSummary):
    """角色详情额外公开的运行配置引用。"""

    llm_profile_id: str
    permission_mode: str
