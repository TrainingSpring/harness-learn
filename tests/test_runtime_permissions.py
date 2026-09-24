"""Runtime 权限预检、暂停和恢复流程的测试。"""

import sys
import unittest
import copy
from pathlib import Path
from unittest.mock import Mock


sys.path.insert(0, str(Path(__file__).parents[1] / "code" / "agent"))

from context.context import Context  # noqa: E402
from head.types import LLMResponse, LLMResponseOutputItem  # noqa: E402
from permission.PermissionManager import PermissionManager  # noqa: E402
from permission.policies import HardSafetyPolicy, ProtectedResourcePolicy  # noqa: E402
from permission.types import (  # noqa: E402
    PermissionAction,
    PermissionDecision,
    PermissionMode,
    PermissionResponse,
    PermissionScope,
)
from session.ExecutionContext import ExecutionContext  # noqa: E402
from runtime.runtime import (  # noqa: E402
    Runtime,
    RuntimeState,
)
from runtime.runtime_events import PermissionRequiredEvent  # noqa: E402
from tools.tools import Tools  # noqa: E402
from tools.types import Tool, ToolResult  # noqa: E402
from permission.types import PermissionRequirement  # noqa: E402


class FakeLLM:
    """满足 Context 初始化和 Runtime 调用所需最小接口的假 LLM。"""

    def __init__(self, responses):
        """保存按次返回的 LLM 响应，并统计请求次数。"""
        self.system_prompt = ""
        self.responses = list(responses)
        self.call_count = 0
        self.contexts = []

    def next_response(self, context):
        """返回下一次预设的流事件。"""
        self.call_count += 1
        self.contexts.append(copy.deepcopy(context.export()))
        response = self.responses.pop(0)
        return iter(response)

    def call_responses(self, _input):
        """满足 Context 压缩路径的最小接口。"""
        return Mock(output_text="summary")


