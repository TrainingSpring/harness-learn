"""统一 Bash Tool 的 action 与动态权限契约。"""

import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parents[2] / "code" / "agent"))

from permission.types import PermissionAction  # noqa: E402
from session.ExecutionContext import ExecutionContext  # noqa: E402
from tools.bash import REGISTER as BASH_TOOL  # noqa: E402
from tools.tools import Tools  # noqa: E402


class BashActionTests(unittest.TestCase):
    """Shell 的前台和后台能力通过一个公开 Tool 进入权限管线。"""

    def test_resolves_permission_from_the_validated_action(self) -> None:
        """启动、检查和停止不能共用错误的静态权限动作。"""
        with tempfile.TemporaryDirectory() as workspace:
            tools = Tools(ExecutionContext(workspace, "agent_1", "session_1"))
            tools.register(BASH_TOOL)

            expected_actions = {
                "execute": ("command", PermissionAction.BASH_EXECUTE),
                "start": ("command", PermissionAction.BASH_EXECUTE),
                "status": ("process_id", PermissionAction.PROCESS_INSPECT),
                "logs": ("process_id", PermissionAction.PROCESS_INSPECT),
                "wait": ("process_id", PermissionAction.PROCESS_INSPECT),
                "stop": ("process_id", PermissionAction.PROCESS_STOP),
            }
            for action, (field, expected_permission) in expected_actions.items():
                with self.subTest(action=action):
                    call = tools.prepare_call(
                        "bash",
                        {"action": action, field: "npm run dev" if field == "command" else "proc_123"},
                        f"call_{action}",
                    )
                    self.assertEqual(call.permission_request.action, expected_permission)


if __name__ == "__main__":
    unittest.main()
