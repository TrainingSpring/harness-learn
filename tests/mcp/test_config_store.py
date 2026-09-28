import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "code" / "agent"))

from mcp.config_store import McpConfigStore
from mcp.errors import (
    McpConfigConflictError,
    McpConfigFormatError,
    McpServerNotFoundError,
)
from mcp.types import LocalMcpServerConfig, RemoteMcpServerConfig


def local_server(server_id: str = "mcp_LOCAL00001") -> LocalMcpServerConfig:
    return LocalMcpServerConfig(
        id=server_id,
        name="Local Files",
        command="node",
        args=["server.js"],
        cwd="/tmp/project",
    )


def remote_server(server_id: str = "mcp_REMOTE0001") -> RemoteMcpServerConfig:
    return RemoteMcpServerConfig(
        id=server_id,
        name="Remote Tools",
        url="https://example.com/mcp",
    )


def test_store_creates_empty_document_and_parent_directory(tmp_path: Path) -> None:
    config_path = tmp_path / "mcp" / "config.json"

    snapshot = McpConfigStore(config_path).read()

    assert config_path.exists()
    assert snapshot.document.version == 1
    assert snapshot.document.servers == ()
    assert snapshot.revision


def test_store_accepts_human_readable_stable_server_id(tmp_path: Path) -> None:
    store = McpConfigStore(tmp_path / "config.json")

    snapshot = store.create(
        LocalMcpServerConfig(
            id="mcp_filesystem",
            name="Filesystem",
            command="npx",
        )
    )

    assert snapshot.document.servers[0].id == "mcp_filesystem"


def test_store_round_trips_local_and_remote_discriminated_configs(tmp_path: Path) -> None:
    store = McpConfigStore(tmp_path / "config.json")
    snapshot = store.save(store.empty_document((local_server(), remote_server())))

    reloaded = store.read()

    assert reloaded.document == snapshot.document
    assert reloaded.document.servers[0].is_local is True
    assert reloaded.document.servers[1].is_local is False
    assert json.loads((tmp_path / "config.json").read_text()) == {
        "version": 1,
        "servers": [
            {
                "id": "mcp_LOCAL00001",
                "name": "Local Files",
                "description": "",
                "is_local": True,
                "transport": "stdio",
                "command": "node",
                "args": ["server.js"],
                "cwd": "/tmp/project",
                "env": {},
                "enabled": True,
                "startup_timeout_ms": 10000,
                "shutdown_timeout_ms": 5000,
            },
            {
                "id": "mcp_REMOTE0001",
                "name": "Remote Tools",
                "description": "",
                "is_local": False,
                "transport": "streamable_http",
                "url": "https://example.com/mcp",
                "headers": {},
                "auth_mode": "none",
                "enabled": True,
                "request_timeout_ms": 30000,
            },
        ],
    }


def test_store_rejects_external_changes_when_revision_is_stale(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    store = McpConfigStore(config_path)
    original = store.read()
    config_path.write_text(
        json.dumps({"version": 1, "servers": []}),
        encoding="utf-8",
    )

    with pytest.raises(McpConfigConflictError):
        store.save(store.empty_document((local_server(),)), expected_revision=original.revision)


def test_store_rejects_invalid_variant_fields_without_destroying_existing_file(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "version": 1,
                "servers": [
                    {
                        "id": "mcp_BAD0000001",
                        "name": "Invalid",
                        "is_local": True,
                        "transport": "streamable_http",
                        "url": "https://example.com/mcp",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(McpConfigFormatError):
        McpConfigStore(config_path).read()

    assert config_path.read_text(encoding="utf-8").endswith("\n") is False


def test_store_update_and_delete_are_keyed_by_stable_server_id(tmp_path: Path) -> None:
    store = McpConfigStore(tmp_path / "config.json")
    created = store.create(local_server())
    updated = store.update(
        RemoteMcpServerConfig(
            id="mcp_LOCAL00001",
            name="Remote Replacement",
            url="https://example.com/other-mcp",
        ),
        expected_revision=created.revision,
    )

    assert updated.document.servers[0].id == "mcp_LOCAL00001"
    assert updated.document.servers[0].is_local is False
    deleted = store.delete("mcp_LOCAL00001", expected_revision=updated.revision)
    assert deleted.document.servers == ()

    with pytest.raises(McpServerNotFoundError):
        store.delete("mcp_LOCAL00001", expected_revision=deleted.revision)
