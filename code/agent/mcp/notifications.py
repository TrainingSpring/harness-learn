"""MCP Server 通知的安全分发，不让观察者异常影响 Transport。"""

from __future__ import annotations

from collections.abc import Callable
from threading import Lock

from .protocol import JsonRpcNotification


_LIST_CHANGED_METHODS = {
    "notifications/tools/list_changed": "tools",
    "notifications/resources/list_changed": "resources",
    "notifications/prompts/list_changed": "prompts",
}


class McpNotificationDispatcher:
    """按能力列表变更类型订阅和分发 Server 通知。"""

    def __init__(self) -> None:
        self._listeners: dict[str, list[Callable[[], None]]] = {
            "tools": [],
            "resources": [],
            "prompts": [],
        }
        self._lock = Lock()

    def subscribe_tools_changed(self, listener: Callable[[], None]) -> Callable[[], None]:
        return self._subscribe("tools", listener)

    def subscribe_resources_changed(self, listener: Callable[[], None]) -> Callable[[], None]:
        return self._subscribe("resources", listener)

    def subscribe_prompts_changed(self, listener: Callable[[], None]) -> Callable[[], None]:
        return self._subscribe("prompts", listener)

    def dispatch(self, notification: JsonRpcNotification) -> bool:
        """处理已验证通知；未知通知由后续能力阶段消费。"""
        kind = _LIST_CHANGED_METHODS.get(notification.method)
        if kind is None:
            return False
        with self._lock:
            listeners = tuple(self._listeners[kind])
        for listener in listeners:
            try:
                listener()
            except Exception:
                pass
        return True

    def _subscribe(self, kind: str, listener: Callable[[], None]) -> Callable[[], None]:
        if not callable(listener):
            raise TypeError("listener 必须可调用")
        with self._lock:
            self._listeners[kind].append(listener)

        def unsubscribe() -> None:
            with self._lock:
                if listener in self._listeners[kind]:
                    self._listeners[kind].remove(listener)

        return unsubscribe
