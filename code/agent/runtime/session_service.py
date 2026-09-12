"""固定成员 DIRECT 与 GROUP 会话的创建用例。"""

from storage.database import StateDatabase
from storage.repositories.agent_profile import AgentProfileRepository
from storage.repositories.session import SessionRepository
from storage.types import Session


class SessionService:
    """按当前产品规则创建成员不可变的会话。

    Attributes:
        sessions: 负责原子写入 Session 聚合的仓储。
        agents: 用于确认用户选择的 AgentProfile 已存在且可用的仓储。

    本服务是 UI/CLI 应使用的会话创建入口。底层 Repository 仍可独立创建
    数据用于迁移和仓储测试，但产品流程必须经由本服务满足成员数量约束。
    """

    def __init__(self, database: StateDatabase) -> None:
        """创建会话服务。

        Args:
            database: 已初始化的 workspace 状态数据库。
        """
        self.sessions = SessionRepository(database)
        self.agents = AgentProfileRepository(database)

    def create_direct_session(
        self,
        agent_id: str,
        title: str | None = None,
    ) -> Session:
        """创建固定一个主 Agent 的 1v1 会话。

        Args:
            agent_id: 用户在会话开始时选中的稳定 Agent ID。
            title: 可选的会话标题。
        """
        self._require_enabled_agents([agent_id])
        return self.sessions.create_with_agents(
            "DIRECT",
            [(agent_id, "PRIMARY")],
            title,
        )

    def create_group_session(
        self,
        agent_ids: list[str],
        title: str | None = None,
    ) -> Session:
        """创建至少包含两个不同 Agent 的 1vN 群聊。

        Args:
            agent_ids: 用户在创建时一次性选择的 Agent ID 列表。
            title: 可选的群聊标题。

        Raises:
            ValueError: 数量不足、存在重复 ID，或 Agent 不存在/已禁用。
        """
        if not isinstance(agent_ids, list):
            raise TypeError("agent_ids 必须是列表")
        if len(agent_ids) < 2:
            raise ValueError("GROUP 会话至少需要两个 Agent")
        if len(set(agent_ids)) != len(agent_ids):
            raise ValueError("GROUP 会话不能重复选择同一个 Agent")
        self._require_enabled_agents(agent_ids)
        return self.sessions.create_with_agents(
            "GROUP",
            [(agent_id, "MEMBER") for agent_id in agent_ids],
            title,
        )

    def _require_enabled_agents(self, agent_ids: list[str]) -> None:
        """确认所有 Agent 配置存在且允许用于新会话。"""
        for agent_id in agent_ids:
            profile = self.agents.get(agent_id)
            if profile is None:
                raise ValueError(f"Agent 配置不存在: {agent_id}")
            if not profile.is_enabled:
                raise ValueError(f"Agent 已禁用: {agent_id}")
