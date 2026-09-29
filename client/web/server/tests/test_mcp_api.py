"""MCP 设置 API 的配置、生命周期和安全边界测试。"""

from pathlib import Path

from mcp.config_store import McpConfigStore
from mcp.registry import McpServerRegistry
from mcp.types import LocalMcpServerConfig, RemoteMcpServerConfig


def _install_store(client, tmp_path: Path) -> McpConfigStore:
    store = McpConfigStore(tmp_path / "mcp" / "config.json")
    client.app.state.services.mcp_config_store = store
    client.app.state.services.mcp_servers = McpServerRegistry(store)
    return store


def test_mcp_api_creates_lists_updates_and_rejects_remote_lifecycle(client, tmp_path: Path):
    store = _install_store(client, tmp_path)
    created = client.post("/api/settings/mcp", json={
        "name": "远程搜索",
        "description": "搜索服务",
        "isLocal": False,
        "url": "https://mcp.example.test/server",
        "authMode": "oauth",
    })
    assert created.status_code == 201
    server_id = created.json()["id"]
    assert created.json()["status"] == "remote"

    listed = client.get("/api/settings/mcp")
    assert listed.status_code == 200
    assert listed.json()["items"][0]["authMode"] == "oauth"
    revision = listed.json()["revision"]

    updated = client.put(f"/api/settings/mcp/{server_id}", json={
        "name": "远程搜索 v2",
        "description": "更新",
        "isLocal": False,
        "url": "https://mcp.example.test/server",
        "authMode": "none",
        "revision": revision,
    })
    assert updated.status_code == 200
    assert updated.json()["name"] == "远程搜索 v2"

    refused = client.post(f"/api/settings/mcp/{server_id}/start")
    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "MCP_REMOTE_LIFECYCLE_UNSUPPORTED"

    assert store.read().document.servers[0].name == "远程搜索 v2"


def test_mcp_api_rejects_stale_revision_and_does_not_expose_secrets(client, tmp_path: Path):
    store = _install_store(client, tmp_path)
    server = RemoteMcpServerConfig(
        id="mcp_REMOTE0001",
        name="远程",
        url="https://mcp.example.test/server",
        headers={"Authorization": "Bearer secret"},
    )
    store.create(server)
    response = client.put("/api/settings/mcp/mcp_REMOTE0001", json={
        "name": "冲突",
        "isLocal": False,
        "url": "https://mcp.example.test/server",
        "revision": "stale",
    })
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "MCP_CONFIG_CONFLICT"

    listed = client.get("/api/settings/mcp")
    assert "Bearer secret" not in listed.text
    assert listed.json()["items"][0]["headers"] == {"Authorization": "[REDACTED]"}


def test_mcp_api_validates_local_configuration(client, tmp_path: Path):
    _install_store(client, tmp_path)
    response = client.post("/api/settings/mcp", json={
        "name": "缺少命令",
        "isLocal": True,
    })
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "MCP_CONFIG_INVALID"


def test_mcp_api_uses_directory_for_local_service_and_reads_metadata(client, tmp_path: Path):
    _install_store(client, tmp_path)
    service_directory = tmp_path / "demo-mcp"
    service_directory.mkdir()
    (service_directory / "package.json").write_text(
        '{"description":"本地工具服务"}', encoding="utf-8"
    )

    metadata = client.get(
        "/api/settings/mcp/directory-metadata",
        params={"path": str(service_directory)},
    )
    assert metadata.status_code == 200
    assert metadata.json() == {
        "path": str(service_directory.resolve()),
        "name": "demo-mcp",
        "description": "本地工具服务",
    }
    directories = client.get("/api/settings/mcp/directories", params={"path": str(tmp_path)})
    assert directories.status_code == 200
    assert any(item["name"] == "demo-mcp" for item in directories.json()["directories"])

    created = client.post("/api/settings/mcp", json={
        "name": "本地工具",
        "isLocal": True,
        "command": "python",
        "directory": str(service_directory),
    })
    assert created.status_code == 201
    assert created.json()["directory"] == str(service_directory)
    assert "cwd" not in created.json()


def test_mcp_api_rejects_missing_local_service_directory(client, tmp_path: Path):
    _install_store(client, tmp_path)
    response = client.post("/api/settings/mcp", json={
        "name": "本地工具",
        "isLocal": True,
        "command": "python",
        "directory": str(tmp_path / "missing"),
    })
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_MCP_DIRECTORY"
