"""组装并驱动 Session 级共享 Context 的运行环境。"""

from collections.abc import Generator
from typing import Any

from context.context import Context
from head.llm import LLM
from head.types import LLMResponse, LLMResponseOutputItem
from permission.types import PermissionResponse
from runtime.agent_factory import AgentFactory
from runtime.runtime import Runtime
from runtime.runtime_events import PermissionRequiredEvent, RuntimeEvent
from storage.context_service import ContextService
from storage.database import StateDatabase
from storage.repositories.context_item import ContextItemRepository
from storage.repositories.session import SessionRepository
from storage.repositories.session_agent import SessionAgentRepository
from storage.types import Session, SessionAgent

from .session_agent_factory import SessionAgentRuntimeFactory


class SessionExecution:
    """一个进程内 Session 的共享 Context 与成员 Runtime 调度器。

    Runtime 仍然独立执行 Agent Loop；本类只负责把同一个 Context 传给当前
    Runtime、持久化会话状态，以及在 GROUP 中选择下一个成员。
    """

    def __init__(
        self,
        *,
        session: Session,
        context: Context,
        context_service: ContextService,
        members: tuple[SessionAgent, ...],
        runtimes: dict[str, Runtime],
    ) -> None:
        self.session = session
        self.context = context
        self.context_service = context_service
        self.members = members
        self.runtimes = runtimes
        self._active_member_index: int | None = None
        self._recorded_output_call_ids = {
            item.call_id
            for item in context_service.load_visible(members[0].agent_id)
            if item.kind == "FUNCTION_CALL_OUTPUT" and item.call_id is not None
        }

    def send(self, message: str) -> Generator[RuntimeEvent, None, None]:
        """持久化一条用户消息并执行本轮 Session 调度。"""
        if self._active_member_index is not None:
            raise ValueError("Session 当前正在等待权限确认，不能发送新消息")

        self.context_service.append_user_message(message)
        self.context.append_user_message(message)
        self.context_service.save_context(self.context)
        yield from self._drive_from(0)

    def resolve_permission(
        self,
        response: PermissionResponse,
    ) -> Generator[RuntimeEvent, None, None]:
        """恢复唯一等待确认的成员 Runtime，并继续 GROUP 的剩余成员。"""
        if self._active_member_index is None:
            raise ValueError("Session 当前没有等待处理的权限请求")

        member_index = self._active_member_index
        member = self.members[member_index]
        runtime = self.runtimes[member.agent_id]
        self._active_member_index = None
        yield from self._drive_from(
            member_index,
            runtime.resolve_permission(self.context, response),
        )

    def _drive_from(
        self,
        member_index: int,
        current_events: Generator[RuntimeEvent, None, None] | None = None,
    ) -> Generator[RuntimeEvent, None, None]:
        """从指定成员开始顺序执行，权限暂停时保留当前位置。"""
        for index in range(member_index, len(self.members)):
            member = self.members[index]
            runtime = self.runtimes[member.agent_id]
            events = current_events if index == member_index and current_events else runtime.run(self.context)
            for event in events:
                self._persist_runtime_changes(member.agent_id, event)
                if isinstance(event, PermissionRequiredEvent):
                    self._active_member_index = index
                    yield event
                    return
                yield event
            current_events = None

    def _persist_runtime_changes(self, agent_id: str, event: RuntimeEvent) -> None:
        """保存快照，并把 Runtime 产生的协议项还原为原始业务事件。"""
        self._persist_function_protocol_items(agent_id)
        if isinstance(event, LLMResponse) and event.type == "done":
            for item in event.data or []:
                if item.type != "message":
                    continue
                text = self._message_text(item)
                if text:
                    self.context_service.append_agent_message(agent_id, text)
            self._persist_function_protocol_items(agent_id)
        self.context_service.save_context(self.context)

    def _persist_function_protocol_items(self, agent_id: str) -> None:
        """同步当前 Runtime 新增的 function call 及其输出。"""
        for item in self.context.export():
            if item.get("type") != "function_call":
                continue
            call_id = item.get("call_id")
            name = item.get("name")
            arguments = item.get("arguments")
            if not isinstance(call_id, str) or not isinstance(name, str):
                continue
            if self.context_service.repository.find_by_call_id(self.session.id, call_id):
                continue
            if not isinstance(arguments, (str, dict)):
                continue
            self.context_service.append_function_call(
                agent_id,
                call_id=call_id,
                name=name,
                arguments=arguments,
            )

        for item in self.context.export():
            if item.get("type") != "function_call_output":
                continue
            call_id = item.get("call_id")
            if not isinstance(call_id, str) or call_id in self._recorded_output_call_ids:
                continue
            call = self.context_service.repository.find_by_call_id(self.session.id, call_id)
            if call is None:
                continue
            self.context_service.append_function_call_output(
                agent_id,
                call_id=call_id,
                output=item.get("output"),
                caused_by_item_id=call.id,
            )
            self._recorded_output_call_ids.add(call_id)

    @staticmethod
    def _message_text(item: LLMResponseOutputItem) -> str:
        """投影 Runtime 已写入 Context 的模型消息文本。"""
        if isinstance(item.content, str):
            return item.content
        if not isinstance(item.content, list):
            return ""
        return "".join(
            part["text"]
            for part in item.content
            if isinstance(part, dict) and isinstance(part.get("text"), str)
        )


class SessionCoordinator:
    """加载固定 Session 成员并组装 SessionExecution。"""

    def __init__(
        self,
        database: StateDatabase,
        *,
        agent_factory: AgentFactory | None = None,
        runtime_factory: SessionAgentRuntimeFactory | None = None,
    ) -> None:
        self.database = database
        self.sessions = SessionRepository(database)
        self.members = SessionAgentRepository(database)
        self.agent_factory = agent_factory or AgentFactory(database)
        self.runtime_factory = runtime_factory or SessionAgentRuntimeFactory()

    def load(self, session_id: str) -> SessionExecution:
        """恢复一个 Session 唯一的 Context，并创建每位成员的独立 Runtime。"""
        session = self.sessions.get(session_id)
        if session is None:
            raise ValueError(f"Session 不存在: {session_id}")
        members = tuple(self.members.list_for_session(session.id))
        if not members:
            raise ValueError(f"Session 没有固定 Agent 成员: {session.id}")

        agents = {member.agent_id: self.agent_factory.load(member.agent_id) for member in members}
        first_agent = agents[members[0].agent_id]
        context = Context(
            LLM(
                first_agent.llm_config.base_url,
                first_agent.llm_config.api_key,
                first_agent.llm_config.model,
                first_agent.llm_config.instructions,
            ),
            session_id=session.id,
        )
        context_service = ContextService(ContextItemRepository(self.database), session.id)
        context_service.restore_context(context, members[0].agent_id)
        runtimes = {
            member.agent_id: self.runtime_factory.create(
                agents[member.agent_id],
                member,
                context,
            )
            for member in members
        }
        return SessionExecution(
            session=session,
            context=context,
            context_service=context_service,
            members=members,
            runtimes=runtimes,
        )
