"""MCP 使用的 JSON-RPC 2.0 消息模型与严格解析边界。"""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, TypeAlias

from .errors import McpProtocolError, McpRemoteError


JsonRpcId: TypeAlias = int | str
JsonRpcParams: TypeAlias = dict[str, Any] | list[Any]
JsonRpcMessage: TypeAlias = "JsonRpcRequest | JsonRpcNotification | JsonRpcResponse"


def _require_id(value: object, *, allow_null: bool = False) -> JsonRpcId | None:
    if value is None and allow_null:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise McpProtocolError("JSON-RPC id 必须是字符串、整数或 null")
    return value


def _require_method(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise McpProtocolError("JSON-RPC method 必须是非空字符串")
    return value


def _require_params(value: object) -> JsonRpcParams | None:
    if value is None:
        return None
    if not isinstance(value, (dict, list)):
        raise McpProtocolError("JSON-RPC params 必须是对象或数组")
    return value


@dataclass(frozen=True)
class JsonRpcRequest:
    """一个需要 Server 返回关联 response 的 JSON-RPC 请求。"""

    id: JsonRpcId
    method: str
    params: JsonRpcParams | None = None

    def __post_init__(self) -> None:
        _require_id(self.id)
        _require_method(self.method)
        _require_params(self.params)

    def to_dict(self) -> dict[str, Any]:
        message: dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": self.id,
            "method": self.method,
        }
        if self.params is not None:
            message["params"] = self.params
        return message


@dataclass(frozen=True)
class JsonRpcNotification:
    """不等待 response 的 JSON-RPC 通知。"""

    method: str
    params: JsonRpcParams | None = None

    def __post_init__(self) -> None:
        _require_method(self.method)
        _require_params(self.params)

    def to_dict(self) -> dict[str, Any]:
        message: dict[str, Any] = {"jsonrpc": "2.0", "method": self.method}
        if self.params is not None:
            message["params"] = self.params
        return message


@dataclass(frozen=True)
class JsonRpcError:
    """远端 response 中的标准 JSON-RPC 错误载荷。"""

    code: int
    message: str
    data: Any = None

    def __post_init__(self) -> None:
        if isinstance(self.code, bool) or not isinstance(self.code, int):
            raise McpProtocolError("JSON-RPC error.code 必须是整数")
        if not isinstance(self.message, str):
            raise McpProtocolError("JSON-RPC error.message 必须是字符串")

    def to_dict(self) -> dict[str, Any]:
        value: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.data is not None:
            value["data"] = self.data
        return value


@dataclass(frozen=True)
class JsonRpcResponse:
    """Server 对一个请求的成功结果或错误结果。"""

    id: JsonRpcId | None
    result: Any = None
    error: JsonRpcError | None = None

    def __post_init__(self) -> None:
        _require_id(self.id, allow_null=True)
        if self.error is not None and not isinstance(self.error, JsonRpcError):
            raise McpProtocolError("JSON-RPC error 必须是对象")

    def unwrap(self) -> Any:
        """返回成功结果；远端错误转换为稳定的内部异常。"""
        if self.error is not None:
            raise McpRemoteError(self.error.code, self.error.message, self.error.data)
        return self.result

    def to_dict(self) -> dict[str, Any]:
        message: dict[str, Any] = {"jsonrpc": "2.0", "id": self.id}
        if self.error is not None:
            message["error"] = self.error.to_dict()
        else:
            message["result"] = self.result
        return message


def parse_message(value: object) -> JsonRpcMessage:
    """验证并解析一条来自不可信 MCP Server 的 JSON-RPC 2.0 消息。"""
    if not isinstance(value, dict):
        raise McpProtocolError("JSON-RPC 消息必须是对象")
    if value.get("jsonrpc") != "2.0":
        raise McpProtocolError("JSON-RPC version 必须为 2.0")

    if "method" in value:
        method = _require_method(value["method"])
        params = _require_params(value.get("params"))
        if "id" not in value:
            return JsonRpcNotification(method=method, params=params)
        request_id = _require_id(value["id"])
        assert request_id is not None
        return JsonRpcRequest(id=request_id, method=method, params=params)

    has_result = "result" in value
    has_error = "error" in value
    if "id" not in value or has_result == has_error:
        raise McpProtocolError("JSON-RPC response 必须恰好包含 result 或 error")
    response_id = _require_id(value["id"], allow_null=True)
    if has_error:
        error = value["error"]
        if not isinstance(error, dict) or set(error) - {"code", "message", "data"}:
            raise McpProtocolError("JSON-RPC error 格式无效")
        if "code" not in error or "message" not in error:
            raise McpProtocolError("JSON-RPC error 缺少 code 或 message")
        return JsonRpcResponse(
            id=response_id,
            error=JsonRpcError(error["code"], error["message"], error.get("data")),
        )
    return JsonRpcResponse(id=response_id, result=value["result"])


def encode_message(message: JsonRpcMessage) -> bytes:
    """将已验证的消息编码为 UTF-8 JSON，拒绝不可序列化的参数。"""
    try:
        return json.dumps(message.to_dict(), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise McpProtocolError("JSON-RPC 消息无法编码为 JSON") from error
