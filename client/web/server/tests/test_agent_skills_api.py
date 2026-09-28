from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from mcp.config_store import McpConfigStore
from mcp.registry import McpServerRegistry
from mcp.types import LocalMcpServerConfig


def _import_skill(client):
    stream = BytesIO()
    with ZipFile(stream, "w", ZIP_DEFLATED) as archive:
        archive.writestr("review/SKILL.md", "---\nname: review\ndescription: Review code\n---\nUse review.\n")
    stream.seek(0)
    response = client.post("/api/settings/skills/import", files={"file": ("review.zip", stream, "application/zip")})
    assert response.status_code == 200
    return response.json()["items"][0]["id"]


def test_create_agent_persists_available_skill_ids(client):
    skill_id = _import_skill(client)
    response = client.post("/api/agents", json={"name": "带技能角色", "description": "review", "personality": "", "expertise": [], "llmProfileId": "llm_TESTLLM001", "tools": [], "skillIds": [skill_id], "isEnabled": True})
    assert response.status_code == 201
    assert response.json()["skills"] == [skill_id]


def test_create_agent_rejects_unknown_skill(client):
    response = client.post("/api/agents", json={"name": "错误角色", "description": "bad", "personality": "", "expertise": [], "llmProfileId": "llm_TESTLLM001", "tools": [], "skillIds": ["skill_UNKNOWN01"], "isEnabled": True})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_SKILL"


def test_update_agent_persists_role_and_skill_configuration(client):
    skill_id = _import_skill(client)
    created = client.post("/api/agents", json={"name": "旧角色", "description": "old", "personality": "", "expertise": [], "llmProfileId": "llm_TESTLLM001", "tools": [], "skillIds": [], "isEnabled": True}).json()
    response = client.patch(f"/api/agents/{created['id']}", json={"name": "新角色", "description": "updated", "personality": "严谨", "expertise": ["review"], "llmProfileId": "llm_TESTLLM001", "tools": ["read"], "skillIds": [skill_id], "isEnabled": True})
    assert response.status_code == 200
    assert response.json()["name"] == "新角色"
    assert response.json()["skills"] == [skill_id]


def test_create_agent_persists_registered_mcp_server_ids(client, tmp_path: Path):
    """Agent 只保存已注册 MCP Server 的稳定 ID，不复制其服务配置。"""
    store = McpConfigStore(tmp_path / "mcp" / "config.json")
    store.create(
        LocalMcpServerConfig(
            id="mcp_SERVER0001",
            name="Test MCP",
            command="python",
        )
    )
    client.app.state.services.mcp_servers = McpServerRegistry(store)

    response = client.post(
        "/api/agents",
        json={
            "name": "带 MCP 的角色",
            "description": "mcp",
            "personality": "",
            "expertise": [],
            "llmProfileId": "llm_TESTLLM001",
            "tools": [],
            "skillIds": [],
            "mcpServerIds": ["mcp_SERVER0001", "mcp_SERVER0001"],
            "isEnabled": True,
        },
    )

    assert response.status_code == 201
    assert response.json()["mcpServerIds"] == ["mcp_SERVER0001"]


def test_create_agent_rejects_unknown_mcp_server(client, tmp_path: Path):
    client.app.state.services.mcp_servers = McpServerRegistry(
        McpConfigStore(tmp_path / "mcp" / "config.json")
    )
    response = client.post(
        "/api/agents",
        json={
            "name": "错误 MCP 角色",
            "description": "mcp",
            "personality": "",
            "expertise": [],
            "llmProfileId": "llm_TESTLLM001",
            "tools": [],
            "skillIds": [],
            "mcpServerIds": ["mcp_MISSING001"],
            "isEnabled": True,
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_MCP_SERVER"
