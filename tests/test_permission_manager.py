"""Session 权限管理器的规则匹配与决策顺序测试。"""

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parents[1] / "code" / "agent"))

from permission.PermissionManager import PermissionManager  # noqa: E402
from permission.policies import HardSafetyPolicy, ProtectedResourcePolicy  # noqa: E402
from permission.types import (  # noqa: E402
    PermissionAction,
    PermissionDecision,
    PermissionMode,
    PermissionRequest,
    PermissionScope,
)


class PermissionManagerTests(unittest.TestCase):
    """验证 Session 规则、资源范围和策略优先级。"""

    def setUp(self) -> None:
        self.session_id = "session_4N9C1R7WBA"
        self.manager = PermissionManager(
            mode=PermissionMode.BUILD,
            session_id=self.session_id,
            project_path="/workspace",
            hard_safety_policy=HardSafetyPolicy(),
            protected_resource_policy=ProtectedResourcePolicy(["/system"]),
        )

    def _request(
        self,
        *,
        action: PermissionAction = PermissionAction.FILE_WRITE,
        resource: str | None = "/workspace/src/app.py",
        call_id: str = "call_001",
        session_id: str | None = None,
    ) -> PermissionRequest:
        return PermissionRequest(
            action=action,
            resource=resource,
            tool_name="write",
            call_id=call_id,
            session_id=session_id or self.session_id,
        )

    def test_build_mode_falls_back_to_ask_for_unruled_write(self) -> None:
        self.assertEqual(self.manager.check(self._request()), PermissionDecision.ASK)

    def test_once_decision_does_not_create_a_reusable_rule(self) -> None:
        request = self._request(call_id="call_123")

        self.assertIsNone(
            self.manager.grant(
                request,
                scope=PermissionScope.ONCE,
                resource="/workspace/src",
            )
        )
        self.assertEqual(self.manager.check(request), PermissionDecision.ASK)

    def test_session_rule_matches_later_calls_in_the_same_session(self) -> None:
        request = self._request()
        self.manager.grant(
            request,
            scope=PermissionScope.SESSION,
            resource="/workspace/src",
        )

        self.assertEqual(
            self.manager.check(self._request(call_id="call_002")),
            PermissionDecision.ALLOW,
        )

    def test_manager_rejects_requests_from_another_session(self) -> None:
        with self.assertRaisesRegex(ValueError, "不属于当前 Session"):
            self.manager.check(self._request(session_id="session_8T2L6MZP1"))

    def test_permission_scope_has_no_agent_member(self) -> None:
        self.assertNotIn("AGENT", PermissionScope.__members__)

    def test_deeper_rule_overrides_broader_rule(self) -> None:
        request = self._request(resource="/workspace/src/.env")
        self.manager.grant(
            request,
            scope=PermissionScope.SESSION,
            resource="/workspace/src",
        )
        self.manager.deny(
            request,
            scope=PermissionScope.SESSION,
            resource="/workspace/src/.env",
        )

        self.assertEqual(self.manager.check(request), PermissionDecision.DENY)
        self.assertEqual(
            self.manager.check(self._request(resource="/workspace/src/app.py")),
            PermissionDecision.ALLOW,
        )

    def test_path_matching_respects_directory_boundaries(self) -> None:
        request = self._request()
        self.manager.grant(
            request,
            scope=PermissionScope.SESSION,
            resource="/workspace/src",
        )

        self.assertEqual(
            self.manager.check(self._request(resource="/workspace/src/module.py")),
            PermissionDecision.ALLOW,
        )
        self.assertEqual(
            self.manager.check(self._request(resource="/workspace/src-other/module.py")),
            PermissionDecision.ASK,
        )

    def test_latest_rule_replaces_same_action_and_resource_slot(self) -> None:
        request = self._request()
        self.manager.grant(
            request,
            scope=PermissionScope.SESSION,
            resource="/workspace/src",
        )
        self.manager.deny(
            request,
            scope=PermissionScope.SESSION,
            resource="/workspace/src",
        )

        self.assertEqual(self.manager.check(request), PermissionDecision.DENY)

    def test_hard_safety_overrides_explicit_yolo_allow_rule(self) -> None:
        manager = PermissionManager(
            mode=PermissionMode.YOLO,
            session_id=self.session_id,
            project_path="/workspace",
            hard_safety_policy=HardSafetyPolicy(),
            protected_resource_policy=ProtectedResourcePolicy(["/system"]),
        )
        request = self._request(resource="/etc/passwd")
        manager.grant(
            request,
            scope=PermissionScope.SESSION,
            resource="/etc/passwd",
        )

        self.assertEqual(manager.check(request), PermissionDecision.DENY)

    def test_protected_resource_overrides_explicit_yolo_allow_rule(self) -> None:
        manager = PermissionManager(
            mode=PermissionMode.YOLO,
            session_id=self.session_id,
            project_path="/workspace",
            hard_safety_policy=HardSafetyPolicy(),
            protected_resource_policy=ProtectedResourcePolicy(["/system"]),
        )
        request = self._request(resource="/system/config")
        manager.grant(
            request,
            scope=PermissionScope.SESSION,
            resource="/system",
        )

        self.assertEqual(manager.check(request), PermissionDecision.ASK)


if __name__ == "__main__":
    unittest.main()
