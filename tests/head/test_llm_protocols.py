import sys
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parents[2] / "code" / "agent"))

from importlib.util import module_from_spec, spec_from_file_location

types_spec = spec_from_file_location("head.types", Path(__file__).parents[2] / "code/agent/head/types.py")
types_module = module_from_spec(types_spec)
sys.modules["head.types"] = types_module
types_spec.loader.exec_module(types_module)
llm_spec = spec_from_file_location("head.llm", Path(__file__).parents[2] / "code/agent/head/llm.py")
llm_module = module_from_spec(llm_spec)
sys.modules["head.llm"] = llm_module
llm_spec.loader.exec_module(llm_module)

LLM = llm_module.LLM
LLMConfig = types_module.LLMConfig
LLMResponse = types_module.LLMResponse


class LLMProtocolTests(unittest.TestCase):
    @staticmethod
    def _internal_tool_turn():
        """模拟 Context 在一次工具调用后提供给下一轮模型的内部消息。"""
        return [
            {"kind": "message", "role": "user", "content": "读取项目说明"},
            {
                "kind": "tool_call",
                "tool_call_id": "call_read_001",
                "tool_name": "read",
                "arguments": {"target_path": "README.md"},
            },
            {
                "kind": "tool_result",
                "tool_call_id": "call_read_001",
                "output": {"status": "ok", "data": "项目说明"},
            },
        ]

    def test_config_validates_protocol_and_defaults_to_responses(self):
        self.assertEqual(LLMConfig("https://example.test", "key", "model").protocol, "responses")
        self.assertEqual(
            LLMConfig("https://example.test", "key", "model", "claude").protocol,
            "claude",
        )
        with self.assertRaises(ValueError):
            LLMConfig("https://example.test", "key", "model", "unknown")

    @patch("head.llm.OpenAI")
    def test_completions_converts_messages_and_tools(self, openai_class):
        llm = LLM("https://example.test", "key", "model", protocol="completions")
        llm.call_completions(
            [{"type": "message", "role": "user", "content": "hello"}],
            tools=[{"name": "read", "description": "read", "parameters": {"type": "object"}}],
            instructions="be concise",
        )
        request = openai_class.return_value.chat.completions.create.call_args.kwargs
        self.assertEqual(request["messages"][0], {"role": "system", "content": "be concise"})
        self.assertEqual(request["messages"][1]["content"], "hello")
        self.assertEqual(request["tools"][0]["function"]["name"], "read")

    @patch("head.llm.OpenAI")
    def test_responses_converts_internal_tool_turn_to_native_input(self, openai_class):
        """Responses 必须接收 API 的 type/call_id/name 字段，而不是 Context 内部字段。"""
        llm = LLM("https://example.test", "key", "model", protocol="responses")

        llm.call_responses(self._internal_tool_turn())

        request = openai_class.return_value.responses.create.call_args.kwargs
        self.assertEqual(request["input"], [
            {"type": "message", "role": "user", "content": "读取项目说明"},
            {
                "type": "function_call",
                "call_id": "call_read_001",
                "name": "read",
                "arguments": '{"target_path": "README.md"}',
            },
            {
                "type": "function_call_output",
                "call_id": "call_read_001",
                "output": '{"status": "ok", "data": "项目说明"}',
            },
        ])

    @patch("head.llm.OpenAI")
    def test_responses_stream_converts_internal_tool_turn_to_native_input(self, openai_class):
        """流式 Responses 入口也必须使用同一份请求适配。"""
        response_stream = openai_class.return_value.responses.stream.return_value
        response_stream.__enter__.return_value = []
        llm = LLM("https://example.test", "key", "model", protocol="responses")

        list(llm.call_responses_stream(self._internal_tool_turn()))

        request = openai_class.return_value.responses.stream.call_args.kwargs
        self.assertEqual(request["input"][1], {
            "type": "function_call",
            "call_id": "call_read_001",
            "name": "read",
            "arguments": '{"target_path": "README.md"}',
        })
        self.assertEqual(request["input"][2], {
            "type": "function_call_output",
            "call_id": "call_read_001",
            "output": '{"status": "ok", "data": "项目说明"}',
        })

    def test_responses_preserves_multimodal_tool_result_content(self):
        """工具层产生的 input_text/input_image 内容不能被二次 JSON 编码。"""
        content = [
            {"type": "input_text", "text": "截图结果"},
            {"type": "input_image", "image_url": "data:image/png;base64,abc", "detail": "auto"},
        ]

        input_items = LLM._responses_input([
            {"kind": "tool_result", "tool_call_id": "call_image_001", "output": content},
        ])

        self.assertEqual(input_items[0]["output"], content)

    def test_completions_converts_internal_tool_turn(self):
        """Chat Completions 必须将内部工具调用配对为 assistant/tool 两条消息。"""
        messages = LLM._completions_messages(self._internal_tool_turn(), "遵守工具结果")

        self.assertEqual(messages, [
            {"role": "system", "content": "遵守工具结果"},
            {"role": "user", "content": "读取项目说明"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [{
                    "id": "call_read_001",
                    "type": "function",
                    "function": {"name": "read", "arguments": '{"target_path": "README.md"}'},
                }],
            },
            {
                "role": "tool",
                "tool_call_id": "call_read_001",
                "content": '{"status": "ok", "data": "项目说明"}',
            },
        ])

    def test_claude_converts_internal_tool_turn(self):
        """Claude 的 tool_use.input 必须是对象，不能泄漏内部 JSON 字符串。"""
        messages = LLM._claude_messages(self._internal_tool_turn())

        self.assertEqual(messages, [
            {"role": "user", "content": "读取项目说明"},
            {
                "role": "assistant",
                "content": [{
                    "type": "tool_use",
                    "id": "call_read_001",
                    "name": "read",
                    "input": {"target_path": "README.md"},
                }],
            },
            {
                "role": "user",
                "content": [{
                    "type": "tool_result",
                    "tool_use_id": "call_read_001",
                    "content": '{"status": "ok", "data": "项目说明"}',
                }],
            },
        ])

    def test_claude_parses_persisted_tool_call_arguments(self):
        """从持久化事件恢复时，Claude 仍必须收到对象形式的 tool_use.input。"""
        turn = self._internal_tool_turn()
        turn[1]["arguments"] = '{"target_path": "README.md"}'

        messages = LLM._claude_messages(turn)

        self.assertEqual(messages[1]["content"][0]["input"], {"target_path": "README.md"})

    @patch("head.llm.OpenAI")
    def test_completions_stream_aggregates_tool_arguments(self, openai_class):
        first = SimpleNamespace(
            choices=[SimpleNamespace(
                delta=SimpleNamespace(
                    content=None,
                    tool_calls=[SimpleNamespace(
                        index=0, id="call_1",
                        function=SimpleNamespace(name="read", arguments='{"path":'),
                    )],
                ),
                finish_reason=None,
            )]
        )
        second = SimpleNamespace(
            choices=[SimpleNamespace(
                delta=SimpleNamespace(
                    content=None,
                    tool_calls=[SimpleNamespace(
                        index=0, id=None,
                        function=SimpleNamespace(name=None, arguments='"a.txt"}'),
                    )],
                ),
                finish_reason="tool_calls",
            )],
            usage=SimpleNamespace(prompt_tokens=2, completion_tokens=3, total_tokens=5),
        )
        openai_class.return_value.chat.completions.create.return_value = iter([first, second])
        events = list(LLM("https://example.test", "key", "model", protocol="completions")
                      .call_completions_stream("hello"))
        call = next(event for event in events if event.type == "function_call")
        self.assertEqual(call.call_id, "call_1")
        self.assertEqual(call.arguments, {"path": "a.txt"})
        self.assertEqual(next(event for event in events if event.type == "done").usage.total_tokens, 5)

    @patch("head.llm.Anthropic", create=True)
    def test_claude_converts_tool_schema(self, anthropic_class):
        # The import is performed inside LLM.__init__, so provide a fake module.
        with patch.dict(sys.modules, {"anthropic": SimpleNamespace(Anthropic=anthropic_class)}):
            llm = LLM("https://example.test", "key", "model", protocol="claude")
            llm.call_claude("hello", tools=[{"name": "read", "parameters": {"type": "object"}}])
        request = anthropic_class.return_value.messages.create.call_args.kwargs
        self.assertEqual(request["messages"], [{"role": "user", "content": "hello"}])
        self.assertEqual(request["tools"][0]["input_schema"]["type"], "object")

    @patch("head.llm.OpenAI")
    def test_generic_entrypoint_dispatches_by_protocol(self, openai_class):
        llm = LLM("https://example.test", "key", "model", protocol="responses")
        llm.call("hello")
        openai_class.return_value.responses.create.assert_called_once()

    def test_old_fourth_positional_argument_remains_system_prompt(self):
        with patch("head.llm.OpenAI"):
            llm = LLM("https://example.test", "key", "model", "system")
        self.assertEqual(llm.system_prompt, "system")
        self.assertEqual(llm.protocol, "responses")


if __name__ == "__main__":
    unittest.main()
