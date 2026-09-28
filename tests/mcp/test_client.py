"""MCP 生命周期、能力、分页和连接隔离测试。"""

from __future__ import annotations

from dataclasses import dataclass
from threading import Event, Thread

import pytest

from mcp.capabilities import McpServerCapabilities
from mcp.client import McpClient, McpClientState
from mcp.connection_manager import McpConnectionKey, McpConnectionManager
from mcp.errors import (
    McpCapabilityUnavailableError,
    McpLifecycleError,
    McpPaginationError,
    McpTransportError,
    McpServerDisabledError,
    McpRemoteError,
)
from mcp.protocol import JsonRpcError, JsonRpcNotification, JsonRpcParams, JsonRpcResponse
from mcp.types import LocalMcpServerConfig


@dataclass
class FakeTransport:
    responses: dict[str, list[object]]

    def __post_init__(self) -> None:
        self.calls: list[tuple[str, JsonRpcParams | None]] = []
        self.notifications: list[tuple[str, JsonRpcParams | None]] = []
        self.closed = False
        self.on_notification = None

    def request(self, method, params=None, *, timeout_ms=None, cancel_event=None):
        self.calls.append((method, params))
        values = self.responses.get(method, [])
        if not values:
            raise AssertionError(f"unexpected method: {method}")
        value = values.pop(0)
        if isinstance(value, Exception):
            raise value
        if isinstance(value, JsonRpcResponse):
            return value
        return JsonRpcResponse(id=len(self.calls), result=value)

    def notify(self, method, params=None):
        self.notifications.append((method, params))

    def close(self):
        self.closed = True


def _initialize_result(*, capabilities=None, protocol="2025-06-18"):
    return {
        "protocolVersion": protocol,
        "capabilities": capabilities or {"tools": {"listChanged": True}, "resources": {}, "prompts": {}},
        "serverInfo": {"name": "fake-server", "version": "1.0"},
        "instructions": "Use tools carefully.",
    }


def test_client_initializes_negotiates_capabilities_and_handles_list_changed() -> None:
    transport = FakeTransport(
        {
            "initialize": [_initialize_result()],
            "tools/list": [{"tools": [{"name": "search"}], "nextCursor": None}, {"tools": [{"name": "updated"}]}],
            "ping": [{}],
        }
    )
    client = McpClient(transport)
    changes = []
    client.notifications.subscribe_tools_changed(lambda: changes.append("tools"))

    info = client.connect()
    assert info.protocol_version == "2025-06-18"
    assert info.server_info.name == "fake-server"
    assert transport.notifications == [("notifications/initialized", None)]
    assert client.list_tools() == ({"name": "search"},)
    assert client.ping() == {}

    client.handle_notification(JsonRpcNotification("notifications/tools/list_changed"))
    assert changes == ["tools"]
    assert client.list_tools() == ({"name": "updated"},)


def test_client_calls_tool_and_reads_resource_and_prompt() -> None:
    transport = FakeTransport(
        {
            "initialize": [_initialize_result()],
            "tools/call": [{"content": [{"type": "text", "text": "done"}], "isError": False}],
            "resources/read": [{"contents": [{"uri": "file:///tmp/readme", "text": "contents"}]}],
            "prompts/get": [{"description": "Greeting", "messages": []}],
        }
    )
    client = McpClient(transport)
    client.connect()

    assert client.call_tool("echo", {"value": "x"})["content"][0]["text"] == "done"
    assert client.read_resource("file:///tmp/readme")["contents"][0]["text"] == "contents"
    assert client.get_prompt("greeting", {"name": "A"})["description"] == "Greeting"
    assert [item[0] for item in transport.calls[-3:]] == [
        "tools/call", "resources/read", "prompts/get"
    ]


def test_client_rejects_incompatible_protocol_or_missing_capability() -> None:
    incompatible = McpClient(FakeTransport({"initialize": [_initialize_result(protocol="2099-01-01")]}))
    with pytest.raises(McpLifecycleError, match="协议版本"):
        incompatible.connect()
    assert incompatible.state is McpClientState.FAILED

    tools_only = McpClient(FakeTransport({"initialize": [_initialize_result(capabilities={"tools": {}})]}))
    tools_only.connect()
    with pytest.raises(McpCapabilityUnavailableError):
        tools_only.list_resources()


