"""Context 历史恢复的基线测试。"""

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


class ContextRestoreContractTests(unittest.TestCase):
    """锁定现有 load_history 的恢复行为。"""

    def test_load_history_replaces_current_messages(self):
        """恢复历史后，Context 应使用传入的历史消息。"""
        context = Context(
            FakeLLM(),
            ExecutionContext("/workspace", "agent_1", "session_old"),
        )
        context.append_msg("旧消息")

        context.load_history(
            "session_restored",
            [{"type": "message", "role": "user", "content": "已恢复"}],
        )

        self.assertEqual(context.sid, "session_restored")
        self.assertEqual(context.messages[0]["content"], "已恢复")


if __name__ == "__main__":
    unittest.main()
