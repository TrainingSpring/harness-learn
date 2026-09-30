"""Web 服务启动配置和应用数据目录设置。"""

import json
import os
from pathlib import Path
import shutil
from threading import RLock

from pydantic import BaseModel, ConfigDict, Field, field_validator


DEFAULT_DATA_DIR = Path.home() / ".harness-learn" / "data"
SETTINGS_PATH = Path.home() / ".harness-learn" / "settings.json"
_SETTINGS_LOCK = RLock()


def _normalize_data_dir(value: str | Path) -> Path:
    """规范化应用数据目录，不把它限制在项目 workspace 内。"""
    resolved = Path(value).expanduser().resolve()
    if not resolved.exists():
        resolved.mkdir(parents=True, exist_ok=True)
    if not resolved.is_dir():
        raise ValueError("存储目录必须是目录")
    return resolved


def load_data_dir() -> Path:
    """从固定用户设置读取存储目录；未设置时使用默认目录。"""
    with _SETTINGS_LOCK:
        try:
            value = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return _normalize_data_dir(DEFAULT_DATA_DIR)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("用户设置文件无法读取") from error
        configured = value.get("data_dir") if isinstance(value, dict) else None
        return _normalize_data_dir(configured or DEFAULT_DATA_DIR)


def _save_settings(value: dict[str, str]) -> None:
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = SETTINGS_PATH.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, SETTINGS_PATH)


def save_data_dir(data_dir: str | Path, *, migration_source: str | Path | None = None) -> Path:
    """保存目标数据目录；迁移会在下次启动、数据库打开前执行。"""
    normalized = _normalize_data_dir(data_dir)
    with _SETTINGS_LOCK:
        value = {"data_dir": str(normalized)}
        if migration_source is not None:
            value["migration_source"] = str(_normalize_data_dir(migration_source))
        _save_settings(value)
    return normalized


def pending_migration_source() -> Path | None:
    """读取等待服务重启后执行的数据迁移来源。"""
    with _SETTINGS_LOCK:
        try:
            value = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, UnicodeDecodeError, json.JSONDecodeError):
            return None
        source = value.get("migration_source") if isinstance(value, dict) else None
        return None if not source else _normalize_data_dir(source)


def clear_pending_migration() -> None:
    """仅在数据库成功迁移后删除迁移来源标记。"""
    with _SETTINGS_LOCK:
        try:
            value = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, UnicodeDecodeError, json.JSONDecodeError):
            return
        if isinstance(value, dict) and "migration_source" in value:
            value.pop("migration_source")
            _save_settings(value)


def migrate_database(source_dir: str | Path, target_dir: str | Path) -> Path:
    """将旧数据目录中的 state.db 移动到目标目录，不覆盖目标数据库。"""
    source = _normalize_data_dir(source_dir)
    target = _normalize_data_dir(target_dir)
    source_db = source / "state.db"
    target_db = target / "state.db"
    if source_db.resolve() == target_db.resolve() or not source_db.exists():
        return target
    if target_db.exists():
        raise FileExistsError(f"目标存储目录已有数据库: {target_db}")
    target_db.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source_db), str(target_db))
    return target


class WebServerSettings(BaseModel):
    """描述一个本地 Web Server 实例的固定网络和静态资源参数。

    Attributes:
        host: HTTP 监听地址，默认只允许本机访问。
        port: HTTP 监听端口。
        frontend_dist: 可选的前端生产构建目录。
    """

    model_config = ConfigDict(frozen=True)

    host: str = "127.0.0.1"
    port: int = Field(default=8765, ge=1, le=65535)
    frontend_dist: Path | None = None

    @field_validator("frontend_dist")
    @classmethod
    def normalize_frontend_dist(cls, value: Path | None) -> Path | None:
        """规范化可选前端构建目录；存在性在挂载静态资源时检查。"""
        return None if value is None else value.expanduser().resolve()
