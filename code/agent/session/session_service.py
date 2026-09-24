"""创建、恢复和执行固定成员 Session 的应用服务。"""

from collections.abc import Generator
from collections.abc import Callable

from context.context import Context
from head.llm import LLM
from head.types import LLMResponse, LLMResponseOutputItem
from permission.PermissionManager import PermissionManager
from permission.types import PermissionMode, PermissionResponse
from runtime.agent import Agent
from runtime.agent_factory import AgentFactory
from runtime.prompt_builder import PromptBuilder
from runtime.runtime import Runtime
from runtime.runtime_events import PermissionRequiredEvent, RuntimeEvent
from storage.context_service import ContextService
from storage.database import StateDatabase
from storage.repositories.agent_profile import AgentProfileRepository
from storage.repositories.context_item import ContextItemRepository
from storage.repositories.session import SessionRepository
from storage.repositories.session_agent import SessionAgentRepository
from storage.repositories.session_permission_rule import SessionPermissionRuleRepository
from storage.types import Session, SessionAgent
from tools.tools import Tools

from .ExecutionContext import ExecutionContext


class SessionExecution:
    """一个已打开 Session 的共享 Context 和成员 Runtime 状态。"""

    def __init__(
        self,
        *,
        session: Session,
        context: Context,
        context_service: ContextService,
        session_repository: SessionRepository,
        members: tuple[SessionAgent, ...],
        runtimes: dict[str, Runtime],
        refresh_runtimes: Callable[[Session], dict[str, Runtime]],
    ) -> None:
        self.session = session
        self.context = context
        self.context_service = context_service
        self._session_repository = session_repository
        self.members = members
        self.runtimes = runtimes
        self._refresh_runtimes = refresh_runtimes
        self._active_member_index: int | None = None
        self._current_member_index: int | None = None
        self._recorded_output_call_ids = {
            item.call_id
            for item in context_service.load_visible(members[0].agent_id)
            if item.kind == "FUNCTION_CALL_OUTPUT" and item.call_id is not None
        }

    def send(self, message: str) -> Generator[RuntimeEvent, None, None]:
        """持久化用户消息并执行当前 Session 的一轮成员调度。"""
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
        """恢复等待权限的成员 Runtime，并继续后续成员。"""
        if self._active_member_index is None:
            raise ValueError("Session 当前没有等待处理的权限请求")
        member_index = self._active_member_index
        runtime = self.runtimes[self.members[member_index].agent_id]
        self._active_member_index = None
        yield from self._drive_from(
            member_index,
            runtime.resolve_permission(self.context, response),
        )

    def cancel(self) -> None:
        """取消当前成员 Runtime，并保留已经持久化的 Session Context。"""
        member_index = self._active_member_index
        if member_index is None:
            member_index = self._current_member_index
        if member_index is not None:
            self.runtimes[self.members[member_index].agent_id].cancel()
        self._active_member_index = None
        self.context_service.save_context(self.context)

    def set_project_path(self, project_path: str | None) -> None:
        """在首条用户消息前更新当前 Session 的项目目录。"""
        self._require_idle_for_settings()
        self.session = self._session_repository.update_project_path_before_first_message(
            self.session.id,
            project_path,
        )
        self.runtimes = self._refresh_runtimes(self.session)

    def set_permission_mode(self, permission_mode: str) -> None:
        """在没有活动 Runtime 时更新当前 Session 的权限模式。"""
        self._require_idle_for_settings()
        self.session = self._session_repository.update_permission_mode(
            self.session.id,
            permission_mode,
        )
        self.runtimes = self._refresh_runtimes(self.session)

    def _require_idle_for_settings(self) -> None:
        if self._active_member_index is not None or self._current_member_index is not None:
            raise ValueError("Session 正在运行，不能修改会话设置")

    def _drive_from(
        self,
        member_index: int,
        current_events: Generator[RuntimeEvent, None, None] | None = None,
    ) -> Generator[RuntimeEvent, None, None]:
        """顺序调用成员 Runtime；权限暂停时保留当前成员位置。"""
        for index in range(member_index, len(self.members)):
            member = self.members[index]
            runtime = self.runtimes[member.agent_id]
            events = (
                current_events
                if index == member_index and current_events
                else runtime.run(self.context)
            )
            self._current_member_index = index
            try:
                for event in events:
                    self._persist_runtime_changes(member.agent_id, event)
                    if isinstance(event, PermissionRequiredEvent):
                        self._active_member_index = index
                        yield event
                        return
                    yield event
            finally:
                # 即使 LLM 或工具在下一个事件前异常，已经写入 Context 的协议项和
                # 治理后的快照仍必须留在当前 Session，不能恢复为旧版本。
                self._persist_function_protocol_items(member.agent_id)
                self.context_service.save_context(self.context)
                self._current_member_index = None
            current_events = None

    def _persist_runtime_changes(self, agent_id: str, event: RuntimeEvent) -> None:
        """保存 Context 快照，并同步 Runtime 已产生的原始业务事件。"""
        self._persist_function_protocol_items(agent_id)
        if isinstance(event, LLMResponse) and event.type == "done":
            for item in event.data or []:
                if item.type != "message":
                    continue
                text = self._message_text(item)
                if text.strip():
                    self.context_service.append_agent_message(agent_id, text)
            self._persist_function_protocol_items(agent_id)
        self.context_service.save_context(self.context)

    def _persist_function_protocol_items(self, agent_id: str) -> None:
        """把 Context 中的新工具协议项写入不可变时间线。"""
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
            if isinstance(arguments, (str, dict)):
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
            if call is not None:
                self.context_service.append_function_call_output(
                    agent_id,
                    call_id=call_id,
                    output=item.get("output"),
                    caused_by_item_id=call.id,
                )
                self._recorded_output_call_ids.add(call_id)

    @staticmethod
    def _message_text(item: LLMResponseOutputItem) -> str:
        """提取已写入 Context 的模型文本。"""
        if isinstance(item.content, str):
            return item.content
        if not isinstance(item.content, list):
            return ""
        return "".join(
            part.get("text") if isinstance(part, dict) else getattr(part, "text", "")
            for part in item.content
            if isinstance(
                part.get("text") if isinstance(part, dict) else getattr(part, "text", None),
                str,
            )
        )


