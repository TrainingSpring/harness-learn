"""流式消息、权限恢复和运行取消路由。"""

import asyncio
import json

from fastapi import APIRouter, Depends, Response, status
from fastapi.responses import StreamingResponse

from ..dependencies import ApplicationServices, get_services
from ..errors import ApiError
from ..schemas.run import PermissionDecisionRequest, SendMessageRequest, ServerEvent
from ..services.chat_service import (
    PermissionMismatchError,
    RunNotFoundError,
    SessionNotRunnableError,
)
from ..services.run_registry import RunAlreadyActiveError


router = APIRouter(tags=["runs"])


def _sse(event: ServerEvent) -> str:
    """把一个 ServerEvent 编码成标准 SSE data 帧。"""
    payload = event.model_dump(mode="json", by_alias=True)
    return f"data: {json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}\n\n"


async def _event_stream(events):
    """逐事件让出控制权，使取消请求能在模型 token 间得到处理。"""
    for event in events:
        yield _sse(event)
        await asyncio.sleep(0)


def _stream_response(events) -> StreamingResponse:
    """创建禁止缓存和代理缓冲的 SSE 响应。"""
    return StreamingResponse(
        _event_stream(events),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/sessions/{session_id}/messages")
async def send_message(
    session_id: str,
    request: SendMessageRequest,
    services: ApplicationServices = Depends(get_services),
) -> StreamingResponse:
    """启动一次用户消息并返回 POST SSE 流。"""
    try:
        events = services.chat_service.start_message(session_id, request.text)
    except SessionNotRunnableError as error:
        raise ApiError(404, "SESSION_NOT_FOUND", "Session 不存在或不可运行") from error
    except RunAlreadyActiveError as error:
        raise ApiError(409, "RUN_ALREADY_ACTIVE", "当前会话已有运行中的请求") from error
    except Exception as error:
        # Agent 加载可能因配置或凭据失败，不能把底层异常文本公开给浏览器。
        raise ApiError(422, "AGENT_LOAD_FAILED", "Agent 配置无法加载") from error
    return _stream_response(events)


@router.post("/runs/{run_id}/permission")
async def resolve_permission(
    run_id: str,
    request: PermissionDecisionRequest,
    services: ApplicationServices = Depends(get_services),
) -> StreamingResponse:
    """确认或拒绝权限，并从原始 Runtime 继续返回事件。"""
    try:
        events = services.chat_service.resolve_permission(run_id, request)
    except RunNotFoundError as error:
        raise ApiError(404, "RUN_NOT_FOUND", "Run 不存在") from error
    except PermissionMismatchError as error:
        raise ApiError(409, "PERMISSION_MISMATCH", "权限确认与待处理调用不匹配") from error
    return _stream_response(events)


@router.post("/runs/{run_id}/cancel", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_run(
    run_id: str,
    services: ApplicationServices = Depends(get_services),
) -> Response:
    """取消活动运行并释放该 Session 的发送占用。"""
    try:
        services.chat_service.cancel(run_id)
    except RunNotFoundError as error:
        raise ApiError(404, "RUN_NOT_FOUND", "Run 不存在") from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)

