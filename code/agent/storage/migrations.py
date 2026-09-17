"""SQLite schema 的版本迁移。"""

import sqlite3

from .errors import StorageSchemaError


CURRENT_SCHEMA_VERSION = 3


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
                ("schema_version", "1"),
            )
            version = 1
        else:
            try:
                version = int(row[0])
            except (TypeError, ValueError) as error:
                raise StorageSchemaError("数据库 schema_version 不是有效整数") from error

        if version > CURRENT_SCHEMA_VERSION:
            raise StorageSchemaError(
                f"数据库 schema 版本 {version} 高于当前版本 {CURRENT_SCHEMA_VERSION}"
            )
        if version == 1:
            _migrate_version_one_to_two(connection)
            version = 2
        if version == 2:
            _migrate_version_two_to_three(connection)
            version = 3

        if version != CURRENT_SCHEMA_VERSION:
            raise StorageSchemaError(
                f"数据库 schema 版本 {version} 暂无可用迁移到版本 "
                f"{CURRENT_SCHEMA_VERSION}"
            )


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


def _migrate_version_one_to_two(connection: sqlite3.Connection) -> None:
    """把临时参与者身份迁移为 ``session_id + agent_id`` 固定成员身份。

    Args:
        connection: 当前迁移事务使用的 SQLite 连接。

    旧上下文通过 session_participants 映射作者和目标，迁移后直接保存稳定的
    agent_id。尚未启用的委托表同步转换字段，以免升级数据库时丢失已有记录；
    当前运行时仍不会创建或消费委托。
    """
    connection.executescript(
        """
        BEGIN IMMEDIATE;

        CREATE TABLE session_agents (
            session_id TEXT NOT NULL,
            agent_id TEXT NOT NULL,
            role TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (session_id, agent_id),
            FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE,
            FOREIGN KEY (agent_id) REFERENCES agent_profiles(id)
        );

        INSERT INTO session_agents (session_id, agent_id, role, created_at)
        SELECT
            session_id,
            agent_id,
            CASE WHEN role = 'PRIMARY' THEN 'PRIMARY' ELSE 'MEMBER' END,
            joined_at
        FROM session_participants;

        CREATE TABLE context_items_v2 (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            sequence_no INTEGER NOT NULL,
            kind TEXT NOT NULL,
            author_agent_id TEXT,
            target_agent_id TEXT,
            visibility TEXT NOT NULL,
            call_id TEXT,
            caused_by_item_id TEXT,
            payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE (session_id, sequence_no),
            FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE,
            FOREIGN KEY (session_id, author_agent_id)
                REFERENCES session_agents(session_id, agent_id),
            FOREIGN KEY (session_id, target_agent_id)
                REFERENCES session_agents(session_id, agent_id),
            FOREIGN KEY (caused_by_item_id) REFERENCES context_items_v2(id)
        );

        INSERT INTO context_items_v2 (
            id, session_id, sequence_no, kind, author_agent_id,
            target_agent_id, visibility, call_id, caused_by_item_id,
            payload_json, created_at
        )
        SELECT
            context_items.id,
            context_items.session_id,
            context_items.sequence_no,
            context_items.kind,
            author.agent_id,
            target.agent_id,
            context_items.visibility,
            context_items.call_id,
            context_items.caused_by_item_id,
            context_items.payload_json,
            context_items.created_at
        FROM context_items
        LEFT JOIN session_participants AS author
            ON author.id = context_items.author_participant_id
        LEFT JOIN session_participants AS target
            ON target.id = context_items.target_participant_id;

        CREATE TABLE agent_delegations_v2 (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            requester_agent_id TEXT NOT NULL,
            worker_agent_id TEXT NOT NULL,
            request_item_id TEXT NOT NULL,
            parent_delegation_id TEXT,
            status TEXT NOT NULL,
            result_item_id TEXT,
            created_at TEXT NOT NULL,
            completed_at TEXT,
            FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE,
            FOREIGN KEY (session_id, requester_agent_id)
                REFERENCES session_agents(session_id, agent_id),
            FOREIGN KEY (session_id, worker_agent_id)
                REFERENCES session_agents(session_id, agent_id),
            FOREIGN KEY (request_item_id) REFERENCES context_items_v2(id),
            FOREIGN KEY (parent_delegation_id) REFERENCES agent_delegations_v2(id),
            FOREIGN KEY (result_item_id) REFERENCES context_items_v2(id)
        );

        INSERT INTO agent_delegations_v2 (
            id, session_id, requester_agent_id, worker_agent_id,
            request_item_id, parent_delegation_id, status, result_item_id,
            created_at, completed_at
        )
        SELECT
            agent_delegations.id,
            agent_delegations.session_id,
            requester.agent_id,
            worker.agent_id,
            agent_delegations.request_item_id,
            agent_delegations.parent_delegation_id,
            agent_delegations.status,
            agent_delegations.result_item_id,
            agent_delegations.created_at,
            agent_delegations.completed_at
        FROM agent_delegations
        JOIN session_participants AS requester
            ON requester.id = agent_delegations.requester_participant_id
        JOIN session_participants AS worker
            ON worker.id = agent_delegations.worker_participant_id;

        DROP TABLE agent_delegations;
        DROP TABLE context_items;
        DROP TABLE session_participants;

        ALTER TABLE context_items_v2 RENAME TO context_items;
        ALTER TABLE agent_delegations_v2 RENAME TO agent_delegations;

        CREATE INDEX idx_context_items_session_sequence
            ON context_items(session_id, sequence_no);
        CREATE INDEX idx_context_items_session_call
            ON context_items(session_id, call_id);
        CREATE INDEX idx_session_agents_session
            ON session_agents(session_id, created_at);
        CREATE INDEX idx_agent_delegations_session_status
            ON agent_delegations(session_id, status);

        UPDATE schema_metadata
        SET value = '2'
        WHERE key = 'schema_version';

        COMMIT;
        """
    )


def _migrate_version_two_to_three(connection: sqlite3.Connection) -> None:
    """为 Session 增加当前实际模型上下文字段。"""
    connection.execute(
        """
        ALTER TABLE sessions
        ADD COLUMN current_context_json TEXT NOT NULL DEFAULT '[]'
        """
    )
    connection.execute(
        """
        UPDATE schema_metadata
        SET value = '3'
        WHERE key = 'schema_version'
        """
    )
