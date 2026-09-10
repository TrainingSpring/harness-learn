"""CLI 权限请求展示与用户选择解析测试。"""

import io
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).parents[1] / "code" / "agent"))
sys.path.insert(0, str(Path(__file__).parents[1] / "code" / "cli"))

from main import read_permission_response, render_permission_request  # noqa: E402
from permission.types import (  # noqa: E402
    PermissionAction,
    PermissionDecision,
    PermissionRequest,
    PermissionScope,
)
from runtime.runtime import PermissionRequiredEvent  # noqa: E402


class CliPermissionTests(unittest.TestCase):
    """验证 CLI 只负责权限确认输入，不自行执行工具。"""

    def setUp(self):
        """构造一个待确认的文件写入事件。"""
        request = PermissionRequest(
            action=PermissionAction.FILE_WRITE,
            resource="/workspace/src/app.py",
            tool_name="write",
            call_id="call_001",
            session_id="session_001",
            agent_key="code_editor",
        )
        self.event = PermissionRequiredEvent(
            type="permission_required",
            request=request,
        )

    def test_render_permission_request_shows_action_and_real_resource(self):
        """用户确认提示必须展示规范化后的真实资源。"""
        output = io.StringIO()
        with redirect_stdout(output):
            render_permission_request(self.event)

        text = output.getvalue()
        self.assertIn("write", text)
        self.assertIn("filesystem.write", text)
        self.assertIn("/workspace/src/app.py", text)

    def test_read_permission_response_maps_allow_session_choice(self):
        """选择当前会话允许时，应生成 SESSION + ALLOW 响应。"""
        with patch("builtins.input", return_value="2"):
            response = read_permission_response(self.event)

        self.assertEqual(response.call_id, "call_001")
        self.assertEqual(response.decision, PermissionDecision.ALLOW)
        self.assertEqual(response.scope, PermissionScope.SESSION)

    def test_read_permission_response_retries_invalid_choice(self):
        """非法选项只重新询问，不能默认放行。"""
        with patch("builtins.input", side_effect=["invalid", "6"]):
            response = read_permission_response(self.event)

        self.assertEqual(response.decision, PermissionDecision.DENY)
        self.assertEqual(response.scope, PermissionScope.AGENT)


if __name__ == "__main__":
    unittest.main()