def test_client_paginates_with_cursor_and_rejects_repeating_cursor() -> None:
    transport = FakeTransport(
        {
            "initialize": [_initialize_result()],
            "prompts/list": [
                {"prompts": [{"name": "first"}], "nextCursor": "page-2"},
                {"prompts": [{"name": "second"}], "nextCursor": None},
            ],
        }
    )
    client = McpClient(transport)
    client.connect()
    assert client.list_prompts() == ({"name": "first"}, {"name": "second"})
    assert transport.calls[-1] == ("prompts/list", {"cursor": "page-2"})

    looping = McpClient(
        FakeTransport(
            {"initialize": [_initialize_result()], "tools/list": [{"tools": [], "nextCursor": "same"}, {"tools": [], "nextCursor": "same"}]}
        )
    )
    looping.connect()
    with pytest.raises(McpPaginationError):
        looping.list_tools()


def test_connection_manager_isolates_clients_by_session_agent_and_server() -> None:
    created: list[FakeTransport] = []

    def factory(_config, notification_handler):
        transport = FakeTransport({"initialize": [_initialize_result()]})
        transport.on_notification = notification_handler
        created.append(transport)
        return transport

    config = LocalMcpServerConfig(id="mcp_LOCAL00001", name="Local", command="python")
    manager = McpConnectionManager(transport_factory=factory)
    first_key = McpConnectionKey("session_ONE0001", "agent_AGENT0001", "mcp_LOCAL00001")
    second_key = McpConnectionKey("session_TWO0001", "agent_AGENT0001", "mcp_LOCAL00001")
    try:
        first = manager.connect(first_key, config)
        assert manager.connect(first_key, config) is first
        second = manager.connect(second_key, config)
        assert second is not first
        assert len(created) == 2

        manager.close_session("session_ONE0001")
        assert created[0].closed is True
        assert created[1].closed is False
    finally:
        manager.close()


def test_failed_client_requires_explicit_reconnect_and_disabled_server_cannot_connect() -> None:
    failed = McpClient(
        FakeTransport({"initialize": [_initialize_result()], "ping": [McpTransportError("disconnected")]})
    )
    failed.connect()
    with pytest.raises(McpTransportError):
        failed.ping()
    assert failed.state is McpClientState.FAILED
    with pytest.raises(McpLifecycleError):
        failed.ping()

    manager = McpConnectionManager(transport_factory=lambda *_args: FakeTransport({"initialize": [_initialize_result()]}))
    key = McpConnectionKey("session_ONE0001", "agent_AGENT0001", "mcp_LOCAL00001")
    disabled = LocalMcpServerConfig(id="mcp_LOCAL00001", name="Local", command="python", enabled=False)
    try:
        with pytest.raises(McpServerDisabledError):
            manager.connect(key, disabled)
    finally:
        manager.close()


def test_connection_manager_closing_during_connect_releases_new_transport() -> None:
    initialize_started = Event()
    allow_initialize_to_finish = Event()
    transports: list[FakeTransport] = []

    class BlockingTransport(FakeTransport):
        def request(self, method, params=None, *, timeout_ms=None, cancel_event=None):
            if method == "initialize":
                initialize_started.set()
                assert allow_initialize_to_finish.wait(1)
            return super().request(method, params, timeout_ms=timeout_ms, cancel_event=cancel_event)

    def factory(_config, _notification_handler):
        transport = BlockingTransport({"initialize": [_initialize_result()]})
        transports.append(transport)
        return transport

    manager = McpConnectionManager(transport_factory=factory)
    key = McpConnectionKey("session_ONE0001", "agent_AGENT0001", "mcp_LOCAL00001")
    errors: list[Exception] = []

    def connect():
        try:
            manager.connect(key, LocalMcpServerConfig(id=key.server_id, name="Local", command="python"))
        except Exception as error:
            errors.append(error)

    thread = Thread(target=connect)
    thread.start()
    assert initialize_started.wait(1)
    manager.close()
    allow_initialize_to_finish.set()
    thread.join(1)

    assert not thread.is_alive()
    assert errors
    assert transports[0].closed is True


def test_remote_json_rpc_error_does_not_mark_healthy_connection_as_failed() -> None:
    client = McpClient(
        FakeTransport(
            {
                "initialize": [_initialize_result()],
                "ping": [
                    JsonRpcResponse(
                        id=2,
                        error=JsonRpcError(-32601, "missing"),
                    )
                ],
            }
        )
    )
    client.connect()
    with pytest.raises(McpRemoteError):
        client.ping()
    assert client.state is McpClientState.READY


def test_client_shutdown_requests_server_and_releases_transport() -> None:
    transport = FakeTransport({"initialize": [_initialize_result()], "shutdown": [{}]})
    client = McpClient(transport)
    client.connect()

    client.shutdown()

    assert transport.calls[-1][0] == "shutdown"
    assert client.state is McpClientState.CLOSED
    assert transport.closed is True
