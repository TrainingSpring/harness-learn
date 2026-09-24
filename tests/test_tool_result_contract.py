import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).parents[1] / "code" / "agent"))

from session.ExecutionContext import ExecutionContext
from permission.types import PermissionAction, PermissionRequirement
from tools.bash import bash
from tools.edit import edit
from tools.read import read
from tools.tools import Tools
from tools.types import Attachment, Tool, ToolResult
from tools.write import write


class ToolResultContractTests(unittest.TestCase):
    """验证工具结果与 Responses 输出适配的公共契约。"""

    @staticmethod
    def _test_permission() -> PermissionRequirement:
        """为不访问真实资源的测试工具提供必填的权限声明。"""
        return PermissionRequirement(PermissionAction.FILE_READ, None)

    def test_execute_serializes_tool_result_as_json(self):
        ctx = ExecutionContext("/tmp", "agent-test", "session-test")
        tools = Tools(ctx)
        tools.register(
            Tool(
                {"name": "structured"},
                lambda _ctx: ToolResult.success({"count": 2}),
                self._test_permission(),
            )
        )

        call = tools.prepare_call("structured", {}, "call-structured")
        result = tools.encode_result(tools.execute(call))

        self.assertEqual(
            json.loads(result),
            {"status": "ok", "data": {"count": 2}},
        )

    def test_execute_rejects_results_that_violate_the_contract(self):
        ctx = ExecutionContext("/tmp", "agent-test", "session-test")
        tools = Tools(ctx)
        tools.register(Tool({"name": "invalid"}, lambda _ctx: {"count": 2}, self._test_permission()))

        call = tools.prepare_call("invalid", {}, "call-invalid")
        result = json.loads(tools.encode_result(tools.execute(call)))

        self.assertEqual(result["error"]["code"], "INVALID_TOOL_RESULT")

    def test_prepare_call_returns_structured_argument_errors(self):
        ctx = ExecutionContext("/tmp", "agent-test", "session-test")
        tools = Tools(ctx)
        tools.register(Tool({"name": "valid"}, lambda _ctx: ToolResult.success(), self._test_permission()))

        with self.assertRaises(Exception) as raised:
            tools.prepare_call("valid", "{", "call-invalid-json")

        self.assertEqual(raised.exception.error.code, "INVALID_ARGUMENTS")

    def test_prepare_call_rejects_non_object_arguments(self):
        ctx = ExecutionContext("/tmp", "agent-test", "session-test")
        tools = Tools(ctx)
        tools.register(Tool({"name": "valid"}, lambda _ctx: ToolResult.success(), self._test_permission()))

        with self.assertRaises(Exception) as raised:
            tools.prepare_call("valid", "[]", "call-list")

        self.assertEqual(raised.exception.error.code, "INVALID_ARGUMENTS")

    def test_encode_result_rejects_non_serializable_result_data(self):
        ctx = ExecutionContext("/tmp", "agent-test", "session-test")
        tools = Tools(ctx)
        tools.register(
            Tool(
                {"name": "invalid_data"},
                lambda _ctx: ToolResult.success({"value": object()}),
                self._test_permission(),
            )
        )

        call = tools.prepare_call("invalid_data", {}, "call-invalid-data")
        with self.assertRaises(TypeError):
            tools.encode_result(tools.execute(call))


    def test_encode_result_converts_image_attachments_to_responses_content(self):
        ctx = ExecutionContext("/tmp", "agent-test", "session-test")
        tools = Tools(ctx)
        tools.register(
            Tool(
                {"name": "image"},
                lambda _ctx: ToolResult.success(
                    data={"path": "/tmp/image.png"},
                    attachments=[
                        Attachment(
                            media_type="image/png",
                            source_kind="bytes",
                            source=b"image-bytes",
                        )
                    ],
                ),
                self._test_permission(),
            )
        )

        call = tools.prepare_call("image", {}, "call-image")
        result = tools.encode_result(tools.execute(call))

        self.assertEqual(
            json.loads(result[0]["text"]),
            {"status": "ok", "data": {"path": "/tmp/image.png"}},
        )
        self.assertEqual(
            result[1],
            {
                "type": "input_image",
                "image_url": "data:image/png;base64,aW1hZ2UtYnl0ZXM=",
                "detail": "auto",
            },
        )

    def test_attachment_can_represent_remote_image_url(self):
        ctx = ExecutionContext("/tmp", "agent-test", "session-test")
        tools = Tools(ctx)
        tools.register(
            Tool(
                {"name": "remote_image"},
                lambda _ctx: ToolResult.success(
                    attachments=[
                        Attachment(
                            media_type="image/jpeg",
                            source_kind="url",
                            source="https://example.com/image.jpg",
                        )
                    ],
                ),
                self._test_permission(),
            )
        )

        call = tools.prepare_call("remote_image", {}, "call-remote-image")
        result = tools.encode_result(tools.execute(call))

        self.assertEqual(result[1]["type"], "input_image")
        self.assertEqual(result[1]["image_url"], "https://example.com/image.jpg")

    def test_all_builtin_tools_return_tool_result(self):
        with tempfile.TemporaryDirectory() as workspace:
            ctx = ExecutionContext(workspace, "agent-test", "session-test")
            source = Path(workspace) / "source.txt"
            source.write_text("before", encoding="utf-8")

            read_result = read(ctx, "source.txt")
            write_result = write(ctx, "written.txt", "content")
            edit_result = edit(
                ctx,
                "source.txt",
                read_result.data["version"],
                [{"old_text": "before", "new_text": "after"}],
            )

            class ShellExecutor:
                def run(self, _command, **_arguments):
                    return {
                        "exit_code": 1,
                        "stdout": "stdout",
                        "stderr": "stderr",
                        "stdout_truncated": False,
                        "stderr_truncated": False,
                    }

            bash_result = bash(
                ctx,
                action="execute",
                command="test",
                executor=ShellExecutor(),
            )

        for result in (read_result, write_result, edit_result, bash_result):
            self.assertIsInstance(result, ToolResult)

        self.assertEqual(read_result.data["content"], "before")
        self.assertEqual(write_result.data["operation"], "created")
        self.assertEqual(edit_result.data["operation"], "edited")
        self.assertEqual(bash_result.status, "ok")
        self.assertEqual(bash_result.data["exit_code"], 1)

    def test_read_returns_structured_failure_for_missing_path(self):
        with tempfile.TemporaryDirectory() as workspace:
            result = read(ExecutionContext(workspace, "agent-test", "session-test"), "missing.txt")

        self.assertEqual(result.status, "error")
        self.assertEqual(result.error.code, "PATH_NOT_FOUND")

    def test_read_returns_image_attachment_without_responses_fields(self):
        with tempfile.TemporaryDirectory() as workspace:
            path = Path(workspace) / "image.png"
            path.write_bytes(b"\x89PNG\r\n\x1a\n")

            result = read(ExecutionContext(workspace, "agent-test", "session-test"), "image.png")

        self.assertIsInstance(result, ToolResult)
        self.assertEqual(result.data["type"], "image")
        self.assertEqual(result.attachments[0].media_type, "image/png")
        self.assertEqual(result.attachments[0].source_kind, "bytes")
        self.assertEqual(result.attachments[0].source, b"\x89PNG\r\n\x1a\n")

    def test_tool_result_enforces_success_and_error_invariants(self):
        with self.assertRaises(ValueError):
            ToolResult(status="unknown")

        with self.assertRaises(ValueError):
            ToolResult(status="error")

        with self.assertRaises(ValueError):
            ToolResult(
                status="ok",
                error=ToolResult.failure("FAILED", "failed").error,
            )


if __name__ == "__main__":
    unittest.main()
