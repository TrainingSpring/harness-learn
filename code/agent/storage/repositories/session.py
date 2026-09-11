"""Session 的 SQLite 仓储。"""

import sqlite3
from dataclasses import replace
from datetime import datetime, timezone

from ..database import StateDatabase
from ..errors import StorageConflictError, StorageFormatError
from ..ids import generate_id, validate_id
from ..types import Session


class SessionRepository:
    """负责会话容器与 sessions 表之间的转换。

    Attributes:
        database: 已初始化的 workspace 状态数据库。

    会话不直接绑定 Agent；Agent 参与关系由 SessionParticipantRepository 管理，
    因此同一个 Session 可以支持 DIRECT、GROUP 和 OPEN 三种协作形态。
    """

    def __init__(self, database: StateDatabase) -> None:
        """创建会话仓储。

        Args:
            database: 已调用 ``initialize()`` 的状态数据库。
        """
        self.database = database

    def create(self, mode: str, title: str | None = None) -> Session:
        """创建一个 ACTIVE 会话。

        Args:
            mode: 会话模式，必须是 DIRECT、GROUP 或 OPEN。
            title: 可选的用户可读标题。

        Returns:
            已写入数据库、带稳定 session_ ID 和时间戳的 Session。
        """
        now = _utc_now()
        session = Session(
            id=generate_id("session"),
            title=title,
            conversation_mode=mode,
            status="ACTIVE",
            created_at=now,
            updated_at=now,
        )
        try:
            with self.database.transaction() as connection:
                connection.execute(
                    """
                    INSERT INTO sessions (
                        id, title, conversation_mode, status,
                        created_at, updated_at, closed_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        session.id,
                        session.title,
                        session.conversation_mode,
                        session.status,
                        session.created_at,
                        session.updated_at,
                        session.closed_at,
                    ),
                )
        except sqlite3.IntegrityError as error:
            raise StorageConflictError(f"Session 创建冲突: {session.id}") from error
        return session

    def get(self, session_id: str) -> Session | None:
        """按稳定 Session ID 读取会话。"""
        validate_id("session", session_id)
        row = self.database.connection.execute(
            "SELECT * FROM sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
        return None if row is None else self._from_row(row)

    def update_status(self, session_id: str, status: str) -> Session | None:
        """更新会话状态，并同步维护 closed_at。

        Args:
            session_id: 待更新的会话 ID。
            status: 新状态，必须是 Session 支持的状态值。

        Returns:
            更新后的 Session；会话不存在时返回 None。
        """
        current = self.get(session_id)
        if current is None:
            return None
        now = _utc_now()
        updated = replace(
            current,
            status=status,
            updated_at=now,
            closed_at=now if status == "CLOSED" else None,
        )
        with self.database.transaction() as connection:
            connection.execute(
                """
                UPDATE sessions
                SET status = ?, updated_at = ?, closed_at = ?
                WHERE id = ?
                """,
                (updated.status, updated.updated_at, updated.closed_at, session_id),
            )
        return updated

    def list_recent(self, limit: int, offset: int) -> list[Session]:
        """按更新时间倒序分页读取最近会话。"""
        self._validate_page(limit, offset)
        rows = self.database.connection.execute(
            """
            SELECT * FROM sessions
            ORDER BY updated_at DESC, id DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        ).fetchall()
        return [self._from_row(row) for row in rows]

    @staticmethod
    def _validate_page(limit: int, offset: int) -> None:
        """验证分页参数，避免无意义的 SQL 查询。"""
        if not isinstance(limit, int) or limit <= 0:
            raise ValueError("limit 必须是正整数")
        if not isinstance(offset, int) or offset < 0:
            raise ValueError("offset 必须是非负整数")

    @staticmethod
    def _from_row(row: sqlite3.Row) -> Session:
        """将数据库行严格转换为 Session。"""
        try:
            return Session(
                id=row["id"],
                title=row["title"],
                conversation_mode=row["conversation_mode"],
                status=row["status"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                closed_at=row["closed_at"],
            )
        except (TypeError, ValueError) as error:
            raise StorageFormatError("Session 数据不符合领域约束") from error


def _utc_now() -> str:
    """生成统一的 UTC ISO 时间字符串。"""
    return datetime.now(timezone.utc).isoformat()
