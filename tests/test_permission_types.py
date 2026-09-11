"""权限领域值对象与执行身份的契约测试。"""

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parents[1] / "code" / "agent"))

from permission.types import (  # noqa: E402
    PermissionAction,
    PermissionDecision,
    PermissionRequest,
    PermissionResponse,
    PermissionRule,
    PermissionScope,
)
from runtime.ExecutionContext import ExecutionContext  # noqa: E402


class PermissionTypeTests(unittest.TestCase):
    """验证权限值对象不会接受语义自相矛盾的状态。"""

    def setUp(self):
        """为每个测试提供同一份实际权限请求。"""
        self.request = PermissionRequest(
            action=PermissionAction.FILE_WRITE,
            resource="/workspace/src/app.py",
            tool_name="write",
            call_id="call_001",
            session_id="session_001",
            agent_id="agent_1V3ASAXQ2A",
        )

    def test_once_rule_binds_only_the_current_call(self):
        """ONCE 规则只能绑定 call_id，不能混入会话或 Agent 身份。"""
        rule = PermissionRule(
            action=PermissionAction.FILE_WRITE,
            resource="/workspace/src",
            decision=PermissionDecision.ALLOW,
            scope=PermissionScope.ONCE,
            call_id="call_001",
        )

        self.assertEqual(rule.call_id, "call_001")
        self.assertIsNone(rule.session_id)
        self.assertIsNone(rule.agent_id)

    def test_rule_rejects_ask_as_a_persisted_decision(self):
        """ASK 是暂态结果，不能被保存为允许/拒绝规则。"""
        with self.assertRaises(ValueError):
            PermissionRule(
                action=PermissionAction.FILE_WRITE,
                resource="/workspace/src",
                decision=PermissionDecision.ASK,
                scope=PermissionScope.ONCE,
                call_id="call_001",
            )

    def test_rule_rejects_scope_identity_from_another_scope(self):
        """SESSION 规则不能错误绑定 call_id，避免规则作用范围失真。"""
        with self.assertRaises(ValueError):
            PermissionRule(
                action=PermissionAction.FILE_WRITE,
                resource="/workspace/src",
                decision=PermissionDecision.ALLOW,
                scope=PermissionScope.SESSION,
                call_id="call_001",
                session_id="session_001",
            )

    def test_response_rejects_ask_decision(self):
        """用户确认只能明确允许或拒绝，不能再次返回 ASK。"""
        with self.assertRaises(ValueError):
            PermissionResponse(
                call_id="call_001",
                decision=PermissionDecision.ASK,
                scope=PermissionScope.ONCE,
            )

    def test_bash_request_can_have_no_resource(self):
        """bash 首版按动作授权，不伪造无法可靠推导的文件资源。"""
        request = PermissionRequest(
            action=PermissionAction.BASH_EXECUTE,
            resource=None,
            tool_name="bash",
            call_id="call_002",
            session_id="session_001",
            agent_id="agent_1V3ASAXQ2A",
        )

        self.assertIsNone(request.resource)

    def test_execution_context_separates_agent_and_session_identity(self):
        """Agent 长期身份与当前会话身份必须是不同字段。"""
        ctx = ExecutionContext(
            workspace="/workspace",
            agent_id="agent_1V3ASAXQ2A",
            session_id="session_001",
        )

        self.assertEqual(ctx.workspace, "/workspace")
        self.assertEqual(ctx.agent_id, "agent_1V3ASAXQ2A")
        self.assertEqual(ctx.session_id, "session_001")
        self.assertEqual(ctx.max_tool_call_length, 20_000)


if __name__ == "__main__":
    unittest.main()
