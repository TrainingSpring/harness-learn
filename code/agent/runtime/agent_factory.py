"""从持久化配置组装当前 Session 的完整 Agent。"""

from context.context import Context
from head.types import LLMConfig
from permission.PermissionManager import PermissionManager
from session.ExecutionContext import ExecutionContext
from storage.database import StateDatabase
from storage.repositories.agent_profile import AgentProfileRepository
from storage.repositories.llm_profile import LLMProfileRepository
from storage.types import AgentProfile, LLMProfile
from tools.registry.catalog import ToolCatalog

from .agent import Agent
from .prompt_builder import PromptBuilder


class AgentFactory:
    """连接 storage 配置与 Session 注入依赖，创建完整 Agent。"""

    def __init__(
        self,
        database: StateDatabase,
        prompt_builder: PromptBuilder | None = None,
        tool_catalog: ToolCatalog | None = None,
    ) -> None:
        self.database = database
        self.llm_profiles = LLMProfileRepository(database)
        self.agent_profiles = AgentProfileRepository(database)
        self.prompt_builder = prompt_builder or PromptBuilder()
        self.tool_catalog = tool_catalog or ToolCatalog()

    def load(
        self,
        agent_id: str,
        *,
        context: Context,
        execution_context: ExecutionContext,
        permission: PermissionManager,
        permission_mode: str,
    ) -> Agent:
        """读取配置并创建一个只属于当前 Session 的 Agent 实例。"""
        profile, llm_profile = self._load_sources(agent_id)
        tool_definitions = tuple(
            self.tool_catalog.get(name) for name in profile.tools
        )
        return Agent(
            agent_id=profile.id,
            name=profile.name,
            description=profile.description,
            personality=profile.personality,
            expertise=tuple(profile.expertise),
            llm_config=self._to_llm_config(llm_profile),
            tool_definitions=tool_definitions,
            context=context,
            execution_context=execution_context,
            permission=permission,
            permission_mode=permission_mode,
            prompt_builder=self.prompt_builder,
        )

    def load_llm_config(self, agent_id: str) -> LLMConfig:
        """读取 Agent 的连接配置，供 Session 创建独立 Context summarizer。"""
        _profile, llm_profile = self._load_sources(agent_id)
        return self._to_llm_config(llm_profile)

    def _load_sources(self, agent_id: str) -> tuple[AgentProfile, LLMProfile]:
        profile = self.agent_profiles.get(agent_id)
        if profile is None:
            raise ValueError(f"Agent 配置不存在: {agent_id}")
        llm_profile = self.llm_profiles.get(profile.llm_profile_id)
        if llm_profile is None:
            raise ValueError(
                f"Agent 引用的 LLM 配置不存在: {profile.llm_profile_id}"
            )
        if not llm_profile.api_key:
            raise ValueError(f"LLM 配置未设置 API Key: {llm_profile.id}")
        return profile, llm_profile

    @staticmethod
    def _to_llm_config(profile: LLMProfile) -> LLMConfig:
        return LLMConfig(
            base_url=profile.base_url or "",
            api_key=profile.api_key,
            model=profile.model,
            protocol=profile.options.get("protocol", "responses"),
        )
