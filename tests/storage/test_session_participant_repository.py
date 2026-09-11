"""SessionParticipantRepository 的 SQLite 集成测试。"""

import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parents[2] / "code" / "agent"))

from storage.database import StateDatabase  # noqa: E402
from storage.errors import StorageConflictError  # noqa: E402
from storage.repositories.agent_profile import AgentProfileRepository  # noqa: E402
from storage.repositories.llm_profile import LLMProfileRepository  # noqa: E402
from storage.repositories.session import SessionRepository  # noqa: E402
from storage.repositories.session_participant import SessionParticipantRepository  # noqa: E402
from storage.types import AgentProfile, LLMProfile, SessionParticipant  # noqa: E402


class SessionParticipantRepositoryTests(unittest.TestCase):
    """验证多 Agent 会话参与关系及其生命周期。"""

    def setUp(self):
        """创建会话、两个 Agent 和参与者仓储。"""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = StateDatabase(self.temp_dir.name)
        self.database.initialize()
        llm_repository = LLMProfileRepository(self.database)
        agent_repository = AgentProfileRepository(self.database)
        llm_repository.save(
            LLMProfile(
                id="llm_7KQ2M8P4XZ",
                name="通用模型",
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
        self.session = SessionRepository(self.database).create("GROUP", "协作")
        self.repository = SessionParticipantRepository(self.database)

    def tearDown(self):
        """关闭数据库并清理临时目录。"""
        self.database.close()
        self.temp_dir.cleanup()

    def _participant(self, participant_id, agent_id, role="PARTICIPANT"):
        """创建一个待加入当前会话的参与者。"""
        return SessionParticipant(
            id=participant_id,
            session_id=self.session.id,
            agent_id=agent_id,
            role=role,
            join_reason="USER_SELECTED",
        )

    def test_add_get_find_and_list_active_round_trip(self):
        """参与者可保存、按 ID 查询、按 Agent 查找并列出。"""
        participant = self.repository.add(
            self._participant("participant_8T2LQ6MZP1", "agent_1V3ASAXQ2A", "PRIMARY")
        )

        self.assertIsNotNone(participant.joined_at)
        self.assertEqual(self.repository.get(participant.id).agent_id, "agent_1V3ASAXQ2A")
        self.assertEqual(
            self.repository.find(self.session.id, "agent_1V3ASAXQ2A").id,
            participant.id,
        )
        self.assertEqual(len(self.repository.list_active(self.session.id)), 1)

    def test_same_agent_cannot_join_one_session_twice(self):
        """同一 Agent 在同一会话只能有一个参与者记录。"""
        self.repository.add(
            self._participant("participant_8T2LQ6MZP1", "agent_1V3ASAXQ2A")
        )

        with self.assertRaises(StorageConflictError):
            self.repository.add(
                self._participant("participant_9U3M7BKP2C", "agent_1V3ASAXQ2A")
            )

    def test_leave_removes_participant_from_active_list(self):
        """离开后保留参与者历史，但不再出现在活跃列表。"""
        participant = self.repository.add(
            self._participant("participant_8T2LQ6MZP1", "agent_1V3ASAXQ2A")
        )

        left = self.repository.leave(participant.id)

        self.assertIsNotNone(left.left_at)
        self.assertEqual(self.repository.list_active(self.session.id), [])
        self.assertIsNotNone(self.repository.get(participant.id))

    def test_add_rejects_unknown_join_reason(self):
        """参与原因使用稳定枚举，未知值不能进入数据库。"""
        participant = self._participant(
            "participant_8T2LQ6MZP1", "agent_1V3ASAXQ2A"
        )
        participant.join_reason = "UNKNOWN"

        with self.assertRaises(ValueError):
            self.repository.add(participant)


if __name__ == "__main__":
    unittest.main()
