"""本地 MCP 服务生命周期管理测试。"""

from __future__ import annotations

from pathlib import Path
import sys
import time

import pytest

from mcp.config_store import McpConfigStore
from mcp.errors import McpLocalServerError, McpRemoteLifecycleError
from mcp.process_manager import McpLocalServerState, McpProcessManager
from mcp.registry import McpServerRegistry
from mcp.types import LocalMcpServerConfig, RemoteMcpServerConfig


_WAITING_SERVER = "import sys\nfor _ in sys.stdin: pass\n"


def _registry(tmp_path: Path, *, command: str | None = None) -> McpServerRegistry:
    script = tmp_path / "server.py"
    script.write_text(command or _WAITING_SERVER, encoding="utf-8")
    store = McpConfigStore(tmp_path / "mcp" / "config.json")
    store.save(
        store.empty_document(
            (
                LocalMcpServerConfig(
                    id="mcp_LOCAL00001",
                    name="Local",
                    command=sys.executable,
                    args=[str(script)],
                    startup_timeout_ms=1_000,
                    shutdown_timeout_ms=100,
                ),
                RemoteMcpServerConfig(
                    id="mcp_REMOTE0001",
                    name="Remote",
                    url="https://example.test/mcp",
                ),
            )
        )
    )
    return McpServerRegistry(store)


def test_manager_starts_stops_and_restarts_one_local_server(tmp_path: Path) -> None:
    manager = McpProcessManager(_registry(tmp_path), startup_probe_ms=20)
    events = []
    manager.subscribe(events.append)
    try:
        started = manager.start("mcp_LOCAL00001")
        assert started.state is McpLocalServerState.RUNNING
        assert started.pid is not None
        assert manager.start("mcp_LOCAL00001") == started

        stopped = manager.stop("mcp_LOCAL00001")
        assert stopped.state is McpLocalServerState.STOPPED
        assert stopped.ended_at is not None

        restarted = manager.restart("mcp_LOCAL00001")
        assert restarted.state is McpLocalServerState.RUNNING
        assert len(events) >= 4
    finally:
        manager.close()


def test_manager_marks_unexpected_process_exit_as_failed(tmp_path: Path) -> None:
    manager = McpProcessManager(
        _registry(tmp_path, command="import sys\nsys.exit(3)\n"),
        startup_probe_ms=20,
    )
    try:
        manager.start("mcp_LOCAL00001")
        deadline = time.monotonic() + 1
        status = manager.status("mcp_LOCAL00001")
        while status.state is McpLocalServerState.RUNNING and time.monotonic() < deadline:
            time.sleep(0.01)
            status = manager.status("mcp_LOCAL00001")
        assert status.state is McpLocalServerState.FAILED
        assert status.exit_code == 3
        assert status.diagnostic_code == "MCP_CONNECTION_CLOSED"
    finally:
        manager.close()


def test_manager_rejects_remote_lifecycle_and_missing_local_instances(tmp_path: Path) -> None:
    manager = McpProcessManager(_registry(tmp_path))
    try:
        with pytest.raises(McpRemoteLifecycleError):
            manager.start("mcp_REMOTE0001")
        with pytest.raises(McpLocalServerError, match="未运行"):
            manager.stop("mcp_LOCAL00001")
    finally:
        manager.close()
