"""会话上下文的业务事件写入与模型输入投影。"""

import json
from typing import Any

from storage.ids import generate_id
from storage.repositories.context_item import ContextItemRepository
from storage.types import ContextItem


class ContextService:
    """在持久化 ContextItem 与 Responses 输入之间提供业务层边界。

    Attributes:
        repository: 负责序号、引用和可见性校验的上下文仓储。
        session_id: 本服务操作的会话 ID。

    ContextService 保存的是用户消息、Agent 消息和工具事件等业务语义；
    ``type``、``role`` 等厂商协议字段只在 ``to_responses_input`` 中生成。
    """

    def __init__(
        self,
        repository: ContextItemRepository,
        session_id: str,
    ) -> None:
        """创建指定会话的上下文服务。

        Args:
            repository: 上下文项仓储。
            session_id: 当前服务绑定的 Session ID。
        """
        self.repository = repository
        self.session_id = session_id

    def append_user_message(
        self,
        text: str,
        *,
        visibility: str = "PUBLIC",
        target_participant_id: str | None = None,
    ) -> ContextItem:
        """追加一条本地用户消息。"""
        self._require_text(text)
        return self._append(
            kind="USER_MESSAGE",
            payload={"text": text},
            visibility=visibility,
            target_participant_id=target_participant_id,
        )

    def append_agent_message(
        self,
        author_participant_id: str,
        text: str,
        *,
        visibility: str = "PUBLIC",
        target_participant_id: str | None = None,
    ) -> ContextItem:
        """追加一条 Agent 消息，可选地定向发送给另一个参与者。"""
        self._require_text(text)
        return self._append(
            kind="AGENT_MESSAGE",
            payload={"text": text},
            author_participant_id=author_participant_id,
            visibility=visibility,
            target_participant_id=target_participant_id,
        )

    def append_function_call(
        self,
        author_participant_id: str,
        *,
        call_id: str,
        name: str,
        arguments: str | dict[str, Any],
    ) -> ContextItem:
        """追加一条 Agent 发起的 function call 业务事件。"""
        if not call_id:
            raise ValueError("call_id 不能为空")
        if not name:
            raise ValueError("工具名称不能为空")
        if isinstance(arguments, dict):
            arguments = json.dumps(arguments, ensure_ascii=False)
        if not isinstance(arguments, str):
            raise TypeError("arguments 必须是字符串或字典")
        return self._append(
            kind="FUNCTION_CALL",
            payload={"name": name, "arguments": arguments},
            author_participant_id=author_participant_id,
            visibility="PUBLIC",
            call_id=call_id,
        )

    def append_function_call_output(
        self,
        author_participant_id: str,
        *,
        call_id: str,
        output: Any,
        caused_by_item_id: str | None = None,
    ) -> ContextItem:
        """追加一条工具调用结果；配对校验由 ContextItemRepository 完成。"""
        if not call_id:
            raise ValueError("call_id 不能为空")
        return self._append(
            kind="FUNCTION_CALL_OUTPUT",
            payload={"output": output},
            author_participant_id=author_participant_id,
            visibility="PUBLIC",
            call_id=call_id,
            caused_by_item_id=caused_by_item_id,
        )

    def load_visible(self, participant_id: str) -> list[ContextItem]:
        """读取指定参与者可见的会话时间线。"""
        return self.repository.list_visible(self.session_id, participant_id)

    @staticmethod
    def to_responses_input(items: list[ContextItem]) -> list[dict[str, Any]]:
        """把业务上下文项转换为当前 LLM 适配器需要的 Responses 输入。"""
        projected: list[dict[str, Any]] = []
        for item in items:
            if item.kind == "USER_MESSAGE":
                projected.append(
                    ContextService._message_item("user", item.payload["text"])
                )
            elif item.kind == "AGENT_MESSAGE":
                projected.append(
                    ContextService._message_item("assistant", item.payload["text"])
                )
            elif item.kind == "FUNCTION_CALL":
                projected.append(
                    {
                        "type": "function_call",
                        "call_id": item.call_id,
                        "name": item.payload["name"],
                        "arguments": item.payload["arguments"],
                    }
                )
            elif item.kind == "FUNCTION_CALL_OUTPUT":
                projected.append(
                    {
                        "type": "function_call_output",
                        "call_id": item.call_id,
                        "output": item.payload["output"],
                    }
                )
            elif item.kind in {"AGENT_DELEGATION", "SYSTEM_EVENT"}:
                # 这些事件没有独立的 Responses 类型，用开发者消息承载事实背景。
                projected.append(
                    ContextService._message_item(
                        "developer",
                        item.payload.get("text", json.dumps(item.payload, ensure_ascii=False)),
                    )
                )
        return projected

    def _append(
        self,
        *,
        kind: str,
        payload: dict[str, Any],
        visibility: str,
        author_participant_id: str | None = None,
        target_participant_id: str | None = None,
        call_id: str | None = None,
        caused_by_item_id: str | None = None,
    ) -> ContextItem:
        """构造业务上下文项并交给仓储完成持久化校验。"""
        return self.repository.append(
            ContextItem(
                id=generate_id("item"),
                session_id=self.session_id,
                sequence_no=0,
                kind=kind,
                author_participant_id=author_participant_id,
                target_participant_id=target_participant_id,
                visibility=visibility,
                payload=payload,
                call_id=call_id,
                caused_by_item_id=caused_by_item_id,
            )
        )

    @staticmethod
    def _message_item(role: str, text: str) -> dict[str, Any]:
        """构造 Responses message 项，协议字段只在此适配边界生成。"""
        return {
            "type": "message",
            "role": role,
            "content": [{"type": "input_text", "text": text}],
        }

    @staticmethod
    def _require_text(text: str) -> None:
        """拒绝空消息，避免把不可用事件写入时间线。"""
        if not isinstance(text, str) or not text.strip():
            raise ValueError("消息文本不能为空")
