"""stdio 与 Streamable HTTP Transport 的行为测试。"""

from __future__ import annotations

import json
from pathlib import Path
import sys
import threading
import time

import httpx
import pytest

from mcp.errors import (
    McpProtocolError,
    McpRequestCancelledError,
    McpSessionExpiredError,
    McpTransportTimeoutError,
)
from mcp.http_transport import StreamableHttpTransport
from mcp.protocol import JsonRpcRequest, JsonRpcResponse
from mcp.stdio_transport import StdioMcpTransport
from mcp.types import LocalMcpServerConfig, RemoteMcpServerConfig


_SERVER_SCRIPT = r'''
import json
import sys
import time

for line in sys.stdin:
    message = json.loads(line)
    if message.get("method") == "notifications/cancelled":
        continue
    if "id" not in message:
        continue
    if message.get("method") == "slow":
        time.sleep(0.3)
    if message.get("method") == "notify":
        sys.stdout.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/progress", "params": {"step": 1}}) + "\n")
        sys.stdout.flush()
    sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": message["id"], "result": message.get("params", {})}) + "\n")
    sys.stdout.flush()
'''


def _local_config(tmp_path: Path) -> LocalMcpServerConfig:
    script = tmp_path / "server.py"
    script.write_text(_SERVER_SCRIPT, encoding="utf-8")
    return LocalMcpServerConfig(
        id="mcp_SERVER0001",
        name="Test",
        command=sys.executable,
        args=[str(script)],
        directory=str(tmp_path),
        startup_timeout_ms=1_000,
        shutdown_timeout_ms=1_000,
    )


def test_stdio_transport_correlates_concurrent_responses_and_notifications(tmp_path: Path) -> None:
    notifications = []
    transport = StdioMcpTransport(_local_config(tmp_path), on_notification=notifications.append)
    try:
        first: list[JsonRpcResponse] = []
        thread = threading.Thread(target=lambda: first.append(transport.request("echo", {"value": 1})))
        thread.start()
        second = transport.request("echo", {"value": 2})
        thread.join()

        assert first[0].unwrap() == {"value": 1}
        assert second.unwrap() == {"value": 2}
        transport.request("notify")
        assert notifications[0].method == "notifications/progress"
    finally:
        transport.close()


def test_stdio_transport_times_out_and_honors_cancellation(tmp_path: Path) -> None:
    transport = StdioMcpTransport(_local_config(tmp_path))
    try:
        with pytest.raises(McpTransportTimeoutError):
            transport.request("slow", timeout_ms=20)

        cancelled = threading.Event()
        cancelled.set()
        with pytest.raises(McpRequestCancelledError):
            transport.request("echo", {"value": 1}, cancel_event=cancelled)
    finally:
        transport.close()


def test_streamable_http_tracks_session_and_parses_sse() -> None:
    seen_headers: list[dict[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_headers.append(dict(request.headers))
        call = json.loads(request.content)
        return httpx.Response(
            200,
            headers={"mcp-session-id": "session-1", "content-type": "text/event-stream"},
            content=f"event: message\ndata: {json.dumps({'jsonrpc': '2.0', 'id': call['id'], 'result': {'ok': True}})}\n\n",
        )

    transport = StreamableHttpTransport(
        RemoteMcpServerConfig(id="mcp_REMOTE0001", name="Remote", url="https://example.test/mcp"),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    try:
        assert transport.request("tools/list").unwrap() == {"ok": True}
        assert transport.request("tools/list").unwrap() == {"ok": True}
        assert "mcp-session-id" not in seen_headers[0]
        assert seen_headers[1]["mcp-session-id"] == "session-1"
    finally:
        transport.close()


def test_streamable_http_dispatches_sse_notifications_before_response() -> None:
    notifications = []

    def handler(request: httpx.Request) -> httpx.Response:
        call = json.loads(request.content)
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=(
                "data: {\"jsonrpc\":\"2.0\",\"method\":\"notifications/tools/list_changed\"}\n\n"
                f"data: {json.dumps({'jsonrpc': '2.0', 'id': call['id'], 'result': {'ok': True}})}\n\n"
            ),
        )

    transport = StreamableHttpTransport(
        RemoteMcpServerConfig(id="mcp_REMOTE0001", name="Remote", url="https://example.test/mcp"),
        on_notification=notifications.append,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    try:
        assert transport.request("tools/list").unwrap() == {"ok": True}
        assert [event.method for event in notifications] == ["notifications/tools/list_changed"]
    finally:
        transport.close()


def test_streamable_http_returns_server_request_response_and_injects_token() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        call = json.loads(request.content)
        if "method" not in call:
            return httpx.Response(202)
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=(
                "data: {\"jsonrpc\":\"2.0\",\"id\":99,\"method\":\"roots/list\"}\n\n"
                f"data: {json.dumps({'jsonrpc': '2.0', 'id': call['id'], 'result': {'ok': True}})}\n\n"
            ),
        )

    transport = StreamableHttpTransport(
        RemoteMcpServerConfig(id="mcp_REMOTE0001", name="Remote", url="https://example.test/mcp"),
        access_token_provider=lambda: "access-token",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    transport.set_request_handler(lambda request: JsonRpcResponse(request.id, {"roots": []}))
    try:
        assert transport.request("tools/list").unwrap() == {"ok": True}
        assert requests[0].headers["authorization"] == "Bearer access-token"
        assert len(requests) == 2
        assert json.loads(requests[1].content)["id"] == 99
    finally:
        transport.close()


def test_transports_reject_malformed_or_incomplete_server_responses(tmp_path: Path) -> None:
    script = tmp_path / "bad_server.py"
    script.write_text("import sys\nsys.stdin.readline()\nprint('not-json', flush=True)\n", encoding="utf-8")
    stdio = StdioMcpTransport(
        LocalMcpServerConfig(id="mcp_SERVER0001", name="Bad", command=sys.executable, args=[str(script)])
    )
    try:
        with pytest.raises(McpProtocolError, match="MCP"):
            stdio.request("tools/list", timeout_ms=1_000)
    finally:
        stdio.close()

    http = StreamableHttpTransport(
        RemoteMcpServerConfig(id="mcp_REMOTE0001", name="Remote", url="https://example.test/mcp"),
        client=httpx.Client(
            transport=httpx.MockTransport(
                lambda _request: httpx.Response(200, headers={"content-type": "text/event-stream"}, content="data: {}\n\n")
            )
        ),
    )
    try:
        with pytest.raises(McpProtocolError, match="JSON-RPC"):
            http.request("tools/list")
    finally:
        http.close()


def test_streamable_http_clears_expired_session_on_404() -> None:
    transport = StreamableHttpTransport(
        RemoteMcpServerConfig(id="mcp_REMOTE0001", name="Remote", url="https://example.test/mcp"),
        client=httpx.Client(transport=httpx.MockTransport(lambda _request: httpx.Response(404))),
    )
    transport._session_id = "stale"  # 验证来自 Server 的失效响应一定清理状态。
    try:
        with pytest.raises(McpSessionExpiredError):
            transport.request("tools/list")
        assert transport.session_id is None
    finally:
        transport.close()
