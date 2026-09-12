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


if __name__ == "__main__":
    unittest.main()
