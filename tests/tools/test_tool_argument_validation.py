"""Tool 参数解析与权限请求边界测试。"""

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parents[2] / "code" / "agent"))

from permission.types import PermissionAction, PermissionRequirement  # noqa: E402
from session.ExecutionContext import ExecutionContext  # noqa: E402
from tools.tools import Tools  # noqa: E402
from tools.types import Tool, ToolCallPreparationError, ToolResult  # noqa: E402


class ToolArgumentValidationTests(unittest.TestCase):
    """验证模型参数在权限检查前被工具专属解析器规范化。"""

    def setUp(self) -> None:
        self.tools = Tools(ExecutionContext("/workspace", "agent_1", "session_1"))

    def test_argument_parser_normalizes_resource_before_permission_request(self) -> None:
        """权限请求必须使用解析器返回的新路径，而不是模型原始参数。"""
        def parse(arguments: dict) -> dict:
            if set(arguments) != {"target_path"}:
                raise ValueError("参数不正确")
            return {"target_path": "normalized/file.txt"}

        self.tools.register(
            Tool(
                {"name": "validated_read"},
                lambda _ctx, **_args: ToolResult.success(),
                PermissionRequirement(PermissionAction.FILE_READ, "target_path"),
                argument_parser=parse,
            )
        )

        call = self.tools.prepare_call(
            "validated_read",
            {"target_path": "../untrusted.txt"},
            "call_1",
        )

        self.assertEqual(call.arguments, {"target_path": "normalized/file.txt"})
        self.assertEqual(
            call.permission_request.resource,
            "/workspace/normalized/file.txt",
        )

    def test_argument_parser_failure_returns_stable_preparation_error(self) -> None:
        """无效参数不能进入权限检查或实际工具执行。"""
        def parse(_arguments: dict) -> dict:
            raise ValueError("limit 必须是正整数")

        self.tools.register(
            Tool(
                {"name": "validated_read"},
                lambda _ctx, **_args: ToolResult.success(),
                PermissionRequirement(PermissionAction.FILE_READ, "target_path"),
                argument_parser=parse,
            )
        )

        with self.assertRaises(ToolCallPreparationError) as raised:
            self.tools.prepare_call(
                "validated_read",
                {"target_path": "file.txt", "limit": -1},
                "call_2",
            )

        self.assertEqual(raised.exception.error.code, "INVALID_ARGUMENTS")

    def test_argument_parser_must_return_a_new_object(self) -> None:
        """解析器返回非对象时不能让后续权限代码接收非法参数。"""
        self.tools.register(
            Tool(
                {"name": "validated_read"},
                lambda _ctx, **_args: ToolResult.success(),
                PermissionRequirement(PermissionAction.FILE_READ, "target_path"),
                argument_parser=lambda _arguments: None,
            )
        )

        with self.assertRaises(ToolCallPreparationError) as raised:
            self.tools.prepare_call(
                "validated_read",
                {"target_path": "file.txt"},
                "call_3",
            )

        self.assertEqual(raised.exception.error.code, "INVALID_ARGUMENTS")


if __name__ == "__main__":
    unittest.main()
