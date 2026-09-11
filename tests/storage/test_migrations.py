"""数据库迁移约束测试。"""

import sqlite3
import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parents[2] / "code" / "agent"))

from storage.migrations import CURRENT_SCHEMA_VERSION, migrate  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
