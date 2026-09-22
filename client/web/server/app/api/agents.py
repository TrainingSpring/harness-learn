"""Agent 目录查询和创建路由。"""

from fastapi import APIRouter, Depends, Query, status

from storage.errors import StorageConflictError
from storage.ids import generate_id
from storage.types import AgentProfile

from ..dependencies import ApplicationServices, get_services
from ..errors import ApiError
from ..schemas.agent import (
    AgentDetail,
    AgentProfileSuggestion,
    AgentProfileSuggestionRequest,
    AgentSummary,
    CreateAgentRequest,
)
from ..schemas.common import ListResponse, Pagination
from ..services.agent_profile_assistant import LLMProfileNotFoundError


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
    )


@router.post("/profile-suggestion", response_model=AgentProfileSuggestion)
async def generate_agent_profile_suggestion(
    request: AgentProfileSuggestionRequest,
    services: ApplicationServices = Depends(get_services),
) -> AgentProfileSuggestion:
    """使用用户选择的 LLM 根据描述生成角色表单草案。"""
    try:
        suggestion = services.agent_profile_assistant.suggest(
            request.description,
            request.llm_profile_id,
        )
    except LLMProfileNotFoundError as error:
        raise ApiError(404, "LLM_PROFILE_NOT_FOUND", "LLM 配置不存在") from error
    except Exception as error:
        # 凭据解析、网络错误和模型输出错误都不能把底层细节暴露给浏览器。
        raise ApiError(502, "AGENT_SUGGESTION_FAILED", "角色信息生成失败") from error
    return AgentProfileSuggestion.model_validate(suggestion)


@router.get("", response_model=ListResponse[AgentSummary])
async def list_agents(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    expertise: str | None = Query(default=None, min_length=1),
    services: ApplicationServices = Depends(get_services),
) -> ListResponse[AgentSummary]:
    """分页列出可用于创建新会话的启用 Agent。"""
    profiles = services.agent_profiles.list_enabled(limit + 1, offset, expertise)
    has_more = len(profiles) > limit
    return ListResponse(
        items=[_summary(profile) for profile in profiles[:limit]],
        pagination=Pagination(limit=limit, offset=offset, has_more=has_more),
    )


@router.get("/{agent_id}", response_model=AgentDetail)
async def get_agent(
    agent_id: str,
    services: ApplicationServices = Depends(get_services),
) -> AgentDetail:
    """读取一个 Agent 的公开详情，包括禁用状态。"""
    try:
        profile = services.agent_profiles.get(agent_id)
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
        request: 浏览器提交的角色描述、LLM 引用和工具集合。
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
        is_enabled=request.is_enabled,
    )
    try:
        saved = services.agent_profiles.save(profile)
    except StorageConflictError as error:
        raise ApiError(409, "AGENT_PROFILE_CONFLICT", "角色配置保存冲突") from error
    return _detail(saved)
