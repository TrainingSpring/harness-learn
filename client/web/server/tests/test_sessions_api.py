"""固定角色 1v1 会话 API 的集成测试。"""

from runtime.context_service import ContextService
from storage.database import StateDatabase
from storage.repositories.context_item import ContextItemRepository


def _create_session(client, title: str = "实现 Web 客户端") -> dict:
    """通过公开接口创建测试使用的 DIRECT 会话。"""
    response = client.post(
        "/api/sessions",
        json={
            "mode": "DIRECT",
            "agentId": "agent_ENABLED001",
            "title": title,
        },
    )
    assert response.status_code == 201
    return response.json()


def test_create_direct_session_binds_selected_agent(client) -> None:
    """创建接口应返回固定角色信息，且不产生临时 participant 身份。"""
    payload = _create_session(client)

    assert payload["conversationMode"] == "DIRECT"
    assert payload["agent"] == {"id": "agent_ENABLED001", "name": "工程师"}
    assert payload["status"] == "ACTIVE"
    assert payload["lastMessage"] is None
    assert "participantId" not in payload


def test_create_session_rejects_non_direct_mode(client) -> None:
    """首期 Web API 不开放 GROUP 会话创建。"""
    response = client.post(
        "/api/sessions",
        json={"mode": "GROUP", "agentId": "agent_ENABLED001"},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_create_session_rejects_disabled_agent_without_empty_session(client) -> None:
    """禁用 Agent 不可选择，失败请求也不能留下空会话。"""
    response = client.post(
        "/api/sessions",
        json={"mode": "DIRECT", "agentId": "agent_DISABLED01"},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "AGENT_NOT_SELECTABLE"
    assert client.get("/api/sessions").json()["items"] == []


def test_list_and_get_direct_session(client) -> None:
    """历史和详情接口应复用只读聚合，返回一致的 Agent 信息。"""
    created = _create_session(client, "查询会话")

    listing = client.get("/api/sessions?limit=30&offset=0")
    detail = client.get(f"/api/sessions/{created['id']}")

    assert listing.status_code == 200
    assert listing.json()["items"][0]["id"] == created["id"]
    assert listing.json()["pagination"]["hasMore"] is False
    assert detail.status_code == 200
    assert detail.json()["id"] == created["id"]
    assert detail.json()["messages"] == []


def test_messages_returns_business_context_in_sequence_order(client) -> None:
    """消息接口返回 ContextItem DTO，并支持 sequence 增量读取。"""
    created = _create_session(client)
    # 使用独立连接预置上下文，避免测试线程直接操作应用线程持有的连接。
    database = StateDatabase(str(client.app.state.services.database.workspace))
    database.initialize()
    try:
        context = ContextService(ContextItemRepository(database), created["id"])
        context.append_user_message("第一条")
        context.append_user_message("第二条")
    finally:
        database.close()

    response = client.get(
        f"/api/sessions/{created['id']}/messages?afterSequence=1"
    )

    assert response.status_code == 200
    assert [item["payload"]["text"] for item in response.json()["items"]] == [
        "第二条"
    ]
    item = response.json()["items"][0]
    assert item["kind"] == "USER_MESSAGE"
    assert item["sequenceNo"] == 2
    assert "type" not in item


def test_unknown_session_returns_stable_error(client) -> None:
    """详情和消息接口对不存在会话使用同一错误码。"""
    session_id = "session_UNKNOWN000"

    detail = client.get(f"/api/sessions/{session_id}")
    messages = client.get(f"/api/sessions/{session_id}/messages")

    assert detail.status_code == messages.status_code == 404
    assert detail.json()["error"]["code"] == "SESSION_NOT_FOUND"
    assert messages.json()["error"]["code"] == "SESSION_NOT_FOUND"
