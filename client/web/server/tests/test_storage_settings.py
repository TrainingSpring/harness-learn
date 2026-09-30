"""应用数据目录设置和数据库迁移测试。"""

from pathlib import Path

import pytest

from app import config


def test_load_data_dir_uses_default_when_no_setting_exists(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    default_dir = tmp_path / "default-data"
    monkeypatch.setattr(config, "DEFAULT_DATA_DIR", default_dir)
    monkeypatch.setattr(config, "SETTINGS_PATH", tmp_path / "settings.json")

    assert config.load_data_dir() == default_dir.resolve()
    assert default_dir.is_dir()


def test_save_data_dir_persists_selected_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    settings_path = tmp_path / "settings.json"
    selected = tmp_path / "selected-data"
    monkeypatch.setattr(config, "SETTINGS_PATH", settings_path)

    assert config.save_data_dir(selected) == selected.resolve()
    assert config.load_data_dir() == selected.resolve()


def test_migrate_database_moves_database_without_overwriting_target(tmp_path: Path) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    (source / "state.db").write_bytes(b"existing-data")

    assert config.migrate_database(source, target) == target.resolve()
    assert not (source / "state.db").exists()
    assert (target / "state.db").read_bytes() == b"existing-data"

    (source / "state.db").write_bytes(b"other-data")
    with pytest.raises(FileExistsError):
        config.migrate_database(source, target)


def test_storage_directory_browser_lists_current_directory_and_parent(client, tmp_path: Path) -> None:
    """存储设置可浏览任意真实目录，而不是应用数据目录的子集。"""
    directory = tmp_path / "storage-choice"
    child = directory / "child"
    directory.mkdir()
    child.mkdir()

    response = client.get("/api/settings/directories", params={"path": str(directory)})

    assert response.status_code == 200
    assert response.json() == {
        "path": str(directory),
        "name": "storage-choice",
        "parentPath": str(tmp_path),
        "directories": [{"path": str(child), "name": "child"}],
    }


def test_storage_directory_browser_rejects_missing_directory(client, tmp_path: Path) -> None:
    """不存在的目录不能作为数据存储位置。"""
    response = client.get("/api/settings/directories", params={"path": str(tmp_path / "missing")})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_DATA_DIR"
