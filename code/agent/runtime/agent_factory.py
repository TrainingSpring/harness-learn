"""从持久化配置组装运行时 Agent。"""

from head.types import LLMConfig
from runtime.agent import Agent
from runtime.prompt_builder import PromptBuilder
from storage.database import StateDatabase
from storage.repositories.agent_profile import AgentProfileRepository
from storage.repositories.llm_profile import LLMProfileRepository
from tools.catalog import ToolCatalog


class AgentFactory:
    """负责把 AgentProfile 及其依赖转换为短生命周期 Agent。

    Factory 是配置层和运行时层之间的组装边界。它可以读取数据库，但 Agent
    本身不需要知道 Repository 或工具模块如何加载。
    """

    def __init__(
        self,
        database: StateDatabase,
        prompt_builder: PromptBuilder | None = None,
        tool_catalog: ToolCatalog | None = None,
    ) -> None:
        """创建 AgentFactory。

        Args:
            database: 已初始化的 workspace 状态数据库。
            prompt_builder: 可选的系统指令构建器。
            tool_catalog: 可选的受信任工具目录。
        """
        self.database = database
        self.llm_profiles = LLMProfileRepository(database)
        self.agent_profiles = AgentProfileRepository(database)
        self.prompt_builder = prompt_builder or PromptBuilder()
        self.tool_catalog = tool_catalog or ToolCatalog()

    def load(
        self,
        agent_id: str,
    ) -> Agent:
        """根据 Agent ID 加载可跨 Session 复用的稳定 Agent。

        Args:
            agent_id: AgentProfile 的稳定 ID。
        Returns:
            不携带 Session 状态的 Agent。

        Raises:
            ValueError: Agent 或其 LLM 配置不存在。
        """
        profile = self.agent_profiles.get(agent_id)
        if profile is None:
            raise ValueError(f"Agent 配置不存在: {agent_id}")

        llm_profile = self.llm_profiles.get(profile.llm_profile_id)
        if llm_profile is None:
            raise ValueError(
                f"Agent 引用的 LLM 配置不存在: {profile.llm_profile_id}"
            )

        tool_definitions = tuple(self.tool_catalog.get(name) for name in profile.tools)
        if not llm_profile.api_key:
            raise ValueError(f"LLM 配置未设置 API Key: {llm_profile.id}")
        instructions = self.prompt_builder.build(profile)
        llm_config = LLMConfig(
            base_url=llm_profile.base_url or "",
            api_key=llm_profile.api_key,
            model=llm_profile.model,
            instructions=instructions,
        )

        return Agent(
            agent_id=profile.id,
            profile=profile,
            llm_config=llm_config,
            tool_definitions=tool_definitions,
        )
