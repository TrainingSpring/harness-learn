from mcp.auth_session import McpAuthorizationManager, McpAuthorizationError
from mcp.oauth import OAuthClient, OAuthMetadata, OAuthToken


def test_authorization_status_does_not_expose_token():
    manager = McpAuthorizationManager()
    assert manager.status("mcp_REMOTE01").authorized is False
    manager._tokens["mcp_REMOTE01"] = OAuthToken("secret", expires_at=9999999999)
    status = manager.status("mcp_REMOTE01")
    assert status.authorized is True
    assert not hasattr(status, "access_token")


def test_expired_authorization_session_is_rejected():
    manager = McpAuthorizationManager(ttl_seconds=1)
    client = OAuthClient(client_id="client", redirect_uri="http://127.0.0.1/callback")
    metadata = OAuthMetadata("https://auth.example/authorize", "https://auth.example/token")
    authorization_id, _ = manager.begin("mcp_REMOTE01", client, metadata)
    manager._sessions[authorization_id] = manager._sessions[authorization_id].__class__(
        **{**manager._sessions[authorization_id].__dict__, "expires_at": 0}
    )
    try:
        try:
            manager.complete(authorization_id, code="code", state="state")
        except McpAuthorizationError:
            pass
        else:
            raise AssertionError("过期授权会话应该失败")
    finally:
        client.close()
