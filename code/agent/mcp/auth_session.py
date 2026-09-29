"""MCP OAuth 用户授权会话的内存状态边界。"""

from __future__ import annotations

from dataclasses import dataclass
import secrets
import time
from threading import Lock

from .errors import McpError
from .oauth import OAuthClient, OAuthMetadata, OAuthStateStore, OAuthToken


class McpAuthorizationError(McpError):
    code = "MCP_AUTH_FAILED"


@dataclass(frozen=True)
class AuthorizationSession:
    id: str
    server_id: str
    client: OAuthClient
    metadata: OAuthMetadata
    state: str
    created_at: float
    expires_at: float


@dataclass(frozen=True)
class AuthorizationStatus:
    server_id: str
    authorized: bool
    expires_at: float | None = None
    has_refresh_token: bool = False
    error: str | None = None


class McpAuthorizationManager:
    """管理 OAuth 授权流程和短期 token，不将 token 写入配置文件。"""

    def __init__(self, *, states: OAuthStateStore | None = None, ttl_seconds: int = 600) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds 必须为正数")
        self.states = states or OAuthStateStore()
        self.ttl_seconds = ttl_seconds
        self._sessions: dict[str, AuthorizationSession] = {}
        self._tokens: dict[str, OAuthToken] = {}
        self._errors: dict[str, str] = {}
        self._lock = Lock()

    def begin(self, server_id: str, client: OAuthClient, metadata: OAuthMetadata) -> tuple[str, str]:
        state, challenge = self.states.create(self.ttl_seconds)
        authorization_id = secrets.token_urlsafe(24)
        session = AuthorizationSession(
            authorization_id, server_id, client, metadata, state,
            time.time(), time.time() + self.ttl_seconds,
        )
        with self._lock:
            self._sessions[authorization_id] = session
        return authorization_id, client.authorization_url(metadata, state, challenge)

    def complete(self, authorization_id: str, *, code: str, state: str) -> OAuthToken:
        with self._lock:
            session = self._sessions.pop(authorization_id, None)
        if session is None or time.time() >= session.expires_at:
            raise McpAuthorizationError("OAuth 授权会话无效或已过期")
        try:
            token = session.client.exchange_code(
                session.metadata, code=code, state=session.state,
                returned_state=state, states=self.states,
            )
        except Exception as error:
            self._errors[session.server_id] = "OAuth 授权失败"
            raise
        with self._lock:
            self._tokens[session.server_id] = token
            self._errors.pop(session.server_id, None)
        return token

    def token(self, server_id: str) -> OAuthToken | None:
        with self._lock:
            token = self._tokens.get(server_id)
        return token

    def status(self, server_id: str) -> AuthorizationStatus:
        with self._lock:
            token = self._tokens.get(server_id)
            error = self._errors.get(server_id)
        return AuthorizationStatus(
            server_id, token is not None and not token.is_expired(),
            token.expires_at if token else None,
            bool(token and token.refresh_token), error,
        )

    def revoke(self, server_id: str, client: OAuthClient, metadata: OAuthMetadata) -> None:
        token = self.token(server_id)
        if token is None:
            return
        client.revoke(metadata, token)
        with self._lock:
            self._tokens.pop(server_id, None)
            self._errors.pop(server_id, None)

    def clear_server(self, server_id: str) -> None:
        with self._lock:
            self._tokens.pop(server_id, None)
            self._errors.pop(server_id, None)
            ids = [key for key, value in self._sessions.items() if value.server_id == server_id]
            for key in ids:
                self._sessions.pop(key, None)

    def close(self) -> None:
        with self._lock:
            sessions = tuple(self._sessions.values())
            self._sessions.clear()
            self._tokens.clear()
            self._errors.clear()
        for session in sessions:
            session.client.close()
