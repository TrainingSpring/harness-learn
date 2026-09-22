"""Session 的 SQLite 仓储。"""

import json
import os
import sqlite3
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any

from ..database import StateDatabase
from ..errors import StorageConflictError, StorageFormatError
from ..ids import generate_id, validate_id
from ..types import Session, SessionAgent


class SessionRepository:
    """负责会话容器与 sessions 表之间的转换。

    Attributes:
        database: 已初始化的 workspace 状态数据库。

    会话不直接绑定 Agent；固定成员关系由 SessionAgentRepository 管理。
    当前只支持 DIRECT 和 GROUP 两种产品形态。
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
            mode: 会话模式，必须是 DIRECT 或 GROUP。
            title: 可选的用户可读标题。

        Returns:
            已写入数据库、带稳定 session_ ID 和时间戳的 Session。
        """
        session = self._new_session(mode, title)
        try:
            with self.database.transaction() as connection:
                self._insert_session(connection, session)
        except sqlite3.IntegrityError as error:
            raise StorageConflictError(f"Session 创建冲突: {session.id}") from error
        return session

    def create_with_agents(
        self,
        mode: str,
        agent_roles: list[tuple[str, str]],
        title: str | None = None,
        permission_mode: str = "plan",
    ) -> Session:
        """在一个事务内创建 Session 及其全部固定 Agent 成员。

        Args:
            mode: 当前支持的 DIRECT 或 GROUP 模式。
            agent_roles: ``(agent_id, role)`` 列表，由 SessionService 根据模式
                构造；仓储会再次通过 SessionAgent 校验字段。
            title: 可选的用户可读标题。

        Returns:
            已持久化的 ACTIVE Session。

        Raises:
            ValueError: 成员列表为空或成员字段不合法。
            StorageConflictError: Session、Agent 外键或成员唯一约束冲突。

        Session 和成员必须共同成功或共同回滚，避免留下无法加载的空会话。
        """
        if not agent_roles:
            raise ValueError("会话必须至少包含一个 Agent")
        session = self._new_session(mode, title, permission_mode)
        members = [
            SessionAgent(
                session_id=session.id,
                agent_id=agent_id,
                role=role,
                created_at=session.created_at,
            )
            for agent_id, role in agent_roles
        ]
        try:
            with self.database.transaction() as connection:
                self._insert_session(connection, session)
                connection.executemany(
                    """
                    INSERT INTO session_agents (
                        session_id, agent_id, role, created_at
                    ) VALUES (?, ?, ?, ?)
                    """,
                    [
                        (
                            member.session_id,
                            member.agent_id,
                            member.role,
                            member.created_at,
                        )
                        for member in members
                    ],
                )
        except sqlite3.IntegrityError as error:
            raise StorageConflictError(
                f"Session 固定成员创建冲突: {session.id}"
            ) from error
        return session

    def get(self, session_id: str) -> Session | None:
        """按稳定 Session ID 读取会话。"""
        validate_id("session", session_id)
        row = self.database.connection.execute(
            "SELECT * FROM sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
        return None if row is None else self._from_row(row)

    def load_current_context(self, session_id: str) -> list[dict[str, Any]]:
        """读取 Session 当前实际模型上下文。"""
        validate_id("session", session_id)
        row = self.database.connection.execute(
            "SELECT current_context_json FROM sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"Session 不存在: {session_id}")
        try:
            messages = json.loads(row["current_context_json"])
        except (TypeError, json.JSONDecodeError) as error:
            raise StorageFormatError(
                f"Session 当前上下文不是有效 JSON: {session_id}"
            ) from error
        self._validate_current_context(messages)
        return messages

    def save_current_context(
        self,
        session_id: str,
        messages: list[dict[str, Any]],
    ) -> None:
        """覆盖保存 Session 当前实际模型上下文。"""
        validate_id("session", session_id)
        self._validate_current_context(messages)
        try:
            encoded = json.dumps(messages, ensure_ascii=False, sort_keys=True)
        except (TypeError, ValueError) as error:
            raise ValueError("当前上下文必须是可 JSON 序列化的消息列表") from error

        with self.database.transaction() as connection:
            exists = connection.execute(
                "SELECT 1 FROM sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
            if exists is None:
                raise ValueError(f"Session 不存在: {session_id}")
            connection.execute(
                """
                UPDATE sessions
                SET current_context_json = ?, updated_at = ?
                WHERE id = ?
                """,
                (encoded, _utc_now(), session_id),
            )

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

    def update_project_path_before_first_message(
        self,
        session_id: str,
        project_path: str | None,
    ) -> Session:
        """仅允许在首条用户消息前设置或更换项目目录。"""
        validate_id("session", session_id)
        if project_path is not None:
            if not isinstance(project_path, str) or not os.path.isabs(project_path):
                raise ValueError("project_path 必须是绝对路径或 None")
            project_path = os.path.normpath(os.path.abspath(project_path))
            if not os.path.isdir(project_path):
                raise ValueError("project_path 必须是存在的目录")
        with self.database.transaction() as connection:
            row = connection.execute(
                "SELECT 1 FROM sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
            if row is None:
                raise ValueError(f"Session 不存在: {session_id}")
            locked = connection.execute(
                """
                SELECT 1 FROM context_items
                WHERE session_id = ? AND kind = 'USER_MESSAGE'
                LIMIT 1
                """,
                (session_id,),
            ).fetchone()
            if locked is not None:
                raise ValueError("Session 已有用户消息，不能更改项目目录")
            connection.execute(
                """
                UPDATE sessions
                SET project_path = ?, updated_at = ?
                WHERE id = ?
                """,
                (project_path, _utc_now(), session_id),
            )
        updated = self.get(session_id)
        if updated is None:
            raise ValueError(f"Session 不存在: {session_id}")
        return updated

    def update_permission_mode(self, session_id: str, permission_mode: str) -> Session:
        """更新空闲 Session 的默认权限模式。"""
        validate_id("session", session_id)
        if permission_mode not in {"plan", "build", "yolo"}:
            raise ValueError(f"未知的权限模式: {permission_mode}")
        with self.database.transaction() as connection:
            changed = connection.execute(
                """
                UPDATE sessions
                SET permission_mode = ?, updated_at = ?
                WHERE id = ?
                """,
                (permission_mode, _utc_now(), session_id),
            ).rowcount
            if changed == 0:
                raise ValueError(f"Session 不存在: {session_id}")
        updated = self.get(session_id)
        if updated is None:
            raise ValueError(f"Session 不存在: {session_id}")
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
    def _new_session(mode: str, title: str | None, permission_mode: str = "plan") -> Session:
        """构造带统一时间戳的新 Session 领域对象。"""
        now = _utc_now()
        return Session(
            id=generate_id("session"),
            title=title,
            conversation_mode=mode,
            status="ACTIVE",
            permission_mode=permission_mode,
            project_path=None,
            created_at=now,
            updated_at=now,
        )

    @staticmethod
    def _insert_session(connection: sqlite3.Connection, session: Session) -> None:
        """在调用方事务中插入 Session，供单表和聚合创建共同使用。"""
        connection.execute(
            """
            INSERT INTO sessions (
                id, title, conversation_mode, status, permission_mode, project_path,
                created_at, updated_at, closed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session.id,
                session.title,
                session.conversation_mode,
                session.status,
                session.permission_mode,
                session.project_path,
                session.created_at,
                session.updated_at,
                session.closed_at,
            ),
        )

    @staticmethod
    def _from_row(row: sqlite3.Row) -> Session:
        """将数据库行严格转换为 Session。"""
        try:
            return Session(
                id=row["id"],
                title=row["title"],
                conversation_mode=row["conversation_mode"],
                status=row["status"],
                permission_mode=row["permission_mode"],
                project_path=row["project_path"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                closed_at=row["closed_at"],
            )
        except (TypeError, ValueError) as error:
            raise StorageFormatError("Session 数据不符合领域约束") from error

    @staticmethod
    def _validate_current_context(messages: Any) -> None:
        """验证当前上下文是由消息字典组成的数组。"""
        if not isinstance(messages, list):
            raise StorageFormatError("当前上下文必须编码为数组")
        if not all(isinstance(message, dict) for message in messages):
            raise StorageFormatError("当前上下文中的消息必须编码为对象")


def _utc_now() -> str:
    """生成统一的 UTC ISO 时间字符串。"""
    return datetime.now(timezone.utc).isoformat()
