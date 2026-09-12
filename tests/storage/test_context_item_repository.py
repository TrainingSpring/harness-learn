"""ContextItemRepository 的 SQLite 集成测试。"""

import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parents[2] / "code" / "agent"))

from storage.database import StateDatabase  # noqa: E402
from storage.errors import StorageConflictError  # noqa: E402
from storage.repositories.agent_profile import AgentProfileRepository  # noqa: E402
from storage.repositories.context_item import ContextItemRepository  # noqa: E402
from storage.repositories.llm_profile import LLMProfileRepository  # noqa: E402
from storage.repositories.session import SessionRepository  # noqa: E402
from storage.types import AgentProfile, ContextItem, LLMProfile  # noqa: E402


class ContextItemRepositoryTests(unittest.TestCase):
    """验证上下文追加、序号、可见性和调用配对约束。"""

    def setUp(self):
        """创建一个带两个固定 Agent 成员的 GROUP 会话。"""
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
        self.session = SessionRepository(self.database).create_with_agents(
            "GROUP",
            [
                ("agent_1V3ASAXQ2A", "MEMBER"),
                ("agent_9U3M7BKP2C", "MEMBER"),
            ],
            "协作",
        )
        self.repository = ContextItemRepository(self.database)

    def tearDown(self):
        """关闭数据库并清理临时目录。"""
        self.database.close()
        self.temp_dir.cleanup()

    def _item(
        self,
        item_id,
        kind,
        *,
        author=None,
        target=None,
        visibility="PUBLIC",
        payload=None,
        call_id=None,
        caused_by=None,
    ):
        """创建待由仓储分配正式序号的上下文项。"""
        return ContextItem(
            id=item_id,
            session_id=self.session.id,
            sequence_no=0,
            kind=kind,
            author_agent_id=author,
            target_agent_id=target,
            visibility=visibility,
            payload=payload or {"text": "消息"},
            call_id=call_id,
            caused_by_item_id=caused_by,
        )

    def test_append_allocates_sequence_and_list_after_returns_ordered_items(self):
        """追加操作由仓储分配从 1 开始的连续序号。"""
        first = self.repository.append(
            self._item("item_3F7XK9A2VC", "USER_MESSAGE")
        )
        second = self.repository.append(
            self._item(
                "item_4G8YL0B3WD",
                "AGENT_MESSAGE",
                author="agent_1V3ASAXQ2A",
            )
        )

        self.assertEqual(first.sequence_no, 1)
        self.assertEqual(second.sequence_no, 2)
        self.assertEqual(
            [item.id for item in self.repository.list_after(self.session.id, 1)],
            [second.id],
        )

    def test_append_updates_session_activity_time_in_same_write(self):
        """追加时间线后 Session 的更新时间应与最新 ContextItem 一致。"""
        stored = self.repository.append(
            self._item("item_3F7XK9A2VC", "USER_MESSAGE")
        )

        refreshed = SessionRepository(self.database).get(self.session.id)

        self.assertIsNotNone(refreshed)
        self.assertEqual(refreshed.updated_at, stored.created_at)

    def test_list_visible_filters_public_targeted_and_private_items(self):
        """按 Agent 读取时只返回该 Agent 可见的上下文。"""
        public = self.repository.append(
            self._item("item_3F7XK9A2VC", "USER_MESSAGE")
        )
        targeted = self.repository.append(
            self._item(
                "item_4G8YL0B3WD",
                "AGENT_MESSAGE",
                author="agent_1V3ASAXQ2A",
                target="agent_9U3M7BKP2C",
                visibility="TARGETED",
            )
        )
        private = self.repository.append(
            self._item(
                "item_5H1ZM7C4XE",
                "AGENT_MESSAGE",
                author="agent_1V3ASAXQ2A",
                visibility="PRIVATE",
            )
        )

        visible_to_worker = self.repository.list_visible(
            self.session.id,
            "agent_9U3M7BKP2C",
        )
        visible_to_author = self.repository.list_visible(
            self.session.id,
            "agent_1V3ASAXQ2A",
        )

        self.assertEqual(
            [item.id for item in visible_to_worker], [public.id, targeted.id]
        )
        self.assertEqual(
            [item.id for item in visible_to_author], [public.id, private.id]
        )

    def test_targeted_item_requires_a_session_agent(self):
        """定向消息不能发送给不属于当前会话的 Agent。"""
        with self.assertRaises(ValueError):
            self.repository.append(
                self._item(
                    "item_3F7XK9A2VC",
                    "AGENT_MESSAGE",
                    author="agent_1V3ASAXQ2A",
                    target="agent_8LRT3N5QYB",
                    visibility="TARGETED",
                )
            )

    def test_agent_items_require_an_author(self):
        """Agent 消息和工具事件不能伪造为没有作者的记录。"""
        with self.assertRaises(ValueError):
            self.repository.append(
                self._item("item_3F7XK9A2VC", "AGENT_MESSAGE")
            )

    def test_function_output_requires_existing_function_call_and_is_unique(self):
        """function_call_output 必须配对先前调用，且不能重复写入。"""
        function_call = self.repository.append(
            self._item(
                "item_3F7XK9A2VC",
                "FUNCTION_CALL",
                author="agent_1V3ASAXQ2A",
                payload={"name": "read"},
                call_id="call_001",
            )
        )
        output = self.repository.append(
            self._item(
                "item_4G8YL0B3WD",
                "FUNCTION_CALL_OUTPUT",
                author="agent_1V3ASAXQ2A",
                payload={"output": "ok"},
                call_id="call_001",
                caused_by=function_call.id,
            )
        )

        with self.assertRaises(StorageConflictError):
            self.repository.append(
                self._item(
                    "item_5H1ZM7C4XE",
                    "FUNCTION_CALL_OUTPUT",
                    author="agent_1V3ASAXQ2A",
                    payload={"output": "duplicate"},
                    call_id="call_001",
                )
            )
        self.assertEqual(
            self.repository.find_by_call_id(self.session.id, "call_001").id,
            function_call.id,
        )
        self.assertEqual(output.sequence_no, 2)

    def test_function_output_without_call_is_rejected(self):
        """没有对应 function_call 的输出不能进入时间线。"""
        with self.assertRaises(ValueError):
            self.repository.append(
                self._item(
                    "item_3F7XK9A2VC",
                    "FUNCTION_CALL_OUTPUT",
                    author="agent_1V3ASAXQ2A",
                    call_id="call_missing",
                )
            )

    def test_append_rejects_causal_item_from_another_session(self):
        """因果引用必须指向同一会话，不能跨会话串联上下文。"""
        other_session = SessionRepository(self.database).create("DIRECT")
        self.database.connection.execute(
            """
            INSERT INTO context_items (
                id, session_id, sequence_no, kind, author_agent_id,
                target_agent_id, visibility, call_id, caused_by_item_id,
                payload_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "item_6J2AN8D5YF",
                other_session.id,
                1,
                "SYSTEM_EVENT",
                None,
                None,
                "PUBLIC",
                None,
                None,
                "{}",
                "2026-01-01T00:00:00+00:00",
            ),
        )
        self.database.connection.commit()

        with self.assertRaises(ValueError):
            self.repository.append(
                self._item(
                    "item_3F7XK9A2VC",
                    "SYSTEM_EVENT",
                    caused_by="item_6J2AN8D5YF",
                )
            )


if __name__ == "__main__":
    unittest.main()
