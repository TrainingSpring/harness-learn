"""StateDatabase 的生命周期和首版 schema 测试。"""

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parents[2] / "code" / "agent"))

from storage.database import StateDatabase  # noqa: E402
from storage.errors import StorageSchemaError  # noqa: E402


class StateDatabaseTests(unittest.TestCase):
    """验证本地状态数据库的创建、迁移和事务边界。"""

    def test_initialize_creates_workspace_local_database(self):
        """数据库应创建在 workspace/.harness/state.db。"""
        with tempfile.TemporaryDirectory() as workspace:
            database = StateDatabase(workspace)
            database.initialize()

            self.assertEqual(
                database.path,
                Path(workspace).resolve() / ".harness" / "state.db",
            )
            self.assertTrue(database.path.is_file())
            self.assertEqual(database.connection.execute("PRAGMA foreign_keys").fetchone()[0], 1)

            database.close()

    def test_initialize_is_idempotent_and_creates_expected_tables(self):
        """重复初始化不能删除数据或重复创建 schema。"""
        with tempfile.TemporaryDirectory() as workspace:
            database = StateDatabase(workspace)
            database.initialize()
            database.connection.execute(
                "INSERT INTO schema_metadata (key, value) VALUES (?, ?)",
                ("custom", "kept"),
            )
            database.connection.commit()
            database.close()

            reopened = StateDatabase(workspace)
            reopened.initialize()
            tables = {
                row[0]
                for row in reopened.connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }

            self.assertIn("schema_metadata", tables)
            self.assertIn("llm_profiles", tables)
            self.assertIn("agent_profiles", tables)
            self.assertIn("permission_agent_rules", tables)
            self.assertIn("sessions", tables)
            self.assertIn("session_agents", tables)
            self.assertIn("context_items", tables)
            self.assertIn("agent_delegations", tables)
            self.assertNotIn("session_participants", tables)
            self.assertNotIn("agent_tool_configs", tables)
            self.assertNotIn("context_item_targets", tables)
            self.assertEqual(
                reopened.connection.execute(
                    "SELECT value FROM schema_metadata WHERE key = ?",
                    ("custom",),
                ).fetchone()[0],
                "kept",
            )
            reopened.close()

    def test_transaction_rolls_back_on_error(self):
        """事务块发生异常时不能留下半写入数据。"""
        with tempfile.TemporaryDirectory() as workspace:
            database = StateDatabase(workspace)
            database.initialize()

            with self.assertRaises(sqlite3.IntegrityError):
                with database.transaction() as connection:
                    connection.execute(
                        "INSERT INTO schema_metadata (key, value) VALUES (?, ?)",
                        ("rollback", "first"),
                    )
                    connection.execute(
                        "INSERT INTO schema_metadata (key, value) VALUES (?, ?)",
                        ("rollback", "second"),
                    )

            self.assertIsNone(
                database.connection.execute(
                    "SELECT value FROM schema_metadata WHERE key = ?",
                    ("rollback",),
                ).fetchone()
            )
            database.close()

    def test_new_database_records_schema_version(self):
        """新数据库必须记录当前 schema 版本。"""
        with tempfile.TemporaryDirectory() as workspace:
            database = StateDatabase(workspace)
            database.initialize()

            version = database.connection.execute(
                "SELECT value FROM schema_metadata WHERE key = ?",
                ("schema_version",),
            ).fetchone()[0]

            self.assertEqual(version, "4")
            database.close()

    def test_database_rejects_a_newer_schema_version(self):
        """程序不能猜测解释比自身更新的数据库。"""
        with tempfile.TemporaryDirectory() as workspace:
            database = StateDatabase(workspace)
            database.initialize()
            database.connection.execute(
                "UPDATE schema_metadata SET value = ? WHERE key = ?",
                ("999", "schema_version"),
            )
            database.connection.commit()
            database.close()

            with self.assertRaises(StorageSchemaError):
                StateDatabase(workspace).initialize()


if __name__ == "__main__":
    unittest.main()
