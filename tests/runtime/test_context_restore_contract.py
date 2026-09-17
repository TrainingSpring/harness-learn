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

    def test_context_can_be_created_with_session_id_without_execution_context(self):
        """Context 的创建不应要求完整的工具执行环境。"""
        context = Context(
            summarizer_llm=FakeLLM(),
            session_id="session_independent",
        )

        self.assertEqual(context.sid, "session_independent")

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

    def test_restore_does_not_share_mutable_state_with_input(self):
        """恢复和导出都必须隔离可变的嵌套消息结构。"""
        messages = [
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "原始"}],
            }
        ]
        context = Context(FakeLLM(), session_id="session_restore")

        context.restore(messages)
        messages[0]["content"][0]["text"] = "外部修改"
        exported = context.export()
        exported[0]["content"][0]["text"] = "导出修改"

        self.assertEqual(context.messages[0]["content"][0]["text"], "原始")

    def test_to_model_input_is_a_fresh_snapshot_with_system_messages(self):
        """模型输入应包含系统消息，但不能让调用方修改 Context 内部。"""
        context = Context(FakeLLM(), session_id="session_input")
        context.append_user_message("你好")
        system_messages = [{"type": "message", "role": "developer", "content": "规则"}]

        model_input = context.to_model_input(system_messages)
        model_input[0]["content"] = "外部修改"
        system_messages[0]["content"] = "系统外部修改"

        self.assertEqual(model_input[1]["content"], "你好")
        self.assertEqual(context.messages[0]["content"], "你好")
        self.assertEqual(context.to_model_input(system_messages)[0]["content"], "系统外部修改")


if __name__ == "__main__":
    unittest.main()
