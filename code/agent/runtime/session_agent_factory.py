"""在 Session 边界创建 Agent 的会话执行环境。"""

from runtime.agent_definition import AgentDefinition
from runtime.runtime import Runtime
from storage.database import StateDatabase
from storage.repositories.session_agent import SessionAgentRepository


class SessionAgentRuntimeFactory:
    """验证固定成员关系后，把 AgentDefinition 实例化为 Session Runtime。"""

    def __init__(self, database: StateDatabase) -> None:
        self.members = SessionAgentRepository(database)

    def create(self, definition: AgentDefinition, session_id: str) -> Runtime:
        """仅为当前 Session 的固定成员创建执行环境。"""
        if not isinstance(definition, AgentDefinition):
            raise TypeError("definition 必须是 AgentDefinition")
        if not self.members.exists(session_id, definition.agent_id):
            raise ValueError("当前 Agent 不属于指定 Session")
        return definition.create_session_runtime(session_id)
