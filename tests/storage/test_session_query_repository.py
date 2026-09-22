"""SessionQueryRepository 的 SQLite 集成测试。"""

import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parents[2] / "code" / "agent"))

from storage.database import StateDatabase  # noqa: E402
from storage.repositories.agent_profile import AgentProfileRepository  # noqa: E402
from storage.repositories.context_item import ContextItemRepository  # noqa: E402
from storage.repositories.llm_profile import LLMProfileRepository  # noqa: E402
from storage.repositories.session import SessionRepository  # noqa: E402
from storage.repositories.session_query import SessionQueryRepository  # noqa: E402
from storage.types import AgentProfile, ContextItem, LLMProfile, Session  # noqa: E402


class SessionQueryRepositoryTests(unittest.TestCase):
    """验证固定 1v1 会话列表和详情的只读聚合查询。"""

    def setUp(self):
        """创建包含两个 Agent 的独立状态数据库。"""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = StateDatabase(self.temp_dir.name)
        self.database.initialize()
        self.session_repository = SessionRepository(self.database)
        self.context_repository = ContextItemRepository(self.database)
        self.repository = SessionQueryRepository(self.database)

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
        agent_repository = AgentProfileRepository(self.database)
        for agent_id, name in (
            ("agent_1V3ASAXQ2A", "代码专家"),
            ("agent_9U3M7BKP2C", "测试专家"),
        ):
            agent_repository.save(
                AgentProfile(
                    id=agent_id,
                    name=name,
                    description="负责开发工作",
                    personality="务实",
                    expertise=["Python"],
                    llm_profile_id="llm_7KQ2M8P4XZ",
                    tools=["read"],
                )
            )

    def tearDown(self):
        """关闭数据库并清理临时目录。"""
        self.database.close()
        self.temp_dir.cleanup()

    def _create_direct(self, agent_id: str, title: str) -> Session:
        """创建一个带唯一 PRIMARY Agent 的 DIRECT 会话。"""
        return self.session_repository.create_with_agents(
            "DIRECT",
            [(agent_id, "PRIMARY")],
            title,
        )

    def _append_message(
        self,
        session_id: str,
        item_id: str,
        kind: str,
        text: str,
        *,
        author_agent_id: str | None = None,
    ) -> ContextItem:
        """向指定会话追加一条可展示消息。"""
        return self.context_repository.append(
            ContextItem(
                id=item_id,
                session_id=session_id,
                sequence_no=0,
                kind=kind,
                author_agent_id=author_agent_id,
                target_agent_id=None,
                visibility="PUBLIC",
                payload={"text": text},
            )
        )

    def test_list_direct_summaries_returns_agent_and_last_displayable_message(self):
        """列表一次聚合唯一 Agent，并忽略最后消息之后的工具事件。"""
        session = self._create_direct("agent_1V3ASAXQ2A", "实现查询")
        self._append_message(
            session.id,
            "item_3F7XK9A2VC",
            "USER_MESSAGE",
            "请读取文件",
        )
        agent_message = self._append_message(
            session.id,
            "item_4G8YL0B3WD",
            "AGENT_MESSAGE",
            "文件内容如下",
            author_agent_id="agent_1V3ASAXQ2A",
        )
        self.context_repository.append(
            ContextItem(
                id="item_5H1ZM7C4XE",
                session_id=session.id,
                sequence_no=0,
                kind="FUNCTION_CALL",
                author_agent_id="agent_1V3ASAXQ2A",
                target_agent_id=None,
                visibility="PUBLIC",
                payload={"name": "read"},
                call_id="call_read_001",
            )
        )

        summaries = self.repository.list_direct_summaries(limit=20, offset=0)

        self.assertEqual(len(summaries), 1)
        self.assertEqual(summaries[0].session.id, session.id)
        self.assertEqual(summaries[0].session.title, session.title)
        self.assertGreaterEqual(
            summaries[0].session.updated_at,
            session.updated_at,
        )
        self.assertEqual(summaries[0].agent_id, "agent_1V3ASAXQ2A")
        self.assertEqual(summaries[0].agent_name, "代码专家")
        self.assertEqual(summaries[0].last_message, "文件内容如下")
        self.assertEqual(summaries[0].last_sequence_no, agent_message.sequence_no)

    def test_list_direct_summaries_filters_group_and_invalid_direct_sessions(self):
        """GROUP、无 Agent 或有多个 Agent 的 DIRECT 会话不进入 1v1 列表。"""
        valid = self._create_direct("agent_1V3ASAXQ2A", "有效会话")
        self.session_repository.create_with_agents(
            "GROUP",
            [
                ("agent_1V3ASAXQ2A", "MEMBER"),
                ("agent_9U3M7BKP2C", "MEMBER"),
            ],
            "群聊",
        )
        self.session_repository.create("DIRECT", "没有 Agent")
        self.session_repository.create_with_agents(
            "DIRECT",
            [
                ("agent_1V3ASAXQ2A", "PRIMARY"),
                ("agent_9U3M7BKP2C", "MEMBER"),
            ],
            "异常的一对一会话",
        )

        summaries = self.repository.list_direct_summaries(limit=20, offset=0)

        self.assertEqual([summary.session.id for summary in summaries], [valid.id])

    def test_list_direct_summaries_has_stable_pagination_for_equal_timestamps(self):
        """更新时间相同时以 Session ID 倒序打破平局，分页不重不漏。"""
        sessions = [
            self._create_direct("agent_1V3ASAXQ2A", f"会话 {index}")
            for index in range(3)
        ]
        self.database.connection.execute(
            "UPDATE sessions SET updated_at = ?",
            ("2026-01-01T00:00:00+00:00",),
        )
        self.database.connection.commit()

        first_page = self.repository.list_direct_summaries(limit=2, offset=0)
        second_page = self.repository.list_direct_summaries(limit=2, offset=2)

        expected_ids = sorted((session.id for session in sessions), reverse=True)
        actual_ids = [item.session.id for item in first_page + second_page]
        self.assertEqual(actual_ids, expected_ids)

    def test_list_direct_summaries_executes_one_select(self):
        """历史列表必须由一条 SELECT 完成，避免按会话追加查询。"""
        self._create_direct("agent_1V3ASAXQ2A", "第一条")
        self._create_direct("agent_9U3M7BKP2C", "第二条")
        statements: list[str] = []
        self.database.connection.set_trace_callback(statements.append)

        try:
            self.repository.list_direct_summaries(limit=20, offset=0)
        finally:
            self.database.connection.set_trace_callback(None)

        select_statements = [
            statement
            for statement in statements
            if statement.lstrip().upper().startswith("SELECT")
        ]
        self.assertEqual(len(select_statements), 1)

    def test_get_direct_detail_returns_summary_and_handles_non_direct_sessions(self):
        """详情返回 DIRECT 聚合；GROUP、非法成员和不存在记录均返回 None。"""
        direct = self._create_direct("agent_9U3M7BKP2C", "查询详情")
        group = self.session_repository.create_with_agents(
            "GROUP",
            [("agent_1V3ASAXQ2A", "MEMBER")],
            "单成员群聊",
        )
        invalid_direct = self.session_repository.create("DIRECT", "缺少 Agent")

        detail = self.repository.get_direct_detail(direct.id)

        self.assertIsNotNone(detail)
        self.assertEqual(detail.session, direct)
        self.assertEqual(detail.agent_id, "agent_9U3M7BKP2C")
        self.assertIsNone(detail.last_message)
        self.assertIsNone(detail.last_sequence_no)
        self.assertIsNone(self.repository.get_direct_detail(group.id))
        self.assertIsNone(self.repository.get_direct_detail(invalid_direct.id))
        self.assertIsNone(
            self.repository.get_direct_detail("session_4N9C1R7WBA")
        )

    def test_query_methods_validate_page_and_session_id(self):
        """无效分页参数和 Session ID 在进入 SQL 前被拒绝。"""
        for limit, offset in ((0, 0), (1, -1), (True, 0)):
            with self.subTest(limit=limit, offset=offset):
                with self.assertRaises(ValueError):
                    self.repository.list_direct_summaries(limit, offset)

        with self.assertRaises(ValueError):
            self.repository.get_direct_detail("not-a-session-id")


if __name__ == "__main__":
    unittest.main()
