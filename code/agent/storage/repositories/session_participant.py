"""SessionParticipant 的 SQLite 仓储。"""

import sqlite3
from dataclasses import replace
from datetime import datetime, timezone

from ..database import StateDatabase
from ..errors import StorageConflictError, StorageFormatError
from ..ids import validate_id
from ..types import SessionParticipant


class SessionParticipantRepository:
    """负责会话参与者与 session_participants 表之间的转换。

    Attributes:
        database: 已初始化的 workspace 状态数据库。

    参与者是 Agent 在某个 Session 中的临时身份。Agent 的长期配置仍由
    AgentProfile 表保存，Session 只引用参与者，不直接承担 Agent 配置。
    """

    def __init__(self, database: StateDatabase) -> None:
        """创建参与者仓储。

        Args:
            database: 已调用 ``initialize()`` 的状态数据库。
        """
        self.database = database

    def add(self, participant: SessionParticipant) -> SessionParticipant:
        """把一个 Agent 加入会话。

        Args:
            participant: 待加入的会话参与者；joined_at 为空时由仓储补齐。

        Returns:
            已写入数据库并带 joined_at 的参与者。

        Raises:
            StorageConflictError: Agent 已在同一会话中存在，或外键不存在。
        """
        self._validate_participant(participant)
        joined_at = participant.joined_at or _utc_now()
        stored = replace(participant, joined_at=joined_at)
        try:
            with self.database.transaction() as connection:
                connection.execute(
                    """
                    INSERT INTO session_participants (
                        id, session_id, agent_id, role, join_reason,
                        joined_at, left_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        stored.id,
                        stored.session_id,
                        stored.agent_id,
                        stored.role,
                        stored.join_reason,
                        stored.joined_at,
                        stored.left_at,
                    ),
                )
        except sqlite3.IntegrityError as error:
            raise StorageConflictError(
                f"参与者加入冲突: {stored.session_id}/{stored.agent_id}"
            ) from error
        return stored

    def get(self, participant_id: str) -> SessionParticipant | None:
        """按参与者 ID 读取会话参与者。"""
        validate_id("participant", participant_id)
        row = self.database.connection.execute(
            "SELECT * FROM session_participants WHERE id = ?",
            (participant_id,),
        ).fetchone()
        return None if row is None else self._from_row(row)

    def list_active(self, session_id: str) -> list[SessionParticipant]:
        """列出会话中尚未离开的参与者。"""
        validate_id("session", session_id)
        rows = self.database.connection.execute(
            """
            SELECT * FROM session_participants
            WHERE session_id = ? AND left_at IS NULL
            ORDER BY joined_at ASC, id ASC
            """,
            (session_id,),
        ).fetchall()
        return [self._from_row(row) for row in rows]

    def find(
        self,
        session_id: str,
        agent_id: str,
    ) -> SessionParticipant | None:
        """查找某 Agent 在指定会话中的参与者记录。"""
        validate_id("session", session_id)
        validate_id("agent", agent_id)
        row = self.database.connection.execute(
            """
            SELECT * FROM session_participants
            WHERE session_id = ? AND agent_id = ?
            """,
            (session_id, agent_id),
        ).fetchone()
        return None if row is None else self._from_row(row)

    def leave(self, participant_id: str) -> SessionParticipant | None:
        """结束参与者的活跃状态，但保留其历史记录。

        Args:
            participant_id: 待退出参与者的 ID。

        Returns:
            更新后的参与者；参与者不存在时返回 None。
        """
        current = self.get(participant_id)
        if current is None:
            return None
        if current.left_at is not None:
            return current
        left_at = _utc_now()
        with self.database.transaction() as connection:
            connection.execute(
                """
                UPDATE session_participants
                SET left_at = ?
                WHERE id = ? AND left_at IS NULL
                """,
                (left_at, participant_id),
            )
        return replace(current, left_at=left_at)

    @staticmethod
    def _validate_participant(participant: SessionParticipant) -> None:
        """验证参与者对象及首期稳定角色/加入原因枚举。"""
        if not isinstance(participant, SessionParticipant):
            raise TypeError("participant 必须是 SessionParticipant")
        if participant.role not in {"PRIMARY", "PARTICIPANT"}:
            raise ValueError(f"未知的参与者角色: {participant.role}")
        if participant.join_reason is not None and participant.join_reason not in {
            "USER_SELECTED",
            "DELEGATED",
            "AUTO_JOINED",
        }:
            raise ValueError(f"未知的参与原因: {participant.join_reason}")

    @staticmethod
    def _from_row(row: sqlite3.Row) -> SessionParticipant:
        """将数据库行严格转换为 SessionParticipant。"""
        try:
            return SessionParticipant(
                id=row["id"],
                session_id=row["session_id"],
                agent_id=row["agent_id"],
                role=row["role"],
                join_reason=row["join_reason"],
                joined_at=row["joined_at"],
                left_at=row["left_at"],
            )
        except (TypeError, ValueError) as error:
            raise StorageFormatError(
                "SessionParticipant 数据不符合领域约束"
            ) from error


def _utc_now() -> str:
    """生成统一的 UTC ISO 时间字符串。"""
    return datetime.now(timezone.utc).isoformat()
