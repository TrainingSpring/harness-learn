"""在 Session 边界创建 Agent 的会话执行环境。"""

from head.llm import LLM
from context.context import Context
from permission.PermissionManager import PermissionManager
from runtime.ExecutionContext import ExecutionContext
from runtime.agent import Agent
from runtime.runtime import Runtime
from storage.types import SessionAgent
from tools.tools import Tools


class SessionAgentRuntimeFactory:
    """把稳定 Agent 和当前 Session 状态组装为一次运行时。"""

    def create(self, agent: Agent, member: SessionAgent, context: Context) -> Runtime:
        """为已验证的 Session 成员创建隔离执行环境。"""
        if not isinstance(agent, Agent):
            raise TypeError("agent 必须是 Agent")
        if not isinstance(member, SessionAgent):
            raise TypeError("member 必须是 SessionAgent")
        if not isinstance(context, Context):
            raise TypeError("context 必须是 Context")
        if member.agent_id != agent.agent_id:
            raise ValueError("SessionAgent 与 Agent 身份不一致")
        if context.sid != member.session_id:
            raise ValueError("Context 与 SessionAgent 所属会话不一致")
        ctx = ExecutionContext(
            workspace=agent.workspace,
            agent_id=agent.agent_id,
            session_id=member.session_id,
        )
        llm = LLM(
            agent.llm_config.base_url,
            agent.llm_config.api_key,
            agent.llm_config.model,
            agent.llm_config.instructions,
        )
        tools = Tools(ctx)
        tools.batch_register(list(agent.tool_definitions))
        permission = PermissionManager(
            mode=agent.permission_mode,
            workspace=agent.workspace,
            agent_id=agent.agent_id,
            rule_repository=agent.permission_rule_repository,
        )
        return Runtime(llm, tools, context, ctx, permission)
