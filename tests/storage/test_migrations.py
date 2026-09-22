"""数据库迁移约束测试。"""

import sqlite3
import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parents[2] / "code" / "agent"))

from storage.migrations import (  # noqa: E402
    CURRENT_SCHEMA_VERSION,
    _create_version_one_schema,
    migrate,
)


class MigrationTests(unittest.TestCase):
    """验证迁移函数可在原始 SQLite 连接上建立首版 schema。"""

    def test_migrate_creates_schema_on_an_empty_connection(self):
        """迁移不应依赖 StateDatabase 的其他运行时状态。"""
        connection = sqlite3.connect(":memory:")

        migrate(connection)

        version = connection.execute(
            "SELECT value FROM schema_metadata WHERE key = ?",
            ("schema_version",),
        ).fetchone()[0]
        self.assertEqual(int(version), CURRENT_SCHEMA_VERSION)

    def test_migrate_can_run_twice(self):
        """迁移重复执行必须保持幂等。"""
        connection = sqlite3.connect(":memory:")

        migrate(connection)
        migrate(connection)

        self.assertIsNotNone(
            connection.execute(
                "SELECT name FROM sqlite_master WHERE name = ?",
                ("context_items",),
            ).fetchone()
        )

    def test_version_one_data_is_mapped_from_participants_to_agents(self):
        """v1 上下文的临时参与者引用应迁移为稳定 Agent 引用。"""
        connection = sqlite3.connect(":memory:")
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(
            "CREATE TABLE schema_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        connection.execute(
            "INSERT INTO schema_metadata (key, value) VALUES ('schema_version', '1')"
        )
        _create_version_one_schema(connection)
        connection.execute(
            """
            INSERT INTO llm_profiles VALUES (
                'llm_7KQ2M8P4XZ', '模型', 'openai', NULL, 'gpt-5',
                'env:OPENAI_API_KEY', '{}', 'created', 'updated'
            )
            """
        )
        connection.execute(
            """
            INSERT INTO agent_profiles VALUES (
                'agent_1V3ASAXQ2A', '角色', '', '', '[]',
                'llm_7KQ2M8P4XZ', '[]', 'BUILD', 1, 'created', 'updated'
            )
            """
        )
        connection.execute(
            """
            INSERT INTO sessions VALUES (
                'session_4N9C1R7WBA', NULL, 'DIRECT', 'ACTIVE',
                'created', 'updated', NULL
            )
            """
        )
        connection.execute(
            """
            INSERT INTO session_participants VALUES (
                'participant_8T2LQ6MZP1', 'session_4N9C1R7WBA',
                'agent_1V3ASAXQ2A', 'PRIMARY', 'USER_SELECTED',
                'joined', NULL
            )
            """
        )
        connection.execute(
            """
            INSERT INTO context_items VALUES (
                'item_3F7XK9A2VC', 'session_4N9C1R7WBA', 1,
                'AGENT_MESSAGE', 'participant_8T2LQ6MZP1', NULL,
                'PUBLIC', NULL, NULL, '{"text":"完成"}', 'created'
            )
            """
        )
        connection.commit()

        migrate(connection)

        member = connection.execute(
            "SELECT session_id, agent_id, role FROM session_agents"
        ).fetchone()
        item = connection.execute(
            "SELECT author_agent_id, target_agent_id FROM context_items"
        ).fetchone()
        old_table = connection.execute(
            "SELECT name FROM sqlite_master WHERE name = 'session_participants'"
        ).fetchone()
        foreign_key_errors = connection.execute("PRAGMA foreign_key_check").fetchall()
        self.assertEqual(
            member,
            ("session_4N9C1R7WBA", "agent_1V3ASAXQ2A", "PRIMARY"),
        )
        self.assertEqual(item, ("agent_1V3ASAXQ2A", None))
        self.assertIsNone(old_table)
        self.assertEqual(foreign_key_errors, [])

    def test_current_context_column_is_added_by_migration(self):
        """当前上下文字段应由显式迁移加入，并默认为空数组。"""
        connection = sqlite3.connect(":memory:")

        migrate(connection)

        columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(sessions)")
        }
        value = connection.execute(
            """
            INSERT INTO sessions (
                id, title, conversation_mode, status,
                created_at, updated_at, closed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            RETURNING current_context_json
            """,
            (
                "session_4N9C1R7WBA",
                None,
                "DIRECT",
                "ACTIVE",
                "created",
                "updated",
                None,
            ),
        ).fetchone()[0]

        self.assertIn("current_context_json", columns)
        self.assertEqual(value, "[]")

    def test_version_two_database_is_upgraded_with_empty_current_context(self):
        """已有 v2 数据升级后应保留会话并增加空的当前上下文。"""
        connection = sqlite3.connect(":memory:")
        _create_version_one_schema(connection)
        connection.execute(
            "CREATE TABLE schema_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        connection.execute(
            "INSERT INTO schema_metadata (key, value) VALUES ('schema_version', '2')"
        )
        connection.execute(
            """
            INSERT INTO sessions VALUES (
                'session_4N9C1R7WBA', '旧会话', 'DIRECT', 'ACTIVE',
                'created', 'updated', NULL
            )
            """
        )
        connection.commit()

        migrate(connection)

        row = connection.execute(
            "SELECT title, current_context_json FROM sessions WHERE id = ?",
            ("session_4N9C1R7WBA",),
        ).fetchone()
        self.assertEqual(row, ("旧会话", "[]"))

    def test_version_three_profile_drops_credential_reference_and_requires_api_key(self):
        """v3 环境变量引用不能伪装成 API Key，升级后必须重新配置。"""
        connection = sqlite3.connect(":memory:")
        _create_version_one_schema(connection)
        connection.execute(
            "CREATE TABLE schema_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        connection.execute(
            "INSERT INTO schema_metadata (key, value) VALUES ('schema_version', '3')"
        )
        connection.execute(
            """
            INSERT INTO llm_profiles VALUES (
                'llm_7KQ2M8P4XZ', '旧模型', 'openai', 'https://api.openai.com/v1',
                'gpt-5', 'env:OPENAI_API_KEY', '{}', 'created', 'updated'
            )
            """
        )
        connection.commit()

        migrate(connection)

        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(llm_profiles)")
        }
        profile = connection.execute(
            "SELECT api_key FROM llm_profiles WHERE id = 'llm_7KQ2M8P4XZ'"
        ).fetchone()
        self.assertIn("api_key", columns)
        self.assertNotIn("credential_ref", columns)
        self.assertEqual(profile[0], "")


if __name__ == "__main__":
    unittest.main()
