"""OpenAI 兼容模型发现服务的边界测试。"""

import asyncio

import httpx

from app.services.llm_model_discovery import ModelDiscoveryError, discover_models


def test_discover_models_extracts_sorted_unique_ids() -> None:
    """只读取模型 ID，并对服务商返回顺序去重排序。"""
    observed_request: httpx.Request | None = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal observed_request
        observed_request = request
        return httpx.Response(
            200,
            json={"data": [{"id": "gpt-5-mini"}, {"id": "gpt-5"}, {"id": "gpt-5"}, {"id": 42}]},
        )

    models = asyncio.run(
        discover_models(
            "openai",
            "https://api.example.com/v1/",
            "sk-test-key",
            transport=httpx.MockTransport(handler),
        )
    )

    assert models == ["gpt-5", "gpt-5-mini"]
    assert observed_request is not None
    assert str(observed_request.url) == "https://api.example.com/v1/models"
    assert observed_request.headers["authorization"] == "Bearer sk-test-key"


def test_discover_models_hides_upstream_details() -> None:
    """上游异常只转换成公开的稳定错误。"""
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="invalid key sk-test-key at https://private.example")

    try:
        asyncio.run(
            discover_models(
                "openai",
                "https://api.example.com/v1",
                "sk-test-key",
                transport=httpx.MockTransport(handler),
            )
        )
    except ModelDiscoveryError as error:
        assert str(error) == "无法获取模型列表，请检查连接配置后重试"
    else:
        raise AssertionError("模型发现应在上游失败时抛出公开错误")
