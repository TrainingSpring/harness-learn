"""前端生产构建的同源静态资源托管。"""

from pathlib import Path

from starlette.exceptions import HTTPException
from starlette.responses import Response
from starlette.staticfiles import StaticFiles


class SpaStaticFiles(StaticFiles):
    """提供真实静态文件，并把前端路由回退到 ``index.html``。

    ``/api`` 即使没有匹配路由也必须保持 HTTP 404，不能返回 HTML 200；否则
    API 客户端会把拼错的地址误判为成功响应。
    """

    def __init__(self, directory: Path) -> None:
        """创建已验证包含 index.html 的 SPA 静态服务。"""
        if not directory.is_dir() or not (directory / "index.html").is_file():
            raise ValueError("frontend_dist 必须包含 index.html")
        super().__init__(directory=str(directory), html=True)

    async def get_response(self, path: str, scope) -> Response:
        """优先返回静态文件，非 API 的缺失路径返回 SPA 入口。"""
        try:
            response = await super().get_response(path, scope)
            if response.status_code != 404:
                return response
        except HTTPException as error:
            if error.status_code != 404:
                raise
        if path == "api" or path.startswith("api/"):
            raise HTTPException(status_code=404)
        return await super().get_response("index.html", scope)

