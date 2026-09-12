"""Agent 发现接口 DTO。"""

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


class AgentDetail(AgentSummary):
    """角色详情额外公开的运行配置引用。"""

    llm_profile_id: str
    permission_mode: str

