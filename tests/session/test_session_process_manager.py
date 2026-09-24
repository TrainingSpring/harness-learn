"""SessionProcessManager 的会话归属与清理测试。"""

import io
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parents[2] / "code" / "agent"))

from session.session_process_manager import (  # noqa: E402
    ProcessManagerError,
    SessionProcessManager,
)


class BlockingProcess:
    """可由测试终止的最小后台进程替身。"""

    def __init__(self) -> None:
        self.pid = 12345
        self.returncode = None
        self.stdout = io.BytesIO(b"service started\n")
        self.stderr = io.BytesIO()
        self._finished = threading.Event()

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        if self._finished.wait(timeout):
            return self.returncode
        raise subprocess.TimeoutExpired("service", timeout)

    def stop(self) -> None:
        self.returncode = -15
        self._finished.set()


class FakeShellExecutor:
    """避免测试启动真实长期服务。"""

    def __init__(self) -> None:
        self.process = BlockingProcess()
        self.calls = []

    def start(self, command, *, cwd):
        self.calls.append({"command": command, "cwd": cwd})
        return self.process


class SessionProcessManagerTests(unittest.TestCase):
    """后台进程只能由创建它的打开 Session 管理。"""

    def setUp(self) -> None:
        self.workspace = tempfile.TemporaryDirectory()
        self.addCleanup(self.workspace.cleanup)
        self.executor = FakeShellExecutor()
        self.terminated = []
        self.manager = SessionProcessManager(
            "session_1",
            shell_executor=self.executor,
            terminate_process=lambda process: (self.terminated.append(process.pid), process.stop()),
            startup_probe_seconds=0.001,
        )

    def test_starts_and_stops_a_session_owned_process(self) -> None:
        """启动后立即可查询，停止只作用于该记录关联的进程树。"""
        started = self.manager.start("npm run dev", cwd=self.workspace.name)

        self.assertEqual(started["state"], "running")
        self.assertEqual(started["command"], "npm run dev")
        self.assertEqual(self.manager.status(started["process_id"])["pid"], 12345)

        stopped = self.manager.stop(started["process_id"])

        self.assertEqual(stopped["state"], "stopped")
        self.assertEqual(self.terminated, [12345])

    def test_another_session_manager_cannot_observe_or_stop_the_process(self) -> None:
        """进程 ID 即使泄露也不能越过 Session 内存边界。"""
        started = self.manager.start("npm run dev", cwd=self.workspace.name)
        another = SessionProcessManager("session_2", startup_probe_seconds=0.001)

        with self.assertRaises(ProcessManagerError) as raised:
            another.status(started["process_id"])

        self.assertEqual(raised.exception.code, "PROCESS_NOT_FOUND")

    def test_stopped_process_cursor_is_bound_to_its_process_id(self) -> None:
        """不同后台服务不能互换日志 cursor。"""
        first = self.manager.start("first", cwd=self.workspace.name)
        with self.assertRaises(ProcessManagerError) as raised:
            self.manager.logs(
                first["process_id"],
                cursor_process_id="proc_other",
                stdout_offset=0,
                stderr_offset=0,
                limit=100,
            )

        self.assertEqual(raised.exception.code, "INVALID_LOG_CURSOR")

    def test_close_stops_all_processes_without_requiring_runtime_cancel(self) -> None:
        """Session 关闭必须清理服务，但 Runtime 取消不参与该生命周期。"""
        self.manager.start("npm run dev", cwd=self.workspace.name)

        self.manager.stop_all()

        self.assertEqual(self.terminated, [12345])

    def test_wait_returns_running_state_after_a_finite_wait(self) -> None:
        """等待不会把持续服务变成无限阻塞。"""
        started = self.manager.start("npm run dev", cwd=self.workspace.name)

        result = self.manager.wait(started["process_id"], timeout_seconds=0.001)

        self.assertEqual(result["state"], "running")

    def test_stop_all_does_not_relabel_an_already_exited_process(self) -> None:
        """自然退出记录不能被 Session 清理流程覆写为用户停止。"""
        self.executor.process.returncode = 0
        self.executor.process._finished.set()
        started = self.manager.start("one-shot", cwd=self.workspace.name)

        self.manager.stop_all()

        self.assertEqual(self.manager.status(started["process_id"])["state"], "exited")


if __name__ == "__main__":
    unittest.main()
