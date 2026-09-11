"""可供用户选择和会话路由使用的 Agent 目录。"""

from storage.repositories.agent_profile import AgentProfileRepository
from storage.types import AgentProfile


class AgentDirectory:
    """封装 Agent 配置发现和加入资格判断。

    Attributes:
        repository: 读取 AgentProfile 的仓储。

    目录只回答“有哪些 Agent 可以选择”，不创建 Runtime Agent，也不负责
    会话参与者写入；这样用户选择和运行时组装仍保持两个清晰职责。
    """

    def __init__(self, repository: AgentProfileRepository) -> None:
        """创建 Agent 目录。

        Args:
            repository: 已初始化的 AgentProfile 仓储。
        """
        self.repository = repository

    def list(
        self,
        limit: int = 100,
        offset: int = 0,
        expertise: str | None = None,
    ) -> list[AgentProfile]:
        """列出启用的 Agent，可按擅长领域筛选。

        Args:
            limit: 最大返回数量。
            offset: 跳过数量。
            expertise: 可选的精确 expertise 标签。
        """
        return self.repository.list_enabled(limit, offset, expertise)

    def get(self, agent_id: str) -> AgentProfile | None:
        """按 Agent ID 查询配置，不改变启用状态语义。"""
        return self.repository.get(agent_id)

    def can_join(self, agent_id: str) -> bool:
        """判断 Agent 是否存在且处于启用状态。

        非法或不存在的 ID 都返回 False；目录不把用户输入错误当成可加入。
        """
        try:
            profile = self.repository.get(agent_id)
        except ValueError:
            return False
        return profile is not None and profile.is_enabled
