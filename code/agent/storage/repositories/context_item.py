"""ContextItem 的 SQLite 时间线仓储。"""

import json
import sqlite3
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any

from ..database import StateDatabase
from ..errors import StorageConflictError, StorageFormatError
from ..ids import validate_id
from ..types import ContextItem


class ContextItemRepository:
    """负责会话时间线的追加、恢复和可见性投影。

    Attributes:
        database: 已初始化的 workspace 状态数据库。

    本仓储只追加历史，不提供更新接口。sequence_no 在数据库事务中分配，
    目标和因果引用也在同一边界内校验，避免上层拼出跨会话或越权可见记录。
    """

    _AUTHOR_REQUIRED_KINDS = frozenset(
        {"AGENT_MESSAGE", "FUNCTION_CALL", "FUNCTION_CALL_OUTPUT"}
    )

    def __init__(self, database: StateDatabase) -> None:
        """创建上下文项仓储。

        Args:
            database: 已调用 ``initialize()`` 的状态数据库。
        """
        self.database = database

    def append(self, item: ContextItem) -> ContextItem:
        """追加一条上下文项并在事务中分配正式序号。

        Args:
            item: 待追加的上下文项。``sequence_no=0`` 表示序号由仓储分配；
                即使调用方传入其他值，仓储也不会信任它。

        Returns:
            已写入数据库、带正式 sequence_no 和 created_at 的上下文项。

        Raises:
            ValueError: 可见性、作者、目标或因果引用不符合会话约束。
            StorageConflictError: ID、function call 或 output 违反唯一约束。
        """
        if not isinstance(item, ContextItem):
            raise TypeError("item 必须是 ContextItem")
        try:
            payload_json = json.dumps(
                item.payload,
                ensure_ascii=False,
                sort_keys=True,
            )
        except (TypeError, ValueError) as error:
            raise ValueError("payload 必须是可 JSON 序列化的字典") from error

        try:
            with self.database.transaction() as connection:
                self._validate_references(connection, item)
                sequence_no = connection.execute(
                    """
                    SELECT COALESCE(MAX(sequence_no), 0) + 1
                    FROM context_items
                    WHERE session_id = ?
                    """,
                    (item.session_id,),
                ).fetchone()[0]
                created_at = item.created_at or _utc_now()
                stored = replace(
                    item,
                    sequence_no=sequence_no,
                    created_at=created_at,
                )
                connection.execute(
                    """
                    INSERT INTO context_items (
                        id, session_id, sequence_no, kind,
                        author_participant_id, target_participant_id,
                        visibility, call_id, caused_by_item_id,
                        payload_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        stored.id,
                        stored.session_id,
                        stored.sequence_no,
                        stored.kind,
                        stored.author_participant_id,
                        stored.target_participant_id,
                        stored.visibility,
                        stored.call_id,
                        stored.caused_by_item_id,
                        payload_json,
                        stored.created_at,
                    ),
                )
        except sqlite3.IntegrityError as error:
            raise StorageConflictError(
                f"上下文项追加冲突: {item.session_id}/{item.id}"
            ) from error
        return stored

    def list_after(self, session_id: str, sequence_no: int) -> list[ContextItem]:
        """读取会话中指定序号之后的全部时间线项。"""
        validate_id("session", session_id)
        if not isinstance(sequence_no, int) or sequence_no < 0:
            raise ValueError("sequence_no 必须是非负整数")
        rows = self.database.connection.execute(
            """
            SELECT * FROM context_items
            WHERE session_id = ? AND sequence_no > ?
            ORDER BY sequence_no ASC
            """,
            (session_id, sequence_no),
        ).fetchall()
        return [self._from_row(row) for row in rows]

    def list_visible(
        self,
        session_id: str,
        participant_id: str,
    ) -> list[ContextItem]:
        """读取一个参与者可见的上下文投影。

        Args:
            session_id: 要读取的会话 ID。
            participant_id: 当前接收 Agent 的参与者 ID。

        Returns:
            PUBLIC 项、发给该参与者的 TARGETED 项，以及该参与者自己产生的
            PRIVATE 项，均按时间线顺序返回。
        """
        validate_id("session", session_id)
        validate_id("participant", participant_id)
        rows = self.database.connection.execute(
            """
            SELECT * FROM context_items
            WHERE session_id = ?
              AND (
                  visibility = 'PUBLIC'
                  OR (visibility = 'TARGETED' AND target_participant_id = ?)
                  OR (visibility = 'PRIVATE' AND author_participant_id = ?)
              )
            ORDER BY sequence_no ASC
            """,
            (session_id, participant_id, participant_id),
        ).fetchall()
        return [self._from_row(row) for row in rows]

    def find_by_call_id(
        self,
        session_id: str,
        call_id: str,
    ) -> ContextItem | None:
        """按会话和模型 call_id 查找一条 function call 相关上下文项。"""
        validate_id("session", session_id)
        if not isinstance(call_id, str) or not call_id:
            raise ValueError("call_id 必须是非空字符串")
        row = self.database.connection.execute(
            """
            SELECT * FROM context_items
            WHERE session_id = ? AND call_id = ?
            ORDER BY sequence_no ASC
            LIMIT 1
            """,
            (session_id, call_id),
        ).fetchone()
        return None if row is None else self._from_row(row)

    def _validate_references(
        self,
        connection: sqlite3.Connection,
        item: ContextItem,
    ) -> None:
        """在追加事务中校验所有会话内作者、目标和因果引用。"""
        session_exists = connection.execute(
            "SELECT 1 FROM sessions WHERE id = ?",
            (item.session_id,),
        ).fetchone()
        if session_exists is None:
            raise ValueError("上下文项所属 Session 不存在")

        if item.author_participant_id is not None:
            author = connection.execute(
                """
                SELECT 1 FROM session_participants
                WHERE id = ? AND session_id = ?
                """,
                (item.author_participant_id, item.session_id),
            ).fetchone()
            if author is None:
                raise ValueError("上下文项作者不属于当前 Session")
        if item.kind in self._AUTHOR_REQUIRED_KINDS and item.author_participant_id is None:
            raise ValueError(f"{item.kind} 必须指定作者参与者")

        if item.visibility == "TARGETED":
            target = connection.execute(
                """
                SELECT 1 FROM session_participants
                WHERE id = ? AND session_id = ? AND left_at IS NULL
                """,
                (item.target_participant_id, item.session_id),
            ).fetchone()
            if target is None:
                raise ValueError("TARGETED 上下文的目标必须是当前活跃参与者")
        elif item.visibility in {"PUBLIC", "PRIVATE"} and item.target_participant_id is not None:
            raise ValueError(f"{item.visibility} 上下文不能指定目标")

        if item.kind == "FUNCTION_CALL":
            self._require_call_id(item)
            existing_call = connection.execute(
                """
                SELECT 1 FROM context_items
                WHERE session_id = ? AND kind = 'FUNCTION_CALL' AND call_id = ?
                """,
                (item.session_id, item.call_id),
            ).fetchone()
            if existing_call is not None:
                raise StorageConflictError("同一 Session 中不能重复写入 function_call")
        elif item.kind == "FUNCTION_CALL_OUTPUT":
            self._require_call_id(item)
            function_call = connection.execute(
                """
                SELECT 1 FROM context_items
                WHERE session_id = ? AND kind = 'FUNCTION_CALL' AND call_id = ?
                """,
                (item.session_id, item.call_id),
            ).fetchone()
            if function_call is None:
                raise ValueError("function_call_output 没有对应的 function_call")
            duplicate_output = connection.execute(
                """
                SELECT 1 FROM context_items
                WHERE session_id = ?
                  AND kind = 'FUNCTION_CALL_OUTPUT'
                  AND call_id = ?
                """,
                (item.session_id, item.call_id),
            ).fetchone()
            if duplicate_output is not None:
                raise StorageConflictError(
                    "同一 function_call 不能重复写入 function_call_output"
                )

        if item.caused_by_item_id is not None:
            caused_by = connection.execute(
                """
                SELECT 1 FROM context_items
                WHERE id = ? AND session_id = ?
                """,
                (item.caused_by_item_id, item.session_id),
            ).fetchone()
            if caused_by is None:
                raise ValueError("caused_by_item_id 必须指向同一 Session 的上下文项")

    @staticmethod
    def _require_call_id(item: ContextItem) -> None:
        """验证 function call 相关项携带非空 call_id。"""
        if not isinstance(item.call_id, str) or not item.call_id:
            raise ValueError(f"{item.kind} 必须指定非空 call_id")

    @staticmethod
    def _from_row(row: sqlite3.Row) -> ContextItem:
        """将数据库行严格转换为 ContextItem。"""
        try:
            payload: Any = json.loads(row["payload_json"])
        except (TypeError, json.JSONDecodeError) as error:
            raise StorageFormatError("ContextItem.payload_json 不是有效 JSON") from error
        if not isinstance(payload, dict):
            raise StorageFormatError("ContextItem.payload_json 必须编码为对象")
        try:
            return ContextItem(
                id=row["id"],
                session_id=row["session_id"],
                sequence_no=row["sequence_no"],
                kind=row["kind"],
                author_participant_id=row["author_participant_id"],
                target_participant_id=row["target_participant_id"],
                visibility=row["visibility"],
                payload=payload,
                call_id=row["call_id"],
                caused_by_item_id=row["caused_by_item_id"],
                created_at=row["created_at"],
            )
        except (TypeError, ValueError) as error:
            raise StorageFormatError("ContextItem 数据不符合领域约束") from error


def _utc_now() -> str:
    """生成统一的 UTC ISO 时间字符串。"""
    return datetime.now(timezone.utc).isoformat()
