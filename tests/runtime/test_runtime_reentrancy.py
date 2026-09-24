"""Runtime 执行状态和权限恢复的 Context 隔离测试。"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "code" / "agent"))

from context.context import Context  # noqa: E402
from head.types import LLMResponse, LLMResponseOutputItem  # noqa: E402
from permission.PermissionManager import PermissionManager  # noqa: E402
from permission.policies import ProtectedResourcePolicy  # noqa: E402
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
    def __init__(self, responses):
        self.system_prompt = ""
        self.responses = list(responses)

    def call_responses_stream(self, _model_input, _tools):
        yield from self.responses.pop(0)


def _call(call_id):
    return LLMResponseOutputItem(
        type="function_call",
        id=f"fc_{call_id}",
        content=None,
        name="write",
        arguments='{"target_path":"/outside/src/app.py"}',
        call_id=call_id,
        status="completed",
    )


def test_running_runtime_rejects_a_second_run_until_the_first_finishes():
    llm = PermissionLLM([
        iter([LLMResponse(type="text", text="处理中")]),
    ])
    execution_context = ExecutionContext("/workspace", "agent_TEST00002", "session_TEST03")
    tools = Tools(execution_context)
    permission = PermissionManager(
        mode=PermissionMode.BUILD,
        session_id=execution_context.session_id,
        project_path=execution_context.project_path,
    )
    runtime = Runtime(llm, tools, execution_context, permission)
    context = Context(PermissionLLM([]), session_id=execution_context.session_id)
    events = runtime.run(context)

    next(events)
    assert runtime.state is RuntimeState.RUNNING
    with pytest.raises(ValueError, match="不能开始新消息"):
        list(runtime.run(context))


def test_permission_resume_writes_tool_output_to_the_passed_context():
    executions = []

    def write(_ctx, **arguments):
        executions.append(arguments)
        return ToolResult.success({"written": arguments["target_path"]})

    execution_context = ExecutionContext("/workspace", "agent_TEST00003", "session_TEST04")
    tools = Tools(execution_context)
    tools.register(
        Tool(
            {"name": "write"},
            write,
            PermissionRequirement(PermissionAction.FILE_WRITE, "target_path"),
        )
    )
    llm = PermissionLLM([
        iter([LLMResponse(type="done", data=[_call("call_001")], is_stop=False)]),
        iter([LLMResponse(type="done", data=[], is_stop=True)]),
    ])
    permission = PermissionManager(
        mode=PermissionMode.BUILD,
        session_id=execution_context.session_id,
        project_path=execution_context.project_path,
        protected_resource_policy=ProtectedResourcePolicy(["/system"]),
    )
    runtime = Runtime(llm, tools, execution_context, permission)
    context_a = Context(PermissionLLM([]), session_id=execution_context.session_id)
    context_b = Context(PermissionLLM([]), session_id="session_TEST05")

    events = list(runtime.run(context_a))
    assert isinstance(events[0], PermissionRequiredEvent)

    list(runtime.resolve_permission(
        context_a,
        PermissionResponse(
            call_id="call_001",
            decision=PermissionDecision.ALLOW,
            scope=PermissionScope.ONCE,
        ),
    ))

    assert executions == [{"target_path": "/outside/src/app.py"}]
    assert context_a.messages[-1]["type"] == "function_call_output"
    assert context_b.messages == []


def test_cancel_clears_pending_permission_and_returns_runtime_to_idle():
    execution_context = ExecutionContext("/workspace", "agent_TEST00004", "session_TEST06")
    tools = Tools(execution_context)
    tools.register(
        Tool(
            {"name": "write"},
            lambda _ctx, **_arguments: ToolResult.success({"ok": True}),
            PermissionRequirement(PermissionAction.FILE_WRITE, "target_path"),
        )
    )
    runtime = Runtime(
        PermissionLLM([
            iter([LLMResponse(type="done", data=[_call("call_003")], is_stop=False)]),
        ]),
        tools,
        execution_context,
        PermissionManager(
            mode=PermissionMode.BUILD,
            session_id=execution_context.session_id,
            project_path=execution_context.project_path,
        ),
    )
    context = Context(PermissionLLM([]), session_id=execution_context.session_id)

    events = list(runtime.run(context))
    assert isinstance(events[0], PermissionRequiredEvent)

    runtime.cancel()

    assert runtime.state is RuntimeState.IDLE
    with pytest.raises(ValueError, match="没有等待处理的权限请求"):
        list(runtime.resolve_permission(
            context,
            PermissionResponse(
                call_id="call_003",
                decision=PermissionDecision.ALLOW,
                scope=PermissionScope.ONCE,
            ),
        ))
