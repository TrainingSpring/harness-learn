import os
import secrets

from head.llm import LLM
from head.types import LLMConfig
from permission.PermissionManager import PermissionManager
from permission.types import PermissionMode
from runtime.runtime import Runtime
from tools.tools import Tools
from context.context import Context
from runtime.ExecutionContext import ExecutionContext

class Agent:
    """组装 LLM、工具、上下文和权限管理器的逻辑 Agent。"""

    def __init__(
        self,
        llm_config: LLMConfig,
        tools: list[str],
        context: Context | None = None,
        agent_key: str = "default",
        permission_mode: PermissionMode = PermissionMode.BUILD,
        workspace: str | None = None,
    ):
        """创建具有稳定 Agent 身份和新会话身份的 Agent。

        Args:
            llm_config: LLM 连接与模型配置。
            tools: 需要注册的工具模块名称。
            context: 可选的既有对话上下文。
            agent_key: 逻辑 Agent 的稳定标识，用于 AGENT 范围权限规则。
            permission_mode: 没有命中明确规则时使用的默认权限模式。
            workspace: 工具处理相对路径的目录；为空时使用当前目录。
        """
        self.agent_key = agent_key
        self.session_id = f"session_{secrets.token_hex(10)}"
        # workspace 只是工具路径解析依据，安全边界会在 harness 层实现。
        self.workspace = workspace if workspace is not None else os.getcwd()
        self.ctx = ExecutionContext(
            workspace=self.workspace,
            agent_key=self.agent_key,
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
        )
        # 运行时（loop）
        self.runtime = Runtime(self.llm,self.tools,self.context,self.ctx,self.permission)


    def send(self,message:str):
        return self.runtime.run(message)
