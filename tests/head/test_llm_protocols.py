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
