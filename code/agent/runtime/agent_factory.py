"""从持久化配置组装运行时 Agent。"""

from head.credential_resolver import CredentialResolver
from head.types import LLMConfig
from permission.types import PermissionMode
from runtime.agent import Agent
from runtime.prompt_builder import PromptBuilder
from storage.database import StateDatabase
from storage.repositories.agent_profile import AgentProfileRepository
from storage.repositories.llm_profile import LLMProfileRepository
from tools.catalog import ToolCatalog


class AgentFactory:
    """负责把 AgentProfile 及其依赖转换为短生命周期 Agent。

    Factory 是配置层和运行时层之间的组装边界。它可以读取数据库，但 Agent
    本身不需要知道 Repository、credential_ref 或工具模块如何加载。
    """

    def __init__(
        self,
        database: StateDatabase,
        credential_resolver: CredentialResolver | None = None,
        prompt_builder: PromptBuilder | None = None,
        tool_catalog: ToolCatalog | None = None,
    ) -> None:
        """创建 AgentFactory。

        Args:
            database: 已初始化的 workspace 状态数据库。
            credential_resolver: 可选的凭据解析器，便于测试和未来扩展。
            prompt_builder: 可选的系统指令构建器。
            tool_catalog: 可选的受信任工具目录。
        """
        self.database = database
        self.llm_profiles = LLMProfileRepository(database)
        self.agent_profiles = AgentProfileRepository(database)
        self.credential_resolver = credential_resolver or CredentialResolver()
        self.prompt_builder = prompt_builder or PromptBuilder()
        self.tool_catalog = tool_catalog or ToolCatalog()

    def load(
        self,
        agent_id: str,
        session_id: str | None = None,
        participant_id: str | None = None,
    ) -> Agent:
        """根据 Agent ID 创建运行时 Agent。

        Args:
            agent_id: AgentProfile 的稳定 ID。
            session_id: 可选的现有会话 ID；不传时由 Agent 创建新会话 ID。
            participant_id: 可选的会话参与者 ID，供后续上下文投影使用。

        Returns:
            已加载 LLM、工具、Context 和权限管理器的 Agent。

        Raises:
            ValueError: Agent 或其 LLM 配置不存在，或权限模式非法。
        """
        profile = self.agent_profiles.get(agent_id)
        if profile is None:
            raise ValueError(f"Agent 配置不存在: {agent_id}")

        llm_profile = self.llm_profiles.get(profile.llm_profile_id)
        if llm_profile is None:
            raise ValueError(
                f"Agent 引用的 LLM 配置不存在: {profile.llm_profile_id}"
            )

        try:
            permission_mode = PermissionMode(profile.permission_mode.lower())
        except (AttributeError, ValueError) as error:
            raise ValueError(
                f"Agent 权限模式无效: {profile.permission_mode}"
            ) from error

        self.tool_catalog.validate_names(profile.tools)
        api_key = self.credential_resolver.resolve(llm_profile.credential_ref)
        instructions = self.prompt_builder.build(profile)
        llm_config = LLMConfig(
            base_url=llm_profile.base_url or "",
            api_key=api_key,
            model=llm_profile.model,
            instructions=instructions,
        )

        agent = Agent(
            llm_config=llm_config,
            tools=profile.tools,
            agent_id=profile.id,
            permission_mode=permission_mode,
            workspace=str(self.database.workspace),
            session_id=session_id,
        )
        # participant_id 是会话级身份，当前 Agent 先保留它供 ContextService 接入。
        agent.participant_id = participant_id
        agent.agent_id = profile.id
        agent.profile = profile
        return agent
