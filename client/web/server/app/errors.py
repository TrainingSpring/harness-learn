"""内部异常到稳定 HTTP 错误契约的转换。"""

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class ApiError(Exception):
    """可安全暴露给浏览器的结构化 API 异常。

    Attributes:
        status_code: HTTP 状态码。
        code: 前端可稳定判断的机器错误码。
        message: 面向用户的简短中文说明。
        details: 可选的非敏感字段级上下文。
    """

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: Any = None,
    ) -> None:
        """创建公开 API 错误。"""
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details


def error_response(
    status_code: int,
    code: str,
    message: str,
    details: Any = None,
) -> JSONResponse:
    """生成所有路由共用的错误 JSON 外壳。"""
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "details": details,
            }
        },
    )


def install_error_handlers(app: FastAPI) -> None:
    """注册框架校验和显式业务错误处理器。"""

    @app.exception_handler(ApiError)
    async def handle_api_error(_request: Request, error: ApiError) -> JSONResponse:
        """将显式业务异常转换为稳定公开格式。"""
        return error_response(
            error.status_code,
            error.code,
            error.message,
            error.details,
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        _request: Request,
        error: RequestValidationError,
    ) -> JSONResponse:
        """避免 FastAPI 默认 ``detail`` 格式泄露到前端契约。"""
        details = [
            {
                "location": list(item["loc"]),
                "message": item["msg"],
                "type": item["type"],
            }
            for item in error.errors()
        ]
        return error_response(422, "VALIDATION_ERROR", "请求参数无效", details)

