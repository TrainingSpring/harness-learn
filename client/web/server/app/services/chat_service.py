"""把同步 Runtime generator 转换为稳定 Web 流事件。"""

from collections.abc import Iterator
from typing import Any

from head.types import LLMResponse
from permission.types import PermissionDecision, PermissionResponse, PermissionScope
from runtime.agent_factory import AgentFactory
from runtime.runtime_events import PermissionRequiredEvent
from storage.repositories.context_item import ContextItemRepository
from storage.repositories.session_query import SessionQueryRepository
from storage.types import ContextItem

from ..schemas.run import PermissionDecisionRequest, ServerEvent
from .run_registry import ActiveRun, RunAlreadyActiveError, RunRegistry


class SessionNotRunnableError(Exception):
    """目标不是首期 Web 客户端可运行的活动 DIRECT 会话。"""


class RunNotFoundError(Exception):
    """runId 不存在或已经结束。"""


class PermissionMismatchError(Exception):
    """权限确认与当前 Runtime 等待的 callId 不匹配。"""


class ChatService:
    """协调 Agent 运行、上下文事件映射和权限暂停恢复。

    Attributes:
        agent_factory: 根据持久化配置加载真实运行时 Agent 的边界。
        session_queries: 验证固定 DIRECT 会话并获得唯一 Agent。
        context_items: 读取 Runtime 已持久化的消息和工具事件。
        registry: 保留跨权限确认请求的原始 Agent 对象。
    """

    def __init__(
        self,
        agent_factory: AgentFactory,
        session_queries: SessionQueryRepository,
        context_items: ContextItemRepository,
        registry: RunRegistry,
    ) -> None:
        """创建 Web 对话应用服务。"""
        self.agent_factory = agent_factory
        self.session_queries = session_queries
        self.context_items = context_items
        self.registry = registry

    def start_message(self, session_id: str, text: str) -> Iterator[ServerEvent]:
        """同步验证并创建 Run，返回延迟执行的事件迭代器。

        Args:
            session_id: 已存在的固定 DIRECT 会话。
            text: 用户本次发送的非空文本。

        创建和冲突检查在返回 StreamingResponse 前完成，因此 404/409 仍能使用
        普通 JSON 错误，而不是已经开始传输后的 SSE 失败事件。
        """
        try:
            summary = self.session_queries.get_direct_detail(session_id)
        except ValueError as error:
            raise SessionNotRunnableError(session_id) from error
        if summary is None or summary.session.status != "ACTIVE":
            raise SessionNotRunnableError(session_id)
        agent = self.agent_factory.load(summary.agent_id, session_id)
        active = self.registry.create(session_id, summary.agent_id, agent)
        active.last_sequence_no = self._latest_sequence(session_id)
        return self._stream(active, agent.send(text), include_started=True)

    def resolve_permission(
        self,
        run_id: str,
        request: PermissionDecisionRequest,
    ) -> Iterator[ServerEvent]:
        """验证前端最小确认数据，并从原 Agent Runtime 恢复流。"""
        active = self.registry.get(run_id)
        if active is None:
            raise RunNotFoundError(run_id)
        if request.call_id != active.pending_call_id:
            raise PermissionMismatchError(request.call_id)
        response = PermissionResponse(
            call_id=request.call_id,
            decision=PermissionDecision(request.decision),
            scope=PermissionScope(request.scope),
        )
        # pending_call_id 在 Runtime 自身完成校验后才没有意义；迭代异常时仍由
        # SSE failure 结束该 Run，不允许同一次确认被重复提交。
        active.pending_call_id = None
        return self._stream(
            active,
            active.agent.resolve_permission(response),
            include_started=False,
        )

    def cancel(self, run_id: str) -> None:
        """停止一个活动 Run；不存在时返回稳定的未找到错误。"""
        if not self.registry.cancel(run_id):
            raise RunNotFoundError(run_id)

    def _stream(
        self,
        active: ActiveRun,
        runtime_events: Iterator[Any],
        *,
        include_started: bool,
    ) -> Iterator[ServerEvent]:
        """按 Runtime 产出顺序合并持久化工具事件和模型流事件。"""
        if include_started:
            yield self._event(active, "run.started", {"status": "running"})
        try:
            for runtime_event in runtime_events:
                # Runtime 先持久化 completed/function call，再把下一个可见事件
                # 交给宿主；先刷新时间线可保持 tool 和 message 的真实先后关系。
                yield from self._flush_context(active)
                if active.cancelled:
                    yield self._event(active, "run.completed", {"status": "cancelled"})
                    return
                if isinstance(runtime_event, PermissionRequiredEvent):
                    active.pending_call_id = runtime_event.request.call_id
                    yield self._permission_event(active, runtime_event)
                    return
                if not isinstance(runtime_event, LLMResponse):
                    continue
                if runtime_event.type == "text" and runtime_event.text:
                    yield self._event(
                        active,
                        "message.delta",
                        {"text": runtime_event.text},
                    )
                elif runtime_event.type == "error":
                    yield self._event(
                        active,
                        "run.failed",
                        {"code": "LLM_STREAM_FAILED", "message": "模型响应失败"},
                    )
                    self.registry.remove(active.run_id)
                    return
                elif runtime_event.type == "done" and runtime_event.is_stop:
                    yield self._event(active, "run.completed", {"status": "completed"})
                    self.registry.remove(active.run_id)
                    return

            # Runtime 正常结束却没有 done 或 permission，视为协议失败。
            yield self._event(
                active,
                "run.failed",
                {"code": "RUNTIME_ENDED", "message": "运行提前结束"},
            )
            self.registry.remove(active.run_id)
        except GeneratorExit:
            self.registry.remove(active.run_id)
            raise
        except Exception:
            # 任何内部异常都只返回稳定错误，不向浏览器暴露路径、SQL 或凭据。
            yield self._event(
                active,
                "run.failed",
                {"code": "RUN_FAILED", "message": "运行失败"},
            )
            self.registry.remove(active.run_id)

    def _flush_context(self, active: ActiveRun) -> Iterator[ServerEvent]:
        """把尚未发送的持久化 ContextItem 转换成完成类事件。"""
        items = self.context_items.list_after(
            active.session_id,
            active.last_sequence_no,
        )
        for item in items:
            active.last_sequence_no = item.sequence_no
            event = self._context_event(active, item)
            if event is not None:
                yield event

    def _context_event(
        self,
        active: ActiveRun,
        item: ContextItem,
    ) -> ServerEvent | None:
        """映射聊天和工具上下文；用户消息由前端乐观显示，不重复发送。"""
        if item.kind == "AGENT_MESSAGE":
            return self._event(
                active,
                "message.completed",
                {"itemId": item.id, "text": item.payload.get("text", "")},
            )
        if item.kind == "FUNCTION_CALL":
            return self._event(
                active,
                "tool.started",
                {
                    "itemId": item.id,
                    "callId": item.call_id,
                    "toolName": item.payload.get("name", ""),
                    "arguments": item.payload.get("arguments"),
                },
            )
        if item.kind == "FUNCTION_CALL_OUTPUT":
            return self._event(
                active,
                "tool.completed",
                {
                    "itemId": item.id,
                    "callId": item.call_id,
                    "output": item.payload.get("output"),
                },
            )
        return None

    def _permission_event(
        self,
        active: ActiveRun,
        event: PermissionRequiredEvent,
    ) -> ServerEvent:
        """仅公开用户判断所需的权限请求字段。"""
        request = event.request
        return self._event(
            active,
            "permission.required",
            {
                "callId": request.call_id,
                "toolName": request.tool_name,
                "action": request.action.value,
                "resource": request.resource,
                "allowedScopes": [scope.value for scope in event.available_scopes],
            },
        )

    def _latest_sequence(self, session_id: str) -> int:
        """读取开始运行前的时间线末尾，避免重发历史 ContextItem。"""
        items = self.context_items.list_after(session_id, 0)
        return 0 if not items else items[-1].sequence_no

    @staticmethod
    def _event(active: ActiveRun, event_type: str, data: dict[str, Any]) -> ServerEvent:
        """为所有事件补充一致的 runId 和 sessionId。"""
        return ServerEvent(
            type=event_type,
            run_id=active.run_id,
            session_id=active.session_id,
            data=data,
        )
