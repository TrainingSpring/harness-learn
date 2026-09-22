"""固定角色 1v1 会话、项目选择和上下文查询路由。"""

from pathlib import Path

from fastapi import APIRouter, Depends, Query, status

from session.session_service import SessionService
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
    ProjectDirectory,
    ProjectDirectoryResponse,
    UpdatePermissionModeRequest,
    UpdateProjectRequest,
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


def _summary(
    item: DirectSessionSummary,
    *,
    workspace: Path,
    is_project_locked: bool,
) -> SessionSummary:
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
        permission_mode=session.permission_mode,
        project_path=_display_project_path(workspace, session.project_path),
        is_project_locked=is_project_locked,
    )


def _display_project_path(workspace: Path, project_path: str | None) -> str | None:
    """把数据库中的绝对项目路径转换为客户端可见的 workspace-relative 路径。"""
    if project_path is None:
        return None
    path = Path(project_path)
    # Session 项目路径由 _resolve_project_path 写入，已保证在 workspace 内；
    # 这里仅为旧数据提供稳定展示，不把服务器绝对路径泄露给浏览器。
    try:
        relative = path.relative_to(workspace.resolve())
    except ValueError:
        return path.name
    return "." if str(relative) == "." else relative.as_posix()


def _resolve_project_path(workspace: Path, value: str | None) -> str | None:
    """将相对 workspace 的目录安全解析成数据库使用的绝对路径。"""
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError("项目目录不能为空或必须为 None")
    candidate = Path(value)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError("项目目录必须是 workspace 内的相对路径")
    resolved = (workspace / candidate).resolve()
    try:
        resolved.relative_to(workspace.resolve())
    except ValueError as error:
        raise ValueError("项目目录必须位于 workspace 内") from error
    if not resolved.is_dir():
        raise ValueError("项目目录不存在或不是目录")
    return str(resolved)


def _is_project_locked(services: ApplicationServices, session_id: str) -> bool:
    """首条用户消息写入时间线后锁定项目选择。"""
    return any(
        item.kind == "USER_MESSAGE"
        for item in services.context_items.list_after(session_id, 0)
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
    project_path: str | None = None
    if request.project_path is not None:
        try:
            project_path = _resolve_project_path(
                services.database.workspace,
                request.project_path,
            )
        except ValueError as error:
            raise ApiError(422, "INVALID_PROJECT_PATH", "项目目录无效") from error
    try:
        execution = session_service.create_direct_session(
            request.agent_id,
            request.title,
            request.permission_mode,
        )
        if project_path is not None:
            try:
                session_service.sessions.update_project_path_before_first_message(
                    execution.session.id,
                    project_path,
                )
            except ValueError as error:
                raise ApiError(422, "INVALID_PROJECT_PATH", "项目目录无效") from error
    except ValueError as error:
        raise ApiError(
            422,
            "AGENT_NOT_SELECTABLE",
            "所选 Agent 不存在或已禁用",
        ) from error
    detail = services.session_queries.get_direct_detail(execution.session.id)
    if detail is None:
        # 创建服务保证固定成员约束；查不到表示内部持久化状态不一致。
        raise ApiError(500, "SESSION_CREATE_FAILED", "会话创建失败")
    return _summary(
        detail,
        workspace=services.database.workspace,
        is_project_locked=_is_project_locked(services, detail.session.id),
    )


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
        items=[
            _summary(
                item,
                workspace=services.database.workspace,
                is_project_locked=_is_project_locked(services, item.session.id),
            )
            for item in items[:limit]
        ],
        pagination=Pagination(limit=limit, offset=offset, has_more=has_more),
    )


