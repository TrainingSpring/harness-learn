"""Web 服务启动配置。"""

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator


class WebServerSettings(BaseModel):
    """描述一个本地 Web Server 实例的固定启动参数。

    Attributes:
        workspace: Agent、工具和状态数据库共同使用的项目目录。
        host: HTTP 监听地址，默认只允许本机访问。
        port: HTTP 监听端口。
        frontend_dist: 可选的前端生产构建目录。
    """

    model_config = ConfigDict(frozen=True)

    workspace: Path
    host: str = "127.0.0.1"
    port: int = Field(default=8765, ge=1, le=65535)
    frontend_dist: Path | None = None

    @field_validator("workspace")
    @classmethod
    def normalize_workspace(cls, value: Path) -> Path:
        """把 workspace 规范化为绝对路径，并拒绝不存在的目录。"""
        resolved = value.expanduser().resolve()
        if not resolved.is_dir():
            raise ValueError("workspace 必须是已存在的目录")
        return resolved

    @field_validator("frontend_dist")
    @classmethod
    def normalize_frontend_dist(cls, value: Path | None) -> Path | None:
        """规范化可选前端构建目录；存在性在挂载静态资源时检查。"""
        return None if value is None else value.expanduser().resolve()

