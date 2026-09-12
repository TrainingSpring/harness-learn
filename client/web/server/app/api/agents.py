"""Agent 目录查询路由。"""

from fastapi import APIRouter, Depends, Query

from runtime.agent_directory import AgentDirectory
from storage.types import AgentProfile

from ..dependencies import get_agent_directory
from ..errors import ApiError
from ..schemas.agent import AgentDetail, AgentSummary
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
    return AgentDetail(
        **_summary(profile).model_dump(),
        llm_profile_id=profile.llm_profile_id,
        permission_mode=profile.permission_mode,
    )
