"""流式 Run、权限暂停与恢复 API 测试。"""

import json

from head.types import LLMResponse
from permission.types import (
    PermissionAction,
    PermissionRequest,
    PermissionResponse,
    PermissionScope,
)
from storage.context_service import ContextService
from runtime.runtime_events import PermissionRequiredEvent
from storage.repositories.context_item import ContextItemRepository


def _events(response) -> list[dict]:
    """解析测试响应中的 SSE data 行。"""
    return [
        json.loads(line[6:])
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]


def _create_session(client) -> str:
    """创建运行测试使用的固定 DIRECT 会话。"""
    response = client.post(
        "/api/sessions",
        json={"mode": "DIRECT", "agentId": "agent_ENABLED001"},
    )
    assert response.status_code == 201
    return response.json()["id"]


class FakeStreamingExecution:
    """模拟已打开 Session 的正常消息运行。"""

    def __init__(self, context: ContextService) -> None:
        """保存测试会话的业务上下文服务。"""
        self.context = context

    def send(self, message: str):
        """依次产生文本增量和完成事件。"""
        self.context.append_user_message(message)
        yield LLMResponse(type="text", text="收到")
        self.context.append_agent_message("agent_ENABLED001", "收到")
        yield LLMResponse(type="done", data=[], is_stop=True)


class FakePermissionExecution:
    """模拟一次 read 权限暂停及确认后的 Session 恢复过程。"""

    call_id = "call_PERMISSION01"

    def __init__(self, context: ContextService) -> None:
        """保存上下文服务和待确认请求。"""
        self.context = context
        self.cancel_calls = 0
        self.request = PermissionRequest(
            action=PermissionAction.FILE_READ,
            resource="/workspace/README.md",
            tool_name="read",
            call_id=self.call_id,
            session_id=context.session_id,
        )

    def cancel(self) -> None:
        """记录 Web 取消已传递给原 SessionExecution。"""
        self.cancel_calls += 1

    def send(self, message: str):
        """持久化调用后发出权限请求并暂停。"""
        self.context.append_user_message(message)
        self.context.append_function_call(
            "agent_ENABLED001",
            call_id=self.call_id,
            name="read",
            arguments={"target_path": "README.md"},
        )
        yield PermissionRequiredEvent(type="permission_required", request=self.request)

    def resolve_permission(self, response: PermissionResponse):
        """记录工具结果并输出最终回复。"""
        assert response.call_id == self.call_id
        self.context.append_function_call_output(
            "agent_ENABLED001",
            call_id=self.call_id,
            output='{"ok":true}',
        )
        yield LLMResponse(type="text", text="文件已读取")
        self.context.append_agent_message("agent_ENABLED001", "文件已读取")
        yield LLMResponse(type="done", data=[], is_stop=True)


class FakeFailingExecution:
    """模拟包含敏感内部文本的运行异常。"""

    def __init__(self, context: ContextService) -> None:
        """保存上下文服务以满足 SessionExecution 的最小契约。"""
        self.context = context

    def send(self, message: str):
        """写入用户事件后抛出不应暴露给浏览器的异常。"""
        self.context.append_user_message(message)
        key_name = "api_key"
        key_value = "sk-" + "internal-secret"
        raise RuntimeError(f"sqlite /private/workspace {key_name}={key_value}")
        yield

    def cancel(self) -> None:
        """失败执行没有可取消的 pending 状态。"""


class FakeSessionService:
    """按测试场景恢复无需外部模型的 SessionExecution。"""

    def __init__(self, database, execution_type) -> None:
        """保存数据库和要实例化的 FakeSessionExecution 类型。"""
        self.database = database
        self.execution_type = execution_type
        self.loaded_session_ids: list[str] = []

    def load(self, session_id: str):
        """为指定会话恢复带持久化上下文的 FakeSessionExecution。"""
        self.loaded_session_ids.append(session_id)
        context = ContextService(ContextItemRepository(self.database), session_id)
        return self.execution_type(context)


def _use_fake_session_service(client, execution_type) -> FakeSessionService:
    """替换 ChatService 的 SessionExecution 恢复边界。"""
    services = client.app.state.services
    session_service = FakeSessionService(
        services.database,
        execution_type,
    )
    services.chat_service.session_service = session_service
    return session_service


