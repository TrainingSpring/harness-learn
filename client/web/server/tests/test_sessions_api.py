"""固定角色 1v1 会话 API 的集成测试。"""

from storage.context_service import ContextService
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
    assert payload["permissionMode"] == "plan"
    assert payload["workspacePath"] is None
    assert payload["isWorkspaceLocked"] is False


def test_session_settings_are_session_scoped_and_workspace_is_relative(client) -> None:
    """权限模式与工作目录应写入 Session，并支持本机绝对路径。"""
    project = client.app.state.services.database.workspace / "demo"
    project.mkdir()
    created = client.post(
        "/api/sessions",
        json={"mode": "DIRECT", "agentId": "agent_ENABLED001", "permissionMode": "build"},
    ).json()

    mode = client.patch(
        f"/api/sessions/{created['id']}/permission-mode",
        json={"permissionMode": "yolo"},
    )
    project_response = client.patch(
        f"/api/sessions/{created['id']}/workspace",
        json={"workspacePath": "demo"},
    )

    assert mode.status_code == project_response.status_code == 200
    assert mode.json()["permissionMode"] == "yolo"
    assert project_response.json()["workspacePath"] == str(project)
    assert project_response.json()["isWorkspaceLocked"] is False
    listing = client.get("/api/sessions/projects?path=.").json()
    assert listing["directories"] == [{"path": str(project), "name": "demo"}]
    assert listing["parentPath"] is not None
    rejected = client.patch(
        f"/api/sessions/{created['id']}/workspace",
        json={"workspacePath": "../outside"},
    )
    assert rejected.status_code == 422
    assert rejected.json()["error"]["code"] == "INVALID_PROJECT_PATH"


def test_project_directory_list_excludes_symlinks_outside_workspace(client, tmp_path) -> None:
    """项目目录浏览跳过软链接，但允许选择 workspace 外的真实目录。"""
    workspace = client.app.state.services.database.workspace
    external_directory = tmp_path.parent / "external-project"
    external_directory.mkdir()
    (workspace / "inside").mkdir()
    (workspace / "outside-link").symlink_to(external_directory, target_is_directory=True)

    response = client.get("/api/sessions/projects?path=.")

    assert response.status_code == 200
    assert response.json()["directories"] == [{"path": str(workspace / "inside"), "name": "inside"}]

    external_response = client.get(f"/api/sessions/projects?path={external_directory}")
    assert external_response.status_code == 200
    assert external_response.json()["path"] == str(external_directory)

    created = _create_session(client)
    rejected = client.patch(
        f"/api/sessions/{created['id']}/workspace",
        json={"workspacePath": str(workspace / "outside-link")},
    )
    assert rejected.status_code == 422
    assert rejected.json()["error"]["code"] == "INVALID_PROJECT_PATH"


def test_workspace_root_has_no_parent(client) -> None:
    """文件系统根目录没有上级目录，供跨平台选择器停止返回。"""
    response = client.get("/api/sessions/projects", params={"path": "/"})

    assert response.status_code == 200
    assert response.json()["parentPath"] is None


def test_external_workspace_directory_can_be_selected(client, tmp_path) -> None:
    """本地 Web 客户端可以选择服务主机上的任意真实工作目录。"""
    external_directory = tmp_path.parent / "external-project-selection"
    external_directory.mkdir()
    created = _create_session(client)

    response = client.patch(
        f"/api/sessions/{created['id']}/workspace",
        json={"workspacePath": str(external_directory)},
    )

    assert response.status_code == 200
    assert response.json()["workspacePath"] == str(external_directory)


def test_active_run_rejects_session_setting_changes(client) -> None:
    """运行中的 Session 不允许在同一执行过程中改变权限边界。"""
    created = _create_session(client)
    registry = client.app.state.services.run_registry
    active = registry.create(created["id"], object())
    try:
        mode = client.patch(
            f"/api/sessions/{created['id']}/permission-mode",
            json={"permissionMode": "yolo"},
        )
        project = client.patch(
            f"/api/sessions/{created['id']}/workspace",
            json={"workspacePath": None},
        )
    finally:
        registry.remove(active.run_id)

    assert mode.status_code == project.status_code == 409
    assert mode.json()["error"]["code"] == "RUN_ALREADY_ACTIVE"
    assert project.json()["error"]["code"] == "RUN_ALREADY_ACTIVE"


def test_project_is_locked_after_first_user_message(client) -> None:
    """首条用户消息后，项目修改必须返回稳定冲突错误。"""
    created = _create_session(client)
    database = StateDatabase(str(client.app.state.services.database.workspace))
    database.initialize()
    try:
        ContextService(ContextItemRepository(database), created["id"]).append_user_message("锁定项目")
    finally:
        database.close()

    detail = client.get(f"/api/sessions/{created['id']}")
    response = client.patch(
        f"/api/sessions/{created['id']}/workspace",
        json={"workspacePath": None},
    )
    assert detail.json()["isWorkspaceLocked"] is True
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "PROJECT_LOCKED"


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
