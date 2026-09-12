"""进程内活动 Runtime 注册表。"""

from dataclasses import dataclass
from datetime import datetime, timezone
import secrets
import string
from typing import Any


_ID_ALPHABET = string.ascii_uppercase + string.digits


class RunAlreadyActiveError(Exception):
    """同一个 Session 已存在尚未结束的 Run。"""


@dataclass
class ActiveRun:
    """一次需要跨 HTTP 请求保留的运行实例。

    Attributes:
        run_id: Web 运行标识，只用于进程内注册和 API 路由。
        session_id: 被本次运行修改的固定会话。
        agent_id: 会话中唯一 Agent 的稳定身份。
        agent: 持有 Runtime 和 pending 工具队列的原始 Agent 对象。
        created_at: 注册时间，供后续超时清理和诊断使用。
        last_sequence_no: 已转换成 SSE 的最后一个 ContextItem 序号。
        pending_call_id: 等待用户确认时唯一允许恢复的 function call ID。
        cancelled: 客户端是否已请求停止。
    """

    run_id: str
    session_id: str
    agent_id: str
    agent: Any
    created_at: str
    last_sequence_no: int = 0
    pending_call_id: str | None = None
    cancelled: bool = False


class RunRegistry:
    """保证每个 Session 最多保留一个活动 Runtime。

    注册表只保存当前进程对象，不承担持久化。权限确认必须取回这里的原 Agent，
    因为重新通过 AgentFactory 加载会丢失 Runtime 中的 pending 工具调用。
    """

    def __init__(self) -> None:
        """创建空的双索引注册表。"""
        self._runs: dict[str, ActiveRun] = {}
        self._session_runs: dict[str, str] = {}

    def create(self, session_id: str, agent_id: str, agent: Any) -> ActiveRun:
        """注册运行实例，并拒绝同一会话的并发运行。"""
        if session_id in self._session_runs:
            raise RunAlreadyActiveError(session_id)
        run = ActiveRun(
            run_id=self._generate_id(),
            session_id=session_id,
            agent_id=agent_id,
            agent=agent,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self._runs[run.run_id] = run
        self._session_runs[session_id] = run.run_id
        return run

    def get(self, run_id: str) -> ActiveRun | None:
        """按 runId 读取活动运行。"""
        return self._runs.get(run_id)

    def get_for_session(self, session_id: str) -> ActiveRun | None:
        """读取指定 Session 当前占用的运行。"""
        run_id = self._session_runs.get(session_id)
        return None if run_id is None else self._runs.get(run_id)

    def remove(self, run_id: str) -> ActiveRun | None:
        """同时释放 runId 和 sessionId 索引，重复调用是安全的。"""
        run = self._runs.pop(run_id, None)
        if run is not None and self._session_runs.get(run.session_id) == run_id:
            self._session_runs.pop(run.session_id, None)
        return run

    def cancel(self, run_id: str) -> bool:
        """标记运行已取消并立即释放会话占用。"""
        run = self.get(run_id)
        if run is None:
            return False
        run.cancelled = True
        self.remove(run_id)
        return True

    def clear(self) -> None:
        """服务关闭时取消并清空全部进程内运行。"""
        for run in self._runs.values():
            run.cancelled = True
        self._runs.clear()
        self._session_runs.clear()

    @staticmethod
    def _generate_id() -> str:
        """生成与持久化 ID 风格一致的进程内 run_ 标识。"""
        suffix = "".join(secrets.choice(_ID_ALPHABET) for _ in range(10))
        return f"run_{suffix}"

