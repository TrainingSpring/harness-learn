"""从 OpenAI 兼容服务商读取可选模型。"""

from typing import Any

import httpx


class ModelDiscoveryError(Exception):
    """模型发现失败时可安全展示给浏览器的错误。"""


async def discover_models(
    provider: str,
    base_url: str | None,
    api_key: str,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> list[str]:
    """读取 OpenAI 兼容 ``/models`` 响应中的模型 ID。

    任何服务商错误都收敛为同一公开异常，避免把连接地址、响应内容或 API Key
    传回浏览器。
    """
    if provider != "openai" or not base_url or not api_key:
        raise ModelDiscoveryError("无法获取模型列表，请检查连接配置后重试")

    endpoint = f"{base_url.rstrip('/')}/models"
    try:
        async with httpx.AsyncClient(timeout=10.0, transport=transport) as client:
            response = await client.get(endpoint, headers={"Authorization": f"Bearer {api_key}"})
            response.raise_for_status()
            payload: Any = response.json()
    except (httpx.HTTPError, ValueError) as error:
        raise ModelDiscoveryError("无法获取模型列表，请检查连接配置后重试") from error

    data = payload.get("data", []) if isinstance(payload, dict) else []
    return sorted({item["id"] for item in data if isinstance(item, dict) and isinstance(item.get("id"), str)})
