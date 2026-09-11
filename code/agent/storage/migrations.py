"""SQLite schema 的版本迁移。"""

import sqlite3

from .errors import StorageSchemaError


CURRENT_SCHEMA_VERSION = 1


def migrate(connection: sqlite3.Connection) -> None:
    """将 SQLite 连接迁移到当前 schema 版本。

    Args:
        connection: 已打开的 SQLite 连接。

    Raises:
        StorageSchemaError: 数据库版本高于当前程序或缺少已知迁移时抛出。

    首版直接创建完整的核心表；之后新增版本时，应在这里追加显式的增量迁移，
    不能通过“表是否存在”猜测数据库版本。
    """
    connection.execute("PRAGMA foreign_keys = ON")
    with connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        row = connection.execute(
            "SELECT value FROM schema_metadata WHERE key = ?",
            ("schema_version",),
        ).fetchone()

        if row is None:
            _create_version_one_schema(connection)
            connection.execute(
                "INSERT INTO schema_metadata (key, value) VALUES (?, ?)",
                ("schema_version", str(CURRENT_SCHEMA_VERSION)),
            )
            return

        try:
            version = int(row[0])
        except (TypeError, ValueError) as error:
            raise StorageSchemaError("数据库 schema_version 不是有效整数") from error

        if version > CURRENT_SCHEMA_VERSION:
            raise StorageSchemaError(
                f"数据库 schema 版本 {version} 高于当前版本 {CURRENT_SCHEMA_VERSION}"
            )
        if version < CURRENT_SCHEMA_VERSION:
            raise StorageSchemaError(
                f"数据库 schema 版本 {version} 暂无可用迁移到版本 "
                f"{CURRENT_SCHEMA_VERSION}"
            )

        _create_version_one_schema(connection)


def _create_version_one_schema(connection: sqlite3.Connection) -> None:
    """创建首版核心表；所有语句均可安全重复执行。"""
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS llm_profiles (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            provider TEXT NOT NULL,
            base_url TEXT,
            model TEXT NOT NULL,
            credential_ref TEXT NOT NULL,
            options_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS agent_profiles (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            personality TEXT NOT NULL DEFAULT '',
            expertise_json TEXT NOT NULL DEFAULT '[]',
            llm_profile_id TEXT NOT NULL,
            tools_json TEXT NOT NULL DEFAULT '[]',
            permission_mode TEXT NOT NULL,
            is_enabled INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (llm_profile_id) REFERENCES llm_profiles(id)
        );

        CREATE TABLE IF NOT EXISTS permission_agent_rules (
            id TEXT PRIMARY KEY,
            agent_id TEXT NOT NULL,
            action TEXT NOT NULL,
            resource_kind TEXT NOT NULL,
            resource_value TEXT NOT NULL,
            decision TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE (agent_id, action, resource_kind, resource_value),
            FOREIGN KEY (agent_id) REFERENCES agent_profiles(id)
        );

        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            title TEXT,
            conversation_mode TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            closed_at TEXT
        );

        CREATE TABLE IF NOT EXISTS session_participants (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            agent_id TEXT NOT NULL,
            role TEXT NOT NULL,
            join_reason TEXT,
            joined_at TEXT NOT NULL,
            left_at TEXT,
            UNIQUE (session_id, agent_id),
            FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE,
            FOREIGN KEY (agent_id) REFERENCES agent_profiles(id)
        );

        CREATE TABLE IF NOT EXISTS context_items (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            sequence_no INTEGER NOT NULL,
            kind TEXT NOT NULL,
            author_participant_id TEXT,
            target_participant_id TEXT,
            visibility TEXT NOT NULL,
            call_id TEXT,
            caused_by_item_id TEXT,
            payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE (session_id, sequence_no),
            FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE,
            FOREIGN KEY (author_participant_id) REFERENCES session_participants(id),
            FOREIGN KEY (target_participant_id) REFERENCES session_participants(id),
            FOREIGN KEY (caused_by_item_id) REFERENCES context_items(id)
        );

        CREATE TABLE IF NOT EXISTS agent_delegations (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            requester_participant_id TEXT NOT NULL,
            worker_participant_id TEXT NOT NULL,
            request_item_id TEXT NOT NULL,
            parent_delegation_id TEXT,
            status TEXT NOT NULL,
            result_item_id TEXT,
            created_at TEXT NOT NULL,
            completed_at TEXT,
            FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE,
            FOREIGN KEY (requester_participant_id) REFERENCES session_participants(id),
            FOREIGN KEY (worker_participant_id) REFERENCES session_participants(id),
            FOREIGN KEY (request_item_id) REFERENCES context_items(id),
            FOREIGN KEY (parent_delegation_id) REFERENCES agent_delegations(id),
            FOREIGN KEY (result_item_id) REFERENCES context_items(id)
        );

        CREATE INDEX IF NOT EXISTS idx_context_items_session_sequence
            ON context_items(session_id, sequence_no);
        CREATE INDEX IF NOT EXISTS idx_context_items_session_call
            ON context_items(session_id, call_id);
        CREATE INDEX IF NOT EXISTS idx_session_participants_session_left
            ON session_participants(session_id, left_at);
        CREATE INDEX IF NOT EXISTS idx_agent_delegations_session_status
            ON agent_delegations(session_id, status);
        """
    )
