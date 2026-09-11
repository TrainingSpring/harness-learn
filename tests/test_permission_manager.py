"""PermissionManager 规则匹配与决策顺序的测试。"""

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
    """验证规则作用域、资源范围和策略优先级。"""

    def setUp(self):
        """每个测试使用独立的内存规则表和工作区。"""
        self.manager = PermissionManager(
            mode=PermissionMode.BUILD,
            workspace="/workspace",
            hard_safety_policy=HardSafetyPolicy(),
            protected_resource_policy=ProtectedResourcePolicy(["/system"]),
        )

    def _request(
        self,
        *,
        action: PermissionAction = PermissionAction.FILE_WRITE,
        resource: str | None = "/workspace/src/app.py",
        call_id: str = "call_001",
        session_id: str = "session_001",
        agent_id: str = "agent_1V3ASAXQ2A",
    ) -> PermissionRequest:
        """创建具有可替换身份字段的真实请求。"""
        return PermissionRequest(
            action=action,
            resource=resource,
            tool_name="write",
            call_id=call_id,
            session_id=session_id,
            agent_id=agent_id,
        )

    def test_build_mode_falls_back_to_ask_for_unruled_write(self):
        """没有规则时，BUILD 写入必须交给用户确认。"""
        self.assertEqual(
            self.manager.check(self._request()),
            PermissionDecision.ASK,
        )

    def test_grant_uses_request_identity_for_once_rule(self):
        """调用方不能伪造规则主体，ONCE 身份必须来自原请求。"""
        request = self._request(call_id="call_123")
        rule = self.manager.grant(
            request,
            scope=PermissionScope.ONCE,
            resource="/workspace/src",
        )

        self.assertEqual(rule.call_id, "call_123")
        self.assertIsNone(rule.session_id)
        self.assertEqual(
            self.manager.check(request),
            PermissionDecision.ALLOW,
        )
        self.assertEqual(
            self.manager.check(self._request(call_id="call_456")),
            PermissionDecision.ASK,
        )

    def test_session_rule_matches_same_session_but_not_another_session(self):
        """SESSION 规则只能覆盖同一会话内的后续调用。"""
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
        self.assertEqual(
            self.manager.check(self._request(session_id="session_002")),
            PermissionDecision.ASK,
        )

    def test_agent_rule_matches_new_session_for_same_logical_agent(self):
        """AGENT 规则跨会话生效，但不得授予其他逻辑 Agent。"""
        request = self._request()
        self.manager.grant(
            request,
            scope=PermissionScope.AGENT,
            resource="/workspace/src",
        )

        self.assertEqual(
            self.manager.check(
                self._request(call_id="call_002", session_id="session_002")
            ),
            PermissionDecision.ALLOW,
        )
        self.assertEqual(
            self.manager.check(self._request(agent_id="agent_9U3M7BKP2C")),
            PermissionDecision.ASK,
        )

    def test_deeper_rule_overrides_broader_rule_in_same_scope(self):
        """更具体的目录规则能保护宽泛允许范围中的敏感文件。"""
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

    def test_path_matching_respects_directory_boundaries(self):
        """目录规则不能用字符串前缀错误覆盖相邻目录。"""
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

    def test_latest_rule_replaces_same_scope_action_and_resource(self):
        """同一规则槽位更新后，决策不应取决于列表遍历顺序。"""
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

    def test_hard_safety_overrides_explicit_yolo_allow_rule(self):
        """绝对黑名单必须先于显式允许和 YOLO 模式执行。"""
        manager = PermissionManager(
            mode=PermissionMode.YOLO,
            workspace="/workspace",
            hard_safety_policy=HardSafetyPolicy(),
            protected_resource_policy=ProtectedResourcePolicy(["/system"]),
        )
        request = self._request(resource="/etc/passwd")
        manager.grant(
            request,
            scope=PermissionScope.AGENT,
            resource="/etc/passwd",
        )

        self.assertEqual(manager.check(request), PermissionDecision.DENY)

    def test_protected_resource_overrides_explicit_yolo_allow_rule(self):
        """受保护资源即使已有允许规则，也必须再次询问用户。"""
        manager = PermissionManager(
            mode=PermissionMode.YOLO,
            workspace="/workspace",
            hard_safety_policy=HardSafetyPolicy(),
            protected_resource_policy=ProtectedResourcePolicy(["/system"]),
        )
        request = self._request(resource="/system/config")
        manager.grant(
            request,
            scope=PermissionScope.AGENT,
            resource="/system",
        )

        self.assertEqual(manager.check(request), PermissionDecision.ASK)


if __name__ == "__main__":
    unittest.main()
