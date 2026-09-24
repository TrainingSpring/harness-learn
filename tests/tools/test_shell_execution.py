"""Shell 执行器的本地资源边界测试。"""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).parents[2] / "code" / "agent"))

from tools.shell.execution import (  # noqa: E402
    BoundedByteBuffer,
    ShellExecutionError,
    ShellExecutor,
    build_minimal_environment,
    build_shell_argv,
)


class BoundedByteBufferTests(unittest.TestCase):
    """确保输出仅在超过总字节上限时才声明截断。"""

    def test_keeps_complete_output_that_exceeds_the_head_reservation(self) -> None:
        """头部预留不是输出上限，未超过总上限的字节不能丢失。"""
        buffer = BoundedByteBuffer(10)

        buffer.append(b"1234567")

        self.assertEqual(buffer.content(), b"1234567")
        self.assertFalse(buffer.truncated)

    def test_keeps_the_output_head_and_tail_after_exceeding_the_limit(self) -> None:
        """超过总上限时仅保留可诊断的头部和最新尾部。"""
        buffer = BoundedByteBuffer(10)

        buffer.append(b"12345678901")

        self.assertTrue(buffer.truncated)
        self.assertEqual(
            buffer.content(),
            b"12345\n... output truncated ...\n78901",
        )

    def test_minimal_environment_excludes_unrelated_host_variables(self) -> None:
        """子进程不能无条件继承宿主进程中可能含凭据的环境变量。"""
        with patch.dict(
            "tools.shell.execution.os.environ",
            {"PATH": "/bin", "HOME": "/tmp", "SENSITIVE_TOKEN": "hidden"},
            clear=True,
        ):
            environment = build_minimal_environment()

        self.assertEqual(environment, {"PATH": "/bin", "HOME": "/tmp"})

    def test_builds_platform_shell_arguments_without_string_concatenation(self) -> None:
        """平台 Shell 的命令和参数边界必须由 argv 表达。"""
        with patch("tools.shell.execution.os.name", "posix"):
            self.assertEqual(build_shell_argv("echo hello"), ["bash", "-lc", "echo hello"])
        with patch("tools.shell.execution.os.name", "nt"):
            self.assertEqual(
                build_shell_argv("echo hello"),
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", "echo hello"],
            )

    def test_maps_missing_shell_to_a_stable_error_code(self) -> None:
        """Shell 未安装时不能泄露底层异常，也不能变成泛化失败。"""
        with patch("tools.shell.execution.subprocess.Popen", side_effect=FileNotFoundError):
            with self.assertRaises(ShellExecutionError) as raised:
                ShellExecutor().start("echo hello", cwd="/tmp")

        self.assertEqual(raised.exception.code, "BASH_EXECUTABLE_NOT_FOUND")


if __name__ == "__main__":
    unittest.main()
