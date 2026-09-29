"""MCP 注册配置的纯 Python 类型和边界校验。"""

from dataclasses import dataclass, field
import re
from typing import TypeAlias
from urllib.parse import urlsplit

from .errors import McpConfigFormatError


_SERVER_ID_PATTERN = re.compile(r"^mcp_[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
_MAX_SERVERS = 100
_MAX_ARGS = 256
_MAX_MAP_ITEMS = 256
_MAX_TEXT_LENGTH = 8192


def _require_text(value: object, field_name: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise McpConfigFormatError(f"{field_name} 必须是字符串")
    if not allow_empty and not value.strip():
        raise McpConfigFormatError(f"{field_name} 不能为空")
    if len(value) > _MAX_TEXT_LENGTH:
        raise McpConfigFormatError(f"{field_name} 超过长度限制")
    return value


def _require_id(value: object) -> str:
    if not isinstance(value, str) or _SERVER_ID_PATTERN.fullmatch(value) is None:
        raise McpConfigFormatError("Server id 格式无效")
    return value


def _require_string_list(value: object, field_name: str, *, limit: int) -> tuple[str, ...]:
    if not isinstance(value, list) or len(value) > limit:
        raise McpConfigFormatError(f"{field_name} 必须是长度不超过 {limit} 的字符串数组")
    return tuple(_require_text(item, field_name) for item in value)


def _require_string_map(value: object, field_name: str, *, header_names: bool = False) -> dict[str, str]:
    if not isinstance(value, dict) or len(value) > _MAX_MAP_ITEMS:
        raise McpConfigFormatError(f"{field_name} 必须是长度不超过 {_MAX_MAP_ITEMS} 的对象")
    result: dict[str, str] = {}
    for key, item in value.items():
        normalized_key = _require_text(key, f"{field_name} key")
        normalized_value = _require_text(item, f"{field_name}[{normalized_key}]", allow_empty=True)
        if "\x00" in normalized_key or "\x00" in normalized_value:
            raise McpConfigFormatError(f"{field_name} 不能包含 NUL 字符")
        if header_names and ("\r" in normalized_key or "\n" in normalized_key or "\r" in normalized_value or "\n" in normalized_value):
            raise McpConfigFormatError("HTTP header 不能包含换行符")
        result[normalized_key] = normalized_value
    return result


def _require_timeout(value: object, field_name: str, default: int) -> int:
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int) or not 100 <= value <= 300_000:
        raise McpConfigFormatError(f"{field_name} 必须是 100 到 300000 之间的整数")
    return value


@dataclass(frozen=True)
class LocalMcpServerConfig:
    """由 Harness 在本机管理、通过 stdio 通信的 MCP Server 配置。"""

    id: str
    name: str
    command: str
    description: str = ""
    args: tuple[str, ...] = ()
    directory: str | None = None
    env: dict[str, str] = field(default_factory=dict)
    enabled: bool = True
    startup_timeout_ms: int = 10_000
    shutdown_timeout_ms: int = 5_000
    is_local: bool = field(default=True, init=False)
    transport: str = field(default="stdio", init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _require_id(self.id))
        object.__setattr__(self, "name", _require_text(self.name, "name"))
        object.__setattr__(self, "description", _require_text(self.description, "description", allow_empty=True))
        object.__setattr__(self, "command", _require_text(self.command, "command"))
        if isinstance(self.args, list):
            object.__setattr__(self, "args", tuple(self.args))
        if not isinstance(self.args, tuple) or len(self.args) > _MAX_ARGS:
            raise McpConfigFormatError(f"args 必须是长度不超过 {_MAX_ARGS} 的字符串数组")
        object.__setattr__(self, "args", tuple(_require_text(arg, "args", allow_empty=True) for arg in self.args))
        if self.directory is not None:
            object.__setattr__(self, "directory", _require_text(self.directory, "directory"))
        object.__setattr__(self, "env", _require_string_map(self.env, "env"))
        if not isinstance(self.enabled, bool):
            raise McpConfigFormatError("enabled 必须是布尔值")
        object.__setattr__(self, "startup_timeout_ms", _require_timeout(self.startup_timeout_ms, "startup_timeout_ms", 10_000))
        object.__setattr__(self, "shutdown_timeout_ms", _require_timeout(self.shutdown_timeout_ms, "shutdown_timeout_ms", 5_000))


@dataclass(frozen=True)
class RemoteMcpServerConfig:
    """通过 Streamable HTTP 连接的远程 MCP Server 配置。"""

    id: str
    name: str
    url: str
    description: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    auth_mode: str = "none"
    enabled: bool = True
    request_timeout_ms: int = 30_000
    oauth_client_id: str | None = None
    oauth_scopes: tuple[str, ...] = ()
    is_local: bool = field(default=False, init=False)
    transport: str = field(default="streamable_http", init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _require_id(self.id))
        object.__setattr__(self, "name", _require_text(self.name, "name"))
        object.__setattr__(self, "description", _require_text(self.description, "description", allow_empty=True))
        url = _require_text(self.url, "url")
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            raise McpConfigFormatError("url 必须是有效的 HTTP(S) 地址且不能包含用户凭据")
        if parsed.fragment:
            raise McpConfigFormatError("url 不能包含 fragment")
        object.__setattr__(self, "url", url)
        object.__setattr__(self, "headers", _require_string_map(self.headers, "headers", header_names=True))
        if self.auth_mode not in {"none", "bearer", "oauth"}:
            raise McpConfigFormatError("auth_mode 必须是 none、bearer 或 oauth")
        if not isinstance(self.enabled, bool):
            raise McpConfigFormatError("enabled 必须是布尔值")
        if self.oauth_client_id is not None:
            object.__setattr__(self, "oauth_client_id", _require_text(self.oauth_client_id, "oauth_client_id"))
        if isinstance(self.oauth_scopes, list):
            object.__setattr__(self, "oauth_scopes", tuple(self.oauth_scopes))
        if not isinstance(self.oauth_scopes, tuple):
            raise McpConfigFormatError("oauth_scopes 必须是字符串数组")
        object.__setattr__(self, "oauth_scopes", tuple(_require_text(scope, "oauth_scopes") for scope in self.oauth_scopes))
        object.__setattr__(self, "request_timeout_ms", _require_timeout(self.request_timeout_ms, "request_timeout_ms", 30_000))


McpServerConfig: TypeAlias = LocalMcpServerConfig | RemoteMcpServerConfig


@dataclass(frozen=True)
class McpConfigDocument:
    """一个完整、已校验的 MCP Server 注册配置文档。"""

    servers: tuple[McpServerConfig, ...] = ()
    version: int = 1

    def __post_init__(self) -> None:
        if self.version != 1 or isinstance(self.version, bool):
            raise McpConfigFormatError("当前只支持 config version 1")
        if not isinstance(self.servers, tuple):
            object.__setattr__(self, "servers", tuple(self.servers))
        if len(self.servers) > _MAX_SERVERS:
            raise McpConfigFormatError(f"servers 最多允许 {_MAX_SERVERS} 个")
        ids: set[str] = set()
        names: set[str] = set()
        for server in self.servers:
            if not isinstance(server, (LocalMcpServerConfig, RemoteMcpServerConfig)):
                raise McpConfigFormatError("servers 中包含未知配置类型")
            if server.id in ids:
                raise McpConfigFormatError("Server id 不能重复")
            normalized_name = server.name.casefold()
            if normalized_name in names:
                raise McpConfigFormatError("Server name 不能重复")
            ids.add(server.id)
            names.add(normalized_name)


@dataclass(frozen=True)
class McpConfigSnapshot:
    """配置内容及其用于乐观并发校验的内容摘要。"""

    document: McpConfigDocument
    revision: str
