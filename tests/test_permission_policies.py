"""权限策略的纯逻辑测试。"""

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parents[1] / "code" / "agent"))

from permission.policies import (  # noqa: E402
    HardSafetyPolicy,
    ModePolicy,
    ProtectedResourcePolicy,
)
from permission.types import (  # noqa: E402
    PermissionAction,
    PermissionDecision,
    PermissionMode,
    PermissionRequest,
)


class PermissionPolicyTests(unittest.TestCase):
    """验证硬安全、受保护资源和模式默认策略的边界。"""

    def _request(
        self,
        action: PermissionAction,
        resource: str | None = "/workspace/src/app.py",
    ) -> PermissionRequest:
        """创建带完整主体身份的测试请求。

        Args:
            action: 被测试的权限动作。
            resource: 被测试的实际资源；bash 可传入 None。

        Returns:
            可直接传入策略的权限请求。
        """
        return PermissionRequest(
            action=action,
            resource=resource,
            tool_name="test_tool",
            call_id="call_001",
            session_id="session_001",
            agent_id="agent_1V3ASAXQ2A",
        )

    def test_hard_safety_denies_writing_critical_system_files(self):
        """关键认证文件不能通过普通规则或模式授权修改。"""
        decision = HardSafetyPolicy().check(
            self._request(PermissionAction.FILE_WRITE, "/etc/passwd")
        )

        self.assertEqual(decision, PermissionDecision.DENY)

    def test_hard_safety_denies_known_root_delete_command(self):
        """只识别明确的根目录递归删除形式，不假装理解完整 shell。"""
        decision = HardSafetyPolicy().check(
            self._request(PermissionAction.BASH_EXECUTE, None),
            command="rm -rf /",
        )

        self.assertEqual(decision, PermissionDecision.DENY)

    def test_hard_safety_does_not_block_regular_project_delete_command(self):
        """有限黑名单不能将正常项目清理误判为绝对危险操作。"""
        decision = HardSafetyPolicy().check(
            self._request(PermissionAction.BASH_EXECUTE, None),
            command="rm -rf build",
        )

        self.assertIsNone(decision)

    def test_protected_resource_requires_confirmation_for_read_and_write(self):
        """受保护目录的读取与写入都必须走 ASK，而非自动放行。"""
        policy = ProtectedResourcePolicy(["/system"])

        self.assertTrue(
            policy.requires_confirmation(
                self._request(PermissionAction.FILE_READ, "/system/config")
            )
        )
        self.assertTrue(
            policy.requires_confirmation(
                self._request(PermissionAction.FILE_WRITE, "/system/config")
            )
        )

    def test_plan_mode_allows_workspace_reads_but_denies_side_effects(self):
        """PLAN 模式只允许项目内读取，不允许文件写入或命令执行。"""
        policy = ModePolicy("/workspace")

        self.assertEqual(
            policy.decide(
                PermissionMode.PLAN,
                self._request(PermissionAction.FILE_READ),
            ),
            PermissionDecision.ALLOW,
        )
        self.assertEqual(
            policy.decide(
                PermissionMode.PLAN,
                self._request(PermissionAction.FILE_WRITE),
            ),
            PermissionDecision.DENY,
        )
        self.assertEqual(
            policy.decide(
                PermissionMode.PLAN,
                self._request(PermissionAction.BASH_EXECUTE, None),
            ),
            PermissionDecision.DENY,
        )

    def test_build_mode_requires_confirmation_for_side_effects_and_external_reads(self):
        """BUILD 允许项目内读取，副作用和项目外访问都要求确认。"""
        policy = ModePolicy("/workspace")

        self.assertEqual(
            policy.decide(
                PermissionMode.BUILD,
                self._request(PermissionAction.FILE_READ),
            ),
            PermissionDecision.ALLOW,
        )
        self.assertEqual(
            policy.decide(
                PermissionMode.BUILD,
                self._request(PermissionAction.FILE_WRITE),
            ),
            PermissionDecision.ASK,
        )
        self.assertEqual(
            policy.decide(
                PermissionMode.BUILD,
                self._request(PermissionAction.FILE_READ, "/outside/secret.txt"),
            ),
            PermissionDecision.ASK,
        )

    def test_yolo_mode_allows_regular_external_actions(self):
        """YOLO 只决定普通资源默认值，硬安全和保护策略由 Manager 先处理。"""
        policy = ModePolicy("/workspace")

        self.assertEqual(
            policy.decide(
                PermissionMode.YOLO,
                self._request(PermissionAction.FILE_WRITE, "/outside/file.txt"),
            ),
            PermissionDecision.ALLOW,
        )
        self.assertEqual(
            policy.decide(
                PermissionMode.YOLO,
                self._request(PermissionAction.BASH_EXECUTE, None),
            ),
            PermissionDecision.ALLOW,
        )


if __name__ == "__main__":
    unittest.main()
