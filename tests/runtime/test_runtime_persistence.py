"""Runtime 写入调用方 Context 的边界测试。"""

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parents[2] / "code" / "agent"))

from context.context import Context  # noqa: E402
from head.types import LLMResponse, LLMResponseOutputItem  # noqa: E402
from permission.PermissionManager import PermissionManager  # noqa: E402
from permission.policies import ProtectedResourcePolicy  # noqa: E402
from permission.types import PermissionMode  # noqa: E402
from session.ExecutionContext import ExecutionContext  # noqa: E402
from runtime.runtime import Runtime  # noqa: E402
from tools.tools import Tools  # noqa: E402


class FakeLLM:
    """返回一轮 Agent 文本消息的最小 LLM。"""

    def call_responses_stream(self, _input, _tools):
        """返回结束响应，模拟 Agent 输出一条消息。"""
        yield LLMResponse(
            type="done",
            data=[
                LLMResponseOutputItem(
                    type="message",
                    id="msg_001",
                    content=[{"type": "output_text", "text": "已完成"}],
                    name=None,
                    arguments=None,
                    call_id=None,
                    status="completed",
                )
            ],
            is_stop=True,
        )


class RuntimePersistenceTests(unittest.TestCase):
    """验证 Runtime 只修改调用方提供的上下文。"""

    def test_run_records_agent_message_in_passed_context(self):
        """用户消息由调用方追加，Agent 输出由 Runtime 追加到同一 Context。"""
        ctx = ExecutionContext(
            "/workspace",
            "agent_1V3ASAXQ2A",
            "session_4N9C1R7WBA",
        )
        tools = Tools(ctx)
        context = Context(FakeLLM(), session_id=ctx.session_id)
        context.append_user_message("请完成任务")
        runtime = Runtime(
            FakeLLM(),
            tools,
            ctx,
            PermissionManager(
                mode=PermissionMode.BUILD,
                workspace="/workspace",
                agent_id="agent_1V3ASAXQ2A",
                protected_resource_policy=ProtectedResourcePolicy(["/system"]),
            ),
        )

        list(runtime.run(context))

        self.assertEqual(context.messages[0]["content"], "请完成任务")
        self.assertEqual(context.messages[1]["content"], "已完成")
        self.assertFalse(hasattr(runtime, "context_service"))


if __name__ == "__main__":
    unittest.main()
