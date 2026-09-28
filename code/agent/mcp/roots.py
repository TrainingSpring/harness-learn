"""从当前 Session workspace 生成 MCP Roots。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote


@dataclass(frozen=True)
class McpRoot:
    uri: str
    name: str | None = None

    def to_dict(self) -> dict[str, str]:
        result = {"uri": self.uri}
        if self.name:
            result["name"] = self.name
        return result


def roots_for_workspace(workspace: str | None) -> tuple[McpRoot, ...]:
    """Roots 只描述当前 workspace，不扩大 PermissionManager 授权范围。"""
    if not workspace:
        return ()
    path = Path(workspace).expanduser().resolve()
    uri = "file://" + quote(path.as_posix(), safe="/")
    return (McpRoot(uri, path.name or str(path)),)
