"""固定角色 1v1 会话和上下文查询路由。"""

from fastapi import APIRouter, Depends, Query, status

from runtime.session_service import SessionService
from storage.types import ContextItem, DirectSessionSummary

from ..dependencies import ApplicationServices, get_services, get_session_service
from ..errors import ApiError
from ..schemas.common import ListResponse, Pagination
from ..schemas.context import ContextItemResponse
from ..schemas.session import (
    ContextItemList,
    CreateDirectSessionRequest,
    SessionAgentSummary,
    SessionDetail,
    SessionSummary,
)


router = APIRouter(prefix="/sessions", tags=["sessions"])


def _context_item(item: ContextItem) -> ContextItemResponse:
    """从持久化领域对象提取浏览器可消费的业务事件字段。"""
    return ContextItemResponse(
        id=item.id,
        sequence_no=item.sequence_no,
        kind=item.kind,
        author_agent_id=item.author_agent_id,
        visibility=item.visibility,
        payload=item.payload,
        call_id=item.call_id,
        caused_by_item_id=item.caused_by_item_id,
        created_at=item.created_at,
    )


def _summary(item: DirectSessionSummary) -> SessionSummary:
    """把 DIRECT 聚合查询结果转换为会话摘要 DTO。"""
    session = item.session
    return SessionSummary(
        id=session.id,
        title=session.title,
        conversation_mode=session.conversation_mode,
        status=session.status,
        agent=SessionAgentSummary(id=item.agent_id, name=item.agent_name),
        last_message=item.last_message,
        last_sequence_no=item.last_sequence_no,
        created_at=session.created_at,
        updated_at=session.updated_at,
    )


def _find_direct(
    services: ApplicationServices,
    session_id: str,
) -> DirectSessionSummary:
    """读取合法 DIRECT 会话，不存在或结构异常时统一返回 404。"""
    try:
        item = services.session_queries.get_direct_detail(session_id)
    except ValueError as error:
        raise ApiError(404, "SESSION_NOT_FOUND", "Session 不存在") from error
    if item is None:
        raise ApiError(404, "SESSION_NOT_FOUND", "Session 不存在")
    return item


@router.post("", response_model=SessionSummary, status_code=status.HTTP_201_CREATED)
async def create_session(
    request: CreateDirectSessionRequest,
    session_service: SessionService = Depends(get_session_service),
    services: ApplicationServices = Depends(get_services),
) -> SessionSummary:
    """创建绑定一个启用 Agent 的固定 DIRECT 会话。"""
    try:
        session = session_service.create_direct_session(request.agent_id, request.title)
    except ValueError as error:
        raise ApiError(
            422,
            "AGENT_NOT_SELECTABLE",
            "所选 Agent 不存在或已禁用",
        ) from error
    detail = services.session_queries.get_direct_detail(session.id)
    if detail is None:
        # 创建服务保证固定成员约束；查不到表示内部持久化状态不一致。
        raise ApiError(500, "SESSION_CREATE_FAILED", "会话创建失败")
    return _summary(detail)


@router.get("", response_model=ListResponse[SessionSummary])
async def list_sessions(
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    services: ApplicationServices = Depends(get_services),
) -> ListResponse[SessionSummary]:
    """分页列出可由首期 Web 客户端恢复的 DIRECT 会话。"""
    items = services.session_queries.list_direct_summaries(limit + 1, offset)
    has_more = len(items) > limit
    return ListResponse(
        items=[_summary(item) for item in items[:limit]],
        pagination=Pagination(limit=limit, offset=offset, has_more=has_more),
    )


@router.get("/{session_id}", response_model=SessionDetail)
async def get_session(
    session_id: str,
    services: ApplicationServices = Depends(get_services),
) -> SessionDetail:
    """返回 DIRECT 会话摘要和完整业务时间线。"""
    summary = _find_direct(services, session_id)
    messages = services.context_items.list_after(session_id, 0)
    return SessionDetail(
        **_summary(summary).model_dump(),
        messages=[_context_item(item) for item in messages],
    )


@router.get("/{session_id}/messages", response_model=ContextItemList)
async def list_messages(
    session_id: str,
    after_sequence: int = Query(default=0, alias="afterSequence", ge=0),
    services: ApplicationServices = Depends(get_services),
) -> ContextItemList:
    """按会话序号增量返回消息与工具执行事件。"""
    _find_direct(services, session_id)
    items = services.context_items.list_after(session_id, after_sequence)
    return ContextItemList(items=[_context_item(item) for item in items])

