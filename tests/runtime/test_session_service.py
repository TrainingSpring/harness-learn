"""固定成员 Session 创建服务的集成测试。"""

import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parents[2] / "code" / "agent"))

from runtime.session_service import SessionService  # noqa: E402
from storage.database import StateDatabase  # noqa: E402
from storage.repositories.agent_profile import AgentProfileRepository  # noqa: E402
from storage.repositories.llm_profile import LLMProfileRepository  # noqa: E402
from storage.repositories.session_agent import SessionAgentRepository  # noqa: E402
from storage.types import AgentProfile, LLMProfile  # noqa: E402


class SessionServiceTests(unittest.TestCase):
    """验证 DIRECT 与 GROUP 会话在创建时一次性固定 Agent。"""

    def setUp(self):
        """创建三个可用于会话选择的 Agent。"""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = StateDatabase(self.temp_dir.name)
        self.database.initialize()
        LLMProfileRepository(self.database).save(
            LLMProfile(
                id="llm_7KQ2M8P4XZ",
                name="通用模型",
                provider="openai",
                base_url=None,
                model="gpt-5",
                credential_ref="env:OPENAI_API_KEY",
            )
        )
        agents = AgentProfileRepository(self.database)
        for agent_id in (
            "agent_1V3ASAXQ2A",
            "agent_9U3M7BKP2C",
            "agent_8LRT3N5QYB",
        ):
            agents.save(
                AgentProfile(
                    id=agent_id,
                    name=agent_id,
                    description="讨论角色",
                    personality="务实",
                    expertise=["Python"],
                    llm_profile_id="llm_7KQ2M8P4XZ",
                    tools=["read"],
                    permission_mode="BUILD",
                )
            )
        self.service = SessionService(self.database)
        self.members = SessionAgentRepository(self.database)

    def tearDown(self):
        """关闭数据库并清理临时目录。"""
        self.database.close()
        self.temp_dir.cleanup()

    def test_create_direct_session_has_exactly_one_primary_agent(self):
        """1v1 会话只能由用户选中的一个 Agent 构成。"""
        session = self.service.create_direct_session(
            "agent_1V3ASAXQ2A",
            title="代码讨论",
        )

        members = self.members.list_for_session(session.id)
        self.assertEqual(session.conversation_mode, "DIRECT")
        self.assertEqual(
            [(member.agent_id, member.role) for member in members],
            [("agent_1V3ASAXQ2A", "PRIMARY")],
        )

    def test_create_group_session_requires_distinct_multiple_agents(self):
        """1vN 群聊至少选择两个不同的 Agent，所有成员地位相同。"""
        session = self.service.create_group_session(
            ["agent_1V3ASAXQ2A", "agent_9U3M7BKP2C"]
        )

        members = self.members.list_for_session(session.id)
        self.assertEqual(session.conversation_mode, "GROUP")
        self.assertEqual({member.role for member in members}, {"MEMBER"})
        self.assertEqual(
            {member.agent_id for member in members},
            {"agent_1V3ASAXQ2A", "agent_9U3M7BKP2C"},
        )

    def test_group_rejects_too_few_or_duplicate_agents_without_writing(self):
        """非法群聊配置应在写库前失败，不能留下空 Session。"""
        for agent_ids in (
            ["agent_1V3ASAXQ2A"],
            ["agent_1V3ASAXQ2A", "agent_1V3ASAXQ2A"],
        ):
            with self.subTest(agent_ids=agent_ids):
                with self.assertRaises(ValueError):
                    self.service.create_group_session(agent_ids)

        count = self.database.connection.execute(
            "SELECT COUNT(*) FROM sessions"
        ).fetchone()[0]
        self.assertEqual(count, 0)

    def test_unknown_agent_rolls_back_session_and_members(self):
        """成员外键失败时，会话和已插入成员必须一起回滚。"""
        with self.assertRaises(ValueError):
            self.service.create_group_session(
                ["agent_1V3ASAXQ2A", "agent_7QWP4N6KTM"]
            )

        session_count = self.database.connection.execute(
            "SELECT COUNT(*) FROM sessions"
        ).fetchone()[0]
        member_count = self.database.connection.execute(
            "SELECT COUNT(*) FROM session_agents"
        ).fetchone()[0]
        self.assertEqual((session_count, member_count), (0, 0))


if __name__ == "__main__":
    unittest.main()
