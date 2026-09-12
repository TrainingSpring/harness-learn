"""Agent 发现 API 契约测试。"""


def test_list_agents_returns_only_enabled_profiles(client) -> None:
    """角色列表只公开可用于新会话的 Agent。"""
    response = client.get("/api/agents?limit=20&offset=0")

    assert response.status_code == 200
    payload = response.json()
    assert [item["id"] for item in payload["items"]] == ["agent_ENABLED001"]
    assert payload["items"][0] == {
        "id": "agent_ENABLED001",
        "name": "工程师",
        "description": "负责实现和审查代码",
        "personality": "直接、严谨",
        "expertise": ["Python", "API"],
        "tools": ["read", "bash"],
        "isEnabled": True,
    }
    assert payload["pagination"] == {"limit": 20, "offset": 0, "hasMore": False}


def test_list_agents_filters_by_expertise(client) -> None:
    """expertise 使用精确标签筛选。"""
    response = client.get("/api/agents?expertise=Python")

    assert response.status_code == 200
    assert len(response.json()["items"]) == 1


def test_get_agent_includes_runtime_configuration(client) -> None:
    """详情公开 LLM 引用和权限模式，但不公开任何凭据。"""
    response = client.get("/api/agents/agent_ENABLED001")

    assert response.status_code == 200
    payload = response.json()
    assert payload["llmProfileId"] == "llm_TESTLLM001"
    assert payload["permissionMode"] == "BUILD"
    assert "credentialRef" not in payload


def test_get_unknown_agent_returns_stable_not_found(client) -> None:
    """不存在角色应返回稳定错误码，而不是底层校验文本。"""
    response = client.get("/api/agents/agent_UNKNOWN000")

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "AGENT_NOT_FOUND",
            "message": "Agent 不存在",
            "details": None,
        }
    }


def test_create_agent_generates_id_and_persists_configuration(client) -> None:
    """创建角色时由服务端生成稳定 ID，并返回完整的角色详情。"""
    response = client.post(
        "/api/agents",
        json={
            "name": "文档助手",
            "description": "负责整理技术文档",
            "personality": "清晰、耐心",
            "expertise": ["Documentation"],
            "llmProfileId": "llm_TESTLLM001",
            "tools": ["read"],
            "permissionMode": "PLAN",
            "isEnabled": True,
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["id"].startswith("agent_")
    assert len(payload["id"]) == len("agent_XXXXXXXXXX")
    assert payload["name"] == "文档助手"
    assert payload["llmProfileId"] == "llm_TESTLLM001"
    assert payload["permissionMode"] == "PLAN"
    assert client.get(f"/api/agents/{payload['id']}").json() == payload


def test_create_agent_rejects_unknown_llm_profile(client) -> None:
    """角色不能引用不存在的 LLM 配置。"""
    response = client.post(
        "/api/agents",
        json={
            "name": "无效角色",
            "llmProfileId": "llm_UNKNOWN000",
            "tools": [],
            "permissionMode": "PLAN",
        },
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "LLM_PROFILE_NOT_FOUND"


def test_create_agent_rejects_unknown_tool(client) -> None:
    """角色只能配置工具目录中已注册的工具。"""
    response = client.post(
        "/api/agents",
        json={
            "name": "无效工具角色",
            "llmProfileId": "llm_TESTLLM001",
            "tools": ["not-a-tool"],
            "permissionMode": "PLAN",
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_TOOL"
