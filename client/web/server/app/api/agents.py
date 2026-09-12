"""Agent 目录查询和创建路由。"""

from fastapi import APIRouter, Depends, Query, status

from runtime.agent_directory import AgentDirectory
from storage.errors import StorageConflictError
from storage.ids import generate_id
from storage.types import AgentProfile

from ..dependencies import ApplicationServices, get_agent_directory, get_services
from ..errors import ApiError
from ..schemas.agent import AgentDetail, AgentSummary, CreateAgentRequest
from ..schemas.common import ListResponse, Pagination


router = APIRouter(prefix="/agents", tags=["agents"])


def _summary(profile: AgentProfile) -> AgentSummary:
    """从内部 AgentProfile 提取列表允许公开的字段。"""
    return AgentSummary(
        id=profile.id,
        name=profile.name,
        description=profile.description,
        personality=profile.personality,
        expertise=profile.expertise,
        tools=profile.tools,
        is_enabled=profile.is_enabled,
    )


def _detail(profile: AgentProfile) -> AgentDetail:
    """将内部角色配置转换为不含敏感信息的详情 DTO。"""
    return AgentDetail(
        **_summary(profile).model_dump(),
        llm_profile_id=profile.llm_profile_id,
        permission_mode=profile.permission_mode,
    )


@router.get("", response_model=ListResponse[AgentSummary])
async def list_agents(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    expertise: str | None = Query(default=None, min_length=1),
    directory: AgentDirectory = Depends(get_agent_directory),
) -> ListResponse[AgentSummary]:
    """分页列出可用于创建新会话的启用 Agent。"""
    profiles = directory.list(limit + 1, offset, expertise)
    has_more = len(profiles) > limit
    return ListResponse(
        items=[_summary(profile) for profile in profiles[:limit]],
        pagination=Pagination(limit=limit, offset=offset, has_more=has_more),
    )


@router.get("/{agent_id}", response_model=AgentDetail)
async def get_agent(
    agent_id: str,
    directory: AgentDirectory = Depends(get_agent_directory),
) -> AgentDetail:
    """读取一个 Agent 的公开详情，包括禁用状态。"""
    try:
        profile = directory.get(agent_id)
    except ValueError as error:
        raise ApiError(404, "AGENT_NOT_FOUND", "Agent 不存在") from error
    if profile is None:
        raise ApiError(404, "AGENT_NOT_FOUND", "Agent 不存在")
    return _detail(profile)


@router.post("", response_model=AgentDetail, status_code=status.HTTP_201_CREATED)
async def create_agent(
    request: CreateAgentRequest,
    services: ApplicationServices = Depends(get_services),
) -> AgentDetail:
    """创建并持久化一个角色配置。

    Args:
        request: 浏览器提交的角色描述、LLM 引用、工具和权限模式。
        services: 当前 workspace 共享的仓储与工具目录。

    Returns:
        新建角色的详情；ID 由服务端生成。
    """
    try:
        llm_profile = services.llm_profiles.get(request.llm_profile_id)
    except ValueError as error:
        raise ApiError(404, "LLM_PROFILE_NOT_FOUND", "LLM 配置不存在") from error
    if llm_profile is None:
        raise ApiError(404, "LLM_PROFILE_NOT_FOUND", "LLM 配置不存在")

    try:
        services.tool_catalog.validate_names(request.tools)
    except ValueError as error:
        raise ApiError(422, "INVALID_TOOL", str(error)) from error

    profile = AgentProfile(
        id=generate_id("agent"),
        name=request.name,
        description=request.description,
        personality=request.personality,
        expertise=request.expertise,
        llm_profile_id=request.llm_profile_id,
        tools=request.tools,
        permission_mode=request.permission_mode,
        is_enabled=request.is_enabled,
    )
    try:
        saved = services.agent_profiles.save(profile)
    except StorageConflictError as error:
        raise ApiError(409, "AGENT_PROFILE_CONFLICT", "角色配置保存冲突") from error
    return _detail(saved)
