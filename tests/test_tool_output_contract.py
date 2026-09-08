import json
import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parents[1] / "code" / "agent"))

from runtime.ExecutionContext import ExecutionContext
from tools.read import read
from tools.tools import Tools
from tools.types import Tool, ToolOutput


class ToolOutputContractTests(unittest.TestCase):
    def test_eval_serializes_structured_business_values(self):
        ctx = ExecutionContext("/tmp", "agent-test")
        tools = Tools(ctx)
        tools.register(Tool({"name": "structured"}, lambda _ctx: {"status": "ok", "count": 2}))

        result = tools.eval("structured", {})

        self.assertIsInstance(result, str)
        self.assertEqual(json.loads(result), {"status": "ok", "count": 2})

    def test_eval_keeps_legacy_responses_content_arrays(self):
        ctx = ExecutionContext("/tmp", "agent-test")
        tools = Tools(ctx)
        legacy_output = [{"type": "input_text", "text": "ok"}]
        tools.register(Tool({"name": "legacy"}, lambda _ctx: legacy_output))

        result = tools.eval("legacy", {})

        self.assertEqual(result, legacy_output)

    def test_read_returns_business_value_for_text_file(self):
        with tempfile.TemporaryDirectory() as workspace:
            path = Path(workspace) / "note.txt"
            path.write_text("hello", encoding="utf-8")
            ctx = ExecutionContext(workspace, "agent-test")

            result = read(ctx, "note.txt")

            self.assertEqual(result["content"], "hello")
            self.assertEqual(result["path"], str(path))

    def test_eval_converts_multimodal_tool_output_to_content_array(self):
        ctx = ExecutionContext("/tmp", "agent-test")
        tools = Tools(ctx)
        tools.register(
            Tool(
                {"name": "image"},
                lambda _ctx: ToolOutput(
                    value={"status": "ok"},
                    content=[{"type": "input_image", "image_url": "data:image/png;base64,abc"}],
                ),
            )
        )

        result = tools.eval("image", {})

        self.assertEqual(result[0]["type"], "input_text")
        self.assertEqual(json.loads(result[0]["text"]), {"status": "ok"})
        self.assertEqual(result[1]["type"], "input_image")


if __name__ == "__main__":
    unittest.main()
