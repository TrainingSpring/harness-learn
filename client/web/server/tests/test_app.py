"""Web 应用生命周期和公共错误契约测试。"""


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

