from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "code" / "agent"))

from mcp.config_store import McpConfigStore
from mcp.errors import McpServerDisabledError, McpServerNotFoundError
from mcp.registry import McpServerRegistry
from mcp.types import LocalMcpServerConfig, RemoteMcpServerConfig


def test_registry_lists_and_gets_current_servers(tmp_path: Path) -> None:
    store = McpConfigStore(tmp_path / "config.json")
    store.save(
        store.empty_document(
            (
                LocalMcpServerConfig(
                    id="mcp_LOCAL00001",
                    name="Local",
                    command="node",
                ),
                RemoteMcpServerConfig(
                    id="mcp_REMOTE0001",
                    name="Remote",
                    url="https://example.com/mcp",
                ),
            )
        )
    )
    registry = McpServerRegistry(store)

    assert [server.id for server in registry.list()] == [
        "mcp_LOCAL00001",
        "mcp_REMOTE0001",
    ]
    assert registry.get("mcp_REMOTE0001").url == "https://example.com/mcp"


def test_registry_distinguishes_missing_and_disabled_servers(tmp_path: Path) -> None:
    store = McpConfigStore(tmp_path / "config.json")
    store.create(
        LocalMcpServerConfig(
            id="mcp_DISABLE001",
            name="Disabled",
            command="node",
            enabled=False,
        )
    )
    registry = McpServerRegistry(store)

    with pytest.raises(McpServerDisabledError):
        registry.require_enabled("mcp_DISABLE001")
    with pytest.raises(McpServerNotFoundError):
        registry.get("mcp_MISSING001")


def test_registry_validates_agent_server_references(tmp_path: Path) -> None:
    store = McpConfigStore(tmp_path / "config.json")
    store.create(
        LocalMcpServerConfig(
            id="mcp_LOCAL00001",
            name="Local",
            command="node",
        )
    )
    registry = McpServerRegistry(store)

    with pytest.raises(McpServerNotFoundError):
        registry.validate_ids(["mcp_LOCAL00001", "mcp_MISSING001"])

    assert registry.validate_ids(["mcp_LOCAL00001", "mcp_LOCAL00001"]) == [
        "mcp_LOCAL00001"
    ]
