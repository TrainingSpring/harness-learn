"""Agent 运行时循环，以及工具权限预检的暂停与恢复。"""

import os
from collections import deque
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Generator, Literal

from context.context import Context
from head.llm import LLM
from head.types import LLMResponse, LLMResponseOutputItem
from permission.PermissionManager import PermissionManager
from permission.types import (
    PermissionDecision,
    PermissionRequest,
    PermissionResponse,
    PermissionScope,
)
from runtime.ExecutionContext import ExecutionContext
from runtime.context_service import ContextService
from tools.tools import Tools
from tools.types import PreparedToolCall, ToolCallPreparationError, ToolResult


class RuntimeState(StrEnum):
    """Runtime 当前所处的生命周期状态。"""

    IDLE = "idle"
    RUNNING = "running"
    WAITING_PERMISSION = "waiting_permission"


@dataclass(frozen=True)
class PermissionRequiredEvent:
    """通知宿主暂停并向用户询问权限的运行时事件。

    Attributes:
        type: 事件类型，固定为 ``permission_required``，便于 CLI/UI 分发。
        request: 要展示给用户的真实动作、资源和调用身份。
        available_scopes: 用户可选择的授权范围；首版包含本次、会话和
            当前 Agent 三种范围。
    """

    type: Literal["permission_required"]
    request: PermissionRequest
    available_scopes: tuple[PermissionScope, ...] = (
        PermissionScope.ONCE,
        PermissionScope.SESSION,
        PermissionScope.AGENT,
    )


@dataclass(frozen=True)
class PendingToolCall:
    """Runtime 暂停时保存的完整工具调用。

    Attributes:
        call: 已解析参数和权限请求的工具调用，恢复时必须复用它，避免
            从模型文本重新解析出不同参数。
        command: bash 原始命令，仅供恢复前后的硬安全判断使用；文件工具
            为 None。
    """

    call: PreparedToolCall
    command: str | None