class RuntimePermissionTests(unittest.TestCase):
    """验证权限决定如何控制工具执行和 LLM loop。"""

    def setUp(self):
        """创建可记录执行次数的 write 工具和 Runtime。"""
        self.executions = []
        self.ctx = ExecutionContext("/workspace", "code_editor", "session_001")
        self.tools = Tools(self.ctx)
        self.tools.register(
            Tool(
                {"name": "write"},
                self._write,
                PermissionRequirement(PermissionAction.FILE_WRITE, "target_path"),
            )
        )
        self.permission = PermissionManager(
            mode=PermissionMode.BUILD,
            session_id=self.ctx.session_id,
            project_path=self.ctx.project_path,
            hard_safety_policy=HardSafetyPolicy(),
            protected_resource_policy=ProtectedResourcePolicy(["/system"]),
        )

    def _write(self, _ctx, **arguments):
        """记录一次工具执行并返回成功结果。"""
        self.executions.append(arguments)
        return ToolResult.success({"written": arguments["target_path"]})

    @staticmethod
    def _function_call(call_id, name="write", arguments='{"target_path":"../outside.txt"}'):
        """构造 Runtime 使用的 Responses 输出项。"""
        return LLMResponseOutputItem(
            type="function_call",
            id=f"fc_{call_id}",
            content=None,
            name=name,
            arguments=arguments,
            call_id=call_id,
            status="completed",
        )

    def _runtime(self, responses):
        """用预设 LLM 响应构造 Runtime，并替换网络调用。"""
        llm = FakeLLM(responses)
        context = Context(FakeLLM([]), session_id=self.ctx.session_id)
        runtime = Runtime(llm, self.tools, self.ctx, self.permission)
        runtime.call_llm = llm.next_response
        return runtime, context, llm

    def test_ask_yields_permission_event_without_executing_or_calling_llm_again(self):
        """ASK 必须暂停在权限请求处，工具和下一轮 LLM 都不能执行。"""
        runtime, context, llm = self._runtime([
            [LLMResponse("done", data=[self._function_call("call_001")], is_stop=False)]
        ])

        context.append_user_message("write a file")
        events = list(runtime.run(context))

        self.assertEqual(len(events), 1)
        self.assertIsInstance(events[0], PermissionRequiredEvent)
        self.assertEqual(events[0].request.call_id, "call_001")
        self.assertEqual(runtime.state, RuntimeState.WAITING_PERMISSION)
        self.assertEqual(self.executions, [])
        self.assertEqual(llm.call_count, 1)

    def test_allow_response_executes_original_call_once_and_resumes_llm(self):
        """用户允许后恢复原调用，写入结果并继续下一轮 LLM。"""
        runtime, context, llm = self._runtime([
            [LLMResponse("done", data=[self._function_call("call_001")], is_stop=False)],
            [LLMResponse("done", data=[], is_stop=True)],
        ])
        context.append_user_message("write a file")
        list(runtime.run(context))

        events = list(runtime.resolve_permission(
            context,
            PermissionResponse(
                call_id="call_001",
                decision=PermissionDecision.ALLOW,
                scope=PermissionScope.ONCE,
            )
        ))

        self.assertEqual(len(self.executions), 1)
        self.assertEqual(self.executions[0]["target_path"], "/outside.txt")
        self.assertEqual(runtime.state, RuntimeState.IDLE)
        self.assertEqual(llm.call_count, 2)
        self.assertEqual(
            llm.contexts[1][-1]["type"],
            "function_call_output",
        )
        self.assertEqual(llm.contexts[1][-1]["call_id"], "call_001")
        output = context.messages[-1]
        self.assertEqual(output["type"], "function_call_output")
        self.assertEqual(output["call_id"], "call_001")

    def test_deny_response_never_executes_tool_but_returns_structured_failure(self):
        """用户拒绝后不执行工具，而是向模型追加标准失败结果。"""
        runtime, context, _llm = self._runtime([
            [LLMResponse("done", data=[self._function_call("call_001")], is_stop=False)],
            [LLMResponse("done", data=[], is_stop=True)],
        ])
        context.append_user_message("write a file")
        list(runtime.run(context))

        list(runtime.resolve_permission(
            context,
            PermissionResponse(
                call_id="call_001",
                decision=PermissionDecision.DENY,
                scope=PermissionScope.ONCE,
            )
        ))

        self.assertEqual(self.executions, [])
        output = context.messages[-1]
        self.assertEqual(output["type"], "function_call_output")
        self.assertIn('"PERMISSION_DENIED"', output["output"])

    def test_invalid_or_repeated_permission_response_does_not_execute_call(self):
        """错误 call_id 和重复确认都不能改变 pending 状态或触发执行。"""
        runtime, context, _llm = self._runtime([
            [LLMResponse("done", data=[self._function_call("call_001")], is_stop=False)],
            [LLMResponse("done", data=[], is_stop=True)],
        ])
        context.append_user_message("write a file")
        list(runtime.run(context))

        with self.assertRaises(ValueError):
            list(runtime.resolve_permission(
                context,
                PermissionResponse(
                    call_id="other-call",
                    decision=PermissionDecision.ALLOW,
                    scope=PermissionScope.ONCE,
                )
            ))
        self.assertEqual(self.executions, [])

        list(runtime.resolve_permission(
            context,
            PermissionResponse(
                call_id="call_001",
                decision=PermissionDecision.DENY,
                scope=PermissionScope.ONCE,
            )
        ))
        with self.assertRaises(ValueError):
            list(runtime.resolve_permission(
                context,
                PermissionResponse(
                    call_id="call_001",
                    decision=PermissionDecision.ALLOW,
                    scope=PermissionScope.ONCE,
                )
            ))
        self.assertEqual(self.executions, [])

    def test_multiple_calls_remain_in_fifo_order_after_first_call_asks(self):
        """同一轮多个调用中，首个 ASK 不能丢失后续调用。"""
        runtime, context, _llm = self._runtime([
            [LLMResponse(
                "done",
                data=[
                    self._function_call("call_001"),
                    self._function_call("call_002"),
                ],
                is_stop=False,
            )],
            [LLMResponse("done", data=[], is_stop=True)],
        ])
        context.append_user_message("write two files")
        first_events = list(runtime.run(context))
        self.assertEqual(first_events[0].request.call_id, "call_001")

        second_events = list(runtime.resolve_permission(
            context,
            PermissionResponse(
                call_id="call_001",
                decision=PermissionDecision.ALLOW,
                scope=PermissionScope.ONCE,
            )
        ))
        self.assertEqual(second_events[0].request.call_id, "call_002")
        self.assertEqual(len(self.executions), 1)

        list(runtime.resolve_permission(
            context,
            PermissionResponse(
                call_id="call_002",
                decision=PermissionDecision.DENY,
                scope=PermissionScope.ONCE,
            )
        ))
        self.assertEqual(len(self.executions), 1)


if __name__ == "__main__":
    unittest.main()
