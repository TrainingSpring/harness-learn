"""PermissionRuleRepository 的 SQLite 集成测试。"""

import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parents[2] / "code" / "agent"))

from permission.types import (  # noqa: E402
    PermissionAction,
    PermissionDecision,
    PermissionRule,
    PermissionScope,
)
from storage.database import StateDatabase  # noqa: E402
from storage.errors import StorageFormatError  # noqa: E402
from storage.repositories.agent_profile import AgentProfileRepository  # noqa: E402
from storage.repositories.llm_profile import LLMProfileRepository  # noqa: E402
from storage.repositories.permission_rule import PermissionRuleRepository  # noqa: E402
from storage.types import AgentProfile, LLMProfile  # noqa: E402


class PermissionRuleRepositoryTests(unittest.TestCase):
    """验证 Agent 级权限规则的保存、隔离和安全边界。"""

    def setUp(self):
        """创建带 Agent 外键的独立测试数据库。"""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = StateDatabase(self.temp_dir.name)
        self.database.initialize()
        self.llm_repository = LLMProfileRepository(self.database)
        self.agent_repository = AgentProfileRepository(self.database)
        self.repository = PermissionRuleRepository(self.database)
        self.llm_repository.save(
            LLMProfile(
                id="llm_7KQ2M8P4XZ",
                name="代码模型",
                provider="openai",
                base_url="https://api.openai.com/v1",
                model="gpt-5",
                credential_ref="env:OPENAI_API_KEY",
            )
        )
        for agent_id, name in (
            ("agent_1V3ASAXQ2A", "代码专家"),
            ("agent_9U3M7BKP2C", "测试专家"),
        ):
            self.agent_repository.save(
                AgentProfile(
                    id=agent_id,
                    name=name,
                    description="负责开发工作",
                    personality="务实",
                    expertise=["Python"],
                    llm_profile_id="llm_7KQ2M8P4XZ",
                    tools=["read"],
                    permission_mode="BUILD",
                )
            )

    def tearDown(self):
        """关闭数据库并清理临时目录。"""
        self.database.close()
        self.temp_dir.cleanup()

    def _rule(self, *, agent_id="agent_1V3ASAXQ2A", resource=None, decision=PermissionDecision.ALLOW):
        """创建一条 Agent 级文件权限规则。"""
        workspace = str(Path(self.temp_dir.name).resolve())
        return PermissionRule(
            action=PermissionAction.FILE_WRITE,
            resource=resource or str(Path(workspace) / "src"),
            decision=decision,
            scope=PermissionScope.AGENT,
            agent_id=agent_id,
        )

    def test_save_and_list_round_trip_rehydrates_absolute_workspace_path(self):
        """数据库保存相对路径，读取后恢复为当前 workspace 下的绝对路径。"""
        rule = self._rule()

        self.repository.save(rule)

        loaded = self.repository.list_for_agent("agent_1V3ASAXQ2A")

        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0].resource, rule.resource)
        stored = self.database.connection.execute(
            "SELECT resource_kind, resource_value FROM permission_agent_rules"
        ).fetchone()
        self.assertEqual(stored[0], "path")
        self.assertEqual(stored[1], "src")

    def test_rules_are_isolated_by_agent_id(self):
        """一个 Agent 不能读取另一个 Agent 的权限规则。"""
        self.repository.save(self._rule())

        self.assertEqual(self.repository.list_for_agent("agent_9U3M7BKP2C"), [])

    def test_save_replaces_same_action_and_resource_slot(self):
        """同一 Agent、动作和资源槽位保存新决定时应更新旧规则。"""
        self.repository.save(self._rule())
        self.repository.save(self._rule(decision=PermissionDecision.DENY))

        loaded = self.repository.list_for_agent("agent_1V3ASAXQ2A")

        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0].decision, PermissionDecision.DENY)

    def test_rejects_non_agent_scope_and_bash_rules(self):
        """首期 Repository 只持久化 Agent 级文件规则。"""
        with self.assertRaises(ValueError):
            self.repository.save(
                PermissionRule(
                    action=PermissionAction.FILE_WRITE,
                    resource=self._rule().resource,
                    decision=PermissionDecision.ALLOW,
                    scope=PermissionScope.SESSION,
                    session_id="session_4N9C1R7WBA",
                )
            )
        with self.assertRaises(ValueError):
            self.repository.save(
                PermissionRule(
                    action=PermissionAction.BASH_EXECUTE,
                    resource=None,
                    decision=PermissionDecision.ALLOW,
                    scope=PermissionScope.AGENT,
                    agent_id="agent_1V3ASAXQ2A",
                )
            )

    def test_rejects_paths_outside_workspace(self):
        """Agent 级持久化规则不能借数据库跨出 workspace。"""
        with self.assertRaises(ValueError):
            self.repository.save(self._rule(resource="/outside"))

    def test_corrupt_stored_path_fails_closed(self):
        """数据库中的越界路径不能被静默加载为有效权限。"""
        self.repository.save(self._rule())
        self.database.connection.execute(
            "UPDATE permission_agent_rules SET resource_value = ?",
            ("../../outside",),
        )
        self.database.connection.commit()

        with self.assertRaises(StorageFormatError):
            self.repository.list_for_agent("agent_1V3ASAXQ2A")


if __name__ == "__main__":
    unittest.main()
