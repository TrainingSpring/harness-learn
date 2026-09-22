"""SessionAgentRepository 的 SQLite 集成测试。"""

import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parents[2] / "code" / "agent"))

from storage.database import StateDatabase  # noqa: E402
from storage.repositories.agent_profile import AgentProfileRepository  # noqa: E402
from storage.repositories.llm_profile import LLMProfileRepository  # noqa: E402
from storage.repositories.session import SessionRepository  # noqa: E402
from storage.repositories.session_agent import SessionAgentRepository  # noqa: E402
from storage.types import AgentProfile, LLMProfile  # noqa: E402


class SessionAgentRepositoryTests(unittest.TestCase):
    """验证 Session 与固定 Agent 成员之间的关联。"""

    def setUp(self):
        """创建会话、两个 Agent 和成员仓储。"""
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
                api_key="sk-test-key",
            )
        )
        agents = AgentProfileRepository(self.database)
        for agent_id, name in (
            ("agent_1V3ASAXQ2A", "代码专家"),
            ("agent_9U3M7BKP2C", "测试专家"),
        ):
            agents.save(
                AgentProfile(
                    id=agent_id,
                    name=name,
                    description="开发工作",
                    personality="务实",
                    expertise=["Python"],
                    llm_profile_id="llm_7KQ2M8P4XZ",
                    tools=["read"],
                )
            )
        self.session = SessionRepository(self.database).create_with_agents(
            "GROUP",
            [
                ("agent_1V3ASAXQ2A", "MEMBER"),
                ("agent_9U3M7BKP2C", "MEMBER"),
            ],
            "协作",
        )
        self.repository = SessionAgentRepository(self.database)

    def tearDown(self):
        """关闭数据库并清理临时目录。"""
        self.database.close()
        self.temp_dir.cleanup()

    def test_get_exists_and_list_round_trip(self):
        """成员可按 session_id 与 agent_id 联合身份读取。"""
        member = self.repository.get(self.session.id, "agent_1V3ASAXQ2A")
        self.assertIsNotNone(member.created_at)
        self.assertEqual(
            self.repository.get(self.session.id, member.agent_id),
            member,
        )
        self.assertTrue(self.repository.exists(self.session.id, member.agent_id))
        self.assertEqual(len(self.repository.list_for_session(self.session.id)), 2)

    def test_member_cannot_be_removed_or_replaced(self):
        """固定角色会话的成员仓储不提供退出或更新入口。"""
        self.assertFalse(hasattr(self.repository, "add"))
        self.assertFalse(hasattr(self.repository, "leave"))
        self.assertFalse(hasattr(self.repository, "replace"))


if __name__ == "__main__":
    unittest.main()
