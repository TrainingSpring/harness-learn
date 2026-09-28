"""MCP 远程 OAuth 2.1 / PKCE 边界，不持久化访问令牌。"""

from __future__ import annotations

from dataclasses import dataclass
import base64
import hashlib
import secrets
import time
from threading import Lock
from typing import Any, Mapping
from urllib.parse import urlencode, urljoin, urlsplit

import httpx

from .errors import McpError


class McpOAuthError(McpError):
    code = "MCP_AUTH_FAILED"


@dataclass(frozen=True)
class OAuthMetadata:
    authorization_endpoint: str
    token_endpoint: str
    registration_endpoint: str | None = None
    revocation_endpoint: str | None = None

    @classmethod
    def from_wire(cls, value: object) -> "OAuthMetadata":
        if not isinstance(value, Mapping):
            raise McpOAuthError("OAuth metadata 必须是对象")
        authorization = value.get("authorization_endpoint")
        token = value.get("token_endpoint")
        if not isinstance(authorization, str) or not isinstance(token, str):
            raise McpOAuthError("OAuth metadata 缺少授权或令牌端点")
        for endpoint in (authorization, token):
            parsed = urlsplit(endpoint)
            if parsed.scheme != "https" or not parsed.netloc:
                raise McpOAuthError("OAuth endpoint 必须使用 HTTPS")
        registration = value.get("registration_endpoint")
        revocation = value.get("revocation_endpoint")
        for field_name, endpoint in (("registration_endpoint", registration), ("revocation_endpoint", revocation)):
            if endpoint is not None:
                if not isinstance(endpoint, str):
                    raise McpOAuthError(f"{field_name} 必须是字符串")
                parsed = urlsplit(endpoint)
                if parsed.scheme != "https" or not parsed.netloc:
                    raise McpOAuthError("OAuth endpoint 必须使用 HTTPS")
        return cls(authorization, token, registration, revocation)


@dataclass(frozen=True)
class OAuthToken:
    access_token: str
    token_type: str = "Bearer"
    refresh_token: str | None = None
    expires_at: float | None = None

    @classmethod
    def from_wire(cls, value: object) -> "OAuthToken":
        if not isinstance(value, Mapping) or not isinstance(value.get("access_token"), str) or not value["access_token"]:
            raise McpOAuthError("OAuth token 响应缺少 access_token")
        token_type = value.get("token_type", "Bearer")
        if not isinstance(token_type, str) or token_type.casefold() != "bearer":
            raise McpOAuthError("MCP 仅支持 Bearer token")
        expires_in = value.get("expires_in")
        expires_at = None
        if expires_in is not None:
            if isinstance(expires_in, bool) or not isinstance(expires_in, (int, float)) or expires_in < 0:
                raise McpOAuthError("expires_in 无效")
            expires_at = time.time() + float(expires_in)
        refresh = value.get("refresh_token")
        if refresh is not None and not isinstance(refresh, str):
            raise McpOAuthError("refresh_token 无效")
        return cls(value["access_token"], token_type, refresh, expires_at)

    def is_expired(self, skew_seconds: int = 30) -> bool:
        return self.expires_at is not None and time.time() + skew_seconds >= self.expires_at


@dataclass(frozen=True)
class PkceChallenge:
    verifier: str
    challenge: str

    @classmethod
    def create(cls) -> "PkceChallenge":
        verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode().rstrip("=")
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
        return cls(verifier, challenge)


class OAuthStateStore:
    def __init__(self) -> None:
        self._states: dict[str, tuple[PkceChallenge, float]] = {}
        self._lock = Lock()

    def create(self, ttl_seconds: int = 600) -> tuple[str, PkceChallenge]:
        if isinstance(ttl_seconds, bool) or not isinstance(ttl_seconds, int) or ttl_seconds <= 0:
            raise McpOAuthError("OAuth state TTL 必须是正整数")
        state = secrets.token_urlsafe(32)
        challenge = PkceChallenge.create()
        with self._lock:
            self._states[state] = (challenge, time.time() + ttl_seconds)
        return state, challenge

    def consume(self, state: str) -> PkceChallenge:
        with self._lock:
            item = self._states.pop(state, None)
        if item is None or time.time() >= item[1]:
            raise McpOAuthError("OAuth state 无效或已过期")
        return item[0]


