"""Agent 运行时循环，以及工具权限预检的暂停与恢复。"""

import os
from collections import deque
from enum import StrEnum
from typing import Generator

from context.context import Context
from head.llm import LLM
from head.types import LLMResponse, LLMResponseOutputItem
from permission.PermissionManager import PermissionManager
from permission.types import PermissionDecision, PermissionRequest, PermissionResponse
from session.ExecutionContext import ExecutionContext
from tools.tools import Tools
from tools.types import PreparedToolCall, ToolCallPreparationError, ToolResult

from .runtime_events import PendingToolCall, PermissionRequiredEvent, RuntimeEvent


class RuntimeState(StrEnum):
    """Runtime 当前所处的生命周期状态。"""

    IDLE = "idle"
    RUNNING = "running"
    WAITING_PERMISSION = "waiting_permission"


class Runtime:
    """协调 LLM、Tools 和 PermissionManager 的 Agent 执行循环。

    Attributes:
        llm: 产生流式 LLM 响应的适配器。
        tools: 负责工具准备、执行和结果编码的工具集。
        permission: 对已构造的 PermissionRequest 作出权限决定的管理器。
        ctx: 本次 Agent 会话的不可变执行环境，包含作者 agent_id。
        state: 对外可观察的运行状态；WAITING_PERMISSION 表示必须调用
            resolve_permission() 才能继续。
    """

    def __init__(
        self,
        llm: LLM,
        tools: Tools,
        ctx: ExecutionContext,
        permission: PermissionManager,
    ) -> None:
        """创建运行时协调器。

        Args:
            llm: LLM 调用适配器。
            tools: 当前 Agent 已注册的工具集。
            ctx: 工具共享的执行环境和身份信息。
            permission: 当前 Agent 的权限管理器。
        """
        self.llm = llm
        self.tools = tools
        self.permission = permission
        self.ctx = ctx
        self._state = RuntimeState.IDLE
        self._cancelled = False
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

    def call_llm(self, context: Context) -> Generator[LLMResponse, None, None]:
        """使用调用方提供的 Context 和工具 schema 请求一次 LLM 流。"""
        return self.llm.call_responses_stream(
            context.to_model_input(self.sys_message),
            self.tools.list,
        )

    def run(
        self,
        context: Context,
    ) -> Generator[RuntimeEvent, None, None]:
        """使用调用方提供的 Context 开始一次 Agent Loop。

        Args:
            context: 当前 Session 持有的模型上下文；Runtime 不保存它。

        Yields:
            LLM 流事件，或在工具权限需要确认时产生的
            PermissionRequiredEvent。

        Runtime 在 WAITING_PERMISSION 或 RUNNING 状态再次接收新消息会
        抛错，防止一个 pending 工具调用被另一条消息覆盖。
        """
        self._validate_context(context)
        if self._state is not RuntimeState.IDLE:
            raise ValueError(f"Runtime 当前状态为 {self._state.value}，不能开始新消息")
        self._cancelled = False
        self._state = RuntimeState.RUNNING
        yield from self._run_llm_loop(context)

    def cancel(self) -> None:
        """取消当前运行，丢弃未执行的工具调用和权限暂停状态。"""
        self._cancelled = True
        self._pending_permission = None
        self._tool_queue.clear()
        self._state = RuntimeState.IDLE

    def _run_llm_loop(
        self,
        context: Context,
    ) -> Generator[RuntimeEvent, None, None]:
        """持续请求 LLM，直到结束或遇到需要用户确认的工具调用。"""
        while True:
            if self._cancelled:
                self._state = RuntimeState.IDLE
                return
            for response in self.call_llm(context):
                if self._cancelled:
                    self._state = RuntimeState.IDLE
                    return
                if response.type != "done":
                    yield response
                    continue

                self._record_response_items(context, response)
                permission_event = self._drain_tool_queue(context)
                if permission_event is not None:
                    self._state = RuntimeState.WAITING_PERMISSION
                    yield permission_event
                    return

                if response.is_stop:
                    self._state = RuntimeState.IDLE
                    yield response
                    return

    def _record_response_items(
        self,
        context: Context,
        response: LLMResponse,
    ) -> None:
        """记录 LLM 输出，并将 function_call 转为待处理队列。

        Args:
            response: 包含已完成 Responses 输出项的 done 事件。

        参数准备失败也会追加标准 ToolResult 失败输出，但不会进入权限
        检查，因为没有合法的 PermissionRequest 可供判断。
        """
        usage = response.usage
        for item in response.data or []:
            if item.type == "message":
                context.append_agent_message(
                    self.ctx.agent_id,
                    self._message_text(item),
                    usage=usage,
                )
                continue
            if item.type != "function_call":
                continue

            context.append_function_call(self.ctx.agent_id, item=item)
            try:
                call = self.tools.prepare_call(
                    item.name,
                    item.arguments,
                    item.call_id,
                )
            except ToolCallPreparationError as error:
                self._append_tool_result(
                    context,
                    item.call_id,
                    ToolResult.failure(
                        error.error.code,
                        error.error.message,
                        details=error.error.details,
                    ),
                )
                continue
            self._tool_queue.append(call)

    def _drain_tool_queue(self, context: Context) -> PermissionRequiredEvent | None:
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
                self._append_tool_result(context, call.call_id, self.tools.execute(call))
                continue
            if decision is PermissionDecision.DENY:
                self._append_tool_result(
                    context,
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
        context: Context,
        response: PermissionResponse,
    ) -> Generator[RuntimeEvent, None, None]:
        """处理用户确认并从 pending 工具调用处继续执行。

        Args:
            response: 只包含 call_id、allow/deny 和 scope 的用户选择。

        Yields:
            当前队列产生的下一个权限事件，或恢复后的 LLM 流事件。

        Raises:
            TypeError: context 不是 Context 实例。
            ValueError: Runtime 没有等待权限，或 call_id 与 pending 调用不符。

        清除 pending 状态发生在确认校验和规则写入之后；错误确认不会改变
        Runtime 状态，也不会触发工具执行。
        """
        self._validate_context(context)
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
        self._append_tool_result(context, pending.call.call_id, result)

        permission_event = self._drain_tool_queue(context)
        if permission_event is not None:
            self._state = RuntimeState.WAITING_PERMISSION
            yield permission_event
            return
        yield from self._run_llm_loop(context)

    def _append_tool_result(
        self,
        context: Context,
        call_id: str,
        result: ToolResult,
    ) -> None:
        """将 ToolResult 统一编码后追加为 function_call_output。"""
        encoded_output = self.tools.encode_result(result)
        context.append_function_call_output(
            self.ctx.agent_id,
            {
                "type": "function_call_output",
                "call_id": call_id,
                "output": encoded_output,
            },
        )

    @staticmethod
    def _validate_context(context: Context) -> None:
        """验证调用方传入的是 Session 的 Context。"""
        if not isinstance(context, Context):
            raise TypeError("context 必须是 Context")

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
