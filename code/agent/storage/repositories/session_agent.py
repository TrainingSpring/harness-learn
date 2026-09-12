"""SessionAgent 的 SQLite 仓储。"""

import sqlite3

from ..database import StateDatabase
from ..errors import StorageFormatError
from ..ids import validate_id
from ..types import SessionAgent


class SessionAgentRepository:
    """管理固定会话与 Agent 之间不可变的成员关系。

    Attributes:
        database: 已初始化的 workspace 状态数据库。

    当前产品在创建会话时确定成员，之后不支持加入、退出或替换，因此本仓储
    只提供读取操作。唯一写入路径是 SessionRepository.create_with_agents()，
    它会在创建 Session 的同一事务中一次性写入全部成员。
    """

    def __init__(self, database: StateDatabase) -> None:
        """创建会话成员仓储。

        Args:
            database: 已调用 ``initialize()`` 的状态数据库。
        """
        self.database = database

    def get(self, session_id: str, agent_id: str) -> SessionAgent | None:
        """按会话和 Agent 的联合身份读取成员关系。

        Args:
            session_id: 会话 ID。
            agent_id: AgentProfile 的稳定 ID。
        """
        validate_id("session", session_id)
        validate_id("agent", agent_id)
        row = self.database.connection.execute(
            """
            SELECT * FROM session_agents
            WHERE session_id = ? AND agent_id = ?
            """,
            (session_id, agent_id),
        ).fetchone()
        return None if row is None else self._from_row(row)

    def exists(self, session_id: str, agent_id: str) -> bool:
        """判断指定 Agent 是否属于该会话。"""
        return self.get(session_id, agent_id) is not None

    def list_for_session(self, session_id: str) -> list[SessionAgent]:
        """按创建顺序列出会话创建时确定的全部 Agent。"""
        validate_id("session", session_id)
        rows = self.database.connection.execute(
            """
            SELECT * FROM session_agents
            WHERE session_id = ?
            ORDER BY created_at ASC, agent_id ASC
            """,
            (session_id,),
        ).fetchall()
        return [self._from_row(row) for row in rows]

    @staticmethod
    def _from_row(row: sqlite3.Row) -> SessionAgent:
        """将数据库行严格转换为 SessionAgent。"""
        try:
            return SessionAgent(
                session_id=row["session_id"],
                agent_id=row["agent_id"],
                role=row["role"],
                created_at=row["created_at"],
            )
        except (TypeError, ValueError) as error:
            raise StorageFormatError("SessionAgent 数据不符合领域约束") from error
