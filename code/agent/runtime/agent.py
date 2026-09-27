"""由 Session 组装、可直接执行的 Agent。"""

from collections.abc import Generator

from context.context import Context
from head.llm import LLM
from head.types import LLMConfig
from permission.PermissionManager import PermissionManager
from permission.types import PermissionResponse
from session.ExecutionContext import ExecutionContext
from tools.tools import Tools
from tools.types import Tool
from skills.types import SkillDefinition
from skills.skills import SkillSet

from .prompt_builder import PromptBuilder
from .runtime import Runtime
from .runtime_events import RuntimeEvent


class Agent:
    """承载一个 Session 成员的身份、能力和 Runtime。"""

    def __init__(
        self,
        *,
        agent_id: str,
        name: str,
        description: str,
        personality: str,
        expertise: tuple[str, ...],
        llm_config: LLMConfig,
        tool_definitions: tuple[Tool, ...],
        skills: tuple[SkillDefinition, ...] = (),
        context: Context,
        execution_context: ExecutionContext,
        permission: PermissionManager,
        permission_mode: str,
        prompt_builder: PromptBuilder | None = None,
    ) -> None:
        if context.session_id != execution_context.session_id:
            raise ValueError("context 与 execution_context 必须属于同一 Session")
        if agent_id != execution_context.agent_id:
            raise ValueError("agent_id 与 execution_context.agent_id 必须一致")

        self.agent_id = agent_id
        self.name = name
        self.description = description
        self.personality = personality
        self.expertise = tuple(expertise)
        self.llm_config = llm_config
        self.tool_definitions = tuple(tool_definitions)
        self.skills = tuple(skills)
        self.skill_set = SkillSet(self.skills)
        self.context = context
        self.execution_context = execution_context
        self.permission = permission
        self.tools = Tools(execution_context)
        self.tools.batch_register(list(self.tool_definitions))

        instructions = (prompt_builder or PromptBuilder()).build(
            self,
            permission_mode=permission_mode,
            skill_metadata=self.skill_set.metadata_prompt(),
        )
        self.llm = LLM(
            llm_config.base_url,
            llm_config.api_key,
            llm_config.model,
            instructions,
        )
        self.runtime = Runtime(
            self.llm,
            self.tools,
            execution_context,
            permission,
            context,
        )

    def run(self, *, active_skill_ids: tuple[str, ...] = ()) -> Generator[RuntimeEvent, None, None]:
        """执行当前 Agent 的一轮 Agent Loop。"""
        return self.runtime.run(
            skill_instructions=self.skill_set.instructions_for(active_skill_ids),
        )

    def resolve_permission(
        self,
        response: PermissionResponse,
    ) -> Generator[RuntimeEvent, None, None]:
        """将用户权限决定转交给当前 Agent 的 Runtime。"""
        return self.runtime.resolve_permission(response)

    def cancel(self) -> None:
        """取消当前 Agent 内部 Runtime 的执行状态。"""
        self.runtime.cancel()
