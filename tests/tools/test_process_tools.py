"""Session 后台进程 Tool 的参数、权限与结果契约测试。"""

import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parents[2] / "code" / "agent"))

from permission.types import PermissionAction  # noqa: E402
from session.ExecutionContext import ExecutionContext  # noqa: E402
from tools.process_logs import REGISTER as PROCESS_LOGS  # noqa: E402
from tools.process_start import REGISTER as PROCESS_START  # noqa: E402
from tools.process_status import REGISTER as PROCESS_STATUS  # noqa: E402
from tools.process_stop import REGISTER as PROCESS_STOP  # noqa: E402
from tools.process_wait import REGISTER as PROCESS_WAIT  # noqa: E402
from tools.tools import Tools  # noqa: E402
from tools.types import ToolCallPreparationError  # noqa: E402


class FakeProcessManager:
    """以确定性会话进程状态验证 Tool，不启动真实服务。"""

    def __init__(self) -> None:
        self.calls = []
        self.cursor_expired = False

    @staticmethod
    def _record(process_id="proc_123"):
        return {
            "process_id": process_id,
            "state": "running",
            "pid": 12345,
            "command": "npm run dev",
            "shell": "bash",
            "cwd": "/workspace",
            "started_at": "2026-01-01T00:00:00+00:00",
            "exit_code": None,
            "ended_at": None,
        }

    def start(self, command, *, cwd):
        self.calls.append(("start", command, cwd))
        return self._record()

    def status(self, process_id):
        self.calls.append(("status", process_id))
        return self._record(process_id)

    def logs(self, process_id, *, cursor_process_id=None, stdout_offset, stderr_offset, limit):
        self.calls.append(("logs", process_id, stdout_offset, stderr_offset, limit))
        return {
            "stdout": "server ready\n",
            "stderr": "",
            "stdout_offset": stdout_offset + 13,
            "stderr_offset": stderr_offset,
            "cursor_expired": self.cursor_expired,
            "truncated": False,
        }

    def wait(self, process_id, *, timeout_seconds):
        self.calls.append(("wait", process_id, timeout_seconds))
        return self._record(process_id)

    def stop(self, process_id):
        self.calls.append(("stop", process_id))
        return self._record(process_id)


class ProcessToolTests(unittest.TestCase):
    """持续进程 Tool 只能使用当前 Session 的注入管理器。"""

    def setUp(self) -> None:
        self.workspace = tempfile.TemporaryDirectory()
        self.addCleanup(self.workspace.cleanup)
        self.manager = FakeProcessManager()
        self.ctx = ExecutionContext(
            self.workspace.name,
            "agent_1",
            "session_1",
            process_manager=self.manager,
        )
        self.tools = Tools(self.ctx)
        for tool in (PROCESS_START, PROCESS_STATUS, PROCESS_LOGS, PROCESS_WAIT, PROCESS_STOP):
            self.tools.register(tool)

    def test_tools_declare_minimum_static_permissions(self) -> None:
        """启动会产生新影响，检查和停止只管理本 Session 已有进程。"""
        self.assertEqual(PROCESS_START.permission.action, PermissionAction.BASH_EXECUTE)
        self.assertEqual(PROCESS_STATUS.permission.action, PermissionAction.PROCESS_INSPECT)
        self.assertEqual(PROCESS_LOGS.permission.action, PermissionAction.PROCESS_INSPECT)
        self.assertEqual(PROCESS_WAIT.permission.action, PermissionAction.PROCESS_INSPECT)
        self.assertEqual(PROCESS_STOP.permission.action, PermissionAction.PROCESS_STOP)

    def test_invalid_arguments_fail_before_permission_preparation(self) -> None:
        """无效命令、cursor 和 timeout 不能触发权限弹窗。"""
        invalid_calls = (
            ("process_start", {"command": " "}),
            ("process_status", {"process_id": 1}),
            ("process_logs", {"process_id": "proc_1", "cursor": 1}),
            ("process_logs", {"process_id": "proc_1", "limit": True}),
            ("process_wait", {"process_id": "proc_1", "timeout": 0}),
            ("process_stop", {"process_id": "proc_1", "extra": True}),
        )
        for name, arguments in invalid_calls:
            with self.subTest(name=name, arguments=arguments):
                with self.assertRaises(ToolCallPreparationError) as raised:
                    self.tools.prepare_call(name, arguments, f"call_{name}")
                self.assertEqual(raised.exception.error.code, "INVALID_ARGUMENTS")

    def test_start_logs_wait_and_stop_return_stable_session_process_results(self) -> None:
        """后台服务启动不阻塞，后续操作通过进程 ID 和 cursor 衔接。"""
        start = self.tools.execute(
            self.tools.prepare_call("process_start", {"command": "npm run dev"}, "call_start")
        )
        logs = self.tools.execute(
            self.tools.prepare_call("process_logs", {"process_id": "proc_123"}, "call_logs")
        )
        waited = self.tools.execute(
            self.tools.prepare_call("process_wait", {"process_id": "proc_123"}, "call_wait")
        )
        stopped = self.tools.execute(
            self.tools.prepare_call("process_stop", {"process_id": "proc_123"}, "call_stop")
        )

        self.assertEqual(start.data["process_id"], "proc_123")
        self.assertEqual(logs.data["stdout"], "server ready\n")
        self.assertIsInstance(logs.data["next_cursor"], str)
        self.assertEqual(waited.data["state"], "running")
        self.assertEqual(stopped.data["process_id"], "proc_123")
        self.assertEqual(self.manager.calls[0], ("start", "npm run dev", self.workspace.name))
        self.assertEqual(self.manager.calls[2], ("wait", "proc_123", 30.0))

    def test_expired_log_cursor_returns_a_retryable_stable_error(self) -> None:
        """日志环淘汰旧数据时不能静默跳转到错误位置。"""
        self.manager.cursor_expired = True

        result = self.tools.execute(
            self.tools.prepare_call(
                "process_logs",
                {"process_id": "proc_123"},
                "call_logs_expired",
            )
        )

        self.assertEqual(result.status, "error")
        self.assertEqual(result.error.code, "LOG_CURSOR_EXPIRED")
        self.assertTrue(result.error.retryable)

    def test_log_return_limit_is_shared_by_stdout_and_stderr(self) -> None:
        """stdout 与 stderr 合计不能突破一次 Tool 返回上限。"""
        result = self.tools.execute(
            self.tools.prepare_call(
                "process_logs",
                {"process_id": "proc_123", "limit": 10},
                "call_logs_limit",
            )
        )

        self.assertEqual(self.manager.calls[-1][-1], 5)

    def test_log_cursor_cannot_be_reused_for_a_different_process(self) -> None:
        """公开 cursor 必须绑定当前 process_id，避免串读其他服务日志。"""
        started = self.tools.execute(
            self.tools.prepare_call("process_start", {"command": "npm run dev"}, "call_start_cursor")
        )
        logs = self.tools.execute(
            self.tools.prepare_call(
                "process_logs",
                {"process_id": started.data["process_id"]},
                "call_logs_cursor",
            )
        )
        forged_for_another_process = self.tools.prepare_call(
            "process_logs",
            {"process_id": "proc_other", "cursor": logs.data["next_cursor"]},
            "call_logs_other",
        )

        self.assertEqual(forged_for_another_process.arguments["process_id"], "proc_other")


if __name__ == "__main__":
    unittest.main()
