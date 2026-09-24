"""工具调用准备阶段的契约测试。"""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).parents[1] / "code" / "agent"))

from permission.types import PermissionAction, PermissionRequirement  # noqa: E402
from session.ExecutionContext import ExecutionContext  # noqa: E402
from tools.tools import Tools  # noqa: E402
from tools.types import Tool, ToolCallPreparationError, ToolResult  # noqa: E402


class ToolPreparationTests(unittest.TestCase):
    """验证工具查找、参数解析和权限请求构造只发生一次。"""

    def setUp(self):
        """创建带有文件工具和 bash 工具的工具集。"""
        self.ctx = ExecutionContext(
            "/workspace",
            "code_editor",
            "session_001",
        )
        self.tools = Tools(self.ctx)
        self.tools.register(
            Tool(
                {"name": "read"},
                lambda _ctx, **_args: ToolResult.success(),
                PermissionRequirement(PermissionAction.FILE_READ, "target_path"),
            )
        )
        self.tools.register(
            Tool(
                {"name": "bash"},
                lambda _ctx, **_args: ToolResult.success(),
                PermissionRequirement(PermissionAction.BASH_EXECUTE, None),
            )
        )

    def test_prepare_call_normalizes_file_resource_to_absolute_path(self):
        """相对路径应基于 workspace 生成稳定的绝对权限资源。"""
        call = self.tools.prepare_call(
            "read",
            {"target_path": "src/../src/app.py"},
            "call_001",
        )

        self.assertEqual(call.arguments["target_path"], "src/../src/app.py")
        self.assertEqual(call.permission_request.resource, "/workspace/src/app.py")
        self.assertEqual(call.permission_request.call_id, "call_001")

    def test_prepare_bash_call_does_not_fake_a_file_resource(self):
        """bash 使用动作授权，不能把 command 文本误当成文件路径。"""
        call = self.tools.prepare_call(
            "bash",
            {"command": "rm -rf build"},
            "call_002",
        )

        self.assertIsNone(call.permission_request.resource)
        self.assertEqual(call.arguments["command"], "rm -rf build")

    def test_prepare_call_rejects_invalid_arguments_as_stable_error(self):
        """非法 JSON 和非对象参数都应进入统一准备错误契约。"""
        for arguments in ("{", "[]"):
            with self.subTest(arguments=arguments):
                with self.assertRaises(ToolCallPreparationError) as raised:
                    self.tools.prepare_call("read", arguments, "call_003")
                self.assertEqual(raised.exception.error.code, "INVALID_ARGUMENTS")

    def test_prepare_call_rejects_missing_resource_argument(self):
        """声明了资源参数的工具缺少该参数时不能进入权限判断。"""
        with self.assertRaises(ToolCallPreparationError) as raised:
            self.tools.prepare_call("read", {}, "call_004")

        self.assertEqual(raised.exception.error.code, "INVALID_ARGUMENTS")

    def test_prepare_call_builds_permission_request_for_external_path(self):
        """越出工作目录的目标应交由 PermissionManager 按模式决定。"""
        call = self.tools.prepare_call(
            "read", {"target_path": "../secret.txt"}, "call_004"
        )

        self.assertEqual(call.permission_request.resource, "/secret.txt")
        self.assertEqual(call.arguments["target_path"], "../secret.txt")

    def test_prepare_call_keeps_absolute_path_outside_workspace(self):
        call = self.tools.prepare_call(
            "read", {"target_path": "/outside/secret.txt"}, "call_008"
        )

        self.assertEqual(call.permission_request.resource, "/outside/secret.txt")

    def test_prepare_call_rejects_file_tools_without_a_project(self):
        """空项目仍可聊天，但文件工具必须返回稳定错误。"""
        tools = Tools(ExecutionContext(None, "code_editor", "session_002"))
        tools.register(
            Tool(
                {"name": "read"},
                lambda _ctx, **_args: ToolResult.success(),
                PermissionRequirement(PermissionAction.FILE_READ, "target_path"),
            )
        )

        with self.assertRaises(ToolCallPreparationError) as raised:
            tools.prepare_call("read", {"target_path": "README.md"}, "call_005")

        self.assertEqual(raised.exception.error.code, "PROJECT_NOT_SELECTED")

    def test_default_grant_resource_is_file_parent_directory(self):
        """文件授权默认提升到目标父目录，以减少重复逐文件确认。"""
        call = self.tools.prepare_call("read", {"target_path": "src/app.py"}, "call_005")

        self.assertEqual(
            self.tools.default_grant_resource(call.permission_request),
            "/workspace/src",
        )

    def test_default_grant_resource_for_bash_is_none(self):
        """bash 没有可靠的单一资源根，默认授权范围保持为 None。"""
        call = self.tools.prepare_call("bash", {"command": "pwd"}, "call_006")

        self.assertIsNone(self.tools.default_grant_resource(call.permission_request))

    def test_execute_fails_closed_if_symlink_target_changes_after_preparation(self):
        call = self.tools.prepare_call(
            "read", {"target_path": "src/app.py"}, "call_007"
        )

        with patch.object(
            self.tools,
            "_resolve_path",
            return_value="/workspace/changed.py",
        ):
            result = self.tools.execute(call)

        self.assertEqual(result.error.code, "PERMISSION_TARGET_CHANGED")


if __name__ == "__main__":
    unittest.main()
