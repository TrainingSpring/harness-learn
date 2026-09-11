"""本地 SQLite 状态数据库的生命周期管理。"""

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .migrations import migrate


class StateDatabase:
    """管理一个 workspace 对应的本地状态数据库。

    Attributes:
        workspace: 规范化后的 workspace 目录。
        path: 状态数据库文件路径，固定为 workspace/.harness/state.db。

    该类只负责连接、事务和 schema 迁移，不负责把数据库行转换为业务对象，
    也不负责权限判断或创建运行时 Agent。
    """

    def __init__(self, workspace: str) -> None:
        """创建数据库管理器，但不立即打开文件。

        Args:
            workspace: 当前项目的工作目录。
        """
        self.workspace = Path(workspace).expanduser().resolve()
        self.path = self.workspace / ".harness" / "state.db"
        self._connection: sqlite3.Connection | None = None

    @property
    def connection(self) -> sqlite3.Connection:
        """返回已经打开的连接。

        Raises:
            RuntimeError: connect 或 initialize 尚未调用时抛出。
        """
        if self._connection is None:
            raise RuntimeError("StateDatabase 尚未连接")
        return self._connection

    def connect(self) -> sqlite3.Connection:
        """打开并缓存数据库连接。

        Returns:
            配置了 Row 工厂、外键约束和 busy timeout 的 SQLite 连接。
        """
        if self._connection is not None:
            return self._connection

        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(str(self.path))
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._connection.execute("PRAGMA busy_timeout = 5000")
        return self._connection

    def initialize(self) -> None:
        """打开数据库并执行 schema 迁移。"""
        migrate(self.connect())

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """提供提交或回滚的事务上下文。

        Yields:
            当前数据库连接。

        事务中的异常会自动回滚并继续向调用方抛出；成功离开上下文时提交。
        """
        connection = self.connection
        try:
            yield connection
        except Exception:
            connection.rollback()
            raise
        else:
            connection.commit()

    def close(self) -> None:
        """关闭数据库连接；重复关闭是安全的。"""
        if self._connection is not None:
            self._connection.close()
            self._connection = None