@router.get("/projects", response_model=ProjectDirectoryResponse)
async def list_project_directories(
    path: str = Query(default=".", max_length=2000),
    services: ApplicationServices = Depends(get_services),
) -> ProjectDirectoryResponse:
    """列出 workspace 当前目录及其直接子目录。"""
    try:
        resolved = _resolve_project_path(services.database.workspace, path)
    except ValueError as error:
        raise ApiError(422, "INVALID_PROJECT_PATH", "项目目录无效") from error
    directory = Path(resolved or services.database.workspace)
    children: list[ProjectDirectory] = []
    for child in sorted(directory.iterdir(), key=lambda item: item.name.lower()):
        if child.name.startswith(".") or not child.is_dir():
            continue
        try:
            relative_path = _relative_path(services.database.workspace, child)
        except ValueError:
            # 目录软链接若逃出 workspace，不能作为项目根暴露给浏览器。
            continue
        children.append(ProjectDirectory(path=relative_path, name=child.name))
    return ProjectDirectoryResponse(
        path=_relative_path(services.database.workspace, directory),
        name=directory.name,
        directories=children,
    )


def _relative_path(workspace: Path, path: Path) -> str:
    """返回前端统一使用的 POSIX workspace-relative 路径。"""
    relative = path.resolve().relative_to(workspace.resolve())
    return "." if str(relative) == "." else relative.as_posix()


@router.get("/{session_id}", response_model=SessionDetail)
async def get_session(
    session_id: str,
    services: ApplicationServices = Depends(get_services),
) -> SessionDetail:
    """返回 DIRECT 会话摘要和完整业务时间线。"""
    summary = _find_direct(services, session_id)
    messages = services.context_items.list_after(session_id, 0)
    return SessionDetail(
        **_summary(
            summary,
            workspace=services.database.workspace,
            is_project_locked=_is_project_locked(services, session_id),
        ).model_dump(),
        messages=[_context_item(item) for item in messages],
    )


@router.patch("/{session_id}/permission-mode", response_model=SessionSummary)
async def update_permission_mode(
    session_id: str,
    request: UpdatePermissionModeRequest,
    services: ApplicationServices = Depends(get_services),
) -> SessionSummary:
    """更新空闲 Session 的权限模式。"""
    detail = _find_direct(services, session_id)
    if services.run_registry.get_for_session(session_id) is not None:
        raise ApiError(409, "RUN_ALREADY_ACTIVE", "当前会话已有运行中的请求")
    try:
        services.session_service.sessions.update_permission_mode(
            session_id,
            request.permission_mode,
        )
    except ValueError as error:
        raise ApiError(422, "INVALID_PERMISSION_MODE", "权限模式无效") from error
    refreshed = services.session_queries.get_direct_detail(session_id)
    if refreshed is None:
        raise ApiError(404, "SESSION_NOT_FOUND", "Session 不存在")
    return _summary(
        refreshed,
        workspace=services.database.workspace,
        is_project_locked=_is_project_locked(services, session_id),
    )


@router.patch("/{session_id}/project", response_model=SessionSummary)
async def update_project(
    session_id: str,
    request: UpdateProjectRequest,
    services: ApplicationServices = Depends(get_services),
) -> SessionSummary:
    """在首条用户消息前设置 Session 的 workspace 项目目录。"""
    detail = _find_direct(services, session_id)
    if services.run_registry.get_for_session(session_id) is not None:
        raise ApiError(409, "RUN_ALREADY_ACTIVE", "当前会话已有运行中的请求")
    if _is_project_locked(services, session_id):
        raise ApiError(409, "PROJECT_LOCKED", "首条消息发送后不能更改项目目录")
    try:
        absolute_path = _resolve_project_path(services.database.workspace, request.project_path)
        services.session_service.sessions.update_project_path_before_first_message(
            session_id,
            absolute_path,
        )
    except ValueError as error:
        raise ApiError(422, "INVALID_PROJECT_PATH", "项目目录无效") from error
    refreshed = services.session_queries.get_direct_detail(session_id)
    if refreshed is None:
        raise ApiError(404, "SESSION_NOT_FOUND", "Session 不存在")
    return _summary(
        refreshed,
        workspace=services.database.workspace,
        is_project_locked=_is_project_locked(services, session_id),
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
