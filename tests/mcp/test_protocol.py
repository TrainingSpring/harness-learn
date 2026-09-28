"""MCP JSON-RPC 协议边界测试。"""

import pytest

from mcp.errors import McpProtocolError, McpRemoteError
from mcp.protocol import JsonRpcNotification, JsonRpcRequest, JsonRpcResponse, parse_message


def test_parse_json_rpc_request_response_and_notification() -> None:
    request = parse_message({"jsonrpc": "2.0", "id": 7, "method": "tools/list", "params": {}})
    response = parse_message({"jsonrpc": "2.0", "id": 7, "result": {"tools": []}})
    notification = parse_message({"jsonrpc": "2.0", "method": "notifications/tools/list_changed"})

    assert isinstance(request, JsonRpcRequest)
    assert isinstance(response, JsonRpcResponse)
    assert isinstance(notification, JsonRpcNotification)
    assert response.unwrap() == {"tools": []}


def test_protocol_rejects_invalid_messages_and_exposes_remote_errors() -> None:
    with pytest.raises(McpProtocolError):
        parse_message({"jsonrpc": "2.0", "id": 1, "result": {}, "error": {}})
    with pytest.raises(McpProtocolError):
        parse_message({"jsonrpc": "1.0", "id": 1, "method": "tools/list"})

    response = parse_message(
        {"jsonrpc": "2.0", "id": "call-1", "error": {"code": -32601, "message": "missing"}}
    )
    assert isinstance(response, JsonRpcResponse)
    with pytest.raises(McpRemoteError, match="missing"):
        response.unwrap()