class SessionService:
    """统一创建、恢复并打开固定成员 Session。"""

    def __init__(self, database: StateDatabase) -> None:
        self.database = database
        self.sessions = SessionRepository(database)
        self.members = SessionAgentRepository(database)
        self.agent_profiles = AgentProfileRepository(database)
        self.agent_factory = AgentFactory(database)

    def create_direct_session(
        self,
        agent_id: str,
        title: str | None = None,
        permission_mode: str = "plan",
    ) -> SessionExecution:
        """创建固定主 Agent 的 DIRECT Session，并立即打开它。"""
        self._require_enabled_agents([agent_id])
        session = self.sessions.create_with_agents(
            "DIRECT",
            [(agent_id, "PRIMARY")],
            title,
            permission_mode,
        )
        return self._open(session)

    def create_group_session(
        self,
        agent_ids: list[str],
        title: str | None = None,
        permission_mode: str = "plan",
    ) -> SessionExecution:
        """创建固定成员 GROUP Session，并立即打开它。"""
        if not isinstance(agent_ids, list):
            raise TypeError("agent_ids 必须是列表")
        if len(agent_ids) < 2:
            raise ValueError("GROUP 会话至少需要两个 Agent")
        if len(set(agent_ids)) != len(agent_ids):
            raise ValueError("GROUP 会话不能重复选择同一个 Agent")
        self._require_enabled_agents(agent_ids)
        session = self.sessions.create_with_agents(
            "GROUP",
            [(agent_id, "MEMBER") for agent_id in agent_ids],
            title,
            permission_mode,
        )
        return self._open(session)

    def load(self, session_id: str) -> SessionExecution:
        """恢复并打开一个已有 Session。"""
        session = self.sessions.get(session_id)
        if session is None:
            raise ValueError(f"Session 不存在: {session_id}")
        return self._open(session)

    def _open(self, session: Session) -> SessionExecution:
        """组装一个 Session 唯一的共享 Context 与成员 Runtime。"""
        members = tuple(self.members.list_for_session(session.id))
        if not members:
            raise ValueError(f"Session 没有固定 Agent 成员: {session.id}")
        agents = {
            member.agent_id: self.agent_factory.load(member.agent_id)
            for member in members
        }
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
        def create_runtimes(current_session: Session) -> dict[str, Runtime]:
            return self._create_runtimes(current_session, members, agents)

        runtimes = create_runtimes(session)
        return SessionExecution(
            session=session,
            context=context,
            context_service=context_service,
            session_repository=self.sessions,
            members=members,
            runtimes=runtimes,
            refresh_runtimes=create_runtimes,
        )

    def _create_runtimes(
        self,
        session: Session,
        members: tuple[SessionAgent, ...],
        agents: dict[str, Agent],
    ) -> dict[str, Runtime]:
        """为一个 Session 生成共享权限、独立执行状态的成员 Runtime。"""
        permission = PermissionManager(
            mode=PermissionMode(session.permission_mode),
            session_id=session.id,
            project_path=session.project_path,
            rule_repository=SessionPermissionRuleRepository(self.database),
        )
        return {
            member.agent_id: self._create_runtime(
                agents[member.agent_id],
                member,
                permission,
                session.permission_mode,
                session.project_path,
            )
            for member in members
        }

    @staticmethod
    def _create_runtime(
        agent: Agent,
        member: SessionAgent,
        permission: PermissionManager,
        permission_mode: str,
        project_path: str | None,
    ) -> Runtime:
        """为固定成员构造独立的 Agent Runtime 能力环境。"""
        if member.agent_id != agent.agent_id:
            raise ValueError("SessionAgent 与 Agent 身份不一致")
        ctx = ExecutionContext(project_path, agent.agent_id, member.session_id)
        llm = LLM(
            agent.llm_config.base_url,
            agent.llm_config.api_key,
            agent.llm_config.model,
            PromptBuilder().build(agent.profile, permission_mode=permission_mode),
        )
        tools = Tools(ctx)
        tools.batch_register(list(agent.tool_definitions))
        return Runtime(llm, tools, ctx, permission)

    def _require_enabled_agents(self, agent_ids: list[str]) -> None:
        """确认新 Session 选择的所有 Agent 均存在且已启用。"""
        for agent_id in agent_ids:
            profile = self.agent_profiles.get(agent_id)
            if profile is None:
                raise ValueError(f"Agent 配置不存在: {agent_id}")
            if not profile.is_enabled:
                raise ValueError(f"Agent 已禁用: {agent_id}")
