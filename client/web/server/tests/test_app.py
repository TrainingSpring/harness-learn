"""Web 应用生命周期和公共错误契约测试。"""

from pathlib import Path

from fastapi.testclient import TestClient

from app.config import WebServerSettings
from app.main import create_app


def test_health_reports_ready_database(client) -> None:
    """健康检查应明确返回服务版本和数据库就绪状态。"""
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"version": "0.1.0", "database": "ready"}


def test_validation_error_uses_public_error_shape(client) -> None:
    """框架参数校验错误也必须使用统一 JSON 外壳。"""
    response = client.get("/api/agents?limit=0")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert isinstance(response.json()["error"]["message"], str)
    assert response.json()["error"]["details"] is not None


def test_frontend_dist_serves_assets_and_spa_routes(tmp_path: Path) -> None:
    """生产模式同源提供静态文件，并为前端路由回退 index。"""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    frontend_dist = tmp_path / "dist"
    assets = frontend_dist / "assets"
    assets.mkdir(parents=True)
    (frontend_dist / "index.html").write_text("<main>Harness</main>", encoding="utf-8")
    (assets / "app.js").write_text("console.log('ok')", encoding="utf-8")
    app = create_app(
        WebServerSettings(workspace=workspace, frontend_dist=frontend_dist)
    )

    with TestClient(app) as static_client:
        route = static_client.get("/agents")
        asset = static_client.get("/assets/app.js")
        missing_api = static_client.get("/api/not-found")

    assert route.status_code == 200
    assert "Harness" in route.text
    assert asset.status_code == 200
    assert "console.log" in asset.text
    assert missing_api.status_code == 404
    assert "Harness" not in missing_api.text
