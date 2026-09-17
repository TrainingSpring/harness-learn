"""Context 消息追加和治理接口测试。"""

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


sys.path.insert(0, str(Path(__file__).parents[2] / "code" / "agent"))

from context.context import Context  # noqa: E402
from head.types import LLMResponseOutputItem, LLMUsage  # noqa: E402


class FakeLLM:
    """可控制压缩结果的最小 LLM 替身。"""

    def __init__(self, output_text="摘要", error=None):
        self.system_prompt = ""
        self.output_text = output_text
        self.error = error

    def call_responses(self, _input):
        if self.error is not None:
            raise self.error
        return SimpleNamespace(output_text=self.output_text)


class ContextGovernanceTests(unittest.TestCase):
    """验证 Context 的统一追加和治理行为。"""

    def test_append_helpers_store_expected_model_messages(self):
        """用户、Agent 和工具输出应通过统一接口进入上下文。"""
        context = Context(FakeLLM(), session_id="session_governance")
        output_item = LLMResponseOutputItem(
            type="function_call",
            id="item_001",
            content=None,
            name="read",
            arguments='{"target_path":"README.md"}',
            call_id="call_001",
            status="completed",
        )

        context.append_user_message("检查项目")
        context.append_agent_message("agent_001", "我开始检查")
        context.append_function_call("agent_001", output_item)
        context.append_function_call_output(
            "agent_001",
            {"type": "function_call_output", "call_id": "call_001", "output": "完成"},
        )

        self.assertEqual(context.messages[0]["role"], "user")
        self.assertEqual(context.messages[1]["role"], "assistant")
        self.assertEqual(context.messages[2]["type"], "function_call")
        self.assertEqual(context.messages[3]["type"], "function_call_output")

    def test_function_call_governance_accepts_dict_messages(self):
        """治理不能假设消息一定是 SDK 对象。"""
        context = Context(FakeLLM(), session_id="session_tool_history")
        context.call_result_num = 1
        context.restore([
            {"type": "function_call", "name": "old", "arguments": "{}"},
            {"type": "function_call_output", "output": "old result"},
            {"type": "function_call", "name": "new", "arguments": "{}"},
            {"type": "function_call_output", "output": "new result"},
        ])

        context.function_call_manager()

        self.assertEqual(context.messages[0]["type"], "message")
        self.assertEqual(context.messages[2]["type"], "function_call")

    def test_compaction_failure_preserves_previous_context(self):
        """压缩模型失败时，治理前的上下文必须完整保留。"""
        context = Context(FakeLLM(error=RuntimeError("模型不可用")), session_id="session_compact")
        context.restore([
            {"type": "message", "role": "user", "content": "保留这条"},
            {"type": "message", "role": "assistant", "content": "以及这条"},
        ])
        before = context.export()

        with self.assertRaises(RuntimeError):
            context.compact_context()

        self.assertEqual(context.export(), before)

    def test_successful_compaction_does_not_duplicate_retained_messages(self):
        """压缩结果应由摘要和保留后缀组成，不能重复原始消息。"""
        context = Context(FakeLLM(output_text="压缩摘要"), session_id="session_compact_ok")
        context.restore([
            {"type": "message", "role": "user", "content": "第一条"},
            {"type": "message", "role": "assistant", "content": "第二条"},
        ])

        context.compact_context()

        self.assertEqual(len(context.messages), 1)
        self.assertIn("压缩摘要", context.messages[0]["content"][0]["text"])

    def test_usage_governance_uses_current_messages(self):
        """追加带 usage 的消息仍应以当前消息集合执行治理。"""
        context = Context(FakeLLM(), session_id="session_usage")
        context.screen_size = 10
        context.append_user_message(
            "当前消息",
            usage=LLMUsage(total_tokens=8, cached_token=0, output_tokens=1, input_tokens=7),
        )

        self.assertTrue(context.messages)


if __name__ == "__main__":
    unittest.main()