class OAuthClient:
    """执行 metadata discovery、PKCE 授权码交换和 refresh。"""

    def __init__(
        self,
        *,
        client_id: str,
        redirect_uri: str,
        scopes: tuple[str, ...] = (),
        resource: str | None = None,
        http_client: httpx.Client | None = None,
    ) -> None:
        if not client_id or not redirect_uri:
            raise ValueError("client_id 和 redirect_uri 不能为空")
        parsed = urlsplit(redirect_uri)
        if parsed.scheme not in {"http", "https"}:
            raise ValueError("redirect_uri 必须是 HTTP(S) URI")
        if resource is not None:
            _require_https_endpoint(resource, "resource")
        self.client_id = client_id
        self.redirect_uri = redirect_uri
        self.scopes = scopes
        self.resource = resource
        self.http = http_client or httpx.Client()
        self._owns_http = http_client is None

    def discover(self, protected_resource_url: str) -> OAuthMetadata:
        parsed = urlsplit(protected_resource_url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise McpOAuthError("OAuth resource discovery 必须使用 HTTPS")
        base = f"{parsed.scheme}://{parsed.netloc}/"
        response = self.http.get(urljoin(base, ".well-known/oauth-authorization-server"))
        if response.status_code != 200:
            raise McpOAuthError("OAuth authorization server metadata 获取失败")
        return OAuthMetadata.from_wire(response.json())

    def authorization_url(self, metadata: OAuthMetadata, state: str, challenge: PkceChallenge) -> str:
        query = urlencode({
            "response_type": "code", "client_id": self.client_id,
            "redirect_uri": self.redirect_uri, "state": state,
            "code_challenge": challenge.challenge, "code_challenge_method": "S256",
            **({"scope": " ".join(self.scopes)} if self.scopes else {}),
            **({"resource": self.resource} if self.resource else {}),
        })
        return f"{metadata.authorization_endpoint}?{query}"

    def exchange_code(self, metadata: OAuthMetadata, *, code: str, state: str, returned_state: str, states: OAuthStateStore) -> OAuthToken:
        if state != returned_state:
            raise McpOAuthError("OAuth state mismatch")
        challenge = states.consume(state)
        response = self.http.post(metadata.token_endpoint, data={
            "grant_type": "authorization_code", "code": code,
            "redirect_uri": self.redirect_uri, "client_id": self.client_id,
            "code_verifier": challenge.verifier,
            **({"resource": self.resource} if self.resource else {}),
        })
        if response.status_code != 200:
            raise McpOAuthError("OAuth authorization code 交换失败")
        return OAuthToken.from_wire(response.json())

    def refresh(self, metadata: OAuthMetadata, token: OAuthToken) -> OAuthToken:
        if not token.refresh_token:
            raise McpOAuthError("当前 token 没有 refresh_token")
        response = self.http.post(metadata.token_endpoint, data={
            "grant_type": "refresh_token", "refresh_token": token.refresh_token,
            "client_id": self.client_id,
            **({"resource": self.resource} if self.resource else {}),
        })
        if response.status_code != 200:
            raise McpOAuthError("OAuth token 刷新失败")
        return OAuthToken.from_wire(response.json())

    def register_client(
        self,
        metadata: OAuthMetadata,
        *,
        redirect_uris: tuple[str, ...],
        client_name: str | None = None,
    ) -> dict[str, Any]:
        """按 RFC 7591 注册客户端；调用方决定是否保存返回的 client_id。"""
        endpoint = metadata.registration_endpoint
        if endpoint is None:
            raise McpOAuthError("OAuth Server 未提供动态注册端点")
        if not redirect_uris or any(not isinstance(uri, str) or not uri for uri in redirect_uris):
            raise McpOAuthError("动态注册必须包含 redirect_uris")
        payload: dict[str, Any] = {"redirect_uris": list(redirect_uris)}
        if client_name:
            payload["client_name"] = client_name
        response = self.http.post(endpoint, json=payload)
        if response.status_code not in {200, 201}:
            raise McpOAuthError("OAuth 客户端动态注册失败")
        value = response.json()
        if not isinstance(value, Mapping) or not isinstance(value.get("client_id"), str):
            raise McpOAuthError("OAuth 动态注册响应缺少 client_id")
        return dict(value)

    def revoke(self, metadata: OAuthMetadata, token: OAuthToken) -> None:
        """撤销 access token；token 只作为本次内存调用参数存在。"""
        endpoint = metadata.revocation_endpoint
        if endpoint is None:
            raise McpOAuthError("OAuth Server 未提供撤销端点")
        response = self.http.post(endpoint, data={
            "token": token.access_token,
            "token_type_hint": "access_token",
            **({"resource": self.resource} if self.resource else {}),
        })
        if response.status_code not in {200, 204}:
            raise McpOAuthError("OAuth token 撤销失败")

    def close(self) -> None:
        if self._owns_http:
            self.http.close()


def _require_https_endpoint(value: str, field_name: str) -> None:
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.netloc or parsed.fragment:
        raise McpOAuthError(f"OAuth {field_name} 必须使用 HTTPS 且不能包含 fragment")
