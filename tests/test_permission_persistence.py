"""PermissionManager 与 Agent 级权限规则仓储的集成测试。"""

import sys
import tempfile
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
from storage.database import StateDatabase  # noqa: E402
from storage.repositories.agent_profile import AgentProfileRepository  # noqa: E402
from storage.repositories.llm_profile import LLMProfileRepository  # noqa: E402
from storage.repositories.permission_rule import PermissionRuleRepository  # noqa: E402
from storage.types import AgentProfile, LLMProfile  # noqa: E402


class PermissionPersistenceTests(unittest.TestCase):
    """验证权限管理器与持久化 Agent 规则之间的边界。"""

    def setUp(self):
        """创建两个 Agent 和一个真实的权限规则仓储。"""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = StateDatabase(self.temp_dir.name)
        self.database.initialize()
        llm_repository = LLMProfileRepository(self.database)
        agent_repository = AgentProfileRepository(self.database)
        llm_repository.save(
            LLMProfile(
                id="llm_7KQ2M8P4XZ",
                name="代码模型",
                provider="openai",
                base_url=None,
                model="gpt-5",
                credential_ref="env:OPENAI_API_KEY",
            )
        )
        for agent_id, name in (
            ("agent_1V3ASAXQ2A", "代码专家"),
            ("agent_9U3M7BKP2C", "测试专家"),
        ):
            agent_repository.save(
                AgentProfile(
                    id=agent_id,
                    name=name,
                    description="开发工作",
                    personality="务实",
                    expertise=["Python"],
                    llm_profile_id="llm_7KQ2M8P4XZ",
                    tools=["read"],
                    permission_mode="BUILD",
                )
            )
        self.repository = PermissionRuleRepository(self.database)
        self.workspace = str(Path(self.temp_dir.name).resolve())

    def tearDown(self):
        """关闭数据库并清理临时目录。"""
        self.database.close()
        self.temp_dir.cleanup()

    def _manager(self, agent_id):
        """创建指定 Agent 的持久化权限管理器。"""
        return PermissionManager(
            mode=PermissionMode.BUILD,
            workspace=self.workspace,
            agent_id=agent_id,
            rule_repository=self.repository,
            hard_safety_policy=HardSafetyPolicy(),
            protected_resource_policy=ProtectedResourcePolicy(["/system"]),
        )

    def _request(self, *, agent_id="agent_1V3ASAXQ2A", session_id="session_4N9C1R7WBA", call_id="call_001"):
        """创建 workspace 内的文件写入请求。"""
        return PermissionRequest(
            action=PermissionAction.FILE_WRITE,
            resource=str(Path(self.workspace) / "src" / "app.py"),
            tool_name="write",
            call_id=call_id,
            session_id=session_id,
            agent_id=agent_id,
        )

    def test_agent_rule_survives_manager_recreation(self):
        """Agent 级允许规则重建权限管理器后仍然有效。"""
        request = self._request()
        self._manager(request.agent_id).grant(
            request,
            scope=PermissionScope.AGENT,
            resource=str(Path(self.workspace) / "src"),
        )

        recreated = self._manager(request.agent_id)

        self.assertEqual(recreated.check(request), PermissionDecision.ALLOW)

    def test_agent_rules_are_not_visible_to_another_agent(self):
        """一个 Agent 保存的规则不能放行另一个 Agent 的请求。"""
        request = self._request()
        self._manager(request.agent_id).grant(
            request,
            scope=PermissionScope.AGENT,
            resource=str(Path(self.workspace) / "src"),
        )

        other_request = self._request(agent_id="agent_9U3M7BKP2C")

        self.assertEqual(
            self._manager(other_request.agent_id).check(other_request),
            PermissionDecision.ASK,
        )

    def test_once_and_session_rules_are_not_restored_from_database(self):
        """ONCE/SESSION 规则只属于当前运行时，重建后必须重新询问。"""
        request = self._request()
        manager = self._manager(request.agent_id)
        manager.grant(request, scope=PermissionScope.ONCE, resource=str(Path(self.workspace) / "src"))
        manager.grant(request, scope=PermissionScope.SESSION, resource=str(Path(self.workspace) / "src"))

        recreated = self._manager(request.agent_id)

        self.assertEqual(recreated.check(request), PermissionDecision.ASK)

    def test_agent_rule_database_failure_does_not_update_memory(self):
        """Agent 规则落库失败时不能提前更新内存授权。"""
        class FailingRepository:
            """模拟持久化失败的最小仓储。"""

            def list_for_agent(self, _agent_id):
                """启动时返回空规则。"""
                return []

            def save(self, _rule):
                """模拟数据库写入失败。"""
                raise RuntimeError("database unavailable")

        manager = PermissionManager(
            mode=PermissionMode.BUILD,
            workspace=self.workspace,
            agent_id="agent_1V3ASAXQ2A",
            rule_repository=FailingRepository(),
            protected_resource_policy=ProtectedResourcePolicy(["/system"]),
        )
        request = self._request()

        with self.assertRaises(RuntimeError):
            manager.grant(
                request,
                scope=PermissionScope.AGENT,
                resource=str(Path(self.workspace) / "src"),
            )

        self.assertEqual(manager.check(request), PermissionDecision.ASK)


if __name__ == "__main__":
    unittest.main()
