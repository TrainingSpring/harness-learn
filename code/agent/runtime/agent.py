import os

from head.llm import LLM
from head.types import LLMConfig
from permission.PermissionManager import PermissionManager
from permission.types import PermissionMode, PermissionResponse
from runtime.runtime import Runtime
from tools.tools import Tools
from context.context import Context
from runtime.ExecutionContext import ExecutionContext
from storage.ids import generate_id
from storage.repositories.permission_rule import PermissionRuleRepository

class Agent:
    """组装 LLM、工具、上下文和权限管理器的逻辑 Agent。"""

    def __init__(
        self,
        llm_config: LLMConfig,
        tools: list[str],
        context: Context | None = None,
        agent_id: str = "agent_default",
        permission_mode: PermissionMode = PermissionMode.BUILD,
        workspace: str | None = None,
        session_id: str | None = None,
        permission_rule_repository: PermissionRuleRepository | None = None,
    ):
        """创建具有稳定 Agent 身份和新会话身份的 Agent。

        Args:
            llm_config: LLM 连接与模型配置。
            tools: 需要注册的工具模块名称。
            context: 可选的既有对话上下文。
            agent_id: 逻辑 Agent 的稳定标识，用于 AGENT 范围权限规则。
            permission_mode: 没有命中明确规则时使用的默认权限模式。
            workspace: 工具处理相对路径的目录；为空时使用当前目录。
            session_id: 可选的既有会话 ID；为空时生成新的 session_ 前缀 ID。
            permission_rule_repository: 可选的 Agent 权限规则仓储；传入后
                PermissionManager 会加载并持久化 AGENT 规则。
        """
        self.agent_id = agent_id
        self.session_id = session_id if session_id is not None else generate_id("session")
        # workspace 只是工具路径解析依据，安全边界会在 harness 层实现。
        self.workspace = workspace if workspace is not None else os.getcwd()
        self.ctx = ExecutionContext(
            workspace=self.workspace,
            agent_id=self.agent_id,
            session_id=self.session_id,
        )
        # LLM
        self.llm = LLM(llm_config.base_url,llm_config.api_key,llm_config.model,llm_config.instructions)
        # 工具
        self.tools = Tools(self.ctx)
        # 注册工具
        self.tools.register_by_names(tools)
        # 上下文
        self.context = context if context is not None else Context(LLM(llm_config.base_url,llm_config.api_key,llm_config.model,llm_config.instructions),self.ctx)
        # 权限管理
        self.permission = PermissionManager(
            mode=permission_mode,
            workspace=self.workspace,
            agent_id=self.agent_id,
            rule_repository=permission_rule_repository,
        )
        # 运行时（loop）
        self.runtime = Runtime(self.llm,self.tools,self.context,self.ctx,self.permission)


    def send(self,message:str):
        return self.runtime.run(message)

    def resolve_permission(self, response: PermissionResponse):
        """将宿主的权限确认转交给 Runtime，并恢复挂起的 Agent loop。

        Args:
            response: 用户针对当前 pending 工具调用的确认结果。
        """
        return self.runtime.resolve_permission(response)
