"""Bash Tool 的参数、前台执行边界与稳定结果测试。"""

import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parents[2] / "code" / "agent"))

from session.ExecutionContext import ExecutionContext  # noqa: E402
from tools.bash import REGISTER as BASH_TOOL  # noqa: E402
from tools.bash import bash  # noqa: E402
from tools.tools import Tools  # noqa: E402
from tools.types import ToolCallPreparationError  # noqa: E402


class FakeShellExecutor:
    """以固定结果验证 Bash 公开契约，不依赖本机 Shell。"""

    def __init__(self, result=None, error=None) -> None:
        self.result = result or {
            "exit_code": 0,
            "stdout": "completed\n",
            "stderr": "",
            "stdout_truncated": False,
            "stderr_truncated": False,
        }
        self.error = error
        self.calls = []

    def run(self, command, *, cwd, timeout_seconds, output_limit_bytes):
        self.calls.append(
            {
                "command": command,
                "cwd": cwd,
                "timeout_seconds": timeout_seconds,
                "output_limit_bytes": output_limit_bytes,
            }
        )
        if self.error is not None:
            raise self.error
        return self.result


class BashToolTests(unittest.TestCase):
    """锁定 Bash 只能执行受本地边界保护的前台命令。"""

    def setUp(self) -> None:
        self.workspace = tempfile.TemporaryDirectory()
        self.addCleanup(self.workspace.cleanup)
        self.ctx = ExecutionContext(self.workspace.name, "agent_1", "session_1")
        self.tools = Tools(self.ctx)
        self.tools.register(BASH_TOOL)

    def test_rejects_invalid_arguments_before_permission_check(self) -> None:
        """命令和 timeout 必须在权限准备前成为可信的内部参数。"""
        for arguments in (
            {},
            {"command": "   "},
            {"command": 1},
            {"command": "pwd", "timeout": 0},
            {"command": "pwd", "timeout": True},
            {"command": "pwd", "timeout": "30"},
            {"command": "pwd", "extra": True},
        ):
            with self.subTest(arguments=arguments):
                with self.assertRaises(ToolCallPreparationError) as raised:
                    self.tools.prepare_call("bash", arguments, "bash-invalid")
                self.assertEqual(raised.exception.error.code, "INVALID_ARGUMENTS")

    def test_uses_default_timeout_and_returns_a_stable_foreground_result(self) -> None:
        """省略 timeout 仍必须使用本地默认值，并保留原始命令。"""
        executor = FakeShellExecutor()

        result = bash(self.ctx, "git status", executor=executor)

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.data["command"], "git status")
        self.assertEqual(result.data["cwd"], self.workspace.name)
        self.assertEqual(result.data["timeout_seconds"], 30)
        self.assertEqual(result.data["exit_code"], 0)
        self.assertFalse(result.data["stdout_truncated"])
        self.assertEqual(executor.calls[0]["timeout_seconds"], 30)

    def test_preserves_nonzero_exit_as_a_completed_command_result(self) -> None:
        """测试失败或编译失败不是 Bash 基础设施失败。"""
        executor = FakeShellExecutor(
            result={
                "exit_code": 2,
                "stdout": "",
                "stderr": "test failed\n",
                "stdout_truncated": False,
                "stderr_truncated": False,
            }
        )

        result = bash(self.ctx, "pytest", timeout=12, executor=executor)

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.data["exit_code"], 2)
        self.assertEqual(result.data["timeout_seconds"], 12)

    def test_rejects_a_missing_workspace_before_starting_a_command(self) -> None:
        """会话选择后被删除的工作目录不能作为 Shell 的 cwd。"""
        missing = str(Path(self.workspace.name) / "missing")
        ctx = ExecutionContext(missing, "agent_1", "session_1")
        executor = FakeShellExecutor()

        result = bash(ctx, "pwd", executor=executor)

        self.assertEqual(result.status, "error")
        self.assertEqual(result.error.code, "WORKSPACE_NOT_FOUND")
        self.assertEqual(executor.calls, [])


if __name__ == "__main__":
    unittest.main()
