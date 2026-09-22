"""SessionRepository 的 SQLite 集成测试。"""

import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parents[2] / "code" / "agent"))

from storage.database import StateDatabase  # noqa: E402
from storage.repositories.session import SessionRepository  # noqa: E402
from storage.types import Session  # noqa: E402


class SessionRepositoryTests(unittest.TestCase):
    """验证会话的创建、状态更新和分页读取。"""

    def setUp(self):
        """为每个测试创建独立状态数据库。"""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = StateDatabase(self.temp_dir.name)
        self.database.initialize()
        self.repository = SessionRepository(self.database)

    def tearDown(self):
        """关闭数据库并清理临时目录。"""
        self.database.close()
        self.temp_dir.cleanup()

    def test_create_and_get_supports_current_conversation_modes(self):
        """DIRECT 和 GROUP 都应创建为可恢复的 ACTIVE 会话。"""
        sessions = [
            self.repository.create("DIRECT", "一对一"),
            self.repository.create("GROUP", "群聊"),
        ]

        self.assertEqual([item.conversation_mode for item in sessions], ["DIRECT", "GROUP"])
        self.assertTrue(all(item.id.startswith("session_") for item in sessions))
        self.assertTrue(all(item.status == "ACTIVE" for item in sessions))
        self.assertEqual(self.repository.get(sessions[0].id).title, "一对一")

    def test_create_rejects_deferred_open_mode(self):
        """Agent 自由交流尚未实现，OPEN 不能进入当前数据模型。"""
        with self.assertRaises(ValueError):
            self.repository.create("OPEN", "自由对话")

    def test_update_status_sets_closed_at_when_session_is_closed(self):
        """关闭会话时记录 closed_at，并保留其他会话字段。"""
        session = self.repository.create("DIRECT")

        updated = self.repository.update_status(session.id, "CLOSED")

        self.assertEqual(updated.status, "CLOSED")
        self.assertIsNotNone(updated.closed_at)
        self.assertEqual(self.repository.get(session.id).closed_at, updated.closed_at)

    def test_update_status_clears_closed_at_when_reopened(self):
        """重新激活会话时清除旧的 closed_at，避免状态自相矛盾。"""
        session = self.repository.create("DIRECT")
        self.repository.update_status(session.id, "CLOSED")

        updated = self.repository.update_status(session.id, "ACTIVE")

        self.assertEqual(updated.status, "ACTIVE")
        self.assertIsNone(updated.closed_at)

    def test_list_recent_returns_newest_sessions_with_pagination(self):
        """最近会话按更新时间倒序返回，并支持 limit/offset。"""
        first = self.repository.create("DIRECT", "first")
        second = self.repository.create("DIRECT", "second")
        third = self.repository.create("DIRECT", "third")

        recent = self.repository.list_recent(limit=2, offset=0)
        page_two = self.repository.list_recent(limit=2, offset=2)

        self.assertEqual([item.id for item in recent], [third.id, second.id])
        self.assertEqual([item.id for item in page_two], [first.id])

    def test_get_returns_none_for_unknown_session(self):
        """读取不存在的会话返回 None，而不是伪造默认状态。"""
        self.assertIsNone(self.repository.get("session_4N9C1R7WBA"))

    def test_update_status_returns_none_for_unknown_session(self):
        """更新不存在的会话返回 None，调用方可区分资源缺失。"""
        self.assertIsNone(
            self.repository.update_status("session_4N9C1R7WBA", "CLOSED")
        )

    def test_current_context_can_be_saved_and_overwritten(self):
        """当前上下文是 Session 级可覆盖状态。"""
        session = self.repository.create("DIRECT")
        first = [{"type": "message", "role": "user", "content": "第一轮"}]
        second = [
            {"type": "message", "role": "developer", "content": "压缩摘要"},
            {"type": "message", "role": "user", "content": "第二轮"},
        ]

        self.repository.save_current_context(session.id, first)
        self.repository.save_current_context(session.id, second)

        self.assertEqual(self.repository.load_current_context(session.id), second)

    def test_current_context_rejects_invalid_database_json(self):
        """数据库中的当前上下文格式损坏时不能静默恢复。"""
        session = self.repository.create("DIRECT")
        self.database.connection.execute(
            "UPDATE sessions SET current_context_json = ? WHERE id = ?",
            ('{"not": "an array"}', session.id),
        )
        self.database.connection.commit()

        from storage.errors import StorageFormatError

        with self.assertRaises(StorageFormatError):
            self.repository.load_current_context(session.id)

    def test_current_context_rejects_non_serializable_messages(self):
        """保存前应拒绝不能 JSON 序列化的消息结构。"""
        session = self.repository.create("DIRECT")

        with self.assertRaises(ValueError):
            self.repository.save_current_context(session.id, [{"value": object()}])

    def test_new_session_has_plan_mode_and_no_project_path(self):
        """新 Session 默认是 PLAN 空项目会话。"""
        session = self.repository.create("DIRECT")

        self.assertEqual(session.permission_mode, "plan")
        self.assertIsNone(session.project_path)

    def test_project_path_can_change_only_before_first_user_message(self):
        """首条用户消息后，项目根目录不允许再切换。"""
        session = self.repository.create("DIRECT")
        project = str(Path(self.temp_dir.name) / "project")
        Path(project).mkdir()

        updated = self.repository.update_project_path_before_first_message(
            session.id,
            project,
        )
        self.assertEqual(updated.project_path, project)

        self.database.connection.execute(
            """
            INSERT INTO context_items (
                id, session_id, sequence_no, kind, author_agent_id,
                target_agent_id, visibility, call_id, caused_by_item_id,
                payload_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "item_4N9C1R7WBA",
                session.id,
                1,
                "USER_MESSAGE",
                None,
                None,
                "PUBLIC",
                None,
                None,
                '{"text": "开始"}',
                "2026-09-22T00:00:00+00:00",
            ),
        )
        self.database.connection.commit()

        with self.assertRaises(ValueError):
            self.repository.update_project_path_before_first_message(
                session.id,
                None,
            )


if __name__ == "__main__":
    unittest.main()
