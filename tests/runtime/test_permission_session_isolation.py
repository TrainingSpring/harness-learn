"""跨 Session 权限暂停与确认隔离测试。"""

import sys
from pathlib import Path

import pytest


sys.path.insert(0, str(Path(__file__).parents[2] / "code" / "agent"))

from context.context import Context  # noqa: E402
from head.types import LLMResponse, LLMResponseOutputItem  # noqa: E402
from permission.PermissionManager import PermissionManager  # noqa: E402
from permission.types import (  # noqa: E402
    PermissionAction,
    PermissionDecision,
    PermissionMode,
    PermissionRequirement,
    PermissionResponse,
    PermissionScope,
)
from runtime.runtime import Runtime, RuntimeState  # noqa: E402
from runtime.runtime_events import PermissionRequiredEvent  # noqa: E402
from session.ExecutionContext import ExecutionContext  # noqa: E402
from tools.tools import Tools  # noqa: E402
from tools.types import Tool, ToolResult  # noqa: E402


class PermissionLLM:
    """按会话返回一次工具调用的最小模型。"""

    def __init__(self, call_id: str) -> None:
        self.system_prompt = ""
        self.call_id = call_id

    def call_responses_stream(self, _model_input, _tools):
        yield LLMResponse(
            type="done",
            data=[
                LLMResponseOutputItem(
                    type="function_call",
                    id=f"fc_{self.call_id}",
                    content=None,
                    name="write",
                    arguments='{"target_path":"src/app.py"}',
                    call_id=self.call_id,
                    status="completed",
                )
            ],
            is_stop=False,
        )


def _waiting_runtime(session_id: str, call_id: str) -> tuple[Runtime, Context]:
    """创建一个会在写入工具前暂停的独立 Session Runtime。"""
    execution_context = ExecutionContext("/workspace", "agent_TEST00005", session_id)
    tools = Tools(execution_context)
    tools.register(
        Tool(
            {"name": "write"},
            lambda _ctx, **_arguments: ToolResult.success({"ok": True}),
            PermissionRequirement(PermissionAction.FILE_WRITE, "target_path"),
        )
    )
    runtime = Runtime(
        PermissionLLM(call_id),
        tools,
        execution_context,
        PermissionManager(
            mode=PermissionMode.BUILD,
            session_id=execution_context.session_id,
            project_path=execution_context.project_path,
        ),
    )
    return runtime, Context(PermissionLLM(call_id), session_id=session_id)


def test_permission_confirmation_cannot_cross_session_runtime():
    """Session A 的 call_id 不能恢复 Session B 等待中的工具调用。"""
    runtime_a, context_a = _waiting_runtime("session_TEST07", "call_A")
    runtime_b, context_b = _waiting_runtime("session_TEST08", "call_B")

    first = list(runtime_a.run(context_a))
    second = list(runtime_b.run(context_b))
    assert isinstance(first[0], PermissionRequiredEvent)
    assert isinstance(second[0], PermissionRequiredEvent)

    with pytest.raises(ValueError, match="call_id"):
        list(runtime_b.resolve_permission(
            context_b,
            PermissionResponse(
                call_id="call_A",
                decision=PermissionDecision.ALLOW,
                scope=PermissionScope.ONCE,
            ),
        ))

    assert runtime_a.state is RuntimeState.WAITING_PERMISSION
    assert runtime_b.state is RuntimeState.WAITING_PERMISSION
