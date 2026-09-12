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
