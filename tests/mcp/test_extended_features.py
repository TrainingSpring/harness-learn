"""MCP 阶段 7-9 的边界测试。"""

from __future__ import annotations

import pytest
import httpx

from mcp.completions import validate_completion_params, validate_completion_result
from mcp.errors import McpProtocolError
from mcp.events import McpLogEvent, McpProgressEvent
from mcp.oauth import McpOAuthError, OAuthClient, OAuthMetadata, OAuthStateStore, OAuthToken
from mcp.notifications import McpNotificationDispatcher
from mcp.protocol import JsonRpcRequest
from mcp.resources import McpResource, McpResourceTemplate, validate_resource_result
from mcp.roots import roots_for_workspace
from mcp.server_requests import McpServerRequestHandler


def test_resources_prompts_and_roots_validate_without_context_side_effects(tmp_path):
    resource = McpResource.from_wire({"uri": "file:///tmp/a", "name": "a"})
    template = McpResourceTemplate.from_wire({"uriTemplate": "file:///tmp/{name}", "name": "files"})
    assert resource.uri == "file:///tmp/a"
    assert template.name == "files"
    assert roots_for_workspace(str(tmp_path))[0].uri.startswith("file://")
    assert validate_resource_result({"contents": [{"uri": "file:///tmp/a", "text": "x"}]})["contents"]


def test_completion_and_server_request_validation():
    params = validate_completion_params({"ref": {"type": "ref/prompt"}, "argument": {"name": "q", "value": "a"}})
    assert params["argument"]["name"] == "q"
    assert validate_completion_result({"completion": {"values": ["one"]}})["completion"]["values"] == ["one"]
    handler = McpServerRequestHandler(workspace="/workspace")
    roots = handler.handle(JsonRpcRequest(1, "roots/list"))
    assert roots.result["roots"][0]["uri"].startswith("file://")
    handler.register("elicitation/create", lambda params: {"action": "decline"})
    assert handler.handle(JsonRpcRequest(2, "elicitation/create", {
        "message": "Choose an option",
        "mode": "form",
        "requestedSchema": {"type": "object"},
    })).result["action"] == "decline"

    handler.register("sampling/createMessage", lambda params: {
        "role": "assistant",
        "content": {"type": "text", "text": "done"},
    })
    sampling = handler.handle(JsonRpcRequest(3, "sampling/createMessage", {
        "messages": [{"role": "user", "content": {"type": "text", "text": "go"}}],
    }))
    assert sampling.result["role"] == "assistant"


def test_prompt_message_and_oauth_metadata_boundaries_are_validated():
    from mcp.prompts import parse_prompt_result

    parse_prompt_result({"messages": [{"role": "user", "content": {"type": "text", "text": "hello"}}]})
    with pytest.raises(McpProtocolError, match="Prompt"):
        parse_prompt_result({"messages": [{"role": "system", "content": {"type": "text", "text": "no"}}]})
    with pytest.raises(McpOAuthError, match="HTTPS"):
        OAuthMetadata.from_wire({
            "authorization_endpoint": "https://auth.example/authorize",
            "token_endpoint": "https://auth.example/token",
            "registration_endpoint": "http://auth.example/register",
        })


def test_notifications_expose_log_and_progress_events():
    dispatcher = McpNotificationDispatcher()
    events = []
    dispatcher.subscribe_events(events.append)
    from mcp.protocol import JsonRpcNotification
    dispatcher.dispatch(JsonRpcNotification("notifications/message", {
        "level": "warning", "data": {"token": "secret", "message": "x"},
    }))
    dispatcher.dispatch(JsonRpcNotification("notifications/progress", {"progressToken": "p", "progress": 2, "total": 3}))
    assert isinstance(events[0], McpLogEvent)
    assert events[0].data["token"] == "[REDACTED]"
    assert isinstance(events[1], McpProgressEvent)


def test_oauth_pkce_state_is_one_time_and_token_expiry_is_bounded():
    store = OAuthStateStore()
    state, challenge = store.create()
    assert len(challenge.verifier) >= 40
    assert store.consume(state) == challenge
    with pytest.raises(McpOAuthError):
        store.consume(state)
    token = OAuthToken.from_wire({"access_token": "secret", "expires_in": 1})
    assert token.expires_at is not None
    assert token.is_expired(skew_seconds=2)
    with pytest.raises(McpOAuthError):
        OAuthStateStore().create(ttl_seconds=0)


def test_oauth_resource_registration_and_revocation_are_explicit():
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/register"):
            return httpx.Response(201, json={"client_id": "client-1"})
        if request.url.path.endswith("/revoke"):
            return httpx.Response(200)
        return httpx.Response(404)

    client = OAuthClient(
        client_id="client-1",
        redirect_uri="http://127.0.0.1/callback",
        resource="https://mcp.example/server",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    metadata = OAuthMetadata(
        "https://auth.example/authorize",
        "https://auth.example/token",
        registration_endpoint="https://auth.example/register",
        revocation_endpoint="https://auth.example/revoke",
    )
    registered = client.register_client(metadata, redirect_uris=(client.redirect_uri,))
    assert registered["client_id"] == "client-1"
    client.revoke(metadata, OAuthToken("access"))
    assert requests[0].content.startswith(b"{")
    assert b"resource=https%3A%2F%2Fmcp.example%2Fserver" in requests[1].content
    client.close()
