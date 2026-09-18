"""Runtime 写入 ContextService 的集成边界测试。"""

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parents[2] / "code" / "agent"))

from context.context import Context  # noqa: E402
from head.types import LLMResponse, LLMResponseOutputItem  # noqa: E402
from permission.PermissionManager import PermissionManager  # noqa: E402
from permission.policies import ProtectedResourcePolicy  # noqa: E402
from permission.types import PermissionMode  # noqa: E402
from runtime.ExecutionContext import ExecutionContext  # noqa: E402
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


class RecordingContextService:
    """记录业务事件的测试替身，不暴露 Responses 协议字段。"""

    def __init__(self):
        """初始化事件记录。"""
        self.events = []

    def append_user_message(self, text):
        """记录用户消息。"""
        self.events.append(("user", text))

    def append_agent_message(self, author_agent_id, text):
        """记录 Agent 消息及其作者。"""
        self.events.append(("agent", author_agent_id, text))


class RuntimePersistenceTests(unittest.TestCase):
    """验证 Runtime 事件同时进入持久化服务和内存投影。"""

    def test_run_records_user_and_agent_business_events(self):
        """启用 ContextService 后，用户和 Agent 消息都应被记录。"""
        ctx = ExecutionContext(
            "/workspace",
            "agent_1V3ASAXQ2A",
            "session_4N9C1R7WBA",
        )
        tools = Tools(ctx)
        context_service = RecordingContextService()
        runtime = Runtime(
            FakeLLM(),
            tools,
            Context(FakeLLM(), session_id=ctx.session_id),
            ctx,
            PermissionManager(
                mode=PermissionMode.BUILD,
                workspace="/workspace",
                agent_id="agent_1V3ASAXQ2A",
                protected_resource_policy=ProtectedResourcePolicy(["/system"]),
            ),
            context_service=context_service,
        )

        list(runtime.run("请完成任务"))

        self.assertEqual(
            context_service.events,
            [
                ("user", "请完成任务"),
                ("agent", "agent_1V3ASAXQ2A", "已完成"),
            ],
        )
        self.assertEqual(runtime.context.messages[0]["content"], "请完成任务")


if __name__ == "__main__":
    unittest.main()
