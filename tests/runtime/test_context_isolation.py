"""Context 实例隔离的基线测试。"""

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parents[2] / "code" / "agent"))

from context.context import Context  # noqa: E402
from runtime.ExecutionContext import ExecutionContext  # noqa: E402


class FakeLLM:
    """满足 Context 初始化所需接口的最小 LLM 替身。"""

    def __init__(self):
        self.system_prompt = ""


class ContextIsolationTests(unittest.TestCase):
    """验证不同会话的 Context 不共享可变消息列表。"""

    def test_context_instances_keep_messages_isolated(self):
        """一个 Context 的追加和加载不能影响另一个 Context。"""
        context_a = Context(
            FakeLLM(),
            ExecutionContext("/workspace", "agent_1", "session_1"),
        )
        context_b = Context(
            FakeLLM(),
            ExecutionContext("/workspace", "agent_1", "session_2"),
        )

        context_a.append_msg("会话 A")
        context_b.append_msg("会话 B")

        self.assertEqual([item["content"] for item in context_a.messages], ["会话 A"])
        self.assertEqual([item["content"] for item in context_b.messages], ["会话 B"])


if __name__ == "__main__":
    unittest.main()