class Runtime:
    """协调 LLM、Context、Tools 和 PermissionManager 的 Agent 执行循环。

    Attributes:
        llm: 产生流式 LLM 响应的适配器。
        tools: 负责工具准备、执行和结果编码的工具集。
        context: 保存发送给模型的 Responses input items。
        permission: 对已构造的 PermissionRequest 作出权限决定的管理器。
        ctx: 本次 Agent 会话的不可变执行环境。
        state: 对外可观察的运行状态；WAITING_PERMISSION 表示必须调用
            resolve_permission() 才能继续。
    """

    def __init__(
        self,
        llm: LLM,
        tools: Tools,
        context: Context,
        ctx: ExecutionContext,
        permission: PermissionManager,
        context_service: ContextService | None = None,
        participant_id: str | None = None,
    ) -> None:
        """创建运行时协调器。

        Args:
            llm: LLM 调用适配器。
            tools: 当前 Agent 已注册的工具集。
            context: 当前会话的模型上下文。
            ctx: 工具共享的执行环境和身份信息。
            permission: 当前 Agent 的权限管理器。
            context_service: 可选的业务上下文持久化服务；为空时只维护内存
                Context，保留纯运行时测试和旧入口的行为。
            participant_id: 当前 Agent 在会话中的参与者身份；启用
                context_service 时必须提供，用于记录 Agent 作者。
        """
        if context_service is not None and not participant_id:
            raise ValueError("启用 context_service 时必须提供 participant_id")
        self.llm = llm
        self.tools = tools
        self.context = context
        self.permission = permission
        self.ctx = ctx
        self.context_service = context_service
        self.participant_id = participant_id
        self._state = RuntimeState.IDLE
        self._pending_permission: PendingToolCall | None = None
        self._tool_queue: deque[PreparedToolCall] = deque()
        self.sys_message = [
            {
                "type": "message",
                "role": "developer",
                "content": [
                    {
                        "type": "input_text",
                        "text": f"当前系统环境：{'windows' if os.name == 'nt' else 'linux'},工作目录{ctx.workspace}",
                    }
                ],
            }
        ]

    @property
    def state(self) -> RuntimeState:
        """返回当前运行状态，供宿主判断是否需要展示权限交互。"""
        return self._state

    def call_llm(self) -> Generator[LLMResponse, Any, None]:
        """使用当前 Context 和工具 schema 请求一次 LLM 流。"""
        return self.llm.call_responses_stream(
            self.context.get_msg(self.sys_message),
            self.tools.list,
        )

    def run(
        self,
        message: str,
    ) -> Generator[LLMResponse | PermissionRequiredEvent, None, None]:
        """开始一次用户消息的 LLM loop。

        Args:
            message: 用户输入的消息文本。

        Yields:
            LLM 流事件，或在工具权限需要确认时产生的
            PermissionRequiredEvent。

        Runtime 在 WAITING_PERMISSION 或 RUNNING 状态再次接收新消息会
        抛错，防止一个 pending 工具调用被另一条消息覆盖。
        """
        if self._state is not RuntimeState.IDLE:
            raise ValueError(f"Runtime 当前状态为 {self._state.value}，不能开始新消息")
        if self.context_service is not None:
            self.context_service.append_user_message(message)
        self.context.append_msg(message)
        self._state = RuntimeState.RUNNING
        yield from self._run_llm_loop()

    def _run_llm_loop(
        self,
    ) -> Generator[LLMResponse | PermissionRequiredEvent, None, None]:
        """持续请求 LLM，直到结束或遇到需要用户确认的工具调用。"""
        while True:
            for response in self.call_llm():
                if response.type != "done":
                    yield response
                    continue

                self._record_response_items(response)
                permission_event = self._drain_tool_queue()
                if permission_event is not None:
                    self._state = RuntimeState.WAITING_PERMISSION
                    yield permission_event
                    return

                if response.is_stop:
                    self._state = RuntimeState.IDLE
                    yield response
                    return

    def _record_response_items(self, response: LLMResponse) -> None:
        """记录 LLM 输出，并将 function_call 转为待处理队列。

        Args:
            response: 包含已完成 Responses 输出项的 done 事件。

        参数准备失败也会追加标准 ToolResult 失败输出，但不会进入权限
        检查，因为没有合法的 PermissionRequest 可供判断。
        """
        usage = response.usage
        for item in response.data or []:
            if item.type == "message":
                if self.context_service is not None:
                    self.context_service.append_agent_message(
                        self.participant_id,
                        self._message_text(item),
                    )
                self.context.append_msg(item, usage=usage)
                continue
            if item.type != "function_call":
                continue

            if self.context_service is not None:
                self.context_service.append_function_call(
                    self.participant_id,
                    call_id=item.call_id,
                    name=item.name,
                    arguments=item.arguments,
                )
            self.context.append_msg(item)
            try:
                call = self.tools.prepare_call(
                    item.name,
                    item.arguments,
                    item.call_id,
                )
            except ToolCallPreparationError as error:
                self._append_tool_result(
                    item.call_id,
                    ToolResult.failure(
                        error.error.code,
                        error.error.message,
                        details=error.error.details,
                    ),
                )
                continue
            self._tool_queue.append(call)

    def _drain_tool_queue(self) -> PermissionRequiredEvent | None:
        """按 FIFO 顺序预检并执行队列中的工具调用。

        Returns:
            首个需要用户确认的事件；队列全部处理完成时返回 None。

        遇到 ASK 时，当前调用被单独保存为 pending，后续调用留在队列中。
        这样恢复后仍能保持模型原始输出的调用顺序。
        """
        while self._tool_queue:
            call = self._tool_queue.popleft()
            command = self._command_for(call)
            decision = self.permission.check(
                call.permission_request,
                command=command,
            )
            if decision is PermissionDecision.ALLOW:
                self._append_tool_result(call.call_id, self.tools.execute(call))
                continue
            if decision is PermissionDecision.DENY:
                self._append_tool_result(
                    call.call_id,
                    self._permission_denied_result(call.permission_request),
                )
                continue

            self._pending_permission = PendingToolCall(call, command)
            return PermissionRequiredEvent(
                type="permission_required",
                request=call.permission_request,
            )
        return None

    def resolve_permission(
        self,
        response: PermissionResponse,
    ) -> Generator[LLMResponse | PermissionRequiredEvent, None, None]:
        """处理用户确认并从 pending 工具调用处继续执行。

        Args:
            response: 只包含 call_id、allow/deny 和 scope 的用户选择。

        Yields:
            当前队列产生的下一个权限事件，或恢复后的 LLM 流事件。

        Raises:
            ValueError: Runtime 没有等待权限，或 call_id 与 pending 调用不符。

        清除 pending 状态发生在确认校验和规则写入之后；错误确认不会改变
        Runtime 状态，也不会触发工具执行。
        """
        if self._state is not RuntimeState.WAITING_PERMISSION:
            raise ValueError("Runtime 当前没有等待处理的权限请求")
        pending = self._pending_permission
        if pending is None or response.call_id != pending.call.call_id:
            raise ValueError("权限响应的 call_id 与待确认调用不匹配")

        request = pending.call.permission_request
        grant_resource = self.tools.default_grant_resource(request)
        if response.decision is PermissionDecision.ALLOW:
            self.permission.grant(
                request,
                scope=response.scope,
                resource=grant_resource,
            )
            result = self.tools.execute(pending.call)
        else:
            self.permission.deny(
                request,
                scope=response.scope,
                resource=grant_resource,
            )
            result = self._permission_denied_result(request)

        self._pending_permission = None
        self._state = RuntimeState.RUNNING
        self._append_tool_result(pending.call.call_id, result)

        permission_event = self._drain_tool_queue()
        if permission_event is not None:
            self._state = RuntimeState.WAITING_PERMISSION
            yield permission_event
            return
        yield from self._run_llm_loop()

    def _append_tool_result(self, call_id: str, result: ToolResult) -> None:
        """将 ToolResult 统一编码后追加为 function_call_output。"""
        encoded_output = self.tools.encode_result(result)
        if self.context_service is not None:
            self.context_service.append_function_call_output(
                self.participant_id,
                call_id=call_id,
                output=encoded_output,
            )
        self.context.append_msg(
            {
                "type": "function_call_output",
                "call_id": call_id,
                "output": encoded_output,
            }
        )

    @staticmethod
    def _message_text(item: LLMResponseOutputItem) -> str:
        """从 LLM 消息输出提取纯文本，供业务上下文持久化。"""
        content = item.content
        if isinstance(content, str):
            return content
        if not isinstance(content, list):
            return ""
        parts: list[str] = []
        for part in content:
            if isinstance(part, dict):
                text = part.get("text")
            else:
                text = getattr(part, "text", None)
            if isinstance(text, str):
                parts.append(text)
        return "".join(parts)

    @staticmethod
    def _command_for(call: PreparedToolCall) -> str | None:
        """提取 bash 原始命令供硬安全策略检查。"""
        command = call.arguments.get("command")
        return command if isinstance(command, str) else None

    @staticmethod
    def _permission_denied_result(request: PermissionRequest) -> ToolResult:
        """构造统一的权限拒绝工具结果。"""
        return ToolResult.failure(
            "PERMISSION_DENIED",
            "当前 Agent 无权执行该工具调用",
            details={
                "action": request.action.value,
                "resource": request.resource,
            },
        )
