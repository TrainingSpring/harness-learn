"""可跨 Session 复用的 Agent 稳定定义。"""

from dataclasses import dataclass

from head.llm import LLM
from head.types import LLMConfig
from permission.PermissionManager import PermissionManager
from permission.types import PermissionMode
from runtime.ExecutionContext import ExecutionContext
from runtime.runtime import Runtime
from tools.tools import Tools
from tools.types import Tool
from storage.types import AgentProfile


@dataclass(frozen=True)
class AgentDefinition:
    """只包含 Agent 身份、配置和能力定义，不包含 Session 状态。"""

    agent_id: str
    profile: AgentProfile
    llm_config: LLMConfig
    tool_definitions: tuple[Tool, ...]
    permission_mode: PermissionMode
    workspace: str
    permission_rule_repository: object | None = None

    def create_session_runtime(self, session_id: str) -> Runtime:
        """为指定 Session 创建隔离的工具、权限和 Runtime 执行状态。"""
        ctx = ExecutionContext(
            workspace=self.workspace,
            agent_id=self.agent_id,
            session_id=session_id,
        )
        llm = LLM(
            self.llm_config.base_url,
            self.llm_config.api_key,
            self.llm_config.model,
            self.llm_config.instructions,
        )
        tools = Tools(ctx)
        tools.batch_register(list(self.tool_definitions))
        permission = PermissionManager(
            mode=self.permission_mode,
            workspace=self.workspace,
            agent_id=self.agent_id,
            rule_repository=self.permission_rule_repository,
        )
        return Runtime(llm, tools, None, ctx, permission)
