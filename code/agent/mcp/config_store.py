"""`config.json` 的读取、校验和原子更新。"""

import hashlib
import json
import os
from pathlib import Path
import tempfile
from threading import RLock
from typing import Any

from .errors import (
    McpConfigConflictError,
    McpConfigFormatError,
    McpServerNotFoundError,
)
from .types import (
    LocalMcpServerConfig,
    McpConfigDocument,
    McpConfigSnapshot,
    McpServerConfig,
    RemoteMcpServerConfig,
)


_LOCAL_FIELDS = {
    "id",
    "name",
    "description",
    "is_local",
    "transport",
    "command",
    "args",
    "cwd",
    "env",
    "enabled",
    "startup_timeout_ms",
    "shutdown_timeout_ms",
}
_REMOTE_FIELDS = {
    "id",
    "name",
    "description",
    "is_local",
    "transport",
    "url",
    "headers",
    "auth_mode",
    "enabled",
    "request_timeout_ms",
}


def _server_from_dict(value: object) -> McpServerConfig:
    if not isinstance(value, dict):
        raise McpConfigFormatError("每个 Server 配置都必须是对象")
    is_local = value.get("is_local")
    if not isinstance(is_local, bool):
        raise McpConfigFormatError("is_local 必须是布尔值")

    allowed_fields = _LOCAL_FIELDS if is_local else _REMOTE_FIELDS
    unknown_fields = set(value) - allowed_fields
    if unknown_fields:
        raise McpConfigFormatError(
            f"Server 配置包含不支持的字段: {', '.join(sorted(unknown_fields))}"
        )

    if is_local:
        if value.get("transport") != "stdio":
            raise McpConfigFormatError("本地 stdio 配置的 transport 必须是 stdio")
        return LocalMcpServerConfig(
            id=value.get("id"),
            name=value.get("name"),
            description=value.get("description", ""),
            command=value.get("command"),
            args=value.get("args", []),
            cwd=value.get("cwd"),
            env=value.get("env", {}),
            enabled=value.get("enabled", True),
            startup_timeout_ms=value.get("startup_timeout_ms", 10_000),
            shutdown_timeout_ms=value.get("shutdown_timeout_ms", 5_000),
        )

    if value.get("transport") != "streamable_http":
        raise McpConfigFormatError("远程配置的 transport 必须是 streamable_http")
    return RemoteMcpServerConfig(
        id=value.get("id"),
        name=value.get("name"),
        description=value.get("description", ""),
        url=value.get("url"),
        headers=value.get("headers", {}),
        auth_mode=value.get("auth_mode", "none"),
        enabled=value.get("enabled", True),
        request_timeout_ms=value.get("request_timeout_ms", 30_000),
    )


def _document_from_dict(value: object) -> McpConfigDocument:
    if not isinstance(value, dict):
        raise McpConfigFormatError("配置文件顶层必须是对象")
    if set(value) != {"version", "servers"}:
        raise McpConfigFormatError("配置文件必须且只能包含 version 和 servers")
    version = value["version"]
    servers = value["servers"]
    if isinstance(version, bool) or not isinstance(version, int):
        raise McpConfigFormatError("version 必须是整数")
    if not isinstance(servers, list):
        raise McpConfigFormatError("servers 必须是数组")
    return McpConfigDocument(
        version=version,
        servers=tuple(_server_from_dict(server) for server in servers),
    )


def _server_to_dict(server: McpServerConfig) -> dict[str, Any]:
    common = {
        "id": server.id,
        "name": server.name,
        "description": server.description,
        "is_local": server.is_local,
        "transport": server.transport,
    }
    if isinstance(server, LocalMcpServerConfig):
        return {
            **common,
            "command": server.command,
            "args": list(server.args),
            "cwd": server.cwd,
            "env": dict(server.env),
            "enabled": server.enabled,
            "startup_timeout_ms": server.startup_timeout_ms,
            "shutdown_timeout_ms": server.shutdown_timeout_ms,
        }
    return {
        **common,
        "url": server.url,
        "headers": dict(server.headers),
        "auth_mode": server.auth_mode,
        "enabled": server.enabled,
        "request_timeout_ms": server.request_timeout_ms,
    }


def _document_to_dict(document: McpConfigDocument) -> dict[str, Any]:
    return {
        "version": document.version,
        "servers": [_server_to_dict(server) for server in document.servers],
    }


