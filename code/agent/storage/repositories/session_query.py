"""固定 1v1 会话的 SQLite 只读聚合仓储。"""

import json
import sqlite3
from typing import Any

from ..database import StateDatabase
from ..errors import StorageFormatError
from ..ids import validate_id
from ..types import DirectSessionSummary, Session


_DIRECT_SUMMARY_SELECT = """
SELECT
    sessions.id AS session_id,
    sessions.title AS session_title,
    sessions.conversation_mode,
    sessions.status AS session_status,
    sessions.permission_mode,
    sessions.project_path,
    sessions.created_at AS session_created_at,
    sessions.updated_at AS session_updated_at,
    sessions.closed_at AS session_closed_at,
    session_agents.agent_id,
    agent_profiles.name AS agent_name,
    last_item.payload_json AS last_payload_json,
    last_item.sequence_no AS last_sequence_no
FROM sessions
JOIN session_agents
    ON session_agents.session_id = sessions.id
   AND session_agents.role = 'PRIMARY'
JOIN agent_profiles
    ON agent_profiles.id = session_agents.agent_id
LEFT JOIN context_items AS last_item
    ON last_item.id = (
        -- 工具事件不覆盖会话摘要，只取序号最大的普通聊天消息。
        SELECT candidate.id
        FROM context_items AS candidate
        WHERE candidate.session_id = sessions.id
          AND candidate.kind IN ('USER_MESSAGE', 'AGENT_MESSAGE')
        ORDER BY candidate.sequence_no DESC, candidate.id DESC
        LIMIT 1
    )
WHERE sessions.conversation_mode = 'DIRECT'
  AND (
      -- 旧数据可能缺少或误添成员，只有唯一固定成员才是合法 1v1 会话。
      SELECT COUNT(*)
      FROM session_agents AS member_count
      WHERE member_count.session_id = sessions.id
  ) = 1
"""


class SessionQueryRepository:
    """一次查询组装客户端需要的固定 1v1 会话数据。

    Attributes:
        database: 已初始化的 workspace 状态数据库。

    本仓储只负责读取。它将 Session、唯一 Agent 和最后可展示消息聚合为
    DirectSessionSummary，避免上层针对每个会话继续查询 Agent 和 ContextItem。
    """

    def __init__(self, database: StateDatabase) -> None:
        """创建会话只读查询仓储。

        Args:
            database: 已调用 ``initialize()`` 的状态数据库。
        """
        self.database = database

    def list_direct_summaries(
        self,
        limit: int,
        offset: int,
    ) -> list[DirectSessionSummary]:
        """稳定分页读取固定 1v1 会话摘要。

        Args:
            limit: 最大返回数量，必须是正整数。
            offset: 按稳定排序跳过的记录数量，必须是非负整数。

        Returns:
            按更新时间和 Session ID 倒序排列的会话摘要。

        DIRECT 会话必须恰好包含一个 PRIMARY Agent 才会返回。该约束既避免
        JOIN 产生重复会话，也防止不完整数据伪装成可恢复的 1v1 会话。
        """
        self._validate_page(limit, offset)
        rows = self.database.connection.execute(
            _DIRECT_SUMMARY_SELECT
            + """
            ORDER BY sessions.updated_at DESC, sessions.id DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        ).fetchall()
        return [self._from_row(row) for row in rows]

    def get_direct_detail(self, session_id: str) -> DirectSessionSummary | None:
        """按 Session ID 读取一个固定 1v1 会话聚合。

        Args:
            session_id: 带 ``session_`` 前缀的稳定会话 ID。

        Returns:
            找到合法 DIRECT 会话时返回摘要；会话不存在、不是 DIRECT 或成员
            不满足唯一 Agent 约束时返回 None。
        """
        validate_id("session", session_id)
        row = self.database.connection.execute(
            _DIRECT_SUMMARY_SELECT
            + """
            AND sessions.id = ?
            LIMIT 1
            """,
            (session_id,),
        ).fetchone()
        return None if row is None else self._from_row(row)

    @staticmethod
    def _validate_page(limit: int, offset: int) -> None:
        """验证分页参数，避免布尔值或无意义数字进入 SQL。

        Args:
            limit: 最大返回数量。
            offset: 跳过的记录数量。
        """
        if not isinstance(limit, int) or isinstance(limit, bool) or limit <= 0:
            raise ValueError("limit 必须是正整数")
        if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
            raise ValueError("offset 必须是非负整数")

    @staticmethod
    def _from_row(row: sqlite3.Row) -> DirectSessionSummary:
        """把一行聚合查询结果严格转换为只读摘要。

        Args:
            row: 同时包含 Session、Agent 和最后消息字段的 SQLite 行。

        Returns:
            校验完成的 DirectSessionSummary。

        Raises:
            StorageFormatError: 数据库字段不符合领域类型或消息格式时抛出。
        """
        try:
            session = Session(
                id=row["session_id"],
                title=row["session_title"],
                conversation_mode=row["conversation_mode"],
                status=row["session_status"],
                permission_mode=row["permission_mode"],
                project_path=row["project_path"],
                created_at=row["session_created_at"],
                updated_at=row["session_updated_at"],
                closed_at=row["session_closed_at"],
            )
            last_message = SessionQueryRepository._message_text(
                row["last_payload_json"]
            )
            return DirectSessionSummary(
                session=session,
                agent_id=row["agent_id"],
                agent_name=row["agent_name"],
                last_message=last_message,
                last_sequence_no=row["last_sequence_no"],
            )
        except (TypeError, ValueError) as error:
            raise StorageFormatError(
                "DIRECT 会话聚合数据不符合领域约束"
            ) from error

    @staticmethod
    def _message_text(payload_json: str | None) -> str | None:
        """从最后一条消息的 JSON 载荷中读取文本。

        Args:
            payload_json: ContextItem 的 JSON 载荷；无消息时为 None。

        Returns:
            无消息时返回 None，否则返回载荷中的 text 字符串。

        Raises:
            StorageFormatError: 载荷不是 JSON 对象或缺少字符串 text 时抛出。
        """
        if payload_json is None:
            return None
        try:
            payload: Any = json.loads(payload_json)
        except (TypeError, json.JSONDecodeError) as error:
            raise StorageFormatError(
                "最后一条消息的 payload_json 不是有效 JSON"
            ) from error
        if not isinstance(payload, dict) or not isinstance(payload.get("text"), str):
            raise StorageFormatError("最后一条可展示消息必须包含字符串 text")
        return payload["text"]