def test_message_stream_emits_ordered_lifecycle_and_cleans_run(client) -> None:
    """正常消息流应包含增量、持久化完成消息和终止事件。"""
    session_id = _create_session(client)
    session_service = _use_fake_session_service(client, FakeStreamingExecution)

    response = client.post(
        f"/api/sessions/{session_id}/messages",
        json={"text": "你好"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = _events(response)
    assert [event["type"] for event in events] == [
        "run.started",
        "message.delta",
        "message.completed",
        "run.completed",
    ]
    assert events[1]["data"]["text"] == "收到"
    assert events[2]["data"]["text"] == "收到"
    assert session_service.loaded_session_ids == [session_id]
    assert client.app.state.services.run_registry.get_for_session(session_id) is None


def test_permission_stream_pauses_and_resumes_original_session_execution(client) -> None:
    """确认权限必须使用注册表中的原 SessionExecution，并延续同一 runId。"""
    session_id = _create_session(client)
    session_service = _use_fake_session_service(client, FakePermissionExecution)

    first = client.post(
        f"/api/sessions/{session_id}/messages",
        json={"text": "读取 README"},
    )
    first_events = _events(first)
    assert [event["type"] for event in first_events] == [
        "run.started",
        "tool.started",
        "permission.required",
    ]
    run_id = first_events[0]["runId"]
    active = client.app.state.services.run_registry.get(run_id)
    assert isinstance(active.execution, FakePermissionExecution)
    assert not hasattr(active, "agent")
    assert session_service.loaded_session_ids == [session_id]
    permission = first_events[-1]["data"]
    assert permission == {
        "callId": "call_PERMISSION01",
        "toolName": "read",
        "action": "filesystem.read",
        "resource": "/workspace/README.md",
        "allowedScopes": ["once", "session"],
    }

    resumed = client.post(
        f"/api/runs/{run_id}/permission",
        json={
            "callId": "call_PERMISSION01",
            "decision": "allow",
            "scope": "once",
        },
    )
    resumed_events = _events(resumed)

    assert all(event["runId"] == run_id for event in resumed_events)
    assert [event["type"] for event in resumed_events] == [
        "tool.completed",
        "message.delta",
        "message.completed",
        "run.completed",
    ]
    assert client.app.state.services.run_registry.get(run_id) is None


def test_invalid_permission_call_id_does_not_resume_tool(client) -> None:
    """浏览器伪造 callId 时应保持原运行暂停。"""
    session_id = _create_session(client)
    _use_fake_session_service(client, FakePermissionExecution)
    first = client.post(
        f"/api/sessions/{session_id}/messages",
        json={"text": "读取 README"},
    )
    run_id = _events(first)[0]["runId"]

    response = client.post(
        f"/api/runs/{run_id}/permission",
        json={"callId": "call_FORGED0001", "decision": "allow", "scope": "once"},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "PERMISSION_MISMATCH"
    assert client.app.state.services.run_registry.get(run_id) is not None


def test_runtime_failure_emits_generic_sse_error_without_internal_details(client) -> None:
    """运行异常只向浏览器公开稳定错误码和通用文案。"""
    session_id = _create_session(client)
    _use_fake_session_service(client, FakeFailingExecution)

    response = client.post(
        f"/api/sessions/{session_id}/messages",
        json={"text": "触发失败"},
    )

    events = _events(response)
    assert [event["type"] for event in events] == ["run.started", "run.failed"]
    assert events[-1]["data"] == {"code": "RUN_FAILED", "message": "运行失败"}
    assert "sqlite" not in response.text
    assert "api_key" not in response.text
    assert "sk-internal-secret" not in response.text


def test_session_rejects_second_active_run_and_can_cancel(client) -> None:
    """一个会话只有一个活动 Run，取消后释放占用。"""
    session_id = _create_session(client)
    _use_fake_session_service(client, FakePermissionExecution)
    first = client.post(
        f"/api/sessions/{session_id}/messages",
        json={"text": "读取 README"},
    )
    run_id = _events(first)[0]["runId"]
    active = client.app.state.services.run_registry.get(run_id)

    conflict = client.post(
        f"/api/sessions/{session_id}/messages",
        json={"text": "重复发送"},
    )
    cancelled = client.post(f"/api/runs/{run_id}/cancel")

    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "RUN_ALREADY_ACTIVE"
    assert cancelled.status_code == 204
    assert active.execution.cancel_calls == 1
    assert client.app.state.services.run_registry.get(run_id) is None
