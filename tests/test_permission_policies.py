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

    def test_build_mode_allows_workspace_access_and_asks_for_external_access(self):
        """BUILD 默认允许工作目录内读写，只对目录外访问确认。"""
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
            PermissionDecision.ALLOW,
        )
        self.assertEqual(
            policy.decide(
                PermissionMode.BUILD,
                self._request(PermissionAction.FILE_READ, "/outside/secret.txt"),
            ),
            PermissionDecision.ASK,
        )

    def test_yolo_mode_allows_external_files_by_default(self):
        """YOLO 默认允许工作目录外文件访问。"""
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

    def test_empty_project_denies_every_project_tool_action(self):
        policy = ModePolicy(None)

        self.assertEqual(
            policy.decide(PermissionMode.YOLO, self._request(PermissionAction.FILE_READ)),
            PermissionDecision.DENY,
        )

    def test_process_inspection_and_stop_are_allowed_in_every_mode(self):
        """这些动作只能作用于 Session 自己的内存记录，不读取外部资源。"""
        policy = ModePolicy(None)
        for mode in PermissionMode:
            for action in (PermissionAction.PROCESS_INSPECT, PermissionAction.PROCESS_STOP):
                with self.subTest(mode=mode, action=action):
                    self.assertEqual(
                        policy.decide(mode, self._request(action, None)),
                        PermissionDecision.ALLOW,
                    )


if __name__ == "__main__":
    unittest.main()