class McpConfigStore:
    """独立管理 MCP 注册 JSON，不依赖 Web、Session 或 SQLite。

    默认位置是当前用户 home 下的 `harness-learn/mcp/config.json`。
    测试和调用方可以显式注入文件路径。
    """

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = (
            Path(path).expanduser().resolve()
            if path is not None
            else Path.home() / "harness-learn" / "mcp" / "config.json"
        )
        self._lock = RLock()

    @staticmethod
    def empty_document(
        servers: tuple[McpServerConfig, ...] = (),
    ) -> McpConfigDocument:
        """创建一个空配置文档或由已校验类型构成的文档。"""
        return McpConfigDocument(servers=servers)

    def read(self) -> McpConfigSnapshot:
        """读取最新配置；首次访问时创建空配置文件。"""
        with self._lock:
            raw = self._read_bytes(create=True)
            try:
                data = json.loads(raw)
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise McpConfigFormatError("配置文件不是有效 UTF-8 JSON") from error
            document = _document_from_dict(data)
            return McpConfigSnapshot(document=document, revision=_revision(raw))

    def save(
        self,
        document: McpConfigDocument,
        *,
        expected_revision: str | None = None,
    ) -> McpConfigSnapshot:
        """保存完整文档；提供 revision 时拒绝覆盖外部更新。"""
        if not isinstance(document, McpConfigDocument):
            raise TypeError("document 必须是 McpConfigDocument")
        with self._lock:
            current = self._read_bytes(create=True)
            current_revision = _revision(current)
            if expected_revision is not None and expected_revision != current_revision:
                raise McpConfigConflictError("MCP 配置已在其他位置修改，请重新读取后再保存")
            encoded = (
                json.dumps(
                    _document_to_dict(document),
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=False,
                )
                + "\n"
            ).encode("utf-8")
            self._atomic_replace(encoded)
            return McpConfigSnapshot(document=document, revision=_revision(encoded))

    def create(
        self,
        server: McpServerConfig,
        *,
        expected_revision: str | None = None,
    ) -> McpConfigSnapshot:
        """按稳定 ID 新增 Server。"""
        with self._lock:
            current = self.read()
            if expected_revision is not None and expected_revision != current.revision:
                raise McpConfigConflictError("MCP 配置已在其他位置修改，请重新读取后再保存")
            if any(item.id == server.id for item in current.document.servers):
                raise McpConfigFormatError("Server id 已存在")
            return self.save(
                McpConfigDocument(servers=(*current.document.servers, server)),
                expected_revision=current.revision,
            )

    def update(
        self,
        server: McpServerConfig,
        *,
        expected_revision: str,
    ) -> McpConfigSnapshot:
        """按稳定 ID 替换 Server 配置，允许本地/远程类型显式变更。"""
        with self._lock:
            current = self.read()
            if expected_revision != current.revision:
                raise McpConfigConflictError("MCP 配置已在其他位置修改，请重新读取后再保存")
            if not any(item.id == server.id for item in current.document.servers):
                raise McpServerNotFoundError(f"MCP Server 不存在: {server.id}")
            updated = tuple(server if item.id == server.id else item for item in current.document.servers)
            return self.save(
                McpConfigDocument(servers=updated),
                expected_revision=current.revision,
            )

    def delete(
        self,
        server_id: str,
        *,
        expected_revision: str | None = None,
    ) -> McpConfigSnapshot:
        """删除 Server；进程停止和 Agent 引用检查由上层服务负责。"""
        with self._lock:
            current = self.read()
            if expected_revision is not None and expected_revision != current.revision:
                raise McpConfigConflictError("MCP 配置已在其他位置修改，请重新读取后再删除")
            remaining = tuple(item for item in current.document.servers if item.id != server_id)
            if len(remaining) == len(current.document.servers):
                raise McpServerNotFoundError(f"MCP Server 不存在: {server_id}")
            return self.save(
                McpConfigDocument(servers=remaining),
                expected_revision=current.revision,
            )

    def _read_bytes(self, *, create: bool) -> bytes:
        try:
            return self.path.read_bytes()
        except FileNotFoundError:
            if not create:
                raise
        self.path.parent.mkdir(parents=True, exist_ok=True)
        initial = b'{\n  "version": 1,\n  "servers": []\n}\n'
        self._atomic_replace(initial)
        return initial

    def _atomic_replace(self, contents: bytes) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=self.path.parent,
                prefix=f".{self.path.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary_file:
                temporary_path = Path(temporary_file.name)
                temporary_file.write(contents)
                temporary_file.flush()
                os.fsync(temporary_file.fileno())
            if os.name != "nt":
                os.chmod(temporary_path, 0o600)
            os.replace(temporary_path, self.path)
        except OSError:
            if temporary_path is not None:
                try:
                    temporary_path.unlink(missing_ok=True)
                except OSError:
                    pass
            raise


def _revision(contents: bytes) -> str:
    return hashlib.sha256(contents).hexdigest()
